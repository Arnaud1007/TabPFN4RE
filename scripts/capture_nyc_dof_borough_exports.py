"""Capture five official NYC borough XLSX responses as private source evidence.

The downloaded bytes remain unqualified inventory. This program never opens
workbook cells or treats a captured ZIP as a historically available sale row.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from typing import Callable, Iterator
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from uuid import uuid4
from zipfile import BadZipFile, LargeZipFile, ZipFile

from audit_nyc_acris_matches_v2 import _secure_directory, _verify_directory_acl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "data" / "raw" / "nyc_dof"
PROTOCOL = "nyc-official-borough-xlsx-v1"
SOURCE_PAGE = (
    "https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page"
)
ADVERTISED_PERIOD = "September 2025-August 2026 (unverified at capture)"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BOROUGHS = (
    (
        "Manhattan",
        "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_manhattan.xlsx",
    ),
    (
        "Bronx",
        "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_bronx.xlsx",
    ),
    (
        "Brooklyn",
        "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_brooklyn.xlsx",
    ),
    (
        "Queens",
        "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_queens.xlsx",
    ),
    (
        "Staten Island",
        "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_statenisland.xlsx",
    ),
)
TIMEOUT_SECONDS = 30
MAX_TRANSFER_SECONDS = 240
MAX_TOTAL_SECONDS = 1800
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_BYTES = 80 * 1024 * 1024
MAX_MEMBERS = 256
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_DECODED_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
MAX_INTENT_BYTES = 8 * 1024
MAX_RECEIPT_BYTES = 8 * 1024
Transport = Callable[[str, str, int], object]
Clock = Callable[[], datetime]
Timer = Callable[[], float]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Official workbook redirect rejected")


@contextmanager
def _http_transport(method: str, url: str, timeout: int) -> Iterator[object]:
    request = Request(url, method=method)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        yield response


class BoundedClient:
    def __init__(
        self, transport: Transport = _http_transport, timeout: int = TIMEOUT_SECONDS
    ):
        if type(timeout) is not int or not 1 <= timeout <= TIMEOUT_SECONDS:
            raise ValueError("Official workbook timeout must be 1 to 30 seconds")
        self.transport = transport
        self.timeout = timeout
        self.count = 0

    @contextmanager
    def request(self, method: str, url: str) -> Iterator[object]:
        if self.count >= len(BOROUGHS):
            raise ValueError("Official workbook request cap reached")
        if method != "GET" or url != BOROUGHS[self.count][1]:
            raise ValueError("Only the next fixed official workbook GET is allowed")
        self.count += 1  # An uncertain request outcome still consumes this slot.
        with self.transport(method, url, self.timeout) as response:
            yield response


def _time_utc(clock: Clock) -> str:
    value = clock()
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("Capture clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _check_utc(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT[0-9:.]+Z", value
    ):
        raise ValueError("Capture timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Capture timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("Capture timestamp is invalid")
    return value


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt" and path.exists():
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def _check_ancestors(path: Path) -> None:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if _reparse(candidate):
            raise ValueError("Private path has a symlink or reparse ancestor")


def _run_directory(run_dir: Path, *, new: bool) -> Path:
    candidate = Path(run_dir).absolute()
    _check_ancestors(PRIVATE_ROOT)
    _check_ancestors(candidate)
    match = re.fullmatch(
        r"official-exports-(\d{8}T\d{6}Z)-([0-9a-f]{12})", candidate.name
    )
    if candidate.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Run must be directly inside private NYC data")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Run ID has an invalid UTC date") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC data root is missing")
    if new:
        if candidate.exists() or _reparse(candidate):
            raise FileExistsError("Official workbook run already exists")
    elif not candidate.is_dir():
        raise ValueError("Official workbook run is missing")
    return candidate


def _write_new(path: Path, body: bytes) -> None:
    if path.exists() or _reparse(path):
        raise FileExistsError("Official workbook artifact already exists")
    temporary = path.parent / f".{uuid4().hex}.part"
    try:
        with temporary.open("xb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _filename(borough: str) -> str:
    return borough.lower().replace(" ", "_") + ".xlsx"


def _receipt_name(borough: str) -> str:
    return "receipt-" + borough.lower().replace(" ", "_") + ".json"


def _length(headers: object) -> int | None:
    declared = headers.get("Content-Length")
    if declared is None:
        return None
    if (
        not isinstance(declared, str)
        or not declared.isascii()
        or not declared.isdecimal()
    ):
        raise ValueError("Official workbook Content-Length is invalid")
    value = int(declared)
    if value > MAX_FILE_BYTES:
        raise ValueError("Official workbook exceeds per-file byte cap")
    return value


def _response_metadata(response: object, url: str) -> dict:
    if response.geturl() != url:
        raise ValueError("Official workbook final URL differs from request")
    if type(response.status) is not int or response.status != 200:
        raise ValueError("Official workbook HTTP status was not 200")
    headers = response.headers
    if headers.get("Content-Type") != MIME:
        raise ValueError("Official workbook MIME type is invalid")
    if headers.get("Content-Encoding", "identity") != "identity":
        raise ValueError("Official workbook encoding is not identity")
    return {
        "http_status": 200,
        "content_type": MIME,
        "declared_bytes": _length(headers),
    }


def _check_elapsed(timer: Timer, start: float, limit: int, phase: str) -> None:
    if timer() - start > limit:
        raise TimeoutError(f"Official workbook {phase} exceeded elapsed-time cap")


def _stream_response(
    response: object,
    target: Path,
    *,
    url: str,
    bundle_bytes: int,
    timer: Timer,
    transfer_start: float,
    total_start: float,
) -> tuple[int, str, dict]:
    metadata = _response_metadata(response, url)
    declared = metadata["declared_bytes"]
    if declared is not None and bundle_bytes + declared > MAX_BUNDLE_BYTES:
        raise ValueError("Official workbook bundle exceeds byte cap")
    temporary = target.parent / f".{uuid4().hex}.part"
    count = 0
    digest = sha256()
    try:
        with temporary.open("xb") as output:
            while True:
                _check_elapsed(timer, transfer_start, MAX_TRANSFER_SECONDS, "transfer")
                _check_elapsed(timer, total_start, MAX_TOTAL_SECONDS, "bundle")
                chunk = response.read(min(CHUNK_BYTES, MAX_FILE_BYTES - count + 1))
                _check_elapsed(timer, transfer_start, MAX_TRANSFER_SECONDS, "transfer")
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ValueError("Official workbook response chunk is invalid")
                count += len(chunk)
                if count > MAX_FILE_BYTES or bundle_bytes + count > MAX_BUNDLE_BYTES:
                    raise ValueError("Official workbook exceeds byte cap")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if declared is not None and count != declared:
            raise ValueError(
                "Official workbook Content-Length differs from bytes received"
            )
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return count, digest.hexdigest(), metadata


def _member_name(name: str) -> str:
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or name.startswith("/")
        or ":" in name
        or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))
    ):
        raise ValueError("Official workbook ZIP member path is unsafe")
    return name.rstrip("/")


def _zip_stats(
    path: Path, *, timer: Timer | None = None, total_start: float | None = None
) -> tuple[int, int]:
    def check_time() -> None:
        if timer is not None and total_start is not None:
            _check_elapsed(timer, total_start, MAX_TOTAL_SECONDS, "bundle")

    try:
        check_time()
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not 3 <= len(members) <= MAX_MEMBERS:
                raise ValueError("Official workbook ZIP member count is invalid")
            names = set()
            declared_total = 0
            for member in members:
                normalized = _member_name(member.filename)
                if normalized in names:
                    raise ValueError("Official workbook ZIP member is duplicated")
                names.add(normalized)
                unix_type = (member.external_attr >> 16) & 0o170000
                if member.flag_bits & 1 or unix_type == stat.S_IFLNK:
                    raise ValueError(
                        "Official workbook ZIP member is encrypted or linked"
                    )
                if member.compress_type not in (0, 8):
                    raise ValueError("Official workbook ZIP compression is unsupported")
                if member.file_size > MAX_MEMBER_BYTES:
                    raise ValueError("Official workbook ZIP member exceeds decoded cap")
                declared_total += member.file_size
                if declared_total > MAX_DECODED_BYTES:
                    raise ValueError("Official workbook ZIP exceeds decoded cap")
            required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}
            if not required.issubset(names) or any(
                (
                    member.is_dir()
                    or ((member.external_attr >> 16) & 0o170000) == stat.S_IFDIR
                )
                and member.filename.rstrip("/") in required
                for member in members
            ):
                raise ValueError(
                    "Official workbook ZIP is missing required OOXML parts"
                )
            decoded_total = 0
            for member in members:
                check_time()
                decoded_member = 0
                with archive.open(member) as source:
                    while True:
                        check_time()
                        chunk = source.read(CHUNK_BYTES)
                        check_time()
                        if not chunk:
                            break
                        decoded_member += len(chunk)
                        decoded_total += len(chunk)
                        if (
                            decoded_member > MAX_MEMBER_BYTES
                            or decoded_total > MAX_DECODED_BYTES
                        ):
                            raise ValueError(
                                "Official workbook ZIP exceeds actual decoded cap"
                            )
                if decoded_member != member.file_size:
                    raise ValueError("Official workbook ZIP decoded size differs")
            return len(members), declared_total
    except (BadZipFile, LargeZipFile, EOFError, RuntimeError) as error:
        raise ValueError("Official workbook ZIP is invalid") from error


def _provenance() -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    lock = PROJECT_ROOT / "locks" / "nyc-borough-capture-environment.json"
    return {
        "code_commit": commit,
        "dirty_tree": bool(status.strip()),
        "environment_lock_sha256": _sha(lock.read_bytes()),
    }


def _check_provenance(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("code_commit"), str)
        or re.fullmatch(r"[a-f0-9]{40}", value["code_commit"]) is None
        or type(value.get("dirty_tree")) is not bool
        or not isinstance(value.get("environment_lock_sha256"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["environment_lock_sha256"]) is None
    ):
        raise ValueError("Official workbook provenance is invalid")
    return {
        key: value[key]
        for key in ("code_commit", "dirty_tree", "environment_lock_sha256")
    }


def _report(manifest: dict, manifest_bytes: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": manifest["run_id"],
        "bundle_status": "bytes_captured_content_unqualified",
        "manifest_sha256": _sha(manifest_bytes),
        "files": {
            entry["borough"]: {"sha256": entry["sha256"], "bytes": entry["bytes"]}
            for entry in manifest["files"]
        },
        "limitations": "Same-publisher bytes only; workbook period, rows, rights and first publication unverified",
    }


def capture_bundle(
    run_dir: Path,
    *,
    transport: Transport = _http_transport,
    clock: Clock = lambda: datetime.now(timezone.utc),
    timer: Timer = time.monotonic,
    provenance: dict | None = None,
) -> dict:
    """Make at most five fixed GETs; preserve private intent even after a failure."""
    start_time = _time_utc(clock)
    source = _check_provenance(_provenance() if provenance is None else provenance)
    target_dir = _run_directory(run_dir, new=True)
    target_dir.mkdir(mode=0o700)
    _secure_directory(target_dir)
    _verify_directory_acl(target_dir)
    intent = {
        "protocol": PROTOCOL,
        "run_id": target_dir.name,
        "started_at_utc": start_time,
        "intended_urls": [{"borough": name, "url": url} for name, url in BOROUGHS],
    }
    intent_bytes = _json_bytes(intent)
    _write_new(target_dir / "intent.json", intent_bytes)
    all_start = timer()
    client = BoundedClient(transport)
    files = []
    bundle_bytes = 0
    phase = "before_request"
    try:
        for borough, url in BOROUGHS:
            _check_elapsed(timer, all_start, MAX_TOTAL_SECONDS, "bundle")
            requested_at = _time_utc(clock)
            transfer_start = timer()
            phase = "request"
            with client.request("GET", url) as response:
                filename = _filename(borough)
                destination = target_dir / filename
                if destination.exists() or _reparse(destination):
                    raise FileExistsError("Official workbook already exists")
                count, digest, metadata = _stream_response(
                    response,
                    destination,
                    url=url,
                    bundle_bytes=bundle_bytes,
                    timer=timer,
                    transfer_start=transfer_start,
                    total_start=all_start,
                )
            phase = "zip_validation"
            member_count, decoded_bytes = _zip_stats(
                destination, timer=timer, total_start=all_start
            )
            _check_elapsed(timer, all_start, MAX_TOTAL_SECONDS, "bundle")
            entry = {
                "borough": borough,
                "url": url,
                "filename": filename,
                "requested_at_utc": requested_at,
                "completed_at_utc": _time_utc(clock),
                "bytes": count,
                "sha256": digest,
                "zip_member_count": member_count,
                "zip_declared_decoded_bytes": decoded_bytes,
                **metadata,
            }
            phase = "receipt"
            _write_new(target_dir / _receipt_name(borough), _json_bytes(entry))
            files.append(entry)
            bundle_bytes += count
            phase = "before_request"
        _check_elapsed(timer, all_start, MAX_TOTAL_SECONDS, "bundle")
        phase = "final_manifest"
        manifest = {
            "protocol": PROTOCOL,
            "run_id": target_dir.name,
            "intent_sha256": _sha(intent_bytes),
            "source_page": SOURCE_PAGE,
            "advertised_period": ADVERTISED_PERIOD,
            "bundle_status": "bytes_captured_content_unqualified",
            "captured_at_utc": _time_utc(clock),
            "files": files,
            **source,
        }
        manifest_bytes = _json_bytes(manifest)
        _write_new(target_dir / "manifest.json", manifest_bytes)
        return _report(manifest, manifest_bytes)
    except Exception as error:
        if isinstance(error, TimeoutError):
            error_class = "TimeoutError"
        elif isinstance(error, ValueError):
            error_class = "ValueError"
        elif isinstance(error, OSError):
            error_class = "OSError"
        else:
            error_class = "OtherError"
        failure = {
            "protocol": PROTOCOL,
            "run_id": target_dir.name,
            "run_status": "incomplete",
            "phase": phase,
            "request_ordinal": client.count,
            "error_class": error_class,
        }
        try:
            _write_new(target_dir / "failure.json", _json_bytes(failure))
        except Exception:
            pass  # Keep the original capture failure and immutable intent.
        raise


def _load_json(path: Path, max_bytes: int) -> tuple[dict, bytes]:
    if _reparse(path) or not path.is_file():
        raise ValueError("Official workbook private artifact missing or linked")
    if path.stat().st_nlink != 1 or path.stat().st_size > max_bytes:
        raise ValueError("Official workbook private artifact linked or exceeds cap")
    body = path.read_bytes()
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Official workbook private JSON is invalid") from error
    if not isinstance(value, dict) or _json_bytes(value) != body:
        raise ValueError("Official workbook private JSON is not canonical")
    return value, body


def replay(run_dir: Path) -> dict:
    """Regenerate aggregate evidence from saved bytes without contacting NYC."""
    target_dir = _run_directory(run_dir, new=False)
    _verify_directory_acl(target_dir)
    if (target_dir / "failure.json").exists() or _reparse(target_dir / "failure.json"):
        raise ValueError("Official workbook run has a failure artifact")
    intent, intent_bytes = _load_json(target_dir / "intent.json", MAX_INTENT_BYTES)
    manifest, manifest_bytes = _load_json(
        target_dir / "manifest.json", MAX_MANIFEST_BYTES
    )
    expected_urls = [{"borough": name, "url": url} for name, url in BOROUGHS]
    if (
        intent.get("protocol") != PROTOCOL
        or intent.get("run_id") != target_dir.name
        or intent.get("intended_urls") != expected_urls
        or manifest.get("protocol") != PROTOCOL
        or manifest.get("run_id") != target_dir.name
        or manifest.get("intent_sha256") != _sha(intent_bytes)
        or manifest.get("bundle_status") != "bytes_captured_content_unqualified"
        or manifest.get("source_page") != SOURCE_PAGE
        or manifest.get("advertised_period") != ADVERTISED_PERIOD
    ):
        raise ValueError("Official workbook manifest or intent is incompatible")
    _check_utc(intent.get("started_at_utc"))
    _check_utc(manifest.get("captured_at_utc"))
    _check_provenance(manifest)
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(BOROUGHS):
        raise ValueError("Official workbook manifest does not have five files")
    for (borough, url), entry in zip(BOROUGHS, entries, strict=True):
        receipt, _ = _load_json(target_dir / _receipt_name(borough), MAX_RECEIPT_BYTES)
        if not isinstance(entry, dict) or receipt != entry:
            raise ValueError("Official workbook receipt differs from manifest")
        if (entry.get("borough"), entry.get("url"), entry.get("filename")) != (
            borough,
            url,
            _filename(borough),
        ):
            raise ValueError("Official workbook file identity is invalid")
        _check_utc(entry.get("requested_at_utc"))
        _check_utc(entry.get("completed_at_utc"))
        if entry.get("http_status") != 200 or entry.get("content_type") != MIME:
            raise ValueError("Official workbook response metadata is invalid")
        path = target_dir / _filename(borough)
        if _reparse(path) or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("Official workbook raw artifact missing or linked")
        if path.stat().st_size > MAX_FILE_BYTES or path.stat().st_size != entry.get(
            "bytes"
        ):
            raise ValueError("Official workbook raw byte count differs")
        if entry.get("declared_bytes") not in (None, entry["bytes"]):
            raise ValueError("Official workbook declared byte count differs")
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_BYTES), b""):
                digest.update(chunk)
        if digest.hexdigest() != entry.get("sha256"):
            raise ValueError("Official workbook raw hash differs")
        if _zip_stats(path) != (
            entry.get("zip_member_count"),
            entry.get("zip_declared_decoded_bytes"),
        ):
            raise ValueError("Official workbook ZIP evidence differs")
    return _report(manifest, manifest_bytes)


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "requests": [{"borough": name, "url": url} for name, url in BOROUGHS],
        "request_cap": len(BOROUGHS),
        "private_root": str(PRIVATE_ROOT),
        "max_file_bytes": MAX_FILE_BYTES,
        "max_bundle_bytes": MAX_BUNDLE_BYTES,
        "status": "plan_only_no_network",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("plan")
    for name in ("capture", "replay"):
        command = subcommands.add_parser(name)
        command.add_argument("run_dir", type=Path)
    options = parser.parse_args()
    try:
        if options.command == "plan":
            result = plan()
        elif options.command == "capture":
            result = capture_bundle(options.run_dir)
        else:
            result = replay(options.run_dir)
    except (OSError, ValueError, TimeoutError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Official workbook capture failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
