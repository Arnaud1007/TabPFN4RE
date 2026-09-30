"""Capture one bounded ACRIS index lookup for the private NYC review sample.

Index records are review leads. This module never appends a review or certifies
a sale label, closing date, or historical availability.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import audit_nyc_acris_matches_v2 as acris
from scripts import private_review_io, review_nyc_sample as review


PROTOCOL = "nyc-source-lookup-v1"
CODE_TABLE_SHA256 = acris.CODE_TABLE_SHA256
CODE_ROWS = acris.CODE_ROWS
PHASE_LIMITS = {"bbl": 1, "master": 30, "linked": 16}
MAX_REQUESTS = 50


def _source_and_sample(source: Path, sample: Path) -> tuple[list[dict], dict]:
    source = review._private_path(
        Path(source).absolute(), review=False, must_exist=True
    )
    sample = review._private_path(
        Path(sample).absolute(), review=False, must_exist=True
    )
    ordinals = review._sample_ordinals(sample)
    rows = review._source_rows(source, ordinals)
    try:
        entries = review._json_lines(sample.read_bytes(), "sample")
    except (OSError, UnicodeError) as error:
        raise ValueError("Frozen sample cannot be read") from error
    if len(entries) != review.SAMPLE_COUNT:
        raise ValueError("Frozen sample count differs")
    for item in entries:
        ordinal = item.get("ordinal")
        if type(ordinal) is not int or ordinal not in rows:
            raise ValueError("Frozen sample ordinal differs")
        expected = sha256(
            f"nyc-review-v1|{review.SOURCE_SHA256}|42|{ordinal}".encode()
        ).hexdigest()
        borough = rows[ordinal]["BOROUGH"].strip()
        if item.get("rank") != expected or not str(
            item.get("structural_cell", "")
        ).startswith(f"{borough}:"):
            raise ValueError("Frozen sample rank or cell differs")
    return entries, rows


def _code_table(path: Path) -> str:
    path = review._private_path(Path(path).absolute(), review=False, must_exist=True)
    content = review._read_bounded(path, 256 * 1024)
    digest = sha256(content).hexdigest()
    if digest != CODE_TABLE_SHA256:
        raise ValueError("ACRIS code table SHA-256 differs")
    try:
        rows = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("ACRIS code table malformed") from error
    if (
        not isinstance(rows, list)
        or len(rows) != CODE_ROWS
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("ACRIS code table shape differs")
    codes = {str(row.get("doc__type", "")).strip().upper() for row in rows}
    if not acris.PRIMARY.issubset(codes) or "CDEC" not in codes:
        raise ValueError("ACRIS deed/context codes missing")
    return digest


def _entries(content: bytes) -> list[dict]:
    if len(content) > review.MAX_LEDGER_BYTES:
        raise ValueError("Frozen review ledger exceeds limit")
    return review._json_lines(content, "review ledger")


def _choose(entries: list[dict], rows: dict, latest: dict) -> dict:
    eligible = sorted(
        (
            item
            for item in entries
            if rows[item["ordinal"]]["BOROUGH"].strip() in {"1", "2", "3", "4"}
            and (
                item["ordinal"] not in latest
                or latest[item["ordinal"]]["review_status"] != "complete"
            )
        ),
        key=lambda item: item["rank"],
    )
    if not eligible:
        raise ValueError("No unreviewed ACRIS sample row remains")
    chosen = eligible[0]
    row = rows[chosen["ordinal"]]
    borough = int(row["BOROUGH"].strip())
    block, lot = row["BLOCK"].strip(), row["LOT"].strip()
    ready = (
        acris.v1.NUMBER.fullmatch(block) is not None
        and acris.v1.NUMBER.fullmatch(lot) is not None
        and int(block) > 0
        and int(lot) > 0
    )
    sale_date = row["SALE DATE"].strip()
    try:
        datetime.strptime(sale_date, "%m/%d/%Y").date()
    except ValueError:
        date_valid = False
    else:
        date_valid = True
    return {
        "ordinal": chosen["ordinal"],
        "rank": chosen["rank"],
        "borough": borough,
        "block": block,
        "lot": lot,
        "sale_date": sale_date,
        "status": "missing_identity"
        if not ready
        else "missing_date"
        if not date_valid
        else "ready",
    }


def choose_next(source: Path, sample: Path, ledger: Path, manifest: Path) -> dict:
    """Validate live inputs and select privately; never print the result."""
    sample_entries, rows = _source_and_sample(source, sample)
    directory = review.RAW_ROOT / "manual-review-v1"
    private_review_io.verify_acl(directory)
    ledger = review._private_path(Path(ledger).absolute(), review=True, must_exist=True)
    manifest = review._private_path(
        Path(manifest).absolute(), review=True, must_exist=True
    )
    with private_review_io.exclusive_lock(ledger, directory):
        ledger_id = review._manifest(manifest)["ledger_id"]
        history, content = review._ledger_content(ledger)
        latest = review._history(history, ledger_id, set(rows), rows)
        return _choose(sample_entries, rows, latest)


def _live_selection(
    source: Path, sample: Path, ledger: Path, manifest: Path
) -> tuple[dict, bytes, str]:
    sample_entries, rows = _source_and_sample(source, sample)
    directory = review.RAW_ROOT / "manual-review-v1"
    private_review_io.verify_acl(directory)
    ledger = review._private_path(Path(ledger).absolute(), review=True, must_exist=True)
    manifest = review._private_path(
        Path(manifest).absolute(), review=True, must_exist=True
    )
    with private_review_io.exclusive_lock(ledger, directory):
        ledger_id = review._manifest(manifest)["ledger_id"]
        history, content = review._ledger_content(ledger)
        latest = review._history(history, ledger_id, set(rows), rows)
        return _choose(sample_entries, rows, latest), content, ledger_id


def _plans(phase: str, selected: dict, responses: dict) -> list[tuple[str, object]]:
    if phase == "bbl":
        if selected["status"] != "ready":
            return []
        bbl = (
            selected["borough"],
            int(selected["block"]),
            int(selected["lot"]),
        )
        return [(acris.legals_bbl_url(*bbl), bbl)]
    if phase == "master":
        candidates = sorted({row["document_id"] for row in responses.get("bbl", [])})
        return [
            (
                acris.master_batch_url(candidates[index : index + 10]),
                candidates[index : index + 10],
            )
            for index in range(0, len(candidates), 10)
        ]
    masters = responses.get("master", {})
    primary = sorted(
        (
            identifier
            for identifier, row in masters.items()
            if str(row.get("doc_type", "")).strip().upper() in acris.PRIMARY
        ),
        key=lambda identifier: acris._date_key(
            selected["sale_date"], masters[identifier], identifier
        ),
    )
    return [(acris.linked_url(identifier), identifier) for identifier in primary]


def _record_request(
    state: dict,
    run_dir: Path,
    client: acris.BoundedClient,
    phase: str,
    url: str,
    requested: object,
) -> dict:
    sequence = len(state["intents"]) + 1
    intent = {"sequence": sequence, "phase": phase, "url": url, "result": "pending"}
    updated = {**state, "intents": [*state["intents"], intent]}
    acris._atomic_json(run_dir / "state.json", updated)
    try:
        body = client.get(url)
    except HTTPError as error:
        try:
            body = error.read(acris.MAX_RESPONSE_BYTES + 1)
            if not isinstance(body, bytes):
                raise ValueError("HTTP error body invalid")
            body = body[: acris.MAX_RESPONSE_BYTES + 1]
            reason = "http_error"
        except Exception:
            body = None
            reason = "http_error_body_unavailable"
        outcome = "http_error"
    except (TimeoutError, URLError, OSError, ValueError) as error:
        body = None
        outcome = acris._status_for(error)
        reason = outcome
    else:
        outcome = "body"
        reason = "response_truncated" if len(body) > acris.MAX_RESPONSE_BYTES else "ok"
    if body is not None:
        name = f"response-{sequence:03d}.bin"
        acris._atomic_body(run_dir / name, body)
        intent = {**intent, "body_file": name, "body_sha256": sha256(body).hexdigest()}
        updated = {**updated, "intents": [*updated["intents"][:-1], intent]}
        acris._atomic_json(run_dir / "state.json", updated)
    if outcome == "body" and reason == "ok":
        try:
            _, saturated = acris._parse(body, phase, requested)
        except ValueError:
            reason = "schema_error"
        else:
            reason = (
                ("saturated_document" if phase == "linked" else f"saturated_{phase}")
                if saturated
                else "ok"
            )
    intent = {**intent, "result": outcome, "reason": reason}
    updated = {**updated, "intents": [*updated["intents"][:-1], intent]}
    acris._atomic_json(run_dir / "state.json", updated)
    return updated


def _read_intent(
    run_dir: Path, intent: dict, phase: str, url: str, requested: object
) -> tuple[list[dict], bool, bool]:
    if intent.get("result") == "pending" and "body_file" not in intent:
        sequence = intent.get("sequence")
        orphan = run_dir / f"response-{sequence:03d}.bin"
        if orphan.exists() or orphan.is_symlink():
            raise ValueError("Private orphan response needs reconciliation")
    if intent.get("result") == "pending" and "body_file" in intent:
        sequence = intent.get("sequence")
        expected_name = f"response-{sequence:03d}.bin"
        if intent["body_file"] != expected_name:
            raise ValueError("Pending private body filename differs")
        path = run_dir / expected_name
        body = acris.v1._private_file(path, run_dir)
        if len(body) > acris.MAX_RESPONSE_BYTES + 1 or sha256(
            body
        ).hexdigest() != intent.get("body_sha256"):
            raise ValueError("Pending private response differs")
    return acris._read_intent(run_dir, intent, phase, url, requested)


def _linked_ambiguous(selected: dict, responses: dict) -> bool:
    expected = (
        str(selected["borough"]),
        str(selected["block"]),
        str(selected["lot"]),
    )
    for rows in responses.get("linked", {}).values():
        lots = {
            (str(row.get("borough")), str(row.get("block")), str(row.get("lot")))
            for row in rows
        }
        units = {str(row.get("unit") or "").strip() for row in rows}
        if not rows or lots != {expected} or "" in units or len(units) != 1:
            return True
        if any(
            str(row.get("partial_lot") or "").strip() not in {"", "0", "N"}
            for row in rows
        ):
            return True
    return False


def _derive(state: dict, run_dir: Path) -> tuple[dict, list[tuple[str, str, object]]]:
    if state.get("protocol") != PROTOCOL or not isinstance(state.get("selected"), dict):
        raise ValueError("Private lookup state protocol differs")
    intents = state.get("intents")
    if not isinstance(intents, list) or len(intents) > MAX_REQUESTS:
        raise ValueError("Private lookup intent ledger invalid")
    selected = state["selected"]
    responses: dict = {}
    pending: list[tuple[str, str, object]] = []
    cursor = 0
    failed = selected["status"] != "ready"
    saturated = False
    unfinished = False
    unknown = False
    for phase in ("bbl", "master", "linked"):
        plan = _plans(phase, selected, responses)
        for url, requested in plan[: PHASE_LIMITS[phase]]:
            if cursor >= len(intents):
                pending.append((phase, url, requested))
                continue
            intent = intents[cursor]
            if intent.get("sequence") != cursor + 1:
                raise ValueError("Private lookup request sequence differs")
            rows, is_saturated, is_failed = _read_intent(
                run_dir, intent, phase, url, requested
            )
            cursor += 1
            saturated |= is_saturated
            failed |= is_failed
            unknown |= intent.get("result") == "pending"
            if not is_failed and not is_saturated:
                if phase == "bbl":
                    responses["bbl"] = rows
                elif phase == "master":
                    responses.setdefault("master", {}).update(
                        {row["document_id"]: row for row in rows}
                    )
                else:
                    responses.setdefault("linked", {})[requested] = rows
        unfinished |= len(plan) > PHASE_LIMITS[phase]
        if unknown:
            break
    if cursor != len(intents):
        raise ValueError("Private lookup has out-of-plan requests")
    status = (
        "INCOMPLETE_ERROR"
        if failed or unknown or pending
        else "PARTIAL_BUDGET"
        if unfinished
        else "COMPLETE_ROUTE_ONLY"
    )
    context_uninspected = any(
        str(row.get("doc_type", "")).strip().upper() not in acris.PRIMARY
        for row in responses.get("master", {}).values()
    )
    aggregate = {
        "protocol": PROTOCOL,
        "status": status,
        "request_intents": len(intents),
        "document_triage_finished": status == "COMPLETE_ROUTE_ONLY"
        and not saturated
        and not context_uninspected
        and not _linked_ambiguous(selected, responses),
        "manual_review_pending": True,
        "manual_reviews_appended": 0,
        "sale_labels_certified": 0,
        "source_sha256": review.SOURCE_SHA256,
        "sample_sha256": review.SAMPLE_SHA256,
        "review_ledger_sha256": state["review_ledger_sha256"],
        "code_table_sha256": state["code_table_sha256"],
    }
    return aggregate, pending


def _run_directory(path: Path) -> Path:
    root = review.RAW_ROOT
    private_review_io.real_directory(root, root.parent)
    path = Path(path).absolute()
    if path.is_symlink() or path.parent.resolve(strict=True) != root.resolve(
        strict=True
    ):
        raise ValueError("Lookup output must be directly inside private raw data")
    return path


def _secure_directory(path: Path) -> None:
    private_review_io.secure_directory(path)


def _verify_directory_acl(path: Path) -> None:
    private_review_io.verify_acl(path)


def replay_lookup(source: Path, sample: Path, code_table: Path, run_dir: Path) -> dict:
    """Recompute a saved lookup without network or mutation."""
    sample_entries, rows = _source_and_sample(source, sample)
    code_hash = _code_table(code_table)
    run_dir = _run_directory(run_dir)
    if not run_dir.is_dir() or (run_dir / "state.json").is_symlink():
        raise ValueError("Private lookup state missing")
    _verify_directory_acl(run_dir)
    state = json.loads(acris.v1._private_file(run_dir / "state.json", run_dir))
    if not isinstance(state, dict):
        raise ValueError("Private lookup state must be an object")
    content = acris.v1._private_file(run_dir / "ledger-snapshot.jsonl", run_dir)
    if (
        state.get("review_ledger_sha256") != sha256(content).hexdigest()
        or state.get("code_table_sha256") != code_hash
    ):
        raise ValueError("Private lookup inputs differ")
    latest = review._history(_entries(content), state["ledger_id"], set(rows), rows)
    if state.get("selected") != _choose(sample_entries, rows, latest):
        raise ValueError("Private lookup selection differs")
    aggregate, _ = _derive(state, run_dir)
    if "aggregate" in state and state["aggregate"] != aggregate:
        raise ValueError("Private lookup saved aggregate differs")
    return aggregate


def run_lookup(
    source: Path,
    sample: Path,
    ledger: Path,
    manifest: Path,
    code_table: Path,
    run_dir: Path,
    *,
    opener=acris._http_get,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """Start a create-only lookup, or replay an existing one without a GET."""
    run_dir = _run_directory(run_dir)
    if run_dir.exists():
        return replay_lookup(source, sample, code_table, run_dir)
    global_lock = review.RAW_ROOT / "nyc-source-lookup-v1-global"
    with private_review_io.exclusive_lock(global_lock, review.RAW_ROOT):
        selected, content, ledger_id = _live_selection(source, sample, ledger, manifest)
        code_hash = _code_table(code_table)
        run_dir.mkdir(mode=0o700)
        _secure_directory(run_dir)
        private_review_io.new_file(run_dir / "ledger-snapshot.jsonl", content)
        state = {
            "protocol": PROTOCOL,
            "selected": selected,
            "ledger_id": ledger_id,
            "review_ledger_sha256": sha256(content).hexdigest(),
            "code_table_sha256": code_hash,
            "intents": [],
        }
        acris._atomic_json(run_dir / "state.json", state)
        client = acris.BoundedClient(opener, clock, sleep, max_requests=MAX_REQUESTS)
        if selected["status"] == "ready":
            sleep(1)
        for phase in ("bbl", "master", "linked"):
            _, pending = _derive(state, run_dir)
            for planned_phase, url, requested in pending:
                if planned_phase != phase or len(state["intents"]) >= MAX_REQUESTS:
                    continue
                state = _record_request(state, run_dir, client, phase, url, requested)
        aggregate, _ = _derive(state, run_dir)
        state = {**state, "aggregate": aggregate}
        acris._atomic_json(run_dir / "state.json", state)
        return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "replay"))
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--code-table", required=True, type=Path)
    parser.add_argument("--private-run-dir", required=True, type=Path)
    parser.add_argument("--review-ledger", type=Path)
    parser.add_argument("--review-manifest", type=Path)
    options = parser.parse_args()
    if options.action == "capture":
        if options.review_ledger is None or options.review_manifest is None:
            parser.error("capture requires review ledger and manifest")
        run_lookup(
            options.source,
            options.sample,
            options.review_ledger,
            options.review_manifest,
            options.code_table,
            options.private_run_dir,
        )
    else:
        replay_lookup(
            options.source, options.sample, options.code_table, options.private_run_dir
        )
    print(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "projection": "private_only_v1",
                "manual_reviews_appended": 0,
                "sale_labels_certified": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
