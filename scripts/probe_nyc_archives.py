"""Bounded, read-only metadata probe for the official NYC rolling-sales archive.

The probe does not request or generate archive CSVs. A visible version is not
evidence that an archived file is downloadable or historically complete.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from audit_nyc_acris_matches_v2 import _secure_directory, _verify_directory_acl


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nyc_dof"
METADATA_URL = "https://data.cityofnewyork.us/api/archival?id=usep-8jbt&version=1"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_VISIBLE_VERSIONS = 13
TIMEOUT_SECONDS = 15
PROTOCOL = "nyc-archive-metadata-v1"
_SAFE_CONTENT_TYPE = re.compile(
    r"application/json(?:;[ ]*charset=[A-Za-z0-9_-]+)?\Z", re.IGNORECASE
)
TransportResponse = tuple[int, bytes] | tuple[int, bytes, dict[str, str]]
Transport = Callable[[str, str, int], TransportResponse]
Clock = Callable[[], datetime]


def metadata_url() -> str:
    return METADATA_URL


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError("Archive metadata redirect rejected")


class HTTPStatusError(ValueError):
    def __init__(self, status: int, content_type: str):
        super().__init__(f"Archive metadata HTTP {status}")
        self.status = status
        self.content_type = content_type


def _http_get(method: str, url: str, timeout: int) -> tuple[int, bytes, dict]:
    request = Request(url, method=method)
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            chunks = []
            total = 0
            while True:
                chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValueError("Archive metadata response exceeds byte cap")
                chunks.append(chunk)
            return (
                response.status,
                b"".join(chunks),
                {"Content-Type": response.headers.get("Content-Type", "")},
            )
    except HTTPError as error:
        content_type = error.headers.get("Content-Type", "") if error.headers else ""
        return error.code, b"", {"Content-Type": content_type}


class BoundedClient:
    def __init__(
        self, transport: Transport = _http_get, timeout: int = TIMEOUT_SECONDS
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 1 <= timeout <= TIMEOUT_SECONDS
        ):
            raise ValueError("Archive metadata timeout must be 1 to 15 seconds")
        self.transport = transport
        self.timeout = timeout
        self.count = 0

    def request(self, method: str, url: str) -> tuple[bytes, str]:
        if method != "GET" or url != METADATA_URL:
            raise ValueError("Only the fixed NYC archive metadata GET is permitted")
        if self.count:
            raise ValueError("Archive metadata request cap reached")
        self.count += 1
        response = self.transport(method, url, self.timeout)
        if not isinstance(response, tuple) or len(response) not in (2, 3):
            raise ValueError("Archive metadata transport response is invalid")
        status, body = response[:2]
        headers = response[2] if len(response) == 3 else {}
        if not isinstance(headers, dict):
            raise ValueError("Archive metadata headers are invalid")
        content_type = headers.get("Content-Type", headers.get("content-type", ""))
        if (
            not isinstance(content_type, str)
            or len(content_type) > 128
            or any(
                ord(character) < 32 or ord(character) > 126
                for character in content_type
            )
        ):
            raise ValueError("Archive metadata content type is invalid")
        if isinstance(status, bool) or not isinstance(status, int):
            raise ValueError("Archive metadata HTTP status is invalid")
        safe_type = (
            content_type
            if content_type
            and (400 <= status <= 599 or _SAFE_CONTENT_TYPE.fullmatch(content_type))
            else "unavailable_or_other"
        )
        if 400 <= status <= 599:
            raise HTTPStatusError(status, safe_type)
        if status != 200:
            raise ValueError("Archive metadata HTTP status was not 200")
        if content_type and safe_type == "unavailable_or_other":
            raise ValueError("Archive metadata response has no JSON content type")
        if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Archive metadata response exceeds byte cap")
        return body, safe_type


def _integer(value: object, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= 2**31 - 1
    ):
        raise ValueError("Archive metadata version is invalid")
    return value


def _created_at(value: object) -> str:
    if not isinstance(value, str) or len(value) > 40 or "T" not in value:
        raise ValueError("Archive metadata createdAt must have a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Archive metadata createdAt is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Archive metadata createdAt must have a timezone")
    if re.fullmatch(r"[0-9T:Z+.-]+", value) is None:
        raise ValueError("Archive metadata createdAt contains invalid characters")
    return value


def extract_metadata(body: bytes) -> dict:
    if not isinstance(body, bytes) or not body or len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Archive metadata body is invalid")
    try:
        document = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Archive metadata JSON is invalid") from error
    if not isinstance(document, list) or len(document) > MAX_VISIBLE_VERSIONS:
        raise ValueError("Archive metadata must be an array of at most 13 entries")
    versions = []
    seen = set()
    for item in document:
        if not isinstance(item, dict):
            raise ValueError("Archive metadata entry must be an object")
        version = _integer(item.get("version"))
        start_version = _integer(item.get("startVersion"), allow_zero=True)
        if version in seen:
            raise ValueError("Archive metadata version is duplicated")
        seen.add(version)
        visible = item.get("visible")
        if not isinstance(visible, bool):
            raise ValueError("Archive metadata visibility is invalid")
        created_at = _created_at(item.get("createdAt"))
        if visible:
            versions.append(
                {
                    "version": version,
                    "start_version": start_version,
                    "created_at": created_at,
                    "visible": visible,
                }
            )
    return {
        "versions": sorted(versions, key=lambda item: item["version"], reverse=True)
    }


def _validated_run_dir(run_dir: Path, *, new: bool) -> Path:
    run_dir = Path(run_dir)
    root = PRIVATE_ROOT.resolve(strict=True)
    if (
        PRIVATE_ROOT.is_symlink()
        or run_dir.is_symlink()
        or run_dir.parent.resolve(strict=True) != root
    ):
        raise ValueError("Archive probe run must be directly inside private NYC data")
    if new and (run_dir.exists() or run_dir.is_symlink()):
        raise FileExistsError("Archive probe run already exists")
    if not new and not run_dir.is_dir():
        raise ValueError("Archive probe run does not exist")
    return run_dir


def _write_new(path: Path, body: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError("Archive probe output already exists")
    temporary = path.parent / f".{uuid4().hex}.part"
    try:
        with temporary.open("xb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _report(body: bytes, manifest: dict) -> dict:
    parsed = extract_metadata(body)
    return {
        "protocol": PROTOCOL,
        "probe_id": "nyc-archive-metadata-" + sha256(body).hexdigest()[:12],
        "metadata_sha256": sha256(body).hexdigest(),
        "metadata_bytes": len(body),
        "http_status": manifest["http_status"],
        "content_type": manifest["content_type"],
        "captured_at_utc": manifest["captured_at_utc"],
        "versions": parsed["versions"],
        "archive_availability": "unverified",
        "certification": "none",
    }


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _capture_time(clock) -> str:
    captured_at = clock()
    if (
        not isinstance(captured_at, datetime)
        or captured_at.tzinfo is None
        or captured_at.utcoffset() is None
    ):
        raise ValueError("Archive probe capture clock must be timezone aware")
    return captured_at.astimezone(timezone.utc).isoformat()


def capture(
    run_dir: Path,
    *,
    transport: Transport = _http_get,
    clock: Clock = lambda: datetime.now(timezone.utc),
    report_path: Path | None = None,
) -> dict:
    run_dir = _validated_run_dir(run_dir, new=True)
    run_dir.mkdir(mode=0o700)
    _secure_directory(run_dir)
    try:
        body, content_type = BoundedClient(transport).request("GET", METADATA_URL)
    except HTTPStatusError as error:
        _write_new(
            run_dir / "manifest.json",
            _json_bytes(
                {
                    "http_status": error.status,
                    "content_type": error.content_type,
                    "captured_at_utc": _capture_time(clock),
                    "run_status": "incomplete_http_error",
                }
            ),
        )
        raise
    manifest = {
        "metadata_sha256": sha256(body).hexdigest(),
        "http_status": 200,
        "content_type": content_type,
        "captured_at_utc": _capture_time(clock),
        "run_status": "metadata_captured",
    }
    _write_new(run_dir / "metadata.bin", body)
    _write_new(run_dir / "manifest.json", _json_bytes(manifest))
    report = _report(body, manifest)
    if report_path is not None:
        _write_new(Path(report_path), _json_bytes(report))
    return report


def replay(run_dir: Path, *, report_path: Path | None = None) -> dict:
    run_dir = _validated_run_dir(run_dir, new=False)
    _verify_directory_acl(run_dir)
    metadata = run_dir / "metadata.bin"
    manifest = run_dir / "manifest.json"
    if any(path.is_symlink() or not path.is_file() for path in (metadata, manifest)):
        raise ValueError("Archive probe private artifacts are missing or linked")
    if metadata.stat().st_size > MAX_RESPONSE_BYTES or manifest.stat().st_size > 4096:
        raise ValueError("Archive probe private artifact exceeds byte cap")
    body = metadata.read_bytes()
    try:
        saved = json.loads(manifest.read_bytes())
        expected = saved["metadata_sha256"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("Archive probe manifest is invalid") from error
    if sha256(body).hexdigest() != expected:
        raise ValueError("Archive probe metadata hash mismatch")
    saved_type = saved.get("content_type")
    if (
        saved.get("run_status") != "metadata_captured"
        or saved.get("http_status") != 200
        or not (
            saved_type == "unavailable_or_other"
            or isinstance(saved_type, str)
            and _SAFE_CONTENT_TYPE.fullmatch(saved_type)
        )
    ):
        raise ValueError("Archive probe manifest status or content type is invalid")
    _created_at(saved.get("captured_at_utc"))
    report = _report(body, saved)
    if report_path is not None:
        _write_new(Path(report_path), _json_bytes(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("plan", help="Print the sole allowed metadata endpoint")
    for name in ("capture", "replay"):
        command = subcommands.add_parser(name)
        command.add_argument("run_dir", type=Path)
        command.add_argument("--report", type=Path)
    options = parser.parse_args()
    try:
        if options.command == "plan":
            result = {"method": "GET", "url": metadata_url(), "request_cap": 1}
        elif options.command == "capture":
            result = capture(options.run_dir, report_path=options.report)
        else:
            result = replay(options.run_dir, report_path=options.report)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Archive probe failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
