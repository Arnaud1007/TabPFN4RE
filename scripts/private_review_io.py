"""Local-only file, lock and ACL primitives for a private review ledger.

Callers validate record semantics. These checks assume trusted same-privilege
processes and do not protect against a malicious concurrent directory swap.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from typing import Iterator, Sequence


def same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.absolute())) == os.path.normcase(str(b.absolute()))


def real_directory(path: Path, parent: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("Private audit directory must be real")
    resolved = path.resolve(strict=True)
    if not same_path(path, resolved) or not resolved.is_relative_to(
        parent.resolve(strict=True)
    ):
        raise ValueError("Private audit directory redirects")


def private_path(path: Path, root: Path, *, must_exist: bool = False) -> Path:
    path = Path(path)
    real_directory(root, root.parent)
    if path.parent != root:
        raise ValueError(
            "Private audit file must be directly inside its approved directory"
        )
    if path.is_symlink() or not same_path(path, path.resolve()):
        raise ValueError("Private audit path redirects")
    if path.exists():
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("Private audit path must be a regular, single-link file")
    elif must_exist:
        raise ValueError("Required private audit file is missing")
    return path


def write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        count = os.write(fd, data[offset:])
        if count <= 0:
            raise OSError("Private audit write made no progress")
        offset += count


def user_sid() -> str:
    try:
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Private ACL user SID unavailable") from error
    fields = next(csv.reader(io.StringIO(result.stdout)), [])
    if len(fields) != 2 or not re.fullmatch(r"S-1-[0-9-]+", fields[1]):
        raise ValueError("Private ACL user SID unavailable")
    return fields[1]


def _powershell_acl(directory: Path, script: str, sid: str) -> dict:
    environment = {
        **os.environ,
        "TABPFN_ACL_DIR": str(directory),
        "TABPFN_OWNER_SID": sid,
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
        raise ValueError("Private review ACL verification failed") from error
    if not isinstance(value, dict):
        raise ValueError("Private review ACL verification failed")
    return value


def _powershell_acl_many(directories: Sequence[Path], sid: str) -> list[object]:
    environment = {
        **os.environ,
        "TABPFN_ACL_DIRS": json.dumps([str(path) for path in directories]),
        "TABPFN_OWNER_SID": sid,
    }
    script = (
        "$ErrorActionPreference='Stop'; "
        "$paths=ConvertFrom-Json -InputObject $env:TABPFN_ACL_DIRS; "
        "$results=New-Object System.Collections.ArrayList; foreach($path in $paths){ $acl=Get-Acl -LiteralPath $path; "
        "$entries=@($acl.Access|ForEach-Object{ $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }); "
        "$allowed=@($env:TABPFN_OWNER_SID,'S-1-5-18','S-1-5-32-544'); "
        "$foreign=@($entries|Where-Object{ $_ -notin $allowed }); "
        "if((-not $acl.AreAccessRulesProtected)-or($entries -notcontains $env:TABPFN_OWNER_SID)-or($foreign.Count -ne 0)){ throw 'ACL verification failed' }; "
        "[void]$results.Add([pscustomobject]@{protected=$acl.AreAccessRulesProtected; entries=[object[]]$entries}) }; "
        "ConvertTo-Json -InputObject ([object[]]$results) -Depth 4 -Compress"
    )
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
        raise ValueError("Private review ACL verification failed") from error
    if isinstance(value, dict) and len(directories) == 1:
        value = [value]
    if not isinstance(value, list):
        raise ValueError("Private review ACL verification failed")
    return value


def verify_acl(directory: Path) -> None:
    verify_acl_many((directory,))


def verify_acl_many(directories: Sequence[Path]) -> None:
    directories = tuple(Path(path) for path in directories)
    if not directories:
        raise ValueError("Private review ACL verification requires a directory")
    if os.name != "nt":
        for directory in directories:
            if directory.stat().st_mode & 0o077:
                raise ValueError("Private review directory permissions are too broad")
        return
    sid = user_sid()
    results = _powershell_acl_many(directories, sid)
    if len(results) != len(directories):
        raise ValueError("Private review ACL verification failed")
    allowed = {sid, "S-1-5-18", "S-1-5-32-544"}
    for verified in results:
        if not isinstance(verified, dict):
            raise ValueError("Private review ACL verification failed")
        entries = verified.get("entries")
        if (
            verified.get("protected") is not True
            or not isinstance(entries, list)
            or not set(entries).issubset(allowed)
            or sid not in entries
        ):
            raise ValueError("Private review ACL verification failed")


def secure_directory(directory: Path) -> None:
    if os.name != "nt":
        verify_acl(directory)
        return
    sid = user_sid()
    script = (
        "$ErrorActionPreference='Stop'; $p=$env:TABPFN_ACL_DIR; "
        "$acl=[System.IO.Directory]::GetAccessControl($p,[System.Security.AccessControl.AccessControlSections]::Access); "
        "$acl.SetAccessRuleProtection($true,$false); "
        "foreach($sidText in @($env:TABPFN_OWNER_SID,'S-1-5-18','S-1-5-32-544')){ "
        "$identity=New-Object System.Security.Principal.SecurityIdentifier($sidText); "
        "$rule=New-Object System.Security.AccessControl.FileSystemAccessRule($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); "
        "$acl.AddAccessRule($rule) }; "
        "[System.IO.Directory]::SetAccessControl($p,$acl); "
        "@{updated=$true}|ConvertTo-Json -Compress"
    )
    _powershell_acl(directory, script, sid)
    verify_acl(directory)


@contextmanager
def exclusive_lock(ledger: Path, root: Path) -> Iterator[None]:
    lock = private_path(ledger.with_name(ledger.name + ".lock"), root)
    try:
        fd = os.open(
            lock,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("Private review ledger lock already exists") from error
    try:
        metadata = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        try:
            write_all(fd, (json.dumps(metadata, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


@contextmanager
def advisory_lock(lock: Path, root: Path) -> Iterator[None]:
    """Hold an OS-owned lock; a leftover lock file does not retain ownership."""
    lock = private_path(lock, root)
    descriptor = os.open(
        lock,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def new_file(path: Path, content: bytes) -> None:
    fd = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600
    )
    try:
        write_all(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_replace(ledger: Path, content: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=ledger.parent, prefix=".nyc-review-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            write_all(stream.fileno(), content)
            os.fsync(stream.fileno())
        os.replace(temporary, ledger)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def summary_target(destination: Path, inputs: tuple[Path, ...]) -> Path:
    destination = Path(destination)
    if (
        not destination.parent.is_dir()
        or destination.is_symlink()
        or destination.exists()
    ):
        raise FileExistsError("Aggregate summary target must be a new regular path")
    if not same_path(destination.parent, destination.parent.resolve()) or any(
        same_path(destination, path) for path in inputs
    ):
        raise ValueError(
            "Aggregate summary target redirects or overlaps private inputs"
        )
    return destination


def write_summary_new(
    destination: Path, result: dict, inputs: tuple[Path, ...]
) -> None:
    destination = summary_target(destination, inputs)
    content = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".nyc-review-summary-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            write_all(stream.fileno(), content)
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
