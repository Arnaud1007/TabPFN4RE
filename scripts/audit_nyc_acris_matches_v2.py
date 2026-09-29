"""Bounded, private NYC ACRIS source-qualification pilot, protocol v2.

No output from this module certifies a sale, close date, or as-of availability.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

import audit_nyc_acris_matches as v1
import profile_nyc_rolling_snapshot as profile


PROTOCOL = "nyc-acris-pilot-v2"
CODE_TABLE_SHA256 = "518363532df753ac364ce47c5d62dfbdbaf609b598845bfcfe2ec83b9739c625"
CODE_ROWS = 126
PRIMARY = frozenset(("DEED", "DEEDP", "DEEDO", "DEED, RC"))
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_URL_LENGTH = 4096
MAX_REQUESTS = 50
PHASE_LIMITS = {"bbl": 4, "master": 30, "linked": 16}
MASTER_FIELDS = (
    "document_id",
    "record_type",
    "doc_type",
    "document_date",
    "recorded_datetime",
    "percent_trans",
    "modified_date",
    "good_through_date",
)
LEGAL_FIELDS = v1.LEGAL_FIELDS
ALLOWED_HOST = "data.cityofnewyork.us"
DOCUMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
_INTENT_FILE = re.compile(r"response-[0-9]{3}\.bin\Z")


def _private_input(path: Path, root: Path, maximum: int) -> bytes:
    body = v1._private_file(path, root)
    if len(body) > maximum:
        raise ValueError("Private input exceeds byte limit")
    return body


def _verify_inputs(
    snapshot: Path, ledger: Path, code_table: Path
) -> tuple[list[dict], str]:
    selected = v1.verify_and_select(snapshot, ledger)
    body = _private_input(code_table, profile._private_root(), 256 * 1024)
    if sha256(body).hexdigest() != CODE_TABLE_SHA256:
        raise ValueError("ACRIS code table SHA-256 differs from pinned protocol")
    try:
        rows = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("ACRIS code table is malformed") from error
    if (
        not isinstance(rows, list)
        or len(rows) != CODE_ROWS
        or any(not isinstance(x, dict) for x in rows)
    ):
        raise ValueError("ACRIS code table shape differs from pinned protocol")
    codes = {str(row.get("doc__type", "")).strip().upper() for row in rows}
    if not PRIMARY.issubset(codes) or "CDEC" not in codes:
        raise ValueError("ACRIS code table lacks frozen deed/context codes")
    return selected, sha256(body).hexdigest()


def _id(value: object) -> str:
    if not isinstance(value, str) or DOCUMENT_ID.fullmatch(value) is None:
        raise ValueError("ACRIS document identifier is malformed")
    return value


def _url(dataset: str, fields: tuple[str, ...], where: str, limit: int) -> str:
    url = f"https://{ALLOWED_HOST}/resource/{dataset}.json?" + urlencode(
        {
            "$select": ",".join(fields),
            "$where": where,
            "$order": "document_id",
            "$limit": limit,
        }
    )
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("ACRIS URL limit exceeded")
    return url


def legals_bbl_url(borough: int, block: int, lot: int) -> str:
    return v1.legals_bbl_url(borough, block, lot)


def master_batch_url(ids: list[str]) -> str:
    if not 1 <= len(ids) <= 10 or len(set(ids)) != len(ids):
        raise ValueError("Master batch must contain one to ten distinct IDs")
    safe = [_id(item) for item in ids]
    return _url(
        v1.MASTER,
        MASTER_FIELDS,
        "document_id in(" + ",".join(f"'{item}'" for item in safe) + ")",
        31,
    )


def linked_url(document_id: str) -> str:
    return _url(v1.LEGALS, LEGAL_FIELDS, f"document_id='{_id(document_id)}'", 101)


def _requested_ids(url: str) -> list[str]:
    where = parse_qs(urlsplit(url).query).get("$where", [""])[0]
    if where.startswith("document_id in(") and where.endswith(")"):
        literals = where[len("document_id in(") : -1].split(",")
        if not literals or len(literals) > 10:
            raise ValueError("Master batch expression is invalid")
        ids = [
            _id(item[1:-1])
            for item in literals
            if item.startswith("'") and item.endswith("'")
        ]
        if len(ids) != len(literals) or len(ids) != len(set(ids)):
            raise ValueError("Master batch expression is invalid")
        return ids
    if where.startswith("document_id='") and where.endswith("'"):
        return [_id(where[len("document_id='") : -1])]
    raise ValueError("Document query expression is invalid")


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
        self.opener = opener
        self.clock = clock
        self.sleep = sleep
        self.max_requests = max_requests
        self.count = 0
        self.last_call = None

    def get(self, url: str) -> bytes:
        if len(url) > MAX_URL_LENGTH:
            raise ValueError("ACRIS URL limit exceeded")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != ALLOWED_HOST
            or parsed.path
            not in (f"/resource/{v1.LEGALS}.json", f"/resource/{v1.MASTER}.json")
            or parsed.fragment
        ):
            raise ValueError("API URL is outside approved NYC Open Data datasets")
        if self.count >= self.max_requests:
            raise ValueError("Pilot HTTP request cap reached")
        if self.last_call is not None:
            remaining = 1 - (self.clock() - self.last_call)
            if remaining > 0:
                self.sleep(remaining)
        self.last_call = self.clock()
        self.count += 1
        body = self.opener(url, 30)
        if not isinstance(body, bytes):
            raise ValueError("API response body is invalid")
        return body[: MAX_RESPONSE_BYTES + 1]


def _atomic_json(path: Path, value: dict) -> None:
    v1._atomic_json(path, value)


def _atomic_body(path: Path, body: bytes) -> None:
    v1._atomic_bytes(path, body)


def _user_sid() -> str:
    try:
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Private run directory user SID unavailable") from error
    import csv
    import io

    fields = next(csv.reader(io.StringIO(identity.stdout)), [])
    if len(fields) != 2 or not re.fullmatch(r"S-1-[0-9-]+", fields[1]):
        raise ValueError("Private run directory user SID unavailable")
    return fields[1]


def _powershell_acl(run_dir: Path, script: str, user_sid: str) -> dict:
    environment = {
        **os.environ,
        "TABPFN_ACL_DIR": str(run_dir),
        "TABPFN_OWNER_SID": user_sid,
    }
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        value = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ValueError("Private run directory ACL verification failed") from error
    if not isinstance(value, dict):
        raise ValueError("Private run directory ACL verification failed")
    return value


def _verify_directory_acl(run_dir: Path) -> None:
    """Read-only verification on initial use and every offline replay."""
    if os.name != "nt":
        if run_dir.stat().st_mode & 0o077:
            raise ValueError("Private run directory permissions are too broad")
        return
    user_sid = _user_sid()
    script = (
        "$ErrorActionPreference='Stop'; "
        "$acl=Get-Acl -LiteralPath $env:TABPFN_ACL_DIR; "
        "$entries=@($acl.Access|ForEach-Object{ $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }); "
        "@{protected=$acl.AreAccessRulesProtected; entries=$entries}|ConvertTo-Json -Compress"
    )
    verified = _powershell_acl(run_dir, script, user_sid)
    allowed = {user_sid, "S-1-5-18", "S-1-5-32-544"}
    entries = verified.get("entries")
    if (
        verified.get("protected") is not True
        or not isinstance(entries, list)
        or not set(entries).issubset(allowed)
        or user_sid not in entries
    ):
        raise ValueError("Private run directory ACL verification failed")


def _secure_directory(run_dir: Path) -> None:
    """Set a protected DACL once; leave existing evidence untouched on replay."""
    if os.name != "nt":
        _verify_directory_acl(run_dir)
        return
    user_sid = _user_sid()
    script = (
        "$ErrorActionPreference='Stop'; $p=$env:TABPFN_ACL_DIR; "
        "$acl=[System.IO.Directory]::GetAccessControl($p,[System.Security.AccessControl.AccessControlSections]::Access); "
        "$acl.SetAccessRuleProtection($true,$false); "
        "foreach($sidText in @($env:TABPFN_OWNER_SID,'S-1-5-18','S-1-5-32-544')){ "
        "$sid=New-Object System.Security.Principal.SecurityIdentifier($sidText); "
        "$rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); "
        "$acl.AddAccessRule($rule) }; "
        "[System.IO.Directory]::SetAccessControl($p,$acl); "
        "@{updated=$true}|ConvertTo-Json -Compress"
    )
    _powershell_acl(run_dir, script, user_sid)
    _verify_directory_acl(run_dir)


def _status_for(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, HTTPError):
        return "http_error"
    if isinstance(error, URLError):
        return "timeout" if isinstance(error.reason, TimeoutError) else "network_error"
    if isinstance(error, OSError):
        return "io_error"
    return "validation_error"


def _parse(body: bytes, phase: str, requested: object) -> tuple[list[dict], bool]:
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("API response truncated")
    try:
        rows = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("API response malformed") from error
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("API response malformed")
    allowed = set(LEGAL_FIELDS if phase != "master" else MASTER_FIELDS)
    if any(set(row) - allowed for row in rows):
        raise ValueError("API response has unrequested fields")
    ids = [_id(row.get("document_id")) for row in rows]
    if phase == "master":
        if len(ids) != len(set(ids)) or set(ids) != set(requested):
            raise ValueError("Master response incomplete or duplicated")
    elif phase == "linked":
        if any(identifier != requested for identifier in ids):
            raise ValueError("Linked Legals response contradicts query")
    else:
        for row in rows:
            try:
                bbl = tuple(int(row[key]) for key in ("borough", "block", "lot"))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("BBL response malformed") from error
            if bbl != requested:
                raise ValueError("BBL response contradicts exact query")
    cap = {"bbl": 250, "master": 30, "linked": 100}[phase]
    if len(rows) > cap:
        return [], True
    return rows, False


def _date_key(sale_date: str, master: dict, identifier: str) -> tuple[int, int, str]:
    try:
        sold = datetime.strptime(sale_date, "%m/%d/%Y").date()
    except (TypeError, ValueError) as error:
        raise ValueError("Frozen rolling sale date malformed") from error
    value = master.get("document_date")
    try:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?",
            value,
        ):
            raise ValueError("Master date format invalid")
        observed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return (2, 10**9, identifier)
    distance = abs((observed - sold).days)
    return (0 if distance <= 365 else 1, distance, identifier)


def _round_robin(queues: dict[int, list]) -> list[tuple[int, object]]:
    output = []
    positions = {b: 0 for b in range(1, 5)}
    while any(positions[b] < len(queues[b]) for b in range(1, 5)):
        for borough in range(1, 5):
            if positions[borough] < len(queues[borough]):
                output.append((borough, queues[borough][positions[borough]]))
                positions[borough] += 1
    return output


def _request_plan(
    selected: list[dict], phase: str, responses: dict
) -> list[tuple[int, str, object]]:
    """Derive phase work only from validated previous private responses."""
    if phase == "bbl":
        return [
            (
                item["borough"],
                legals_bbl_url(item["borough"], int(item["block"]), int(item["lot"])),
                (item["borough"], int(item["block"]), int(item["lot"])),
            )
            for item in selected
            if item["status"] == "ready"
        ]
    if phase == "master":
        owned: dict[str, int] = {}
        for borough in range(1, 5):
            for row in responses.get(("bbl", borough), []):
                owned.setdefault(row["document_id"], borough)
        queues = {borough: [] for borough in range(1, 5)}
        for identifier, borough in sorted(owned.items()):
            queues[borough].append(identifier)
        batches = {
            borough: [queue[j : j + 10] for j in range(0, len(queue), 10)]
            for borough, queue in queues.items()
        }
        return [
            (borough, master_batch_url(batch), batch)
            for borough, batch in _round_robin(batches)
        ]
    owners: dict[str, int] = {}
    dates: dict[str, dict] = {}
    for borough in range(1, 5):
        for row in responses.get(("bbl", borough), []):
            identifier = row["document_id"]
            master = responses.get(("master", identifier))
            if master and str(master.get("doc_type", "")).strip().upper() in PRIMARY:
                owners.setdefault(identifier, borough)
                dates[identifier] = master
    queues = {borough: [] for borough in range(1, 5)}
    by_borough = {item["borough"]: item for item in selected}
    for identifier, borough in owners.items():
        key = _date_key(by_borough[borough]["sale_date"], dates[identifier], identifier)
        queues[borough].append((key, identifier))
    for borough in queues:
        queues[borough].sort()
    return [
        (borough, linked_url(identifier), identifier)
        for borough, (_, identifier) in _round_robin(queues)
    ]


def _private_assessment(
    selected: list[dict], responses: dict, intents: list[dict]
) -> dict:
    """Keep source ambiguities in private evidence, never public aggregates."""
    all_master = {key[1]: row for key, row in responses.items() if key[0] == "master"}
    attempted_master = {
        identifier
        for intent in intents
        if intent.get("phase") == "master"
        for identifier in _requested_ids(intent["url"])
    }
    assessment = {}
    for item in selected:
        borough = item["borough"]
        candidate_ids = sorted(
            {row["document_id"] for row in responses.get(("bbl", borough), [])}
        )
        primary = [
            identifier
            for identifier in candidate_ids
            if identifier in all_master
            and str(all_master[identifier].get("doc_type", "")).strip().upper()
            in PRIMARY
        ]
        context = [
            identifier
            for identifier in candidate_ids
            if identifier in all_master and identifier not in primary
        ]
        flags = []
        if len(primary) > 1:
            flags.append("multiple_deed_candidates")
        for identifier in primary:
            master = all_master[identifier]
            if str(master.get("percent_trans", "")).strip() not in ("", "100"):
                flags.append("partial_interest")
            linked = responses.get(("linked", identifier), [])
            if not linked:
                flags.append("linked_legals_unresolved")
                continue
            lots = {
                (str(row.get("borough")), str(row.get("block")), str(row.get("lot")))
                for row in linked
            }
            if len(lots) > 1:
                flags.append("multiple_lots")
            units = {str(row.get("unit", "")).strip() for row in linked}
            if "" in units:
                flags.append("blank_or_missing_unit")
            if len(units) > 1:
                flags.append("conflicting_units")
            if any(
                str(row.get("partial_lot", "")).strip() not in ("", "0", "N")
                for row in linked
            ):
                flags.append("partial_lot")
        assessment[str(borough)] = {
            "candidate_ids": candidate_ids,
            "primary_inspection_ids": primary,
            "unresolved_context_ids": context,
            "not_inspected_budget_ids": [
                identifier
                for identifier in candidate_ids
                if identifier not in attempted_master
            ],
            "attempted_master_unresolved_ids": [
                identifier
                for identifier in candidate_ids
                if identifier in attempted_master and identifier not in all_master
            ],
            "linked_uninspected_ids": [
                identifier
                for identifier in primary
                if ("linked", identifier) not in responses
            ],
            "flags": sorted(set(flags)),
            "disposition": "needs_manual_review"
            if not primary
            else "provisional_primary_queue",
        }
    return assessment


def _read_intent(
    run_dir: Path, intent: dict, phase: str, expected_url: str, requested: object
) -> tuple[list[dict], bool, bool]:
    if intent.get("phase") != phase or intent.get("url") != expected_url:
        raise ValueError("Private evidence query sequence differs from protocol")
    result = intent.get("result")
    if result == "pending":
        return [], False, True
    if result not in (
        "body",
        "http_error",
        "timeout",
        "network_error",
        "io_error",
        "validation_error",
    ):
        raise ValueError("Private evidence intent result is invalid")
    filename = intent.get("body_file")
    if filename is None:
        if result == "body":
            raise ValueError("Private evidence missing response body")
        if intent.get("reason") not in (result, "http_error_body_unavailable"):
            raise ValueError("Private evidence no-body reason differs")
        return [], False, True
    if not isinstance(filename, str) or not _INTENT_FILE.fullmatch(filename):
        raise ValueError("Private evidence response filename is invalid")
    body_path = run_dir / filename
    if (
        body_path.is_symlink()
        or not body_path.is_file()
        or body_path.stat().st_size > MAX_RESPONSE_BYTES + 1
    ):
        raise ValueError("Private evidence response body cap or path invalid")
    body = v1._private_file(body_path, run_dir)
    if sha256(body).hexdigest() != intent.get("body_sha256"):
        raise ValueError("Private evidence response hash mismatch")
    if result != "body":
        if intent.get("reason") != result:
            raise ValueError("Private evidence transport reason differs")
        return [], False, True
    if len(body) > MAX_RESPONSE_BYTES:
        if intent.get("reason") != "response_truncated":
            raise ValueError("Private evidence truncation reason differs")
        return [], False, True
    try:
        rows, saturated = _parse(body, phase, requested)
    except ValueError:
        if intent.get("reason") != "schema_error":
            raise ValueError("Private evidence schema reason differs") from None
        return [], False, True
    expected_reason = (
        ("saturated_document" if phase == "linked" else f"saturated_{phase}")
        if saturated
        else "ok"
    )
    if intent.get("reason") != expected_reason:
        raise ValueError("Private evidence response reason differs")
    return rows, saturated, False


def _derive(
    state: dict, selected: list[dict], run_dir: Path
) -> tuple[dict, dict, list[tuple[str, int, str, object]]]:
    if state.get("protocol") != PROTOCOL or state.get("selected") != selected:
        raise ValueError("Private evidence protocol or selected rows differ")
    intents = state.get("intents")
    if not isinstance(intents, list) or len(intents) > MAX_REQUESTS:
        raise ValueError("Private evidence intent ledger is invalid")
    responses: dict = {}
    pending: list[tuple[str, int, str, object]] = []
    cursor = 0
    failed = any(item["status"] != "ready" for item in selected)
    saturated = False
    unfinished = False
    unknown = False
    completed_bbls = set()
    for phase in ("bbl", "master", "linked"):
        plan = _request_plan(selected, phase, responses)
        quota = PHASE_LIMITS[phase]
        for borough, url, requested in plan[:quota]:
            if cursor < len(intents):
                intent = intents[cursor]
                if intent.get("sequence") != cursor + 1:
                    raise ValueError("Private evidence intent sequence is invalid")
                rows, is_saturated, is_failed = _read_intent(
                    run_dir, intent, phase, url, requested
                )
                cursor += 1
                saturated |= is_saturated
                failed |= is_failed
                if phase == "bbl" and not is_failed:
                    completed_bbls.add(borough)
                if intent.get("result") == "pending":
                    unknown = True
                if phase == "bbl" and not is_failed and not is_saturated:
                    responses[(phase, borough)] = rows
                elif phase == "master" and not is_failed and not is_saturated:
                    responses.update({(phase, row["document_id"]): row for row in rows})
                elif phase == "linked" and not is_failed and not is_saturated:
                    responses[(phase, requested)] = rows
            else:
                pending.append((phase, borough, url, requested))
        if len(plan) > quota:
            unfinished = True
        if unknown:
            break
    if cursor != len(intents):
        raise ValueError("Private evidence has excess or out-of-order intents")
    four_bbl = all(
        item["status"] == "ready" for item in selected
    ) and completed_bbls == {1, 2, 3, 4}
    incomplete = failed or unknown or bool(pending)
    status = (
        "INCOMPLETE_ERROR"
        if incomplete
        else "PARTIAL_BUDGET"
        if unfinished
        else "COMPLETE_ROUTE_ONLY"
    )
    triage_finished = status == "COMPLETE_ROUTE_ONLY" and not saturated and not pending
    # Other codes are context, never evidence of a negative sale match.
    context_uninspected = any(
        str(row.get("doc_type", "")).strip().upper() not in PRIMARY
        for key, row in responses.items()
        if key[0] == "master"
    )
    triage_finished = triage_finished and not context_uninspected
    aggregate = {
        "protocol": PROTOCOL,
        "status": status,
        "http_requests": len(intents),
        "four_bbl_queries_finished": four_bbl,
        "document_triage_finished": triage_finished,
        "manual_review_pending": True,
        "manual_reviews_completed": 0,
        "sale_labels_certified": 0,
        "snapshot_sha256": v1.SNAPSHOT_SHA256,
        "ledger_sha256": v1.LEDGER_SHA256,
        "code_table_sha256": CODE_TABLE_SHA256,
        "query_sha256": sha256(
            "|".join(sha256(x["url"].encode()).hexdigest() for x in intents).encode()
        ).hexdigest(),
    }
    return aggregate, responses, pending


def _record_request(
    state: dict,
    run_dir: Path,
    client: BoundedClient,
    phase: str,
    url: str,
    requested: object,
) -> None:
    sequence = len(state["intents"]) + 1
    intent = {"sequence": sequence, "phase": phase, "url": url, "result": "pending"}
    state["intents"] = [*state["intents"], intent]
    _atomic_json(run_dir / "state.json", state)
    try:
        body = client.get(url)
    except HTTPError as error:
        try:
            body = error.read(MAX_RESPONSE_BYTES + 1)
            if not isinstance(body, bytes):
                raise ValueError("HTTP error body is invalid")
            body = body[: MAX_RESPONSE_BYTES + 1]
            reason = "http_error"
        except Exception:
            body = None
            reason = "http_error_body_unavailable"
        outcome = "http_error"
    except (TimeoutError, URLError, OSError, ValueError) as error:
        body = None
        outcome = _status_for(error)
        reason = outcome
    else:
        outcome = "body"
        if len(body) > MAX_RESPONSE_BYTES:
            reason = "response_truncated"
        else:
            try:
                _, saturated = _parse(body, phase, requested)
            except ValueError:
                reason = "schema_error"
            else:
                reason = (
                    (
                        "saturated_document"
                        if phase == "linked"
                        else f"saturated_{phase}"
                    )
                    if saturated
                    else "ok"
                )
    if body is not None:
        name = f"response-{sequence:03d}.bin"
        _atomic_body(run_dir / name, body)
        intent = {**intent, "body_file": name, "body_sha256": sha256(body).hexdigest()}
    intent = {**intent, "result": outcome, "reason": reason}
    state["intents"] = [*state["intents"][:-1], intent]
    _atomic_json(run_dir / "state.json", state)


def run_pilot(
    snapshot: Path,
    ledger: Path,
    code_table: Path,
    run_dir: Path,
    *,
    opener=_http_get,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    selected, code_hash = _verify_inputs(snapshot, ledger, code_table)
    root = profile._private_root()
    run_dir = Path(run_dir).absolute()
    if run_dir.is_symlink() or run_dir.parent.resolve(strict=True) != root:
        raise ValueError("Pilot output must be inside private raw data")
    state_path = run_dir / "state.json"
    if run_dir.exists():
        if not run_dir.is_dir() or not state_path.is_file() or state_path.is_symlink():
            raise ValueError("Existing pilot lacks private state")
        _verify_directory_acl(run_dir)
        state = json.loads(v1._private_file(state_path, run_dir))
        if state.get("code_table_sha256") != code_hash:
            raise ValueError("Existing pilot code table hash differs")
        aggregate, responses, _ = _derive(state, selected, run_dir)
        if ("aggregate" in state and state["aggregate"] != aggregate) or (
            "private_assessment" in state
            and state["private_assessment"]
            != _private_assessment(selected, responses, state["intents"])
        ):
            raise ValueError("Private evidence summary differs from saved responses")
        return aggregate
    run_dir.mkdir(mode=0o700)
    _secure_directory(run_dir)
    state = {
        "protocol": PROTOCOL,
        "selected": selected,
        "code_table_sha256": code_hash,
        "intents": [],
    }
    _atomic_json(state_path, state)
    client = BoundedClient(opener, clock, sleep)
    for phase in ("bbl", "master", "linked"):
        _, _, pending = _derive(state, selected, run_dir)
        for planned_phase, _, url, requested in pending:
            if planned_phase != phase:
                continue
            if len(state["intents"]) >= MAX_REQUESTS:
                break
            _record_request(state, run_dir, client, phase, url, requested)
    aggregate, responses, _ = _derive(state, selected, run_dir)
    state["aggregate"] = aggregate
    state["private_assessment"] = _private_assessment(
        selected, responses, state["intents"]
    )
    _atomic_json(state_path, state)
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--code-table", required=True, type=Path)
    parser.add_argument("--private-run-dir", required=True, type=Path)
    args = parser.parse_args()
    result = run_pilot(
        args.snapshot, args.ledger, args.code_table, args.private_run_dir
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "COMPLETE_ROUTE_ONLY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
