from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import struct
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.compare_hcpa_parcel_releases import compare_releases, main


FIELDS = (("FOLIO", "C", 10, 0), ("PIN", "C", 12, 0), ("JUST", "N", 8, 0))


def _dbf(rows: list[tuple[str, str, str]]) -> bytes:
    record_length = 1 + sum(field[2] for field in FIELDS)
    header_length = 32 + 32 * len(FIELDS) + 1
    header = bytearray(32)
    header[0] = 3
    header[4:8] = struct.pack("<I", len(rows))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)
    descriptors = bytearray()
    for name, field_type, width, decimals in FIELDS:
        descriptor = bytearray(32)
        encoded = name.encode("ascii")
        descriptor[: len(encoded)] = encoded
        descriptor[11] = ord(field_type)
        descriptor[16] = width
        descriptor[17] = decimals
        descriptors.extend(descriptor)
    records = b"".join(
        b" "
        + folio.encode().ljust(10)
        + pin.encode().ljust(12)
        + just.encode().rjust(8)
        for folio, pin, just in rows
    )
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def _archive(
    path: Path, rows: list[tuple[str, str, str]], member="dailyparcels.dbf"
) -> str:
    with ZipFile(path, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr(member, _dbf(rows))
        zipped.writestr("dailyparcels.shp", b"fixed-geometry")
        zipped.writestr("dailyparcels.shx", b"fixed-index")
    return sha256(path.read_bytes()).hexdigest()


def test_compare_counts_changes_without_disclosing_values(tmp_path: Path) -> None:
    old = tmp_path / "old.zip"
    new = tmp_path / "new.zip"
    old_hash = _archive(old, [("1", "A", "100"), ("2", "B", "200")])
    new_hash = _archive(new, [("1", "A", "125"), ("2", "B", "200")])

    result = compare_releases(old, old_hash, new, new_hash)

    assert result["records"] == 2
    assert result["changed_records"] == 1
    assert result["unchanged_records"] == 1
    assert result["field_change_counts"] == {"JUST": 1}
    rendered = str(result)
    assert "125" not in rendered and "FOLIO" not in result["field_change_counts"]


def test_compare_rejects_hash_mismatch_before_parsing(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    digest = _archive(archive, [("SECRET", "A", "100")], member="wrong.dbf")

    with pytest.raises(ValueError, match="hash mismatch") as caught:
        compare_releases(archive, "0" * 64, archive, digest)

    assert "SECRET" not in str(caught.value)


def test_compare_counts_key_change_when_geometry_is_identical(tmp_path: Path) -> None:
    old = tmp_path / "old.zip"
    new = tmp_path / "new.zip"
    old_hash = _archive(old, [("1", "A", "100")])
    new_hash = _archive(new, [("1", "B", "100")])

    result = compare_releases(old, old_hash, new, new_hash)

    assert result["field_change_counts"] == {"PIN": 1}


def test_compare_rejects_duplicate_member(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("dailyparcels.dbf", _dbf([("1", "A", "100")]))
        zipped.writestr("dailyparcels.dbf", _dbf([("1", "A", "100")]))
        zipped.writestr("dailyparcels.shp", b"fixed-geometry")
        zipped.writestr("dailyparcels.shx", b"fixed-index")
    digest = sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="exactly one"):
        compare_releases(archive, digest, archive, digest)


def test_cli_writes_aggregate_json(tmp_path: Path, monkeypatch, capsys) -> None:
    archive = tmp_path / "same.zip"
    digest = _archive(archive, [("1", "A", "100")])
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "compare",
            "--old",
            str(archive),
            "--old-sha256",
            digest,
            "--new",
            str(archive),
            "--new-sha256",
            digest,
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    assert '"changed_records": 0' in output.read_text(encoding="utf-8")
    assert capsys.readouterr().out == output.read_text(encoding="utf-8")


def test_cli_refuses_to_overwrite_source_archive(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "same.zip"
    digest = _archive(archive, [("1", "A", "100")])
    original = archive.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        [
            "compare",
            "--old",
            str(archive),
            "--old-sha256",
            digest,
            "--new",
            str(archive),
            "--new-sha256",
            digest,
            "--output",
            str(archive),
        ],
    )

    with pytest.raises(ValueError, match="must not replace"):
        main()
    assert archive.read_bytes() == original


def test_compare_rejects_schema_drift(tmp_path: Path) -> None:
    old = tmp_path / "old.zip"
    new = tmp_path / "new.zip"
    old_hash = _archive(old, [("1", "A", "100")])
    with ZipFile(new, "w", ZIP_DEFLATED) as zipped:
        changed = bytearray(_dbf([("1", "A", "100")]))
        changed[32 + 16] = 9
        zipped.writestr("dailyparcels.dbf", bytes(changed))
        zipped.writestr("dailyparcels.shp", b"fixed-geometry")
        zipped.writestr("dailyparcels.shx", b"fixed-index")
    new_hash = sha256(new.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="record width disagrees"):
        compare_releases(old, old_hash, new, new_hash)


def test_compare_rejects_duplicate_field_names(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate-field.zip"
    changed = bytearray(_dbf([("1", "A", "100")]))
    changed[64:75] = b"FOLIO\0\0\0\0\0\0"
    with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("dailyparcels.dbf", bytes(changed))
        zipped.writestr("dailyparcels.shp", b"fixed-geometry")
        zipped.writestr("dailyparcels.shx", b"fixed-index")
    digest = sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="field definition"):
        compare_releases(archive, digest, archive, digest)


def test_compare_rejects_changed_geometry(tmp_path: Path) -> None:
    old = tmp_path / "old.zip"
    new = tmp_path / "new.zip"
    old_hash = _archive(old, [("1", "A", "100")])
    with ZipFile(new, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("dailyparcels.dbf", _dbf([("1", "A", "100")]))
        zipped.writestr("dailyparcels.shp", b"changed-geometry")
        zipped.writestr("dailyparcels.shx", b"fixed-index")
    new_hash = sha256(new.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="geometry changed"):
        compare_releases(old, old_hash, new, new_hash)
