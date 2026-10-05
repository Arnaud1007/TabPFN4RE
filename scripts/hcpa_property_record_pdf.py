"""Bounded offline extraction for private HCPA property-record evidence.

This module only compares document, parcel, property-class and qualification
identifiers.  It intentionally makes no claim about closing dates, sale-price
scope, historical availability or reuse rights.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import re
import zlib

from scripts.audit_hcpa_pin_crosswalk import transform_pin


_ALLOWED_PIN_PREFIXES = frozenset(("A", "T", "U"))
_STREAM_HEADER = re.compile(
    rb"<<(.*?)>>\s*stream\r?\n", re.DOTALL
)
_DIRECT_LENGTH = re.compile(
    rb"/Length\s+([0-9]+)\b(?!\s+[0-9]+\s+R\b)"
)
_FILTER = re.compile(rb"/Filter\s*/([A-Za-z0-9]+)")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_PDF_BYTES = 10_000_000
_MAX_DECODED_BYTES = 10_000_000
_MAX_STREAMS = 256
_MAX_FIELDS = 10_000
_MAX_STRUCTURE_MARKERS = 1_024


class _MalformedTextStream(ValueError):
    """Signal that every candidate field from one decoded stream is invalid."""


def pin_to_strap(value: object) -> str:
    """Convert one strictly formatted HCPA A/T/U PIN to its 22-byte strap."""
    if not isinstance(value, str) or not value or value[0] not in _ALLOWED_PIN_PREFIXES:
        raise ValueError("PIN must use the exact supported ASCII A/T/U format")
    strap = transform_pin(value)
    if strap is None or len(strap) != 22:
        raise ValueError("PIN must use the exact supported ASCII A/T/U format")
    return strap


def _positive_limit(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _decode_flate(data: bytes, limit: int) -> bytes:
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(data, limit + 1)
        if len(decoded) > limit or decoder.unconsumed_tail:
            raise ValueError("Decoded PDF stream exceeds the configured limit")
        decoded += decoder.flush(limit + 1 - len(decoded))
    except zlib.error as error:
        raise ValueError("PDF contains a corrupt FlateDecode stream") from error
    if len(decoded) > limit or not decoder.eof or decoder.unused_data:
        raise ValueError("PDF FlateDecode stream violates its bounded contract")
    return decoded


def _literal_at(content: bytes, start: int) -> tuple[str, int]:
    result = bytearray()
    depth = 1
    index = start + 1
    while index < len(content):
        byte = content[index]
        if byte == 0x5C:  # backslash
            index += 1
            if index >= len(content):
                raise ValueError("PDF literal string ends with an escape")
            escaped = content[index]
            common = {
                ord("n"): b"\n",
                ord("r"): b"\r",
                ord("t"): b"\t",
                ord("b"): b"\b",
                ord("f"): b"\f",
            }
            if escaped in common:
                result.extend(common[escaped])
            elif escaped in b"()\\":
                result.append(escaped)
            elif escaped in b"\r\n":
                if escaped == 0x0D and index + 1 < len(content) and content[index + 1] == 0x0A:
                    index += 1
            elif 0x30 <= escaped <= 0x37:
                digits = bytes((escaped,))
                while len(digits) < 3 and index + 1 < len(content) and 0x30 <= content[index + 1] <= 0x37:
                    index += 1
                    digits += bytes((content[index],))
                result.append(int(digits, 8))
            else:
                result.append(escaped)
        elif byte == 0x28:
            depth += 1
            result.append(byte)
        elif byte == 0x29:
            depth -= 1
            if depth == 0:
                try:
                    return result.decode("latin-1"), index + 1
                except UnicodeDecodeError as error:  # pragma: no cover - latin-1 is total
                    raise ValueError("PDF literal string cannot be decoded") from error
            result.append(byte)
        else:
            result.append(byte)
        index += 1
    raise ValueError("PDF contains an unterminated literal string")


def _token_at(content: bytes, index: int, token: bytes) -> bool:
    delimiters = b"\x00\t\n\x0c\r ()<>[]{}/%"
    before_ok = index == 0 or content[index - 1] in delimiters
    end = index + len(token)
    after_ok = end == len(content) or content[end] in delimiters
    return before_ok and after_ok


def _find_operator(content: bytes, token: bytes, start: int) -> int:
    """Find a PDF operator while skipping literal strings and comments."""
    index = start
    while index < len(content):
        byte = content[index]
        if byte == 0x28:
            try:
                _, index = _literal_at(content, index)
            except ValueError:
                # Flate streams may contain fonts or other binary programs.
                # An unmatched literal means this stream has no safely
                # extractable page-text operator after this point.
                raise _MalformedTextStream from None
            continue
        if byte == 0x25:
            line_end = content.find(b"\n", index + 1)
            if line_end < 0:
                return -1
            index = line_end + 1
            continue
        if content.startswith(token, index) and _token_at(content, index, token):
            return index
        index += 1
    return -1


def _ordered_tj_literals(content: bytes, max_fields: int) -> list[str]:
    fields: list[str] = []
    cursor = 0
    while cursor < len(content):
        start = _find_operator(content, b"BT", cursor)
        if start < 0:
            break
        object_end = _find_operator(content, b"ET", start + 2)
        if object_end < 0:
            break
        block = content[start + 2 : object_end]
        index = 0
        while index < len(block):
            if block[index] == 0x25:
                carriage_return = block.find(b"\r", index + 1)
                line_feed = block.find(b"\n", index + 1)
                endings = tuple(
                    position for position in (carriage_return, line_feed) if position >= 0
                )
                index = min(endings) + 1 if endings else len(block)
                continue
            if block[index] != 0x28:
                index += 1
                continue
            try:
                value, literal_end = _literal_at(block, index)
            except ValueError:
                raise _MalformedTextStream from None
            operator = literal_end
            while operator < len(block) and block[operator] in b"\x00\t\n\x0c\r ":
                operator += 1
            if block.startswith(b"Tj", operator) and _token_at(
                block, operator, b"Tj"
            ):
                fields.append(value)
                if len(fields) > max_fields:
                    raise ValueError("PDF field count exceeds the safety ceiling")
            index = literal_end
        cursor = object_end + 2
    return fields


def extract_ordered_fields(
    pdf_bytes: bytes,
    *,
    expected_sha256: str,
    max_pdf_bytes: int,
    max_decoded_bytes: int,
) -> tuple[str, ...]:
    """Extract ordered ``Tj`` literal strings from bounded Flate PDF streams."""
    pdf_limit = _positive_limit(max_pdf_bytes, "max_pdf_bytes")
    decoded_limit = _positive_limit(max_decoded_bytes, "max_decoded_bytes")
    if pdf_limit > _MAX_PDF_BYTES:
        raise ValueError("max_pdf_bytes exceeds the parser safety ceiling")
    if decoded_limit > _MAX_DECODED_BYTES:
        raise ValueError("max_decoded_bytes exceeds the parser safety ceiling")
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be 64 lowercase hexadecimal digits")
    if not isinstance(pdf_bytes, bytes) or not 0 < len(pdf_bytes) <= pdf_limit:
        raise ValueError("PDF input is empty, invalid or oversized")
    if sha256(pdf_bytes).hexdigest() != expected_sha256:
        raise ValueError("PDF SHA-256 does not match the registered artifact")
    if not pdf_bytes.startswith(b"%PDF-") or b"/Encrypt" in pdf_bytes:
        raise ValueError("Input is not a supported unencrypted PDF")
    if pdf_bytes.count(b"%%EOF") != 1 or not pdf_bytes.rstrip().endswith(b"%%EOF"):
        raise ValueError("PDF must contain one final EOF marker")
    if (
        pdf_bytes.count(b"<<") > _MAX_STRUCTURE_MARKERS
        or pdf_bytes.count(b"stream") > _MAX_STRUCTURE_MARKERS
    ):
        raise ValueError("PDF structure-marker count exceeds the safety ceiling")

    fields: list[str] = []
    decoded_total = 0
    stream_count = 0
    decoded_stream_count = 0
    for match in _STREAM_HEADER.finditer(pdf_bytes):
        if stream_count >= _MAX_STREAMS:
            raise ValueError("PDF stream count exceeds the safety ceiling")
        stream_count += 1
        dictionary = match.group(1)
        length_match = _DIRECT_LENGTH.search(dictionary)
        filter_match = _FILTER.search(dictionary)
        if length_match is None or filter_match is None:
            raise ValueError("PDF stream lacks a direct length or filter")
        if filter_match.group(1) != b"FlateDecode":
            # Property-record PDFs can contain JPEG/image streams alongside
            # their Flate text stream. Images are never decoded or inspected.
            continue
        length = int(length_match.group(1))
        start = match.end()
        end = start + length
        if length <= 0 or end > len(pdf_bytes):
            raise ValueError("PDF stream length is invalid")
        boundary = pdf_bytes[end:].lstrip(b"\r\n")
        if re.match(rb"endstream(?:\r?\n|\s+endobj\b)", boundary) is None:
            raise ValueError("PDF stream boundary is invalid")
        remaining = decoded_limit - decoded_total
        if remaining <= 0:
            raise ValueError("Decoded PDF streams exceed the configured limit")
        decoded = _decode_flate(pdf_bytes[start:end], remaining)
        decoded_total += len(decoded)
        try:
            stream_fields = _ordered_tj_literals(
                decoded, _MAX_FIELDS - len(fields)
            )
        except _MalformedTextStream:
            continue
        fields.extend(stream_fields)
        decoded_stream_count += 1
    if decoded_stream_count == 0 or not fields:
        raise ValueError("PDF contains no supported text fields")
    return tuple(fields)


def _field_pairs(ordered_fields: Sequence[str]) -> dict[str, str | None]:
    if isinstance(ordered_fields, (str, bytes)) or any(
        not isinstance(item, str) for item in ordered_fields
    ):
        raise ValueError("Ordered PDF fields must be a sequence of strings")
    pairs: dict[str, str | None] = {}
    for index in range(0, len(ordered_fields) - 1, 2):
        label, value = ordered_fields[index], ordered_fields[index + 1]
        pairs[label] = value if label not in pairs else None
    return pairs


def _state(expected: object, actual: str | None) -> str:
    if not isinstance(expected, str) or not expected or actual is None or not actual:
        return "unknown"
    return "match" if expected == actual else "mismatch"


def compare_sample_row(
    row: Mapping[str, object], ordered_fields: Sequence[str]
) -> dict[str, bool | str]:
    """Compare permitted private identifiers without inferring transaction facts."""
    if not isinstance(row, Mapping):
        raise ValueError("Sample row must be a mapping")
    fields = _field_pairs(ordered_fields)
    try:
        expected_strap = pin_to_strap(row.get("PIN"))
    except ValueError:
        expected_strap = ""
    return {
        "privacy_sensitive": True,
        "document_identity": _state(row.get("DOC_NUM"), fields.get("Document Number")),
        "parcel_unit_identity": _state(expected_strap, fields.get("Parcel ID")),
        "property_class": _state(row.get("DOR_CODE"), fields.get("DOR Code")),
        "qualification_code": _state(row.get("QU"), fields.get("Qualification")),
    }
