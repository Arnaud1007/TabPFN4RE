"""Exact HCPA instrument grouping for source audit, without transaction claims.

The SQLite spool and row-level sample flags stay under ignored data/raw/hcpa.
The aggregate JSON contains counts only and is safe for the tracked run record.
"""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from time import monotonic
from zipfile import ZipFile

from sample_hcpa_audit import (
    EXPECTED_ARCHIVE_SHA256,
    EXPECTED_MEMBER_BYTES,
    MAX_ARCHIVE_BYTES,
    PRIVATE_ROOT,
    _archive_hash,
    _read_dbf_header,
    _value,
)


EXPECTED_SAMPLE_SHA256 = (
    "2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9"
)
MAX_SAMPLE_BYTES = 10_000_000
MAX_SPOOL_BYTES = 2_000_000_000
MIN_FREE_DISK_BYTES = 3_000_000_000
MAX_RUNTIME_SECONDS = 3_600
BATCH_SIZE = 5_000
SAMPLE_FIELDS = ("DOC_NUM", "PIN", "FOLIO", "S_DATE", "S_AMT", "QU")
SIGNAL_NAMES = (
    "same_valid_amount",
    "has_repeated_valid_amount",
    "conflicting_amount",
    "invalid_amount",
    "different_known_parcel",
    "unknown_parcel",
    "conflicting_date",
    "mixed_qualification",
)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_private(path: Path) -> None:
    root = PRIVATE_ROOT.resolve(strict=True)
    if PRIVATE_ROOT.is_symlink() or os.path.normcase(
        str(PRIVATE_ROOT.absolute())
    ) != os.path.normcase(str(root)):
        raise ValueError("Private HCPA root redirects to another path")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Row-level input or output must remain private")
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError("Private row-level file must not be a hard link")


