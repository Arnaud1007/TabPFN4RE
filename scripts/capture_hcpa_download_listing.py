"""Capture one bounded HCPA download listing; never infer sale availability."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import secrets
import subprocess
from urllib.request import HTTPRedirectHandler, build_opener

from scripts.private_review_io import (
    new_file,
    real_directory,
    secure_directory,
    verify_acl,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://downloads.hcpafl.org/Default.aspx"
PRIVATE_ROOT = ROOT / "data/raw/hcpa/listing-captures"
PUBLIC_ROOT = ROOT / "runs"
MAX_HTML_BYTES = 256 * 1024
MAX_OBSERVATION_BYTES = 16 * 1024
TIMEOUT_SECONDS = 20
RUN_ID = re.compile(r"u0-hcpa-listing-\d{8}T\d{6}Z-[0-9a-f]{8}\Z")
NAMES = {
    "allsales": re.compile(r"allsales_\d{2}_\d{2}_\d{4}\.zip\Z"),
    "parcels": re.compile(r"parcels?_\d{2}_\d{2}_\d{4}\.zip\Z"),
}
SIZE = re.compile(r"\d+(?:\.\d+)? (?:KB|MB|GB)\Z")
DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}(?:AM|PM)\Z")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("HCPA listing redirect rejected")


_HTTP_OPENER = build_opener(_NoRedirect)


class _FileRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_count = 0
        self.table_closed = False
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.cells: list[str] = []
        self.parts: list[str] = []
        self.rows: list[tuple[str, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self.in_table:
                raise ValueError("HCPA file table is nested")
            if dict(attrs).get("id") == "grdFiles_ctl00":
                self.table_count += 1
                self.in_table = True
        elif self.in_table and tag == "tr":
            if self.in_row:
                raise ValueError("HCPA listing has a nested row")
            self.in_row = True
            self.cells = []
        elif self.in_row and tag == "td":
            if self.in_cell:
                raise ValueError("HCPA listing has a nested cell")
            self.in_cell = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_cell:
            value = "".join(self.parts).strip()
            if len(value) > 128 or any(ord(char) < 32 for char in value):
                raise ValueError("HCPA listing has an invalid cell")
            self.cells.append(value)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.in_cell:
                raise ValueError("HCPA listing has an unclosed cell")
            self.rows.append(tuple(self.cells))
            self.in_row = False
        elif tag == "table" and self.in_table:
            if self.in_row or self.in_cell:
                raise ValueError("HCPA file table has an unclosed row")
            self.in_table = False
            self.table_closed = True


def parse_listing(raw: bytes) -> dict[str, dict[str, str]]:
    """Return the two observed filename families from the expected table."""
    if not 0 < len(raw) <= MAX_HTML_BYTES:
        raise ValueError("HCPA listing has invalid byte size")
    try:
        parser = _FileRows()
        parser.feed(raw.decode("utf-8"))
        parser.close()
    except UnicodeError as error:
        raise ValueError("HCPA listing is not UTF-8") from error
    if parser.table_count != 1 or not parser.table_closed:
        raise ValueError("HCPA file table is missing or duplicated")
    found: dict[str, dict[str, str]] = {}
    for cells in parser.rows:
        if not cells or not cells[0].startswith(("allsales_", "parcel_", "parcels_")):
            continue
        family = "allsales" if cells[0].startswith("allsales_") else "parcels"
        if len(cells) != 3 or not NAMES[family].fullmatch(cells[0]):
            raise ValueError("HCPA listing row has invalid filename or columns")
        if (
            family in found
            or not SIZE.fullmatch(cells[1])
            or not DATE.fullmatch(cells[2])
        ):
            raise ValueError("HCPA listing row is duplicated or malformed")
        try:
            datetime.strptime(cells[2], "%m/%d/%Y %I:%M%p")
        except ValueError as error:
            raise ValueError("HCPA listing has invalid displayed date") from error
        found[family] = {
            "filename": cells[0],
            "displayed_size": cells[1],
            "displayed_last_updated": cells[2],
        }
    if set(found) != set(NAMES):
        raise ValueError("HCPA listing is missing a required file family")
    return found


def fetch_listing(opener=None) -> bytes:
    """Fetch the fixed source URL with redirect, type and byte limits."""
    selected_opener = opener or _HTTP_OPENER.open
    with selected_opener(SOURCE_URL, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != SOURCE_URL or getattr(response, "status", None) != 200:
            raise ValueError("HCPA listing source or HTTP status changed")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type != "text/html":
            raise ValueError("HCPA listing is not HTML")
        length = response.headers.get("Content-Length")
        if length is not None and (
            not length.isdecimal() or int(length) > MAX_HTML_BYTES
        ):
            raise ValueError("HCPA listing Content-Length is invalid")
        raw = response.read(MAX_HTML_BYTES + 1)
    if not 0 < len(raw) <= MAX_HTML_BYTES:
        raise ValueError("HCPA listing exceeds byte limit or is empty")
    if length is not None and int(length) != len(raw):
        raise ValueError("HCPA listing byte count differs from Content-Length")
    return raw


def _stamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _real_root(path: Path, *, private: bool, create: bool = False) -> Path:
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("Capture directory redirects through a symlink")
    if private and create and not path.exists():
        path.mkdir(mode=0o700)
        secure_directory(path)
    real_directory(path, path.parent)
    if private:
        verify_acl(path)
    return path


def _code_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return commit, bool(status)


def save_capture(
    raw: bytes, run_id: str, started_at: datetime, completed_at: datetime
) -> dict[str, object]:
    """Publish one immutable aggregate manifest backed by private exact bytes."""
    if RUN_ID.fullmatch(run_id) is None:
        raise ValueError("Invalid HCPA listing run ID")
    started, completed = _stamp(started_at), _stamp(completed_at)
    if started_at > completed_at or completed_at > datetime.now(UTC) + timedelta(
        minutes=5
    ):
        raise ValueError("HCPA listing capture clock is inconsistent")
    listings = parse_listing(raw)
    commit, dirty = _code_state()
    public_root = _real_root(PUBLIC_ROOT, private=False)
    private_root = _real_root(PRIVATE_ROOT, private=True, create=True)
    run_dir = public_root / run_id
    run_dir.mkdir()
    new_file(run_dir / ".incomplete", b"capture_incomplete\n")
    raw_path = private_root / f"{run_id}.html"
    new_file(raw_path, raw)
    observation: dict[str, object] = {
        "run_id": run_id,
        "status": "observed_not_qualified",
        "source_url": SOURCE_URL,
        "capture_started_at_utc": started,
        "capture_completed_at_utc": completed,
        "raw_html_private_path": str(
            Path("data/raw/hcpa/listing-captures") / raw_path.name
        ),
        "raw_html_bytes": len(raw),
        "raw_html_sha256": sha256(raw).hexdigest(),
        "observed_listings": listings,
        "code_commit": commit,
        "dirty_tree_at_capture": dirty,
        "first_public_availability_verified": False,
        "certified_sale_labels": 0,
        "g_us_gate": "PENDING",
    }
    payload = (json.dumps(observation, indent=2, sort_keys=True) + "\n").encode()
    new_file(
        private_root / f"{run_id}.manifest.sha256",
        (sha256(payload).hexdigest() + "\n").encode(),
    )
    new_file(run_dir / "observation.json", payload)
    (run_dir / ".incomplete").unlink()
    return observation


def verify_capture(path: Path) -> dict[str, object]:
    """Replay a committed observation against its unchanged private HTML."""
    public_root = _real_root(PUBLIC_ROOT, private=False)
    private_root = _real_root(PRIVATE_ROOT, private=True)
    if (
        RUN_ID.fullmatch(path.parent.name) is None
        or path.name != "observation.json"
        or path.parent.parent != public_root
        or path.parent.is_symlink()
        or not path.parent.is_dir()
        or (path.parent / ".incomplete").exists()
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_nlink != 1
        or not 0 < path.stat().st_size <= MAX_OBSERVATION_BYTES
    ):
        raise ValueError("HCPA observation path or size is invalid")
    real_directory(path.parent, public_root)
    with path.open("rb") as stream:
        payload = stream.read(MAX_OBSERVATION_BYTES + 1)
    try:
        record = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("HCPA observation is invalid JSON") from error
    run_id = path.parent.name
    if not isinstance(record, dict) or set(record) != {
        "run_id",
        "status",
        "source_url",
        "capture_started_at_utc",
        "capture_completed_at_utc",
        "raw_html_private_path",
        "raw_html_bytes",
        "raw_html_sha256",
        "observed_listings",
        "code_commit",
        "dirty_tree_at_capture",
        "first_public_availability_verified",
        "certified_sale_labels",
        "g_us_gate",
    }:
        raise ValueError("HCPA observation schema changed")
    if (
        record["run_id"] != run_id
        or record["source_url"] != SOURCE_URL
        or record["status"] != "observed_not_qualified"
        or record["first_public_availability_verified"] is not False
        or record["certified_sale_labels"] != 0
        or record["g_us_gate"] != "PENDING"
        or record["raw_html_private_path"]
        != str(Path("data/raw/hcpa/listing-captures") / f"{run_id}.html")
        or not isinstance(record["code_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", record["code_commit"]) is None
        or type(record["dirty_tree_at_capture"]) is not bool
        or type(record["raw_html_bytes"]) is not int
        or not isinstance(record["raw_html_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", record["raw_html_sha256"]) is None
    ):
        raise ValueError("HCPA observation identity changed")
    try:
        started = datetime.fromisoformat(
            record["capture_started_at_utc"].replace("Z", "+00:00")
        )
        completed = datetime.fromisoformat(
            record["capture_completed_at_utc"].replace("Z", "+00:00")
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("HCPA observation timestamp is invalid") from error
    if (
        _stamp(started) != record["capture_started_at_utc"]
        or _stamp(completed) != record["capture_completed_at_utc"]
        or started > completed
        or completed > datetime.now(UTC) + timedelta(minutes=5)
    ):
        raise ValueError("HCPA observation timestamp order changed")
    digest_path = private_root / f"{run_id}.manifest.sha256"
    if (
        digest_path.is_symlink()
        or not digest_path.is_file()
        or digest_path.stat().st_nlink != 1
        or digest_path.stat().st_size != 65
    ):
        raise ValueError("HCPA private manifest digest is missing")
    with digest_path.open("rb") as stream:
        saved_digest = stream.read(66)
    if saved_digest != (sha256(payload).hexdigest() + "\n").encode():
        raise ValueError("HCPA observation manifest hash changed")
    raw_path = private_root / f"{run_id}.html"
    if raw_path.is_symlink() or not raw_path.is_file() or raw_path.stat().st_nlink != 1:
        raise ValueError("HCPA private HTML is missing or redirected")
    with raw_path.open("rb") as stream:
        raw = stream.read(MAX_HTML_BYTES + 1)
    if len(raw) != record.get("raw_html_bytes") or sha256(
        raw
    ).hexdigest() != record.get("raw_html_sha256"):
        raise ValueError("HCPA private HTML size or hash changed")
    if parse_listing(raw) != record.get("observed_listings"):
        raise ValueError("HCPA listing interpretation changed")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-run-id")
    args = parser.parse_args()
    if args.verify_run_id is not None:
        result = verify_capture(PUBLIC_ROOT / args.verify_run_id / "observation.json")
    else:
        started = datetime.now(UTC)
        raw = fetch_listing()
        completed = datetime.now(UTC)
        run_id = f"u0-hcpa-listing-{completed.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        result = save_capture(raw, run_id, started, completed)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
