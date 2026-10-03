"""Synthetic tests for a private, bounded Cook County source-audit capture."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_cook_sales_audit as capture  # noqa: E402


class FakeResponse(BytesIO):
    def __init__(self, body: bytes, url: str, *, actual_url: str | None = None):
        super().__init__(body)
        self.url = url if actual_url is None else actual_url
        self.status = 200
        self.headers = {"Content-Type": "application/json", "ETag": '"fixture"'}

    def geturl(self) -> str:
        return self.url


class FakeOpener:
    def __init__(self, *, count: int = 40):
        self.count = count
        self.calls: list[str] = []
        self.metadata_version_after: int | None = None
        self.count_after: int | None = None
        self.duplicate_ids = False
        self.extra_field = False
        self.invalid_date = False
        self.invalid_trailing_date = False
        self.invalid_time = False
        self.short_page = False
        self.redirect = False
        self.metadata_calls = 0
        self.count_calls = 0

    def __call__(self, url: str, *, timeout: int):
        self.calls.append(url)
        self.testcase_timeout(timeout)
        parsed = urlsplit(url)
        if url == capture.METADATA_URL:
            self.metadata_calls += 1
            version = (
                self.metadata_version_after
                if self.metadata_calls > 1 and self.metadata_version_after is not None
                else 42
            )
            body = json.dumps(
                {
                    "id": "wvhk-k5uv",
                    "rowsUpdatedAt": version,
                    "viewLastModified": 7,
                    "columns": [
                        {"fieldName": field} for field in capture.REQUIRED_SOURCE_FIELDS
                    ],
                }
            ).encode()
            return FakeResponse(body, url)
        query = parse_qs(parsed.query)
        if parsed.path != "/resource/wvhk-k5uv.json":
            raise AssertionError(f"Unexpected path: {parsed.path}")
        if query.get("$select") == ["count(*) AS n"]:
            self.count_calls += 1
            n = (
                self.count_after
                if self.count_calls > len(capture.CELLS)
                and self.count_after is not None
                else self.count
            )
            return FakeResponse(json.dumps([{"n": str(n)}]).encode(), url)
        assert query["$select"] == [",".join(capture.SELECT_FIELDS)]
        assert query["$order"] == ["row_id ASC"]
        assert "buyer_name" not in query["$select"][0]
        assert "seller_name" not in query["$select"][0]
        cell = next(
            cell
            for cell in capture.CELLS
            if query["$where"] == [capture.cell_where(cell)]
        )
        offset = int(query["$offset"][0])
        date = cell.start_date
        price = max(1, cell.min_price or 1)
        records = []
        for index in range(10 if not self.short_page else 9):
            row_id = "shared" if self.duplicate_ids else f"{cell.slug}-{offset + index}"
            records.append(
                {
                    "row_id": row_id,
                    "pin": "00000000000001",
                    "sale_date": (
                        "1999-01-01T00:00:00"
                        if self.invalid_date
                        else f"{date}T00:00:00garbage"
                        if self.invalid_trailing_date
                        else f"{date}T99:99:99"
                        if self.invalid_time
                        else f"{date}T00:00:00"
                    ),
                    "sale_price": str(price),
                    **({"buyer_name": "Private Person"} if self.extra_field else {}),
                }
            )
        body = json.dumps(records).encode()
        actual_url = url + "/redirect" if self.redirect else url
        return FakeResponse(body, url, actual_url=actual_url)

    @staticmethod
    def testcase_timeout(timeout: int) -> None:
        if timeout <= 0 or timeout > 60:
            raise AssertionError("Unbounded request timeout")


class CookCaptureTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.private_root = Path(temp.name) / "data" / "raw" / "cook_county"
        root_patch = patch.object(capture, "PRIVATE_ROOT", self.private_root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.now = lambda: datetime(2026, 10, 3, 12, tzinfo=timezone.utc)

    def test_capture_has_exact_quotas_private_bytes_and_aggregate_only_result(self):
        opener = FakeOpener()
        result = capture.capture_sample(opener=opener, now=self.now)
        self.assertEqual(result["sample_rows"], 200)
        self.assertEqual(result["cell_count"], 10)
        self.assertEqual(result["capture_status"], "private_source_audit_only")
        self.assertFalse(result["historical_asof_eligible"])
        self.assertNotIn("00000000000001", json.dumps(result))
        self.assertNotIn("Private Person", json.dumps(result))
        self.assertEqual(opener.metadata_calls, 2)
        self.assertEqual(opener.count_calls, 20)
        completed = list(self.private_root.glob("cook-sales-v1-*"))
        self.assertEqual(len(completed), 1)
        manifest = json.loads((completed[0] / "manifest.json").read_text())
        self.assertEqual(len(manifest["sample_row_ids"]), 200)
        self.assertEqual(len(set(manifest["sample_row_ids"])), 200)
        self.assertEqual(len(list(completed[0].glob("rows-*.json"))), 20)
        self.assertEqual(len(list(completed[0].glob("count-*.json"))), 20)
        self.assertEqual(len(manifest["responses"]), 42)
        self.assertEqual(len(opener.calls), 42)
        self.assertEqual(capture.verify_capture(completed[0])["sample_rows"], 200)

    def test_source_version_change_rejects_completion(self):
        opener = FakeOpener()
        opener.metadata_version_after = 43
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            capture.capture_sample(opener=opener, now=self.now)
        self.assertFalse(list(self.private_root.glob("cook-sales-v1-*")))

    def test_unhashable_metadata_field_has_explicit_error(self):
        data = json.dumps(
            {
                "id": capture.DATASET_ID,
                "rowsUpdatedAt": 42,
                "viewLastModified": 7,
                "columns": [{"fieldName": []}],
            }
        ).encode()
        with self.assertRaisesRegex(ValueError, "invalid column names"):
            capture._metadata(data)

    def test_cell_count_change_rejects_completion(self):
        opener = FakeOpener()
        opener.count_after = 41
        with self.assertRaisesRegex(ValueError, "counts changed"):
            capture.capture_sample(opener=opener, now=self.now)
        self.assertFalse(list(self.private_root.glob("cook-sales-v1-*")))

    def test_insufficient_cell_rejects_before_any_row_request(self):
        opener = FakeOpener(count=19)
        with self.assertRaisesRegex(ValueError, "fewer than 20"):
            capture.capture_sample(opener=opener, now=self.now)
        self.assertEqual(opener.count_calls, 10)
        self.assertEqual(len(opener.calls), 11)

    def test_duplicate_row_id_rejects_completion(self):
        opener = FakeOpener()
        opener.duplicate_ids = True
        with self.assertRaisesRegex(ValueError, "duplicate row_id"):
            capture.capture_sample(opener=opener, now=self.now)
        self.assertFalse(list(self.private_root.glob("cook-sales-v1-*")))

    def test_unrequested_personal_field_rejects_completion(self):
        opener = FakeOpener()
        opener.extra_field = True
        with self.assertRaisesRegex(ValueError, "unrequested field"):
            capture.capture_sample(opener=opener, now=self.now)
        self.assertFalse(list(self.private_root.rglob("rows-*.json")))

    def test_wrong_cell_date_rejects_completion(self):
        opener = FakeOpener()
        opener.invalid_date = True
        with self.assertRaisesRegex(ValueError, "cell membership"):
            capture.capture_sample(opener=opener, now=self.now)

    def test_malformed_trailing_date_rejects_completion(self):
        opener = FakeOpener()
        opener.invalid_trailing_date = True
        with self.assertRaisesRegex(ValueError, "invalid date"):
            capture.capture_sample(opener=opener, now=self.now)

    def test_invalid_time_rejects_completion(self):
        opener = FakeOpener()
        opener.invalid_time = True
        with self.assertRaisesRegex(ValueError, "invalid date"):
            capture.capture_sample(opener=opener, now=self.now)

    def test_short_page_rejects_completion(self):
        opener = FakeOpener()
        opener.short_page = True
        with self.assertRaisesRegex(ValueError, "page length"):
            capture.capture_sample(opener=opener, now=self.now)

    def test_redirect_rejects_completion(self):
        opener = FakeOpener()
        opener.redirect = True
        with self.assertRaisesRegex(ValueError, "redirect"):
            capture.capture_sample(opener=opener, now=self.now)

    def test_tampered_private_response_fails_replay(self):
        completed = capture.capture_sample(opener=FakeOpener(), now=self.now)
        directory = self.private_root / completed["private_directory"]
        row_file = next(directory.glob("rows-*.json"))
        row_file.write_bytes(row_file.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            capture.verify_capture(directory)

    def test_verify_rejects_external_directory(self):
        external = Path(self.private_root.parents[2]) / "external"
        external.mkdir()
        (external / "manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "private root"):
            capture.verify_capture(external)

    def test_verify_rejects_redirected_capture_directory(self):
        completed = capture.capture_sample(opener=FakeOpener(), now=self.now)
        directory = self.private_root / completed["private_directory"]
        outside = Path(self.private_root.parents[2]) / "outside"
        outside.mkdir()
        original_resolve = Path.resolve

        def simulated_junction(path, *args, **kwargs):
            return (
                outside
                if path == directory
                else original_resolve(path, *args, **kwargs)
            )

        with patch.object(Path, "resolve", simulated_junction):
            with self.assertRaisesRegex(ValueError, "private root"):
                capture.verify_capture(directory)

    def test_verify_rejects_symlinked_private_response(self):
        completed = capture.capture_sample(opener=FakeOpener(), now=self.now)
        directory = self.private_root / completed["private_directory"]
        row_file = next(directory.glob("rows-*.json"))
        original_is_symlink = Path.is_symlink

        def simulated_symlink(path):
            return path == row_file or original_is_symlink(path)

        with patch.object(Path, "is_symlink", simulated_symlink):
            with self.assertRaisesRegex(ValueError, "symlink"):
                capture.verify_capture(directory)

    def test_verify_rejects_manifest_missing_response_hash(self):
        completed = capture.capture_sample(opener=FakeOpener(), now=self.now)
        directory = self.private_root / completed["private_directory"]
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["responses"] = [
            entry
            for entry in manifest["responses"]
            if entry["file"] != "rows-old-low-0.json"
        ]
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "response inventory"):
            capture.verify_capture(directory)

    def test_v1_capture_is_single_use(self):
        capture.capture_sample(opener=FakeOpener(), now=self.now)
        with self.assertRaisesRegex(FileExistsError, "v1 capture already exists"):
            capture.capture_sample(opener=FakeOpener(), now=self.now)

    def test_incomplete_capture_requires_review_before_retry(self):
        opener = FakeOpener()
        opener.extra_field = True
        with self.assertRaisesRegex(ValueError, "unrequested field"):
            capture.capture_sample(opener=opener, now=self.now)
        with self.assertRaisesRegex(FileExistsError, "v1 capture already exists"):
            capture.capture_sample(opener=FakeOpener(), now=self.now)


if __name__ == "__main__":
    unittest.main()
