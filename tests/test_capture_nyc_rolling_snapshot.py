"""Synthetic checks for a bounded NYC rolling-sales source capture."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_rolling_snapshot as capture  # noqa: E402


NAMES = ("BOROUGH", "ADDRESS", "SALE PRICE", "SALE DATE")
FIELDS = ("borough", "address", "sale_price", "sale_date")


def _metadata(*, version: int = 42, names=NAMES, fields=FIELDS) -> bytes:
    return json.dumps(
        {
            "id": "usep-8jbt",
            "rowsUpdatedAt": version,
            "viewLastModified": version,
            "columns": [
                {"name": name, "fieldName": field}
                for name, field in zip(names, fields, strict=True)
            ],
        }
    ).encode()


def _csv(*, header=NAMES, rows=(("1", "10 Main St", "100000", "2026-08-01"),)):
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode()


class FakeResponse(BytesIO):
    def __init__(self, body: bytes, url: str, *, content_type: str = "text/csv"):
        super().__init__(body)
        self.url = url
        self.headers = {
            "Content-Type": content_type,
            "ETag": '"test-version"',
            "Last-Modified": "Tue, 15 Sep 2026 15:56:41 GMT",
        }

    def geturl(self) -> str:
        return self.url


class FakeOpener:
    def __init__(
        self,
        csv_body: bytes,
        *,
        before=None,
        after=None,
        csv_url=None,
        count_before=1,
        count_after=None,
    ):
        self.csv_body = csv_body
        self.before = before or _metadata()
        self.after = after or self.before
        self.csv_url = csv_url or capture.CSV_URL
        self.count_before = count_before
        self.count_after = count_before if count_after is None else count_after
        self.calls = []
        self.metadata_calls = 0
        self.count_calls = 0

    def __call__(self, url: str, *, timeout: int):
        self.calls.append((url, timeout))
        if url == capture.METADATA_URL:
            self.metadata_calls += 1
            body = self.before if self.metadata_calls == 1 else self.after
            return FakeResponse(body, url, content_type="application/json")
        if url == capture.COUNT_URL:
            self.count_calls += 1
            count = self.count_before if self.count_calls == 1 else self.count_after
            return FakeResponse(
                json.dumps([{"count": str(count)}]).encode(),
                url,
                content_type="application/json",
            )
        if url == capture.CSV_URL:
            return FakeResponse(self.csv_body, self.csv_url)
        raise AssertionError(f"Unexpected URL: {url}")


class SnapshotCaptureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private_root = Path(self.temp.name) / "data" / "raw" / "nyc_dof"
        self.root_patch = patch.object(capture, "PRIVATE_ROOT", self.private_root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.when = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)

    def test_success_saves_original_bytes_and_aggregate_only_manifest(self):
        body = _csv(
            rows=(
                ("1", "10 Main St", "100000", "2026-08-01"),
                ("1", "20 Side St", "200000", "2026-08-02"),
            )
        )
        opener = FakeOpener(body, count_before=2)
        result = capture.capture_snapshot(opener=opener, now=lambda: self.when)
        csv_files = list(self.private_root.glob("*.csv"))
        self.assertEqual(len(csv_files), 1)
        self.assertEqual(csv_files[0].read_bytes(), body)
        self.assertEqual(result["sha256"], sha256(body).hexdigest())
        self.assertEqual(result["bytes"], len(body))
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["capture_status"], "inventory_only_not_asof_eligible")
        self.assertNotIn("Main St", json.dumps(result))
        self.assertEqual(
            [call[0] for call in opener.calls],
            [
                capture.METADATA_URL,
                capture.COUNT_URL,
                capture.CSV_URL,
                capture.METADATA_URL,
                capture.COUNT_URL,
            ],
        )

    def test_clean_short_csv_without_content_length_is_rejected(self):
        opener = FakeOpener(_csv(), count_before=2)
        with self.assertRaisesRegex(ValueError, "count"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_count_changes_during_capture_is_rejected(self):
        opener = FakeOpener(_csv(), count_before=1, count_after=2)
        with self.assertRaisesRegex(ValueError, "count"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_existing_symlink_ancestor_rejects_before_mkdir(self):
        external = Path(self.temp.name) / "external"
        external.mkdir()
        linked = Path(self.temp.name) / "linked"
        private = linked / "raw" / "nyc_dof"
        original_is_symlink = Path.is_symlink

        def synthetic_link(path):
            return path == linked or original_is_symlink(path)

        with (
            patch.object(capture, "PRIVATE_ROOT", private),
            patch.object(Path, "is_symlink", synthetic_link),
            patch.object(Path, "mkdir", side_effect=AssertionError("mkdir was called")),
        ):
            with self.assertRaisesRegex(ValueError, "redirect"):
                capture.capture_snapshot(
                    opener=FakeOpener(_csv()), now=lambda: self.when
                )
        self.assertFalse((external / "raw").exists())
        self.assertFalse((linked / "raw").exists())

    def test_default_http_opener_refuses_redirect_before_follow(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/sink")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"unwanted")

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/start"
        with self.assertRaisesRegex(ValueError, "redirect"):
            capture._strict_urlopen(url, timeout=2)
        self.assertEqual(seen, ["/start"])

    def test_field_name_header_is_accepted(self):
        result = capture.capture_snapshot(
            opener=FakeOpener(_csv(header=FIELDS)), now=lambda: self.when
        )
        self.assertEqual(result["header_kind"], "fieldName")

    def test_version_change_rejects_and_leaves_no_csv(self):
        opener = FakeOpener(_csv(), after=_metadata(version=43))
        with self.assertRaisesRegex(ValueError, "changed during capture"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_schema_change_rejects(self):
        altered = _metadata(names=("BOROUGH", "ADDRESS", "PRICE", "SALE DATE"))
        with self.assertRaisesRegex(ValueError, "changed during capture"):
            capture.capture_snapshot(
                opener=FakeOpener(_csv(), after=altered), now=lambda: self.when
            )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_wrong_header_rejects_and_cleans_up(self):
        with self.assertRaisesRegex(ValueError, "CSV header"):
            capture.capture_snapshot(
                opener=FakeOpener(
                    _csv(header=("BOROUGH", "ADDRESS", "SALE PRICE", "OTHER"))
                ),
                now=lambda: self.when,
            )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_malformed_row_rejects_and_cleans_up(self):
        body = _csv() + b'1,"unterminated,100000,2026-08-02\r\n'
        with self.assertRaisesRegex(ValueError, "CSV record"):
            capture.capture_snapshot(opener=FakeOpener(body), now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_oversize_stream_rejects_before_publication(self):
        with patch.object(capture, "MAX_CSV_BYTES", 20):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                capture.capture_snapshot(
                    opener=FakeOpener(_csv()), now=lambda: self.when
                )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_row_limit_rejects_before_publication(self):
        with patch.object(capture, "MAX_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "row limit"):
                capture.capture_snapshot(
                    opener=FakeOpener(
                        _csv(
                            rows=(
                                ("1", "a", "1", "2026-08-01"),
                                ("1", "b", "2", "2026-08-02"),
                            )
                        )
                    ),
                    now=lambda: self.when,
                )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_redirected_csv_response_rejects(self):
        opener = FakeOpener(_csv(), csv_url="https://other.example/data.csv")
        with self.assertRaisesRegex(ValueError, "redirect"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_html_response_rejects_without_publication(self):
        original = FakeOpener(_csv())

        def opener(url, *, timeout):
            response = original(url, timeout=timeout)
            if url == capture.CSV_URL:
                response.headers["Content-Type"] = "text/html"
            return response

        with self.assertRaisesRegex(ValueError, "Content-Type"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_declared_length_mismatch_rejects_without_publication(self):
        original = FakeOpener(_csv())

        def opener(url, *, timeout):
            response = original(url, timeout=timeout)
            if url == capture.CSV_URL:
                response.headers["Content-Length"] = "1"
            return response

        with self.assertRaisesRegex(ValueError, "Content-Length"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_metadata_description_change_rejects_even_if_versions_agree(self):
        changed = json.loads(_metadata())
        changed["description"] = "New publisher note"
        opener = FakeOpener(_csv(), after=json.dumps(changed).encode())
        with self.assertRaisesRegex(ValueError, "changed during capture"):
            capture.capture_snapshot(opener=opener, now=lambda: self.when)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_completion_clock_failure_cannot_publish_file(self):
        calls = 0

        def failing_clock():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("clock failed")
            return self.when

        with self.assertRaisesRegex(ValueError, "clock failed"):
            capture.capture_snapshot(opener=FakeOpener(_csv()), now=failing_clock)
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_existing_target_is_never_overwritten(self):
        original = b"do not overwrite"
        target = self.private_root / "existing.csv"
        self.private_root.mkdir(parents=True)
        target.write_bytes(original)
        with patch.object(capture, "_new_filename", return_value="existing.csv"):
            with self.assertRaises(FileExistsError):
                capture.capture_snapshot(
                    opener=FakeOpener(_csv()), now=lambda: self.when
                )
        self.assertEqual(target.read_bytes(), original)

    def test_dry_run_does_not_touch_network_or_disk(self):
        result = capture.dry_run()
        self.assertEqual(result["capture_status"], "dry_run_no_network")
        self.assertFalse(self.private_root.exists())


if __name__ == "__main__":
    unittest.main()