def _load_sample(
    sample: Path, expected_sha256: str, expected_rows: int
) -> dict[int, dict[str, object]]:
    if sample.stat().st_size > MAX_SAMPLE_BYTES:
        raise ValueError("Sample exceeds the private-audit size cap")
    if _hash_file(sample) != expected_sha256:
        raise ValueError("Sample checksum differs from the frozen sample")
    rows: dict[int, dict[str, object]] = {}
    for line in sample.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            ordinal = item["record_ordinal"]
            if (
                not isinstance(item, dict)
                or type(ordinal) is not int
                or ordinal < 1
                or ordinal in rows
                or any(not isinstance(item[name], str) for name in SAMPLE_FIELDS)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed or duplicate private sample row") from exc
        rows[ordinal] = item
    if len(rows) != expected_rows:
        raise ValueError("Private sample row count differs from the audit contract")
    return rows


def _check_budget(spool: Path, deadline: float) -> None:
    if monotonic() > deadline:
        raise TimeoutError("Document-group audit exceeded its execution-time cap")
    if spool.exists() and spool.stat().st_size > MAX_SPOOL_BYTES:
        raise ValueError("Private SQLite spool exceeded its size cap")


def _configure_spool_limit(connection: sqlite3.Connection) -> None:
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if page_size < 512 or page_size > 65_536 or page_size & (page_size - 1):
        raise ValueError("Unexpected SQLite page size for private spool")
    page_cap = MAX_SPOOL_BYTES // page_size
    if page_cap < 1:
        raise ValueError("Private SQLite spool size cap is too small")
    connection.execute(f"PRAGMA max_page_count={page_cap}")
    applied = connection.execute("PRAGMA max_page_count").fetchone()[0]
    if applied != page_cap:
        raise ValueError("Private SQLite spool page cap was not applied")


def _source_rows(
    archive: Path,
    expected_member_bytes: int,
    sample_rows: dict[int, dict[str, object]],
    connection: sqlite3.Connection,
    spool: Path,
    deadline: float,
) -> tuple[int, int, int, int, int, str]:
    active = deleted = blank = nonblank = 0
    batch: list[tuple[str, str, int, str, str, str, str]] = []
    seen_sample: set[int] = set()
    with ZipFile(archive) as zipped:
        info = zipped.getinfo("allsales.dbf")
        if (
            info.file_size != expected_member_bytes
            or info.compress_size <= 0
            or info.file_size / info.compress_size > 20
        ):
            raise ValueError("DBF member size or compression ratio is unexpected")
        with zipped.open(info) as source:
            count, row_length, fields = _read_dbf_header(source, info.file_size)
            for ordinal in range(1, count + 1):
                if ordinal % BATCH_SIZE == 0:
                    _check_budget(spool, deadline)
                record = source.read(row_length)
                if len(record) != row_length:
                    raise ValueError("DBF ends before its header record count")
                if record[:1] == b"*":
                    deleted += 1
                    continue
                if record[:1] != b" ":
                    raise ValueError("Unexpected DBF record marker")
                active += 1
                if ordinal in sample_rows:
                    item = sample_rows[ordinal]
                    if any(
                        item[name] != _value(record, fields[name])
                        for name in SAMPLE_FIELDS
                    ):
                        raise ValueError(
                            "Sample row differs from the pinned DBF source"
                        )
                    seen_sample.add(ordinal)
                doc = _value(record, fields["DOC_NUM"])
                if not doc:
                    blank += 1
                    continue
                nonblank += 1
                batch.append(
                    (
                        doc,
                        _amount_key(_value(record, fields["S_AMT"])),
                        ordinal,
                        _value(record, fields["PIN"]),
                        _value(record, fields["FOLIO"]),
                        _value(record, fields["S_DATE"]),
                        _value(record, fields["QU"]),
                    )
                )
                if len(batch) >= BATCH_SIZE:
                    connection.executemany(
                        "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?)", batch
                    )
                    connection.commit()
                    batch.clear()
                    _check_budget(spool, deadline)
            if source.read(2) != b"\x1a":
                raise ValueError("Expected DBF end-of-file marker")
    if seen_sample != sample_rows.keys():
        raise ValueError("Sample ordinal is deleted or outside the pinned DBF source")
    if batch:
        connection.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        connection.commit()
        _check_budget(spool, deadline)
    return count, active, deleted, blank, nonblank, f"{info.CRC:08x}"


def _amount(raw: str) -> Decimal | None:
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _amount_key(raw: str) -> str:
    """Canonical exact Decimal equality key without context-dependent rounding."""
    amount = _amount(raw)
    if amount is None:
        return ""
    if amount.is_zero():
        return "0"
    sign, digits, exponent = amount.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return f"{sign}:{''.join(str(digit) for digit in digits)}:{exponent}"


def _size_bucket(size: int) -> str:
    if size <= 20:
        return str(size)
    for limit, label in ((50, "21-50"), (100, "51-100")):
        if size <= limit:
            return label
    return "101+"


class _GroupAccumulator:
    """Fixed-memory group state; only sampled ordinals are retained."""

    def __init__(self) -> None:
        self.size = 0
        self.sample_ordinals: list[int] = []
        self.first_amount_key: str | None = None
        self.last_amount_key: str | None = None
        self.first_pin: str | None = None
        self.first_folio: str | None = None
        self.first_date: str | None = None
        self.first_qu: str | None = None
        self.invalid_amount = False
        self.unknown_parcel = False
        self.amount_conflict = False
        self.repeated_amount = False
        self.pin_conflict = False
        self.folio_conflict = False
        self.date_conflict = False
        self.qu_conflict = False

    def add(
        self,
        ordinal: int,
        amount_key: str,
        pin: str,
        folio: str,
        date: str,
        qu: str,
        sample_rows: dict[int, dict[str, object]],
    ) -> None:
        self.size += 1
        if ordinal in sample_rows:
            self.sample_ordinals.append(ordinal)
        if not amount_key:
            self.invalid_amount = True
        elif self.first_amount_key is None:
            self.first_amount_key = amount_key
        elif amount_key != self.first_amount_key:
            self.amount_conflict = True
        if amount_key and amount_key == self.last_amount_key:
            self.repeated_amount = True
        self.last_amount_key = amount_key
        if not pin or not folio:
            self.unknown_parcel = True
        if pin:
            if self.first_pin is None:
                self.first_pin = pin
            elif pin != self.first_pin:
                self.pin_conflict = True
        if folio:
            if self.first_folio is None:
                self.first_folio = folio
            elif folio != self.first_folio:
                self.folio_conflict = True
        if date:
            if self.first_date is None:
                self.first_date = date
            elif date != self.first_date:
                self.date_conflict = True
        if qu:
            if self.first_qu is None:
                self.first_qu = qu
            elif qu != self.first_qu:
                self.qu_conflict = True

    def summary(self) -> dict[str, object]:
        return {
            "group_size": self.size,
            "same_valid_amount": not self.invalid_amount and not self.amount_conflict,
            "has_repeated_valid_amount": self.repeated_amount,
            "conflicting_amount": self.amount_conflict,
            "invalid_amount": self.invalid_amount,
            "different_known_parcel": self.pin_conflict or self.folio_conflict,
            "unknown_parcel": self.unknown_parcel,
            "conflicting_date": self.date_conflict,
            "mixed_qualification": self.qu_conflict,
        }


def _summarize_spool(
    connection: sqlite3.Connection,
    spool: Path,
    sample_rows: dict[int, dict[str, object]],
    blank_rows: int,
    deadline: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    groups = singletons = repeated = repeated_rows = maximum = 0
    sizes: Counter[str] = Counter()
    signals: Counter[str] = Counter()
    sample_flags: dict[int, dict[str, object]] = {}
    current_document: str | None = None
    current = _GroupAccumulator()

    def finish() -> None:
        nonlocal groups, singletons, repeated, repeated_rows, maximum
        if not current.size:
            return
        result = current.summary()
        size = current.size
        groups += 1
        maximum = max(maximum, size)
        if size == 1:
            singletons += 1
        else:
            repeated += 1
            repeated_rows += size
            sizes[_size_bucket(size)] += 1
            for name, value in result.items():
                if name != "group_size" and value:
                    signals[name] += 1
        for ordinal in current.sample_ordinals:
            sample_flags[ordinal] = {"record_ordinal": ordinal, **result}

    query = (
        "SELECT document, amount_key, ordinal, pin, folio, sale_date, qualification "
        "FROM sales ORDER BY document, amount_key, ordinal"
    )
    if any(
        "USE TEMP B-TREE" in detail.upper()
        for _, _, _, detail in connection.execute("EXPLAIN QUERY PLAN " + query)
    ):
        raise ValueError("Document-group query requires an unbounded temporary sort")
    cursor = connection.execute(query)
    for i, (document, amount_key, ordinal, pin, folio, date, qu) in enumerate(
        cursor, 1
    ):
        if document != current_document:
            finish()
            current = _GroupAccumulator()
            current_document = document
        current.add(ordinal, amount_key, pin, folio, date, qu, sample_rows)
        if i % BATCH_SIZE == 0:
            _check_budget(spool, deadline)
    finish()
    blank_sample = singleton_sample = repeated_sample = 0
    sample_sizes: Counter[str] = Counter()
    sample_signals: Counter[str] = Counter()
    for ordinal, item in sample_rows.items():
        if item["DOC_NUM"].strip():
            if ordinal not in sample_flags:
                raise ValueError("Nonblank sample document missing from group index")
            flag = sample_flags[ordinal]
            size = flag["group_size"]
            sample_sizes[_size_bucket(size)] += 1
            if size == 1:
                singleton_sample += 1
            else:
                repeated_sample += 1
                for name, value in flag.items():
                    if name not in ("record_ordinal", "group_size") and value:
                        sample_signals[name] += 1
        else:
            blank_sample += 1
            sample_flags[ordinal] = {"record_ordinal": ordinal, "group_size": 0}
            sample_sizes["blank"] += 1
    summary: dict[str, object] = {
        "document_groups": groups,
        "singleton_groups": singletons,
        "repeated_groups": repeated,
        "rows_in_repeated_groups": repeated_rows,
        "max_group_size": maximum,
        "repeated_group_size_histogram": dict(sorted(sizes.items())),
        "repeated_group_signals": {name: signals[name] for name in SIGNAL_NAMES},
        "sample_rows": len(sample_rows),
        "sample_blank_document_rows": blank_sample,
        "sample_singleton_document_rows": singleton_sample,
        "sample_repeated_document_rows": repeated_sample,
        "sample_repeated_document_signals": {
            name: sample_signals[name] for name in SIGNAL_NAMES
        },
        "sample_group_size_histogram": dict(sorted(sample_sizes.items())),
    }
    if groups != singletons + repeated or blank_rows < blank_sample:
        raise ValueError("Document-group counts do not reconcile")
    return summary, [sample_flags[ordinal] for ordinal in sorted(sample_flags)]


def _install_outputs(
    flags: Path, aggregate: Path, private_bytes: bytes, public_bytes: bytes
) -> None:
    staged: list[Path] = []
    installed: list[Path] = []
    try:
        for destination, content in ((flags, private_bytes), (aggregate, public_bytes)):
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".hcpa-document-groups-", delete=False
            ) as stream:
                staged.append(Path(stream.name))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, destination in zip(staged, (flags, aggregate)):
            os.link(temporary, destination)
            installed.append(destination)
    except BaseException:
        for destination in installed:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)


