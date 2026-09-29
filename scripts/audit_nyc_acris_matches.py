"""Run a bounded, private ACRIS linkage pilot against four frozen NYC rows.

This is source qualification, not a sale-label, close-date, or as-of validation.
All selected identities, queries, and API responses stay in ignored raw data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4

import profile_nyc_rolling_snapshot as profile


SNAPSHOT_SHA256 = "84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2"
LEDGER_SHA256 = "e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca"
SNAPSHOT_ROWS = 82_345
LEDGER_ROWS = 200
PROTOCOL = "nyc-acris-pilot-v1"
BASE = "https://data.cityofnewyork.us/resource/"
LEGALS = "8h5j-fqxa"
MASTER = "bnx9-e6tj"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REQUESTS = 50
DOC_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
NUMBER = re.compile(r"[0-9]+\Z")
LEGAL_FIELDS = (
    "document_id",
    "record_type",
    "borough",
    "block",
    "lot",
    "unit",
    "partial_lot",
    "air_rights",
    "subterranean_rights",
    "property_type",
    "good_through_date",
)
MASTER_FIELDS = (
    "document_id",
    "record_type",
    "doc_type",
    "document_date",
    "recorded_datetime",
    "document_amt",
    "percent_trans",
    "modified_date",
    "good_through_date",
)


def _private_file(path: Path, root: Path) -> bytes:
    path = Path(path).absolute()
    if (
        path.is_symlink()
        or path.parent.resolve(strict=True) != root
        or not path.is_file()
    ):
        raise ValueError("Input must be a regular file inside private raw data")
    with path.open("rb") as source:
        body = source.read(profile.MAX_CSV_BYTES + 1)
    if len(body) > profile.MAX_CSV_BYTES:
        raise ValueError("Private input exceeds byte limit")
    return body


def _rows(body: bytes):
    try:
        reader = csv.DictReader(
            StringIO(body.decode("utf-8-sig"), newline=""), restkey="EXTRA"
        )
        if tuple(reader.fieldnames or ()) != profile.HEADER:
            raise ValueError("Snapshot header differs from pinned schema")
        for ordinal, row in enumerate(reader, 1):
            if "EXTRA" in row or any(value is None for value in row.values()):
                raise ValueError("Snapshot row has malformed field count")
            yield ordinal, row
    except (UnicodeError, csv.Error) as error:
        raise ValueError("Snapshot CSV is malformed") from error


def verify_and_select(snapshot: Path, ledger: Path) -> list[dict]:
    """Verify the exact source and sample, then select one fixed row per ACRIS borough."""
    root = profile._private_root()
    csv_body = _private_file(snapshot, root)
    if sha256(csv_body).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("Snapshot SHA-256 differs from pinned protocol")
    ledger_body = _private_file(ledger, root)
    if (
        len(ledger_body) > 128 * 1024
        or sha256(ledger_body).hexdigest() != LEDGER_SHA256
    ):
        raise ValueError("Sample ledger SHA-256 differs from pinned protocol")
    rows = dict(_rows(csv_body))
    if len(rows) != SNAPSHOT_ROWS:
        raise ValueError("Snapshot row count differs from pinned protocol")
    try:
        entries = [json.loads(line) for line in ledger_body.splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Sample ledger is malformed") from error
    if len(entries) != LEDGER_ROWS:
        raise ValueError("Sample ledger row count differs from pinned protocol")
    seen = set()
    selected = {}
    for item in entries:
        if not isinstance(item, dict) or type(item.get("ordinal")) is not int:
            raise ValueError("Sample ledger ordinal is malformed")
        ordinal = item["ordinal"]
        if ordinal in seen or ordinal not in rows:
            raise ValueError("Sample ledger ordinal is duplicate or absent")
        seen.add(ordinal)
        expected_rank = sha256(
            f"nyc-review-v1|{SNAPSHOT_SHA256}|42|{ordinal}".encode()
        ).hexdigest()
        if item.get("rank") != expected_rank:
            raise ValueError("Sample ledger rank differs from frozen selection")
        row = rows[ordinal]
        borough = row["BOROUGH"].strip()
        if not isinstance(item.get("structural_cell"), str) or not item[
            "structural_cell"
        ].startswith(f"{borough}:"):
            raise ValueError("Sample ledger structural cell differs from source")
        if borough in ("1", "2", "3", "4") and (
            borough not in selected or expected_rank < selected[borough]["rank"]
        ):
            selected[borough] = {
                "ordinal": ordinal,
                "rank": expected_rank,
                "borough": int(borough),
                "block": row["BLOCK"].strip(),
                "lot": row["LOT"].strip(),
                "sale_date": row["SALE DATE"].strip(),
            }
    if set(selected) != set("1234"):
        raise ValueError("Sample ledger lacks an ACRIS borough")
    result = []
    for borough in "1234":
        item = selected[borough]
        block, lot = item["block"], item["lot"]
        result.append(
            {
                **item,
                "status": "ready"
                if NUMBER.fullmatch(block)
                and NUMBER.fullmatch(lot)
                and int(block) > 0
                and int(lot) > 0
                else "missing_identity",
            }
        )
    return result


def _url(dataset: str, where: str, fields: tuple[str, ...], limit: int) -> str:
    return (
        BASE
        + dataset
        + ".json?"
        + urlencode(
            {
                "$select": ",".join(fields),
                "$where": where,
                "$order": "document_id",
                "$limit": limit,
            }
        )
    )


def legals_bbl_url(borough: int, block: int, lot: int) -> str:
    if borough not in range(1, 5) or min(block, lot) <= 0:
        raise ValueError(
            "BBL must contain positive numeric components in ACRIS coverage"
        )
    return _url(
        LEGALS, f"borough={borough} AND block={block} AND lot={lot}", LEGAL_FIELDS, 251
    )


def _document_id(value: str) -> str:
    if not isinstance(value, str) or not DOC_ID.fullmatch(value):
        raise ValueError("ACRIS document identifier is malformed")
    return value


def master_url(document_id: str) -> str:
    return _url(MASTER, f"document_id='{_document_id(document_id)}'", MASTER_FIELDS, 3)


def legals_document_url(document_id: str) -> str:
    return _url(LEGALS, f"document_id='{_document_id(document_id)}'", LEGAL_FIELDS, 101)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError("ACRIS HTTP redirect rejected")


def _http_get(url: str, timeout: int) -> bytes:
    with build_opener(_NoRedirect()).open(url, timeout=timeout) as response:
        return response.read(MAX_RESPONSE_BYTES + 1)


class BoundedClient:
    def __init__(
        self,
        opener=_http_get,
        clock=time.monotonic,
        sleep=time.sleep,
        max_requests=MAX_REQUESTS,
    ):
        self.opener, self.clock, self.sleep = opener, clock, sleep
        self.max_requests = max_requests
        self.count = 0
        self.last_call = None

    def get(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "data.cityofnewyork.us"
            or parsed.path
            not in (f"/resource/{LEGALS}.json", f"/resource/{MASTER}.json")
        ):
            raise ValueError("API URL is outside approved NYC Open Data datasets")
        if self.count >= self.max_requests:
            raise ValueError("Pilot HTTP request cap reached")
        if self.last_call is not None:
            delay = 1.0 - (self.clock() - self.last_call)
            if delay > 0:
                self.sleep(delay)
        self.last_call = self.clock()
        self.count += 1
        body = self.opener(url, 30)
        if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("API response byte limit exceeded or invalid response")
        return body


def parse_rows(body: bytes, cap: int) -> list[dict]:
    try:
        rows = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("API response is malformed JSON") from error
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("API response is malformed rows")
    if len(rows) > cap:
        raise ValueError("API response is saturated")
    return rows


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.parent / f".{uuid4().hex}.part"
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _atomic_bytes(path: Path, body: bytes) -> None:
    temp = path.parent / f".{uuid4().hex}.part"
    try:
        with temp.open("xb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _validated_ids(rows: list[dict], *, bbl=None, document=None) -> list[str]:
    ids = []
    for row in rows:
        identifier = _document_id(row.get("document_id"))
        if document is not None and identifier != document:
            raise ValueError("API document response contradicts exact query")
        if bbl is not None:
            try:
                actual = tuple(int(row[key]) for key in ("borough", "block", "lot"))
            except (KeyError, ValueError, TypeError) as error:
                raise ValueError("API BBL response is malformed") from error
            if actual != bbl:
                raise ValueError("API BBL response contradicts exact query")
        ids.append(identifier)
    return ids


def _summarize(
    master_rows: list[dict], legal_rows: list[dict]
) -> tuple[str, list[str]]:
    reasons = []
    if not master_rows or not legal_rows:
        return "unresolved", ["missing_linked_record"]
    lots = {
        (str(row.get("borough")), str(row.get("block")), str(row.get("lot")))
        for row in legal_rows
    }
    if len(lots) > 1:
        reasons.append("multiple_lots")
    if any(not str(row.get("unit", "")).strip() for row in legal_rows):
        reasons.append("blank_or_missing_unit")
    if len({str(row.get("unit", "")).strip() for row in legal_rows}) > 1:
        reasons.append("conflicting_units")
    if any(
        str(row.get("partial_lot", "")).strip() not in ("", "0", "N")
        for row in legal_rows
    ):
        reasons.append("partial_lot")
    if any(
        str(row.get("percent_trans", "")).strip() not in ("", "100")
        for row in master_rows
    ):
        reasons.append("partial_interest")
    types = {str(row.get("doc_type", "")).upper().strip() for row in master_rows}
    if any("MTGE" in kind or "MORT" in kind for kind in types):
        reasons.append("mortgage_or_non_deed")
    if len(master_rows) > 1:
        reasons.append("multiple_master_rows")
    return ("ambiguous" if reasons else "candidate_for_manual_review"), reasons


def document_type_category(value: object) -> str:
    kind = str(value).strip().upper() if value is not None else ""
    if kind == "DEED":
        return "DEED"
    if kind in ("MTGE", "MORTGAGE"):
        return "MORTGAGE"
    return "OTHER" if kind else "UNKNOWN"


def _document_summary(
    ids: list[str], documents: list[tuple[str, list[dict], list[dict]]]
):
    reasons = []
    statuses = []
    types: Counter[str] = Counter()
    for _, masters, linked in documents:
        status, found = _summarize(masters, linked)
        statuses.append(status)
        reasons.extend(found)
        types.update(document_type_category(row.get("doc_type")) for row in masters)
    if len(ids) > 1:
        reasons.append("multiple_candidate_documents")
    status = (
        "unresolved"
        if "unresolved" in statuses
        else "ambiguous"
        if reasons
        else "candidate_for_manual_review"
    )
    return status, set(reasons), types


def _aggregate(counts, reasons, types, urls: list[str]) -> dict:
    return {
        "status": "completed_provisional_pilot",
        "protocol": PROTOCOL,
        "counts_by_borough": {key: dict(value) for key, value in counts.items()},
        "ambiguity_reasons": dict(reasons),
        "candidate_document_types": dict(types),
        "http_requests": len(urls),
        "query_sha256": sha256(
            "|".join(sha256(url.encode()).hexdigest() for url in urls).encode()
        ).hexdigest(),
        "snapshot_sha256": SNAPSHOT_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "manual_reviews_completed": 0,
        "sale_labels_certified": 0,
    }


def failure_category(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (HTTPError, URLError)):
        return "http_error"
    if isinstance(error, OSError):
        return "io_error"
    message = str(error).lower()
    if "redirect" in message:
        return "redirect_rejected"
    if "request cap" in message:
        return "request_cap"
    if "response byte" in message:
        return "response_limit"
    if "saturated" in message:
        return "saturated"
    if "malformed" in message or "contradict" in message or "unrequested" in message:
        return "schema_error"
    return "validation_error"


def inspection_order(
    sale_date: str, documents: list[tuple[str, list[dict]]]
) -> list[str]:
    """Order every document for human inspection; never exclude by date distance."""
    try:
        origin = datetime.strptime(sale_date, "%m/%d/%Y").date()
    except (TypeError, ValueError) as error:
        raise ValueError("Rolling sale date is malformed") from error

    def key(document: tuple[str, list[dict]]):
        identifier, rows = document
        distances = []
        for row in rows:
            try:
                observed = datetime.strptime(
                    str(row["document_date"])[:10], "%Y-%m-%d"
                ).date()
            except (KeyError, TypeError, ValueError):
                continue
            distances.append(abs((observed - origin).days))
        distance = min(distances, default=None)
        return (
            2 if distance is None else 0 if distance <= 365 else 1,
            distance if distance is not None else 10**9,
            identifier,
        )

    return [identifier for identifier, _ in sorted(documents, key=key)]


def _verify_replay(state: dict, selected: list[dict], run_dir: Path) -> None:
    if (
        state.get("protocol") != PROTOCOL
        or state.get("selected") != selected
        or state.get("status") not in ("complete", "incomplete")
    ):
        raise ValueError("Existing pilot state status or selection is invalid")
    aggregate = state.get("aggregate")
    expected_status = (
        "completed_provisional_pilot" if state["status"] == "complete" else "incomplete"
    )
    if not isinstance(aggregate, dict) or aggregate.get("status") != expected_status:
        raise ValueError("Existing pilot state status contradicts aggregate")
    entries = state.get("responses")
    if not isinstance(entries, list) or len(entries) > MAX_REQUESTS:
        raise ValueError("Existing pilot saved responses are invalid")
    recorded = set()
    cursor = 0
    counts = {str(b): Counter() for b in range(1, 5)}
    reasons: Counter[str] = Counter()
    types: Counter[str] = Counter()
    expected_order = {}

    def take(url: str, cap: int, *, bbl=None, document=None):
        nonlocal cursor
        if cursor == len(entries):
            return None
        entry = entries[cursor]
        filename = entry.get("filename") if isinstance(entry, dict) else None
        if (
            not isinstance(filename, str)
            or not re.fullmatch(r"response-[0-9]{3}\.json", filename)
            or filename in recorded
        ):
            raise ValueError("Existing pilot has an invalid saved response filename")
        recorded.add(filename)
        if entry.get("url") != url:
            raise ValueError(
                "Existing pilot saved query sequence differs from frozen pilot"
            )
        body = _private_file(run_dir / filename, run_dir)
        if sha256(body).hexdigest() != entry.get("sha256"):
            raise ValueError("Saved API response hash differs from pilot state")
        rows = parse_rows(body, cap)
        allowed = LEGAL_FIELDS if f"/{LEGALS}.json" in url else MASTER_FIELDS
        if any(set(row) - set(allowed) for row in rows):
            raise ValueError("Saved API response contains unrequested fields")
        _validated_ids(rows, bbl=bbl, document=document)
        cursor += 1
        return rows

    complete = True
    for item in selected:
        borough = str(item["borough"])
        if item["status"] != "ready":
            counts[borough]["missing_identity"] += 1
            continue
        bbl = (item["borough"], int(item["block"]), int(item["lot"]))
        legals = take(legals_bbl_url(*bbl), 250, bbl=bbl)
        if legals is None:
            complete = False
            break
        ids = sorted(set(_validated_ids(legals)))
        if not ids:
            counts[borough]["no_acris_candidate"] += 1
            continue
        documents = []
        for identifier in ids:
            masters = take(master_url(identifier), 2, document=identifier)
            if masters is None:
                complete = False
                break
            linked = take(legals_document_url(identifier), 100, document=identifier)
            if linked is None:
                complete = False
                break
            documents.append((identifier, masters, linked))
        if not complete:
            break
        expected_order[str(item["ordinal"])] = inspection_order(
            item["sale_date"],
            [(identifier, masters) for identifier, masters, _ in documents],
        )
        status, found, found_types = _document_summary(ids, documents)
        counts[borough][status] += 1
        reasons.update(found)
        types.update(found_types)
    if cursor != len(entries) or (state["status"] == "complete" and not complete):
        raise ValueError(
            "Existing pilot saved query sequence is incomplete or excessive"
        )
    stored_order = state.get("inspection_order", {})
    if (
        not isinstance(stored_order, dict)
        or any(
            key not in expected_order or expected_order[key] != value
            for key, value in stored_order.items()
        )
        or (state["status"] == "complete" and stored_order != expected_order)
    ):
        raise ValueError("Existing pilot inspection order differs from saved responses")
    if state["status"] == "complete":
        expected_aggregate = _aggregate(
            counts, reasons, types, [entry["url"] for entry in entries]
        )
        if aggregate != expected_aggregate:
            raise ValueError("Existing pilot aggregate differs from saved queries")
    elif (
        any(
            key
            not in {
                "status",
                "protocol",
                "failure_kind",
                "http_requests",
                "snapshot_sha256",
                "ledger_sha256",
                "manual_reviews_completed",
                "sale_labels_certified",
            }
            for key in aggregate
        )
        or aggregate.get("sale_labels_certified", 0) != 0
        or aggregate.get("manual_reviews_completed", 0) != 0
    ):
        raise ValueError("Existing incomplete aggregate has unverifiable fields")


def run_pilot(
    snapshot: Path,
    ledger: Path,
    run_dir: Path,
    *,
    opener=_http_get,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """Run once or replay validated private evidence without further HTTP requests."""
    selected = verify_and_select(snapshot, ledger)
    root = profile._private_root()
    run_dir = Path(run_dir).absolute()
    if run_dir.is_symlink() or run_dir.parent.resolve(strict=True) != root:
        raise ValueError("Pilot output must be inside private raw data")
    state_path = run_dir / "state.json"
    if run_dir.exists():
        if not run_dir.is_dir() or state_path.is_symlink() or not state_path.is_file():
            raise ValueError("Existing pilot lacks a valid private state")
        state = json.loads(_private_file(state_path, run_dir))
        if (
            state.get("snapshot_sha256") != SNAPSHOT_SHA256
            or state.get("ledger_sha256") != LEDGER_SHA256
        ):
            raise ValueError("Existing pilot is incompatible with pinned inputs")
        _verify_replay(state, selected, run_dir)
        return state["aggregate"]
    run_dir.mkdir(mode=0o700)
    state = {
        "protocol": PROTOCOL,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "selected": selected,
        "responses": [],
        "status": "incomplete",
        "aggregate": {"status": "incomplete"},
    }
    _atomic_json(state_path, state)
    client = BoundedClient(opener, clock, sleep)
    counts = {str(b): Counter() for b in range(1, 5)}
    reasons: Counter[str] = Counter()
    types: Counter[str] = Counter()
    query_urls = []

    def fetch(url: str, cap: int, *, bbl=None, document=None) -> list[dict]:
        nonlocal state
        body = client.get(url)
        rows = parse_rows(body, cap)
        allowed = LEGAL_FIELDS if f"/{LEGALS}.json" in url else MASTER_FIELDS
        if any(set(row) - set(allowed) for row in rows):
            raise ValueError("API response contains unrequested fields")
        _validated_ids(rows, bbl=bbl, document=document)
        filename = f"response-{len(state['responses']) + 1:03d}.json"
        _atomic_bytes(run_dir / filename, body)
        state = {
            **state,
            "responses": [
                *state["responses"],
                {
                    "filename": filename,
                    "sha256": sha256(body).hexdigest(),
                    "url": url,
                },
            ],
        }
        _atomic_json(state_path, state)
        query_urls.append(url)
        return rows

    try:
        for item in selected:
            borough = str(item["borough"])
            if item["status"] != "ready":
                counts[borough]["missing_identity"] += 1
                continue
            bbl = (item["borough"], int(item["block"]), int(item["lot"]))
            legal_candidates = fetch(legals_bbl_url(*bbl), 250, bbl=bbl)
            ids = sorted(set(_validated_ids(legal_candidates)))
            if not ids:
                counts[borough]["no_acris_candidate"] += 1
                continue
            per_document = []
            for identifier in ids:
                masters = fetch(master_url(identifier), 2, document=identifier)
                linked = fetch(
                    legals_document_url(identifier), 100, document=identifier
                )
                per_document.append((identifier, masters, linked))
            state = {
                **state,
                "inspection_order": {
                    **state.get("inspection_order", {}),
                    str(item["ordinal"]): inspection_order(
                        item["sale_date"],
                        [
                            (identifier, masters)
                            for identifier, masters, _ in per_document
                        ],
                    ),
                },
            }
            _atomic_json(state_path, state)
            status, document_reasons, document_types = _document_summary(
                ids, per_document
            )
            counts[borough][status] += 1
            reasons.update(document_reasons)
            types.update(document_types)
        aggregate = _aggregate(counts, reasons, types, query_urls)
        state = {**state, "status": "complete", "aggregate": aggregate}
    except (
        ValueError,
        TimeoutError,
        OSError,
        UnicodeError,
        TypeError,
        KeyError,
    ) as error:
        aggregate = {
            "status": "incomplete",
            "protocol": PROTOCOL,
            "failure_kind": failure_category(error),
            "http_requests": client.count,
            "snapshot_sha256": SNAPSHOT_SHA256,
            "ledger_sha256": LEDGER_SHA256,
            "manual_reviews_completed": 0,
            "sale_labels_certified": 0,
        }
        state = {**state, "aggregate": aggregate}
    _atomic_json(state_path, state)
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--private-run-dir", required=True, type=Path)
    arguments = parser.parse_args()
    result = run_pilot(arguments.snapshot, arguments.ledger, arguments.private_run_dir)
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "completed_provisional_pilot":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
