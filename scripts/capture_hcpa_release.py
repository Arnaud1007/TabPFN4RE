"""Capture exact current HCPA ZIP bytes for prospective source evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from time import monotonic
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
    build_opener,
)

from scripts.private_review_io import (
    advisory_lock,
    new_file,
    real_directory,
    secure_directory,
    verify_acl,
)
from scripts.hcpa_release_observation_ledger import append_observation


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://downloads.hcpafl.org/Default.aspx"
PRIVATE_ROOT = ROOT / "data/raw/hcpa/prospective-releases"
MAX_HTML_BYTES = 256 * 1024
MAX_ZIP_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
TIMEOUT_SECONDS = 60
CAPTURE_LIMIT_SECONDS = 600
FILE_NAMES = {
    "allsales": re.compile(r"allsales_\d{2}_\d{2}_\d{4}\.zip\Z"),
    "parcels": re.compile(r"parcels_\d{2}_\d{2}_\d{4}\.zip\Z"),
}
POSTBACK = re.compile(
    r"javascript:__doPostBack\('(?P<target>grdFiles\$ctl00\$ctl\d{2}\$ctl00)',''\)\Z"
)
HIDDEN = {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"}
ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}
DISPOSITION = re.compile(
    r'attachment;\s*filename=(?:"([A-Za-z0-9_.]+)"|([A-Za-z0-9_.]+))\Z',
    re.IGNORECASE,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("HCPA download redirected")


class _Form(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms = 0
        self.tables = 0
        self.form_open = False
        self.table_open = False
        self.anchor_open = False
        self.anchor_href = ""
        self.anchor_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.hidden: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "form1":
            if (
                values.get("method", "").lower() != "post"
                or values.get("action") != "./Default.aspx"
            ):
                raise ValueError("HCPA download form action changed")
            self.forms += 1
            self.form_open = True
        elif self.form_open and tag == "input" and values.get("name") in HIDDEN:
            name = values["name"]
            if name in self.hidden or not values.get("value"):
                raise ValueError("HCPA form hidden field is missing or duplicated")
            self.hidden[name] = values["value"]
        elif self.form_open and tag == "table" and values.get("id") == "grdFiles_ctl00":
            self.tables += 1
            self.table_open = True
        elif self.table_open and tag == "a":
            if self.anchor_open:
                raise ValueError("HCPA listing has nested links")
            self.anchor_open = True
            self.anchor_href = values.get("href") or ""
            self.anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self.anchor_open:
            self.anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_open:
            if not self.table_open or not self.form_open:
                raise ValueError("HCPA filename link left the file table")
            self.links.append(("".join(self.anchor_parts).strip(), self.anchor_href))
            self.anchor_open = False
        elif tag == "table" and self.table_open:
            if self.anchor_open:
                raise ValueError("HCPA file table closed inside a link")
            self.table_open = False
        elif tag == "form" and self.form_open:
            if self.table_open or self.anchor_open:
                raise ValueError("HCPA form closed inside the file table")
            self.form_open = False


def _validate_request(family: str, expected_filename: str) -> None:
    if (
        family not in FILE_NAMES
        or FILE_NAMES[family].fullmatch(expected_filename) is None
    ):
        raise ValueError("Invalid HCPA release family or filename")


def parse_form(raw: bytes, family: str, expected_filename: str) -> dict[str, object]:
    """Bind an exact listed filename to its own ASP.NET postback target."""
    _validate_request(family, expected_filename)
    if not 0 < len(raw) <= MAX_HTML_BYTES:
        raise ValueError("HCPA listing size is invalid")
    try:
        parser = _Form()
        parser.feed(raw.decode("utf-8"))
        parser.close()
    except UnicodeError as error:
        raise ValueError("HCPA listing is not UTF-8") from error
    if parser.forms != 1 or parser.tables != 1 or parser.form_open or parser.table_open:
        raise ValueError("HCPA download form or file table is invalid")
    if set(parser.hidden) != HIDDEN:
        raise ValueError("HCPA download form hidden fields changed")
    matches = [href for name, href in parser.links if name == expected_filename]
    if len(matches) != 1:
        raise ValueError("Expected HCPA ZIP is missing or duplicated")
    target_match = POSTBACK.fullmatch(matches[0])
    if target_match is None:
        raise ValueError("HCPA ZIP postback is invalid")
    return {
        "url": SOURCE_URL,
        "fields": {
            "__EVENTTARGET": target_match["target"],
            "__EVENTARGUMENT": "",
            **parser.hidden,
        },
    }


def _response_ok(response, content_types: set[str], max_bytes: int) -> int | None:
    if response.geturl() != SOURCE_URL or response.status != 200:
        raise ValueError("HCPA response redirected or failed")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if content_type not in content_types:
        raise ValueError("HCPA response content type changed")
    length = response.headers.get("Content-Length")
    if length is None:
        return None
    if not length.isdecimal() or not 0 < int(length) <= max_bytes:
        raise ValueError("HCPA response length is invalid")
    return int(length)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def prepare_private_root() -> None:
    """Create the ignored raw-data chain securely on a fresh clone."""
    for directory in (ROOT / "data/raw", ROOT / "data/raw/hcpa", PRIVATE_ROOT):
        if directory.is_symlink():
            raise ValueError("HCPA private directory redirects")
        if not directory.exists():
            directory.mkdir(mode=0o700)
            secure_directory(directory)
        real_directory(directory, directory.parent)
    verify_acl(PRIVATE_ROOT)


def _resume_pending_registrations() -> None:
    pending_manifests: list[tuple[datetime, Path]] = []
    for pending in PRIVATE_ROOT.glob("hcpa-*/.ledger_pending"):
        manifest_path = pending.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        completed = datetime.fromisoformat(
            manifest["capture_completed_at_utc"].replace("Z", "+00:00")
        )
        pending_manifests.append((completed, pending))
    for _completed, pending in sorted(pending_manifests, key=lambda item: item[0]):
        append_observation(
            PRIVATE_ROOT / "observations.jsonl",
            pending.parent / "manifest.json",
            PRIVATE_ROOT,
        )
        pending.unlink()


def _capture_session_lock():
    """Use an OS-owned lock that is released automatically after termination."""
    return advisory_lock(PRIVATE_ROOT / "capture-session.lock", PRIVATE_ROOT)


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


def _capture_locked(
    run_dir: Path,
    family: str,
    expected_filename: str,
    *,
    opener,
    clock,
    register_ledger: bool = False,
) -> dict[str, object]:
    """Save one immutable private ZIP and manifest, leaving failures incomplete."""
    _validate_request(family, expected_filename)
    run_dir = Path(run_dir)
    if run_dir.parent != PRIVATE_ROOT or run_dir.is_symlink():
        raise ValueError("Capture path must be a new private run directory")
    if run_dir.exists():
        raise FileExistsError("HCPA capture run directory already exists")
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    started = clock()
    code_commit, dirty_tree = _code_state()
    deadline = monotonic() + CAPTURE_LIMIT_SECONDS
    with opener(SOURCE_URL, timeout=TIMEOUT_SECONDS) as listing:
        listed_length = _response_ok(listing, {"text/html"}, MAX_HTML_BYTES)
        html = listing.read(MAX_HTML_BYTES + 1)
        if listed_length is not None and len(html) != listed_length:
            raise ValueError("HCPA listing length changed during retrieval")
    form = parse_form(html, family, expected_filename)
    request = Request(
        form["url"],
        data=urlencode(form["fields"]).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    run_dir.mkdir(mode=0o700)
    secure_directory(run_dir)
    verify_acl(run_dir)
    new_file(run_dir / ".incomplete", b"capture_incomplete\n")
    new_file(run_dir / "listing.html", html)
    partial = run_dir / f"{expected_filename}.part"
    digest = sha256()
    total = 0
    with opener(request, timeout=TIMEOUT_SECONDS) as response:
        expected_length = _response_ok(response, ZIP_TYPES, MAX_ZIP_BYTES)
        disposition = response.headers.get("Content-Disposition", "")
        match = DISPOSITION.fullmatch(disposition)
        if match is None or (match[1] or match[2]) != expected_filename:
            raise ValueError("HCPA response filename differs from listed release")
        with partial.open("xb") as output:
            while chunk := response.read(CHUNK_BYTES):
                if monotonic() > deadline:
                    raise TimeoutError("HCPA capture exceeded total time budget")
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise ValueError("HCPA ZIP exceeds capture byte cap")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
    if expected_length is not None and total != expected_length:
        raise ValueError("HCPA ZIP length changed during retrieval")
    with partial.open("rb") as stream:
        if stream.read(4) != b"PK\x03\x04":
            raise ValueError("HCPA response is not a ZIP")
    if monotonic() > deadline:
        raise TimeoutError("HCPA capture exceeded total time budget")
    completed = clock()
    if completed < started:
        raise ValueError("Capture clock moved backward")
    os.replace(partial, run_dir / expected_filename)
    result: dict[str, object] = {
        "status": "observed_not_qualified",
        "source_url": SOURCE_URL,
        "family": family,
        "filename": expected_filename,
        "capture_started_at_utc": _timestamp(started),
        "capture_completed_at_utc": _timestamp(completed),
        "raw_zip_bytes": total,
        "raw_zip_sha256": digest.hexdigest(),
        "listing_html_sha256": sha256(html).hexdigest(),
        "code_commit": code_commit,
        "dirty_tree_at_capture": dirty_tree,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "response_filename_verified": True,
        "zip_structure_validated": False,
        "first_public_availability_verified": False,
        "certified_sale_labels": 0,
        "g_us_gate": "PENDING",
    }
    new_file(
        run_dir / "manifest.json",
        (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(),
    )
    incomplete = run_dir / ".incomplete"
    pending = run_dir / ".ledger_pending"
    if register_ledger:
        os.replace(incomplete, pending)
        append_observation(
            PRIVATE_ROOT / "observations.jsonl",
            run_dir / "manifest.json",
            PRIVATE_ROOT,
        )
        pending.unlink()
    else:
        incomplete.unlink()
    return result


def capture(
    run_dir: Path,
    family: str,
    expected_filename: str,
    *,
    opener,
    clock,
    register_ledger: bool = False,
) -> dict[str, object]:
    """Serialize capture through registration and resume earlier pending work."""
    with _capture_session_lock():
        _resume_pending_registrations()
        return _capture_locked(
            run_dir,
            family,
            expected_filename,
            opener=opener,
            clock=clock,
            register_ledger=register_ledger,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", choices=sorted(FILE_NAMES))
    parser.add_argument("expected_filename")
    args = parser.parse_args()
    _validate_request(args.family, args.expected_filename)
    prepare_private_root()
    opener = build_opener(HTTPCookieProcessor(CookieJar()), _NoRedirect()).open
    run_id = f"hcpa-{args.family}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    result = capture(
        PRIVATE_ROOT / run_id,
        args.family,
        args.expected_filename,
        opener=opener,
        clock=lambda: datetime.now(UTC),
        register_ledger=True,
    )
    print(
        json.dumps(
            {**result, "private_run_dir": str(PRIVATE_ROOT / run_id)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