def profile_document_groups(
    archive: Path,
    sample: Path,
    private_flags: Path,
    aggregate: Path,
    *,
    expected_archive_sha256: str = EXPECTED_ARCHIVE_SHA256,
    expected_member_bytes: int = EXPECTED_MEMBER_BYTES,
    expected_sample_sha256: str = EXPECTED_SAMPLE_SHA256,
    expected_sample_rows: int = 200,
) -> dict[str, object]:
    """Write private per-sample flags and aggregate instrument-linkage counts."""
    archive, sample = Path(archive), Path(sample)
    private_flags, aggregate = Path(private_flags), Path(aggregate)
    for path in (archive, sample, private_flags):
        _check_private(path)
    if (
        len(
            {
                archive.resolve(),
                sample.resolve(),
                private_flags.resolve(),
                aggregate.resolve(),
            }
        )
        != 4
    ):
        raise ValueError("Source and output paths must differ")
    if not private_flags.parent.is_dir() or not aggregate.parent.is_dir():
        raise ValueError("Output parent directory must exist")
    if private_flags.exists() or aggregate.exists():
        raise FileExistsError("Audit output exists; refusing overwrite")
    if shutil.disk_usage(PRIVATE_ROOT).free < MIN_FREE_DISK_BYTES:
        raise ValueError("Insufficient free disk for private SQLite spool")
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the source-audit size cap")
    source_sha = _archive_hash(archive)
    if source_sha != expected_archive_sha256:
        raise ValueError("Archive checksum differs from the audited source")
    sample_rows = _load_sample(sample, expected_sample_sha256, expected_sample_rows)
    deadline = monotonic() + MAX_RUNTIME_SECONDS
    with tempfile.NamedTemporaryFile(
        dir=PRIVATE_ROOT,
        prefix=".hcpa-document-groups-spool-",
        suffix=".sqlite",
        delete=False,
    ) as stream:
        spool = Path(stream.name)
    try:
        with closing(sqlite3.connect(spool)) as connection:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA cache_size=-65536")
            _configure_spool_limit(connection)
            connection.execute(
                "CREATE TABLE sales (document TEXT NOT NULL, amount_key TEXT NOT NULL, "
                "ordinal INTEGER NOT NULL, pin TEXT, folio TEXT, sale_date TEXT, "
                "qualification TEXT, PRIMARY KEY (document, amount_key, ordinal)) "
                "WITHOUT ROWID"
            )
            count, active, deleted, blank, nonblank, crc = _source_rows(
                archive, expected_member_bytes, sample_rows, connection, spool, deadline
            )
            summary, flags = _summarize_spool(
                connection, spool, sample_rows, blank, deadline
            )
        if summary["singleton_groups"] + summary["rows_in_repeated_groups"] != nonblank:
            raise ValueError("Document-group row counts do not reconcile")
        result: dict[str, object] = {
            "source_archive_sha256": source_sha,
            "sample_sha256": expected_sample_sha256,
            "member": "allsales.dbf",
            "member_crc32": crc,
            "member_uncompressed_bytes": expected_member_bytes,
            "header_record_count": count,
            "active_rows": active,
            "deleted_rows": deleted,
            "blank_document_rows": blank,
            "nonblank_document_rows": nonblank,
            **summary,
            "interpretation": (
                "Exact trimmed document-number linkage candidates only; repeated "
                "identifiers or amounts do not prove duplicate economic transfers. "
                "Sample is edge-enriched and not a prevalence estimate."
            ),
        }
        if count != active + deleted or active != blank + nonblank:
            raise ValueError("Source-row counts do not reconcile")
        private_bytes = "".join(
            json.dumps(flag, sort_keys=True) + "\n" for flag in flags
        ).encode("utf-8")
        public_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        _install_outputs(private_flags, aggregate, private_bytes, public_bytes)
        return result
    finally:
        spool.unlink(missing_ok=True)


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) != 4:
        raise SystemExit(
            "Usage: profile_hcpa_document_groups.py ARCHIVE.zip "
            "PRIVATE_SAMPLE.jsonl PRIVATE_FLAGS.jsonl AGGREGATE.json"
        )
    result = profile_document_groups(*(Path(argument) for argument in args))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
