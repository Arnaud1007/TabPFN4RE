"""One-shot, private Illinois Additional PINs source capture and offline replay.

This source can clarify declaration scope; it cannot certify a sale label.
Never print a declaration ID, PIN, raw response, or exact request URL.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from scripts import audit_illinois_ptax203_links as audit
from scripts import private_review_io as private_io
from scripts import probe_illinois_ptax203 as ptax


DATASET_ID = "ay2h-5hx3"
HOST = "illinois-edp.data.socrata.com"
METADATA_URL = f"https://{HOST}/api/views/{DATASET_ID}.json"
API_URL = f"https://{HOST}/resource/{DATASET_ID}.json"
PROTOCOL = "illinois-ptax203-additional-pins-v2"
PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "illinois_ptax203"
RUN_NAME = f"ptax-additional-v2-{ptax.cook.CAPTURE_SHA256[:16]}"
ROW_FIELDS = (
    "declaration_id",
    "pin",
    "lot_size_or_acreage",
    "lot_size_units",
    "split_parcel",
)
OBSERVED_COLUMNS = {
    "declaration_id": (610418722, "text"),
    "pin": (610418723, "text"),
    "lot_size_or_acreage": (610418724, "text"),
    "lot_size_units": (610418725, "text"),
    "split_parcel": (610418727, "text"),
}
COOK_SHA256 = ptax.cook.CAPTURE_SHA256
PTAX_SHA256 = audit.PINNED_RESPONSE_SET_SHA256
ROWS_UPDATED_AT = 1790506807
VIEW_LAST_MODIFIED = 1789611867
MAX_METADATA = 64 * 1024
MAX_COUNT = 8 * 1024
MAX_ROWS = 64 * 1024
MAX_PRIVATE = 1024 * 1024
MAX_REQUESTS = 18
MAX_TOTAL_ROWS = 500
TIMEOUT = 15
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ASCII_DECIMAL = re.compile(r"[0-9]+\Z")


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json(data: bytes) -> object:
    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError("Nonfinite JSON constant")

    try:
        return json.loads(
            data,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError) as error:
        raise ValueError("Additional PINs JSON is malformed") from error


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _valid_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def select_declarations(rows: object) -> tuple[str, ...]:
    """Freeze all 80 exact IDs from the already verified PTAX response bytes."""
    if not isinstance(rows, list) or len(rows) != audit.EXPECTED_DECLARATIONS:
        raise ValueError("Pinned declaration population differs")
    identifiers = []
    for row in rows:
        if not isinstance(row, dict) or not _valid_id(row.get("declaration_id")):
            raise ValueError("Pinned declaration identity is malformed")
        identifiers.append(row["declaration_id"])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Pinned declaration identity repeats")
    return tuple(sorted(identifiers))


def _batches(identifiers: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    if (
        not isinstance(identifiers, tuple)
        or len(identifiers) != audit.EXPECTED_DECLARATIONS
        or tuple(sorted(set(identifiers))) != identifiers
        or not all(map(_valid_id, identifiers))
    ):
        raise ValueError("Additional PIN selection is not frozen")
    return tuple(identifiers[index : index + 10] for index in range(0, 80, 10))


def query_url(identifiers: tuple[str, ...], *, count: bool) -> str:
    if (
        not isinstance(identifiers, tuple)
        or not 1 <= len(identifiers) <= 10
        or len(set(identifiers)) != len(identifiers)
        or not all(map(_valid_id, identifiers))
    ):
        raise ValueError("Invalid exact-declaration query batch")
    quoted = ",".join(
        "'" + identifier.replace("'", "''") + "'" for identifier in identifiers
    )
    params = {
        "$select": "count(*) as matched_count" if count else ",".join(ROW_FIELDS),
        "$where": f"declaration_id IN ({quoted})",
    }
    if not count:
        params.update({"$order": ",".join(ROW_FIELDS), "$limit": "100"})
    return API_URL + "?" + urlencode(params)


def metadata_identity(data: bytes) -> dict:
    record = _json(data)
    if not isinstance(record, dict) or record.get("id") != DATASET_ID:
        raise ValueError("Additional PINs source identity differs")
    if (
        record.get("publicationStage"),
        record.get("provenance"),
        record.get("licenseId"),
    ) != ("published", "official", "PUBLIC_DOMAIN"):
        raise ValueError("Additional PINs source status or licence differs")
    if (
        record.get("rowsUpdatedAt") != ROWS_UPDATED_AT
        or record.get("viewLastModified") != VIEW_LAST_MODIFIED
        or "rowIdentifierColumnId" in record
    ):
        raise ValueError("Additional PINs source version or row key differs")
    columns = record.get("columns")
    if not isinstance(columns, list) or len(columns) != len(ROW_FIELDS):
        raise ValueError("Additional PINs source schema differs")
    schema = {}
    ids = []
    for column in columns:
        if (
            not isinstance(column, dict)
            or not isinstance(column.get("fieldName"), str)
            or type(column.get("id")) is not int
            or not isinstance(column.get("dataTypeName"), str)
            or not column["dataTypeName"]
        ):
            raise ValueError("Additional PINs column metadata is malformed")
        schema[column["fieldName"]] = (
            column["id"],
            column["dataTypeName"],
        )
        ids.append(column["id"])
    if (
        set(schema) != set(ROW_FIELDS)
        or len(schema) != len(columns)
        or len(set(ids)) != len(ids)
        or schema != OBSERVED_COLUMNS
    ):
        raise ValueError("Additional PINs source schema differs")
    return {
        "rows_updated_at": ROWS_UPDATED_AT,
        "view_last_modified": VIEW_LAST_MODIFIED,
        "columns": {name: schema[name] for name in sorted(schema)},
        "license_id": "PUBLIC_DOMAIN",
        "row_identifier_column_id": None,
    }


def check_metadata_pair(before: bytes, after: bytes) -> dict:
    left, right = metadata_identity(before), metadata_identity(after)
    if left != right:
        raise ValueError("Additional PINs source changed during capture")
    return left


def parse_count(data: bytes) -> int:
    values = _json(data)
    if (
        not isinstance(values, list)
        or len(values) != 1
        or not isinstance(values[0], dict)
        or set(values[0]) != {"matched_count"}
    ):
        raise ValueError("Additional PINs count response is malformed")
    text = values[0].get("matched_count")
    if not isinstance(text, str) or not ASCII_DECIMAL.fullmatch(text):
        raise ValueError("Additional PINs count response is malformed")
    number = int(text)
    if number > 100:
        raise ValueError("Additional PINs batch exceeds cap")
    return number


def parse_rows(
    data: bytes, identifiers: tuple[str, ...], *, expected_count: int
) -> list[dict]:
    rows = _json(data)
    if (
        type(expected_count) is not int
        or not 0 <= expected_count <= 100
        or not isinstance(rows, list)
        or len(rows) != expected_count
    ):
        raise ValueError("Additional PINs count and rows disagree")
    for row in rows:
        if not isinstance(row, dict) or not set(row) <= set(ROW_FIELDS):
            raise ValueError("Additional PINs row includes unrequested fields")
        if row.get("declaration_id") not in identifiers:
            raise ValueError("Additional PINs row outside frozen declaration set")
        if any(
            value is not None
            and (
                not isinstance(value, (str, int, float, bool))
                or isinstance(value, str)
                and (len(value) > 256 or any(ord(char) < 32 for char in value))
            )
            for value in row.values()
        ):
            raise ValueError("Additional PINs row contains unsafe value")
    return rows


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
        raise CaptureFailure("Additional PINs redirect rejected", status=code)


def _build_opener():
    return build_opener(ProxyHandler({}), _NoRedirect)


_OPENER = _build_opener()


def _source_dir() -> Path:
    return ptax.PRIVATE_ROOT / audit.SOURCE_RUN_NAME


def _offline_dir() -> Path:
    return audit._private_root() / audit.RUN_NAME


def _verify_offline(source_dir: Path, offline_dir: Path) -> None:
    summary = audit.verify(offline_dir, source_dir)
    if (
        summary.get("cook_capture_sha256") != COOK_SHA256
        or summary.get("response_set_sha256") != PTAX_SHA256
        or summary.get("review_queue_size") != audit.EXPECTED_COOK_ROWS
        or summary.get("certified_sale_labels") != 0
    ):
        raise ValueError("Pinned offline diagnostic differs")


def _load_sources() -> tuple[list[dict], list[dict], dict]:
    source_dir = _source_dir()
    _verify_offline(source_dir, _offline_dir())
    cook_rows, ptax_rows, info = audit._load_sources(source_dir)
    if (
        len(cook_rows) != audit.EXPECTED_COOK_ROWS
        or len(ptax_rows) != audit.EXPECTED_DECLARATIONS
        or info.get("cook_capture_sha256") != COOK_SHA256
        or info.get("response_set_sha256") != PTAX_SHA256
    ):
        raise ValueError("Pinned Additional PINs inputs differ")
    return cook_rows, ptax_rows, info


def _private_root() -> Path:
    absolute = PRIVATE_ROOT.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink() or (
            candidate.exists()
            and not private_io.same_path(candidate, candidate.resolve())
        ):
            raise ValueError("Additional PINs private root redirects")
    PRIVATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_io.secure_directory(PRIVATE_ROOT)
    private_io.real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    private_io.verify_acl(PRIVATE_ROOT)
    return PRIVATE_ROOT


def _new_run() -> Path:
    root = _private_root()
    directory = root / RUN_NAME
    directory.mkdir(mode=0o700, exist_ok=False)
    private_io.secure_directory(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    return directory


def _read_bounded(path: Path, cap: int) -> bytes:
    if path.stat().st_size > cap:
        raise ValueError("Additional PINs private artifact exceeds cap")
    with path.open("rb") as stream:
        content = stream.read(cap + 1)
    if len(content) > cap:
        raise ValueError("Additional PINs private artifact exceeds cap")
    return content


def _write(directory: Path, name: str, data: bytes) -> None:
    if (
        not isinstance(data, bytes)
        or sum(path.stat().st_size for path in directory.iterdir()) + len(data)
        > MAX_PRIVATE
    ):
        raise ValueError("Additional PINs private budget exceeded")
    private_io.new_file(private_io.private_path(directory / name, directory), data)


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
        raise ValueError("Additional PINs source URL is not approved")
    start = monotonic()
    try:
        with _OPENER.open(url, timeout=TIMEOUT) as response:
            status = response.status
            if response.geturl() != url or status != 200:
                raise CaptureFailure(
                    "Additional PINs redirect or status rejected", status=status
                )
            body = response.read(cap + 1)
            if (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
                != "application/json"
            ):
                raise CaptureFailure(
                    "Additional PINs content type rejected",
                    status=status,
                    body_hash=_hash(body),
                    truncated=len(body) > cap,
                )
    except HTTPError as error:
        try:
            body = error.read(cap + 1)
        finally:
            error.close()
        raise CaptureFailure(
            "Additional PINs HTTP request failed",
            status=error.code,
            body_hash=_hash(body),
            truncated=len(body) > cap,
        ) from None
    if len(body) > cap:
        raise CaptureFailure(
            "Additional PINs response cap exceeded",
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
        raise ValueError("Additional PINs request budget exceeded")
    event = {
        "index": index,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "url_sha256": _hash(url.encode()),
        "status": None,
        "duration_seconds": None,
        "response_sha256": None,
        "body_saved": False,
        "truncated": False,
    }
    start = monotonic()
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
                "error": type(error).__name__,
            }
        )
    except (OSError, ValueError) as error:
        event["error"] = type(error).__name__
    event["duration_seconds"] = event["duration_seconds"] or monotonic() - start
    _write(directory, f"event-{index:02d}.json", _encoded(event))
    if not event["body_saved"]:
        raise CaptureFailure("Additional PINs request failed; run is incomplete")
    return body


def capture() -> Path:
    """Capture one 18-request maximum run after validating frozen inputs."""
    _, ptax_rows, _ = _load_sources()
    identifiers = select_declarations(ptax_rows)
    batches = _batches(identifiers)
    directory = _new_run()
    _write(
        directory,
        "selection.json",
        _encoded(
            {
                "protocol": PROTOCOL,
                "cook_capture_sha256": COOK_SHA256,
                "ptax_response_set_sha256": PTAX_SHA256,
                "declaration_ids": identifiers,
                "declaration_ids_sha256": _hash(_encoded(identifiers)),
            }
        ),
    )
    index = 0
    before = _request(directory, index, METADATA_URL, MAX_METADATA, metadata_identity)
    index += 1
    all_rows: list[dict] = []
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
        all_rows.extend(rows)
        if len(all_rows) > MAX_TOTAL_ROWS:
            raise ValueError("Additional PINs total rows exceed cap")
    after = _request(directory, index, METADATA_URL, MAX_METADATA, metadata_identity)
    check_metadata_pair(before, after)
    _write(
        directory,
        "complete.json",
        _encoded(
            {
                "protocol": PROTOCOL,
                "request_count": index + 1,
                "returned_observations": len(all_rows),
                "declaration_ids_sha256": _hash(_encoded(identifiers)),
            }
        ),
    )
    return directory


def _replay(directory: Path) -> dict:
    root = _private_root()
    directory = Path(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    if not private_io.same_path(directory, root / RUN_NAME):
        raise ValueError("Additional PINs private run identity differs")
    complete_path = private_io.private_path(
        directory / "complete.json", directory, must_exist=True
    )
    _, ptax_rows, _ = _load_sources()
    identifiers = select_declarations(ptax_rows)
    selection = _json(
        _read_bounded(
            private_io.private_path(
                directory / "selection.json", directory, must_exist=True
            ),
            64 * 1024,
        )
    )
    if selection != {
        "protocol": PROTOCOL,
        "cook_capture_sha256": COOK_SHA256,
        "ptax_response_set_sha256": PTAX_SHA256,
        "declaration_ids": list(identifiers),
        "declaration_ids_sha256": _hash(_encoded(identifiers)),
    }:
        raise ValueError("Additional PINs frozen selection differs")
    batches = _batches(identifiers)
    expected_urls = [METADATA_URL]
    for batch in batches:
        expected_urls.extend(
            (query_url(batch, count=True), query_url(batch, count=False))
        )
    expected_urls.append(METADATA_URL)
    if len(expected_urls) != MAX_REQUESTS:
        raise ValueError("Additional PINs request plan differs")
    expected_files = {"selection.json", "complete.json"}
    for index in range(len(expected_urls)):
        expected_files.add(f"event-{index:02d}.json")
        expected_files.add(f"response-{index:02d}.json")
    if {path.name for path in directory.iterdir()} != expected_files:
        raise ValueError("Additional PINs private file set differs")
    if sum(path.stat().st_size for path in directory.iterdir()) > MAX_PRIVATE:
        raise ValueError("Additional PINs private budget exceeded")
    complete = _json(_read_bounded(complete_path, 4096))
    responses = []
    for index, url in enumerate(expected_urls):
        cap = (
            MAX_METADATA
            if index in (0, len(expected_urls) - 1)
            else (MAX_COUNT if index % 2 else MAX_ROWS)
        )
        event = _json(
            _read_bounded(
                private_io.private_path(
                    directory / f"event-{index:02d}.json", directory, must_exist=True
                ),
                4096,
            )
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
            raise ValueError("Additional PINs request ledger differs")
        responses.append(body)
    check_metadata_pair(responses[0], responses[-1])
    rows: list[dict] = []
    for number, batch in enumerate(batches):
        count = parse_count(responses[number * 2 + 1])
        rows.extend(parse_rows(responses[number * 2 + 2], batch, expected_count=count))
        if len(rows) > MAX_TOTAL_ROWS:
            raise ValueError("Additional PINs total rows exceed cap")
    if complete != {
        "protocol": PROTOCOL,
        "request_count": MAX_REQUESTS,
        "returned_observations": len(rows),
        "declaration_ids_sha256": _hash(_encoded(identifiers)),
    }:
        raise ValueError("Additional PINs completion manifest differs")
    return {"rows": rows, "responses": responses}


def verify(directory: Path) -> dict:
    """Replay exact private bytes and return a fixed public allowlist."""
    replay = _replay(directory)
    responses = replay["responses"]
    return {
        "protocol": PROTOCOL,
        "status": "complete",
        "cook_capture_sha256": COOK_SHA256,
        "ptax_response_set_sha256": PTAX_SHA256,
        "additional_metadata_sha256": _hash(responses[0]),
        "additional_response_set_sha256": _hash(
            _encoded([_hash(body) for body in responses])
        ),
        "selected_cook_rows": audit.EXPECTED_COOK_ROWS,
        "selected_declarations": audit.EXPECTED_DECLARATIONS,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }


def _public_destination(output: Path, directory: Path) -> Path:
    parent = output.parent.resolve()
    for forbidden in (PRIVATE_ROOT, audit.RAW_ROOT, Path(directory)):
        if parent.is_relative_to(forbidden.resolve()):
            raise ValueError("Public output cannot be inside private raw data")
    return private_io.summary_target(output, (Path(directory) / "selection.json",))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Private Illinois Additional PINs source audit"
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
        _public_destination(options.output, options.run_dir)
        summary = verify(options.run_dir)
        private_io.write_summary_new(
            options.output,
            summary,
            (options.run_dir / "selection.json",),
        )
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, ValueError):
        print(
            "Additional PINs source audit failed; inspect private run state",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
