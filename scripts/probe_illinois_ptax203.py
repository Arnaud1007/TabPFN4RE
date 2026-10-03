"""Bounded private PTAX-203 linkage audit; never certifies sale labels.

Run ``capture`` once against the frozen Cook sample, then use ``verify`` for
offline replay. Only the verifier's aggregate summary may leave private storage.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from scripts import private_review_io as private_io
from scripts import review_cook_sales_sample as cook


DATASET_ID = "it54-y4c6"
HOST = "illinois-edp.data.socrata.com"
METADATA_URL = f"https://{HOST}/api/views/{DATASET_ID}.json"
API_URL = f"https://{HOST}/resource/{DATASET_ID}.json"
PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "illinois_ptax203"
PROTOCOL = "illinois-ptax203-link-v1"
ROW_FIELDS = (
    "declaration_id",
    "status",
    "document_number",
    "date_recorded",
    "line_1_county",
    "line_1_primary_pin",
    "line_1_unit",
    "line_2_total_parcels",
    "line_3_additional_pins",
    "line_4_instrument_date",
    "line_5_instrument_type",
    "line_8_current_use",
    "line_10b_sale_between_related",
    "line_11_full_consideration",
    "line_12a_total_personal",
    "line_13_net_consideration",
)
MAX_METADATA = 512 * 1024
MAX_COUNT = 8 * 1024
MAX_ROWS = 64 * 1024
MAX_REQUESTS = 22
TIMEOUT = 15


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json(data: bytes) -> object:
    try:
        return json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Source JSON is malformed") from error


def select_documents(
    rows: object, *, expected_rows: int = 100
) -> dict[str, tuple[str, ...]]:
    """Choose exact recent Cook document strings and retain private row links."""
    if (
        not isinstance(rows, list)
        or type(expected_rows) is not int
        or not 1 <= expected_rows <= 100
    ):
        raise ValueError("Invalid frozen selection input")
    selected: dict[str, list[str]] = {}
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Frozen Cook row is malformed")
        year = row.get("year")
        if year not in ("2024", "2025", 2024, 2025):
            continue
        doc = row.get("doc_no")
        if not isinstance(doc, str) or not doc:
            continue
        if len(doc) > 128 or any(ord(character) < 32 for character in doc):
            raise ValueError("Frozen Cook document is unsafe for exact query")
        identifier = row.get("row_id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Frozen Cook row identity is missing")
        selected.setdefault(doc, []).append(identifier)
        count += 1
    if count != expected_rows:
        raise ValueError("Frozen Cook recent-document membership differs")
    return {doc: tuple(selected[doc]) for doc in sorted(selected)}


def _batches(documents: dict[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    keys = tuple(documents)
    if not keys or len(keys) > 100 or keys != tuple(sorted(set(keys))):
        raise ValueError("Document selection is not frozen and bounded")
    return tuple(keys[index : index + 10] for index in range(0, len(keys), 10))


def query_url(documents: list[str] | tuple[str, ...], *, count: bool) -> str:
    if (
        not isinstance(documents, (list, tuple))
        or not 1 <= len(documents) <= 10
        or any(
            not isinstance(doc, str)
            or not doc
            or len(doc) > 128
            or any(ord(char) < 32 for char in doc)
            for doc in documents
        )
    ):
        raise ValueError("Invalid exact-document query batch")
    if len(set(documents)) != len(documents):
        raise ValueError("Duplicate exact-document query value")
    quoted = ",".join("'" + doc.replace("'", "''") + "'" for doc in documents)
    params = {
        "$select": "count(*) as matched_count" if count else ",".join(ROW_FIELDS),
        "$where": f"document_number IN ({quoted})",
    }
    if not count:
        params.update({"$order": "declaration_id", "$limit": "100"})
    return API_URL + "?" + urlencode(params)


def metadata_identity(data: bytes) -> dict:
    record = _json(data)
    if not isinstance(record, dict) or record.get("id") != DATASET_ID:
        raise ValueError("Wrong PTAX dataset metadata")
    if (
        record.get("publicationStage"),
        record.get("provenance"),
        record.get("licenseId"),
    ) != ("published", "official", "PUBLIC_DOMAIN"):
        raise ValueError("PTAX publisher or licence status differs")
    columns = record.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("PTAX schema is missing")
    indexed = {}
    for col in columns:
        if (
            not isinstance(col, dict)
            or not isinstance(col.get("fieldName"), str)
            or type(col.get("id")) is not int
        ):
            raise ValueError("PTAX column metadata is invalid")
        indexed[col["fieldName"]] = col["id"]
    if not set(ROW_FIELDS) <= set(indexed) or len(indexed) != len(columns):
        raise ValueError("PTAX schema is incompatible")
    if record.get("rowIdentifierColumnId") != indexed["declaration_id"]:
        raise ValueError("PTAX row identifier changed")
    versions = (record.get("rowsUpdatedAt"), record.get("viewLastModified"))
    if any(type(value) is not int or value <= 0 for value in versions):
        raise ValueError("PTAX source version unavailable")
    return {
        "rows_updated_at": versions[0],
        "view_last_modified": versions[1],
        "fields": sorted(indexed),
        "license_id": record["licenseId"],
    }


def check_metadata_pair(before: bytes, after: bytes) -> dict:
    left, right = metadata_identity(before), metadata_identity(after)
    if left != right:
        raise ValueError("PTAX source changed during capture")
    return left


def parse_count(data: bytes) -> int:
    values = _json(data)
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], dict)
    ):
        raise ValueError("PTAX count response is malformed")
    text = values[0].get("matched_count")
    if not isinstance(text, str) or not text.isdecimal():
        raise ValueError("PTAX count response is malformed")
    count = int(text)
    if count > 100:
        raise ValueError("PTAX count exceeds frozen per-batch cap")
    return count


def parse_rows(
    data: bytes, documents: tuple[str, ...], *, expected_count: int
) -> list[dict]:
    values = _json(data)
    if not isinstance(values, list) or len(values) != expected_count:
        raise ValueError("PTAX row and count responses disagree")
    seen = set()
    for row in values:
        if not isinstance(row, dict) or not set(row) <= set(ROW_FIELDS):
            raise ValueError("PTAX response includes unrequested fields")
        if any(
            value is not None
            and (
                not isinstance(value, (str, int, float, bool))
                or (isinstance(value, str) and len(value) > 256)
            )
            for value in row.values()
        ):
            raise ValueError("PTAX response has an unsafe field value")
        identifier, document = row.get("declaration_id"), row.get("document_number")
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier in seen
            or not isinstance(document, str)
            or document not in documents
        ):
            raise ValueError("PTAX row identity or exact document differs")
        seen.add(identifier)
    return values


class CaptureFailure(ValueError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body_hash: str | None = None,
        truncated: bool = False,
    ):
        super().__init__(message)
        self.status = status
        self.body_hash = body_hash
        self.truncated = truncated


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, _req, _fp, code, _msg, _headers, _newurl):
        raise CaptureFailure("PTAX redirect rejected", status=code)


_OPENER = build_opener(_NoRedirect)


def _private_root() -> Path:
    absolute = PRIVATE_ROOT.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink() or (
            candidate.exists()
            and not private_io.same_path(candidate, candidate.resolve())
        ):
            raise ValueError("PTAX private root redirects")
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_io.secure_directory(PRIVATE_ROOT)
    private_io.real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    private_io.verify_acl(PRIVATE_ROOT)
    return PRIVATE_ROOT


def _new_run() -> Path:
    root = _private_root()
    directory = root / f"ptax-link-v1-{cook.CAPTURE_SHA256[:16]}"
    directory.mkdir(mode=0o700, exist_ok=False)
    private_io.secure_directory(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    return directory


def _file(directory: Path, name: str) -> Path:
    return private_io.private_path(directory / name, directory)


def _write(directory: Path, name: str, data: bytes) -> None:
    private_io.new_file(_file(directory, name), data)


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _read_bounded(path: Path, cap: int) -> bytes:
    if path.stat().st_size > cap:
        raise ValueError("PTAX private artifact exceeds cap")
    with path.open("rb") as stream:
        content = stream.read(cap + 1)
    if len(content) > cap:
        raise ValueError("PTAX private artifact exceeds cap")
    return content


def _fetch(url: str, cap: int) -> tuple[bytes, int, float, str]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.path
        not in (f"/api/views/{DATASET_ID}.json", f"/resource/{DATASET_ID}.json")
    ):
        raise ValueError("PTAX source URL is not approved")
    start = monotonic()
    try:
        with _OPENER.open(url, timeout=TIMEOUT) as response:
            status = response.status
            if response.geturl() != url or status != 200:
                raise ValueError("PTAX redirect or HTTP status rejected")
            body = response.read(cap + 1)
            if (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
                != "application/json"
            ):
                raise CaptureFailure(
                    "PTAX content type rejected",
                    status=status,
                    body_hash=_hash(body),
                    truncated=len(body) > cap,
                )
    except HTTPError as error:
        body = error.read(cap + 1)
        raise CaptureFailure(
            "PTAX HTTP request failed",
            status=error.code,
            body_hash=_hash(body),
            truncated=len(body) > cap,
        ) from None
    if len(body) > cap:
        raise CaptureFailure(
            "PTAX response cap exceeded",
            status=status,
            body_hash=_hash(body),
            truncated=True,
        )
    return (
        body,
        status,
        monotonic() - start,
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _request(directory: Path, index: int, url: str, cap: int, validator) -> bytes:
    if index >= MAX_REQUESTS:
        raise ValueError("PTAX request budget exceeded")
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    start = monotonic()
    event = {
        "index": index,
        "started_at_utc": started,
        "url_sha256": _hash(url.encode()),
        "status": None,
        "duration_seconds": None,
        "response_sha256": None,
        "body_saved": False,
        "truncated": False,
    }
    try:
        body, status, duration, completed = _fetch(url, cap)
        event.update(
            {
                "status": status,
                "duration_seconds": duration,
                "completed_at_utc": completed,
                "response_sha256": _hash(body),
            }
        )
        validator(body)
        _write(directory, f"response-{index:02d}.json", body)
        event["body_saved"] = True
    except CaptureFailure as error:
        event.update(
            {
                "status": error.status,
                "response_sha256": error.body_hash,
                "truncated": error.truncated,
                "error": str(error),
            }
        )
    except (OSError, ValueError) as error:
        event["error"] = type(error).__name__
    event["duration_seconds"] = event["duration_seconds"] or monotonic() - start
    _write(directory, f"event-{index:02d}.json", _encoded(event))
    if not event["body_saved"]:
        raise CaptureFailure("PTAX request failed; private run is incomplete")
    return body


def capture() -> Path:
    """Perform the one-shot, 22-GET maximum audit after claiming private state."""
    documents = select_documents(cook._capture_rows())
    batches = _batches(documents)
    directory = _new_run()
    plan = {
        "protocol": PROTOCOL,
        "cook_capture_sha256": cook.CAPTURE_SHA256,
        "documents": documents,
        "batch_size": 10,
        "selected_cook_rows": sum(map(len, documents.values())),
    }
    _write(directory, "selection.json", _encoded(plan))
    index = 0
    before = _request(directory, index, METADATA_URL, MAX_METADATA, metadata_identity)
    index += 1
    all_ids = set()
    for batch in batches:
        count = parse_count(
            _request(
                directory, index, query_url(batch, count=True), MAX_COUNT, parse_count
            )
        )
        index += 1
        rows = parse_rows(
            _request(
                directory,
                index,
                query_url(batch, count=False),
                MAX_ROWS,
                lambda data, b=batch, c=count: parse_rows(data, b, expected_count=c),
            ),
            batch,
            expected_count=count,
        )
        index += 1
        for row in rows:
            identifier = row["declaration_id"]
            if identifier in all_ids:
                raise ValueError("PTAX declaration repeats across query batches")
            all_ids.add(identifier)
    after = _request(directory, index, METADATA_URL, MAX_METADATA, metadata_identity)
    check_metadata_pair(before, after)
    _write(
        directory,
        "complete.json",
        _encoded(
            {
                "protocol": PROTOCOL,
                "request_count": index + 1,
                "returned_declarations": len(all_ids),
            }
        ),
    )
    return directory


def verify(directory: Path) -> dict:
    """Offline replay of a complete private capture; return aggregate-only facts."""
    root = _private_root()
    directory = Path(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    selection = _json(
        _read_bounded(
            private_io.private_path(
                directory / "selection.json", directory, must_exist=True
            ),
            64 * 1024,
        )
    )
    if (
        not isinstance(selection, dict)
        or selection.get("protocol") != PROTOCOL
        or selection.get("cook_capture_sha256") != cook.CAPTURE_SHA256
    ):
        raise ValueError("PTAX private selection identity differs")
    documents = select_documents(cook._capture_rows())
    if (
        selection.get("documents")
        != {key: list(value) for key, value in documents.items()}
        or selection.get("batch_size") != 10
        or selection.get("selected_cook_rows") != 100
    ):
        raise ValueError("PTAX private selection differs from pinned Cook sample")
    complete_bytes = _read_bounded(
        private_io.private_path(
            directory / "complete.json", directory, must_exist=True
        ),
        4096,
    )
    complete = _json(complete_bytes)
    batches = _batches(documents)
    expected_urls = [METADATA_URL]
    for batch in batches:
        expected_urls.extend(
            [query_url(batch, count=True), query_url(batch, count=False)]
        )
    expected_urls.append(METADATA_URL)
    if (
        not isinstance(complete, dict)
        or complete.get("protocol") != PROTOCOL
        or complete.get("request_count") != len(expected_urls)
        or len(expected_urls) > MAX_REQUESTS
    ):
        raise ValueError("PTAX completion manifest differs")
    responses = []
    for index, url in enumerate(expected_urls):
        event = _json(
            _read_bounded(
                private_io.private_path(
                    directory / f"event-{index:02d}.json", directory, must_exist=True
                ),
                4096,
            )
        )
        cap = (
            MAX_METADATA
            if index in (0, len(expected_urls) - 1)
            else (MAX_COUNT if index % 2 else MAX_ROWS)
        )
        body = _read_bounded(
            private_io.private_path(
                directory / f"response-{index:02d}.json", directory, must_exist=True
            ),
            cap,
        )
        if (
            not isinstance(event, dict)
            or event.get("index") != index
            or event.get("url_sha256") != _hash(url.encode())
            or event.get("response_sha256") != _hash(body)
            or event.get("status") != 200
            or event.get("body_saved") is not True
            or event.get("truncated") is not False
            or not isinstance(event.get("duration_seconds"), (int, float))
            or event["duration_seconds"] < 0
            or not isinstance(event.get("started_at_utc"), str)
            or not isinstance(event.get("completed_at_utc"), str)
        ):
            raise ValueError("PTAX request ledger differs from frozen plan")
        responses.append(body)
    check_metadata_pair(responses[0], responses[-1])
    identifiers = set()
    for number, batch in enumerate(batches):
        count = parse_count(responses[number * 2 + 1])
        rows = parse_rows(responses[number * 2 + 2], batch, expected_count=count)
        for row in rows:
            identifier = row["declaration_id"]
            if identifier in identifiers:
                raise ValueError("PTAX declaration repeats across batches")
            identifiers.add(identifier)
    if complete.get("returned_declarations") != len(identifiers):
        raise ValueError("PTAX completion count differs")
    expected_files = (
        {"selection.json", "complete.json"}
        | {f"event-{index:02d}.json" for index in range(len(expected_urls))}
        | {f"response-{index:02d}.json" for index in range(len(expected_urls))}
    )
    if {path.name for path in directory.iterdir()} != expected_files:
        raise ValueError("PTAX private run has unexpected or missing artifacts")
    return {
        "protocol": PROTOCOL,
        "status": "complete",
        "cook_capture_sha256": cook.CAPTURE_SHA256,
        "source_metadata_sha256": _hash(responses[0]),
        "response_set_sha256": _hash(_encoded([_hash(body) for body in responses])),
        "selected_cook_rows": sum(map(len, documents.values())),
        "unique_document_strings": len(documents)
        if len(documents) >= 5
        else "suppressed",
        "returned_declarations": len(identifiers)
        if len(identifiers) >= 5
        else "suppressed",
        "request_count": len(expected_urls),
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Private, bounded Illinois PTAX-203 source probe"
    )
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(arguments)
    try:
        if options.action == "capture":
            if options.run_dir or options.output:
                parser.error("capture takes no run directory or public output")
            capture()
            return 0
        if not options.run_dir or not options.output:
            parser.error("verify needs --run-dir and --output")
        private_io.summary_target(options.output, (options.run_dir / "selection.json",))
        result = verify(options.run_dir)
        private_io.write_summary_new(
            options.output, result, (options.run_dir / "selection.json",)
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError):
        print("PTAX source audit failed; inspect private run state", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
