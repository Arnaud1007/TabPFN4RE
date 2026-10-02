"""Offline behavioral tests for the fixed NYC generated archive capture."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_generated_archive as archive  # noqa: E402


NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
HEADER = ("BOROUGH", "ADDRESS", "SALE PRICE", "SALE DATE")
ROW_LOCATION = "compressed/materializations/v3/foxtrot.67157/62/rows"
COLUMN_LOCATION = "compressed/materializations/v3/foxtrot.67157/62/columns"


def _archive_list(*, version=62, visible=True, changed=False) -> bytes:
    return json.dumps(
        [
            {
                "createdAt": "2026-04-20T18:29:25.966Z",
                "version": version,
                "startVersion": 61,
                "visible": visible,
                **({"extra": "changed"} if changed else {}),
            }
        ]
    ).encode()


def _status(
    *,
    kind="done",
    version=62,
    dataset="foxtrot.67157",
    row_location=ROW_LOCATION,
    column_location=COLUMN_LOCATION,
    ref_size=4_597_291,
    gzipped=True,
    extra_value=None,
    extra_top=None,
) -> bytes:
    return json.dumps(
        {
            "type": kind,
            "value": {
                "datasetName": dataset,
                "version": version,
                "rowLocation": row_location,
                "columnLocation": column_location,
                "refSize": ref_size,
                "gzipped": gzipped,
                **({"unexpected": extra_value} if extra_value is not None else {}),
            },
            **({"unexpected": extra_top} if extra_top is not None else {}),
        }
    ).encode()


def _csv(
    *, header=HEADER, rows=(("1", "10 Main St", "100000", "2026-01-02"),)
) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class FakeResponse(BytesIO):
    def __init__(self, body: bytes, url: str, *, content_type: str):
        super().__init__(body)
        self.status = 200
        self._url = url
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        }

    def geturl(self) -> str:
        return self._url


class FakeOpener:
    def __init__(
        self,
        *,
        csv_body: bytes | None = None,
        list_before: bytes | None = None,
        list_after: bytes | None = None,
        status_before: bytes | None = None,
        status_after: bytes | None = None,
    ):
        self.csv_body = _csv() if csv_body is None else csv_body
        self.list_before = _archive_list() if list_before is None else list_before
        self.list_after = self.list_before if list_after is None else list_after
        self.status_before = _status() if status_before is None else status_before
        self.status_after = self.status_before if status_after is None else status_after
        self.calls: list[str] = []
        self.list_calls = 0
        self.status_calls = 0
        self.redirect_csv_to: str | None = None

    def __call__(self, url: str, *, timeout: int):
        if not isinstance(timeout, int) or not 0 < timeout <= 30:
            raise AssertionError("Archive requests need a bounded timeout")
        self.calls.append(url)
        if url == archive.LIST_URL:
            self.list_calls += 1
            body = self.list_before if self.list_calls == 1 else self.list_after
            return FakeResponse(body, url, content_type="application/json")
        if url == archive.STATUS_URL:
            self.status_calls += 1
            body = self.status_before if self.status_calls == 1 else self.status_after
            return FakeResponse(body, url, content_type="application/json")
        if url == archive.CSV_URL:
            return FakeResponse(
                self.csv_body,
                self.redirect_csv_to or url,
                content_type="text/csv",
            )
        raise AssertionError(f"Unexpected network URL: {url}")


class GeneratedArchiveCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.private_root.mkdir(parents=True)
        self.run_dir = self.private_root / "generated-archive-test"
        root_patch = patch.object(archive, "PRIVATE_ROOT", self.private_root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        git_patch = patch.object(archive, "_git_state", return_value=("a" * 40, False))
        git_patch.start()
        self.addCleanup(git_patch.stop)
        ignored_patch = patch.object(archive, "_check_git_ignored", return_value=None)
        ignored_patch.start()
        self.addCleanup(ignored_patch.stop)
        secure_patch = patch.object(archive.private_review_io, "secure_directory")
        self.secure_directory = secure_patch.start()
        self.addCleanup(secure_patch.stop)
        verify_patch = patch.object(archive.private_review_io, "verify_acl")
        self.verify_acl = verify_patch.start()
        self.addCleanup(verify_patch.stop)

    def capture(self, opener: FakeOpener) -> dict:
        return archive.capture(self.run_dir, opener=opener, clock=lambda: NOW)

    def test_plan_is_fixed_read_only_version_62(self) -> None:
        self.assertEqual(archive.VERSION, 62)
        self.assertEqual(archive.DATASET_ID, "usep-8jbt")
        self.assertEqual(
            archive.LIST_URL,
            "https://data.cityofnewyork.us/api/archival?id=usep-8jbt&version=1",
        )
        self.assertEqual(
            archive.STATUS_URL,
            "https://data.cityofnewyork.us/api/archival?id=usep-8jbt&version=62&method=status",
        )
        self.assertEqual(
            archive.CSV_URL,
            "https://data.cityofnewyork.us/api/archival.csv?id=usep-8jbt&version=62&method=export",
        )
        plan = archive.plan()
        self.assertNotIn("PUT", json.dumps(plan))
        self.assertNotIn("POST", json.dumps(plan))
        self.assertIn(archive.CSV_URL, json.dumps(plan))

    def test_capture_five_gets_and_private_raw_only(self) -> None:
        raw = _csv(rows=(("1", "10 Main St", "100000", "2026-01-02"),))
        opener = FakeOpener(csv_body=raw)
        result = self.capture(opener)
        self.assertEqual(
            opener.calls,
            [
                archive.LIST_URL,
                archive.STATUS_URL,
                archive.CSV_URL,
                archive.STATUS_URL,
                archive.LIST_URL,
            ],
        )
        saved = list(self.run_dir.glob("*.csv"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), raw)
        self.assertEqual(result["csv_sha256"], sha256(raw).hexdigest())
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["version"], 62)
        self.assertFalse(result["historical_asof_eligible"])
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertTrue((self.run_dir / "manifest.json").is_file())
        self.assertEqual(archive.replay(self.run_dir), result)
        self.secure_directory.assert_called()
        self.verify_acl.assert_called()
        self.assertNotIn("Main St", json.dumps(result))
        self.assertNotIn("100000", json.dumps(result))
        self.assertNotIn("Main St", (self.run_dir / "manifest.json").read_text())

    def test_observed_six_field_status_shape_is_accepted(self) -> None:
        result = self.capture(FakeOpener())
        self.assertEqual(result["version"], 62)
        self.assertEqual(result["rows"], 1)
        self.assertFalse(result["historical_asof_eligible"])

    def test_valid_json_v1_two_field_status_rejects_before_csv(self) -> None:
        v1_status = json.dumps(
            {
                "type": "done",
                "value": {"datasetName": "foxtrot.67157", "version": 62},
            }
        ).encode()
        opener = FakeOpener(status_before=v1_status)

        with self.assertRaises(ValueError):
            self.capture(opener)

        self.assertEqual(opener.calls, [archive.LIST_URL, archive.STATUS_URL])
        self.assertFalse((self.run_dir / "archive.csv").exists())
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_unfinished_archive_status_prevents_csv_request(self) -> None:
        opener = FakeOpener(status_before=_status(kind="in_progress"))
        with self.assertRaises(ValueError):
            self.capture(opener)
        self.assertEqual(opener.calls, [archive.LIST_URL, archive.STATUS_URL])
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_wrong_archive_version_prevents_csv_request(self) -> None:
        for kwargs in (
            {"list_before": _archive_list(version=63)},
            {"list_before": _archive_list(visible=False)},
            {"status_before": _status(version=63)},
            {"status_before": _status(dataset="foxtrot.99999")},
        ):
            with self.subTest(kwargs=kwargs):
                test_dir = (
                    self.private_root / f"case-{len(list(self.private_root.iterdir()))}"
                )
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(**kwargs)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertNotIn(archive.CSV_URL, opener.calls)
                    self.assertFalse((test_dir / "manifest.json").exists())

    def test_other_version_list_entries_may_change(self) -> None:
        before = json.loads(_archive_list()) + [
            {
                "createdAt": "2026-07-15T15:01:35.025Z",
                "version": 63,
                "startVersion": 62,
                "visible": True,
            }
        ]
        after = before[:1] + [
            {
                "createdAt": "2026-07-16T15:01:35.025Z",
                "version": 63,
                "startVersion": 62,
                "visible": True,
            }
        ]
        result = self.capture(
            FakeOpener(
                list_before=json.dumps(before).encode(),
                list_after=json.dumps(after).encode(),
            )
        )
        self.assertEqual(result["version"], 62)

    def test_version_62_metadata_must_match_frozen_record(self) -> None:
        record = json.loads(_archive_list())[0]
        for changed in (
            {**record, "createdAt": "2026-04-21T18:29:25.966Z"},
            {**record, "startVersion": 60},
            {**record, "version": True},
        ):
            with self.subTest(changed=changed):
                test_dir = (
                    self.private_root
                    / f"metadata-{len(list(self.private_root.iterdir()))}"
                )
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(list_before=json.dumps([changed]).encode())
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertNotIn(archive.CSV_URL, opener.calls)

    def test_json_response_caps_prevent_csv_request(self) -> None:
        for kwargs in (
            {"list_before": b"x" * (3 * 1024 * 1024)},
            {"status_before": b"x" * (3 * 1024 * 1024)},
        ):
            with self.subTest(section=next(iter(kwargs))):
                test_dir = (
                    self.private_root / f"json-{len(list(self.private_root.iterdir()))}"
                )
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(**kwargs)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertNotIn(archive.CSV_URL, opener.calls)

    def test_slow_drip_status_exceeds_elapsed_budget_without_manifest(self) -> None:
        elapsed = [0.0]
        base = FakeOpener()

        class SlowResponse(FakeResponse):
            def read(self, size: int = -1) -> bytes:
                elapsed[0] += 20.0
                return super().read(1)

        def opener(url: str, *, timeout: int):
            response = base(url, timeout=timeout)
            if url == archive.STATUS_URL:
                return SlowResponse(
                    response.getvalue(), url, content_type="application/json"
                )
            return response

        with patch.object(archive.time, "monotonic", side_effect=lambda: elapsed[0]):
            with self.assertRaises(TimeoutError):
                archive.capture(self.run_dir, opener=opener, clock=lambda: NOW)
        self.assertEqual(base.calls, [archive.LIST_URL, archive.STATUS_URL])
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_utf8_bom_and_normalized_header_are_accepted(self) -> None:
        data = b"\xef\xbb\xbf" + _csv(
            header=("Borough", "Address", "sale_price", "Sale Date")
        )
        result = self.capture(FakeOpener(csv_body=data))
        self.assertEqual(result["rows"], 1)

    def test_ten_thousand_rows_are_counted_without_public_rows(self) -> None:
        rows = (
            ("1", f"Address {index}", "100000", "2026-01-02") for index in range(10_000)
        )
        result = self.capture(FakeOpener(csv_body=_csv(rows=rows)))
        self.assertEqual(result["rows"], 10_000)
        self.assertNotIn("Address 9999", json.dumps(result))

    def test_malformed_status_rejects_before_csv(self) -> None:
        invalid = (
            b"",
            b"null",
            b"[]",
            b'{"type":"done","type":"done","value":{"datasetName":"foxtrot.67157","version":62}}',
            _status(version=True),
            _status(dataset=""),
            json.dumps({"type": "done", "value": {"version": 62}}).encode(),
            _status(extra_value="wrong"),
            _status(extra_top="wrong"),
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                test_dir = self.private_root / f"status-{index}"
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(status_before=body)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertNotIn(archive.CSV_URL, opener.calls)

    def test_status_storage_paths_size_and_compression_are_pinned(self) -> None:
        invalid = (
            _status(row_location="../../rows"),
            _status(row_location=COLUMN_LOCATION),
            _status(row_location=ROW_LOCATION.replace("/62/", "/63/")),
            _status(column_location="../../columns"),
            _status(column_location=ROW_LOCATION),
            _status(
                column_location=COLUMN_LOCATION.replace(
                    "foxtrot.67157", "foxtrot.99999"
                )
            ),
            _status(ref_size=0),
            _status(ref_size=-1),
            _status(ref_size=archive.MAX_CSV_BYTES + 1),
            _status(ref_size=True),
            _status(ref_size="4597291"),
            _status(gzipped=False),
            _status(gzipped="true"),
            _status(gzipped=1),
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                test_dir = self.private_root / f"status-storage-{index}"
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(status_before=body)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertNotIn(archive.CSV_URL, opener.calls)
                    self.assertFalse((test_dir / "manifest.json").exists())

    def test_malformed_archive_list_rejects_before_status(self) -> None:
        record = json.loads(_archive_list())[0]
        invalid = (
            b"",
            b"not-json",
            b"{}",
            b"[]",
            b'["unexpected"]',
            b'[{"version":62,"version":62}]',
            json.dumps([record, record]).encode(),
            json.dumps([{**record, "createdAt": "2026-04-20T18:29:25.966"}]).encode(),
            json.dumps([{**record, "createdAt": "2026-99-20T18:29:25.966Z"}]).encode(),
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                test_dir = self.private_root / f"list-{index}"
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(list_before=body)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertEqual(opener.calls, [archive.LIST_URL])

    def test_dirty_checkout_rejects_before_network(self) -> None:
        with patch.object(archive, "_git_state", return_value=("a" * 40, True)):

            def no_network(*_args, **_kwargs):
                self.fail("Dirty checkout opened a source URL")

            with self.assertRaisesRegex(ValueError, "dirty"):
                archive.capture(self.run_dir, opener=no_network, clock=lambda: NOW)
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_changed_status_or_metadata_after_download_has_no_manifest(self) -> None:
        for kwargs in (
            {"status_after": _status(kind="in_progress")},
            {"status_after": _status(version=63)},
            {"status_after": _status(dataset="different.dataset")},
            {"status_after": _status(ref_size=4_597_292)},
            {
                "status_after": _status(
                    row_location=ROW_LOCATION.replace("/rows", "/other")
                )
            },
            {"status_after": _status(gzipped=False)},
            {"list_after": _archive_list(version=63)},
            {"list_after": _archive_list(changed=True)},
        ):
            with self.subTest(kwargs=kwargs):
                test_dir = (
                    self.private_root / f"case-{len(list(self.private_root.iterdir()))}"
                )
                with patch.object(self, "run_dir", test_dir):
                    opener = FakeOpener(**kwargs)
                    with self.assertRaises(ValueError):
                        self.capture(opener)
                    self.assertEqual(
                        opener.calls[:3],
                        [archive.LIST_URL, archive.STATUS_URL, archive.CSV_URL],
                    )
                    self.assertFalse((test_dir / "manifest.json").exists())

    def test_csv_header_and_row_integrity(self) -> None:
        invalid = (
            _csv(header=("", "ADDRESS", "SALE PRICE", "SALE DATE")),
            _csv(header=("BOROUGH", "ADDRESS", "SALE PRICE", "OTHER")),
            _csv(header=("BOROUGH", "ADDRESS", "SALE PRICE", "SALE PRICE")),
            _csv(rows=()),
            _csv(rows=(("1", "10 Main St", "100000"),)),
            _csv() + b'1,"unterminated,100000,2026-01-03\r\n',
            b"BOROUGH,ADDRESS,SALE PRICE,SALE DATE\r\n\xff\r\n",
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                with patch.object(self, "run_dir", self.private_root / f"csv-{index}"):
                    with self.assertRaises(ValueError):
                        self.capture(FakeOpener(csv_body=body))
                    self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_csv_byte_and_row_caps_prevent_manifest(self) -> None:
        with patch.object(archive, "MAX_CSV_BYTES", 25):
            with self.assertRaises(ValueError):
                self.capture(FakeOpener())
            self.assertFalse((self.run_dir / "manifest.json").exists())
        with (
            patch.object(archive, "MAX_ROWS", 1),
            patch.object(self, "run_dir", self.private_root / "row-cap"),
        ):
            with self.assertRaises(ValueError):
                self.capture(
                    FakeOpener(
                        csv_body=_csv(
                            rows=(
                                ("1", "A", "1", "2026-01-01"),
                                ("1", "B", "2", "2026-01-02"),
                            )
                        )
                    )
                )
            self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_redirected_csv_response_is_rejected(self) -> None:
        opener = FakeOpener()
        opener.redirect_csv_to = "https://other.example/archive.csv"
        with self.assertRaises(ValueError):
            self.capture(opener)
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_http_errors_content_type_encoding_and_length_are_rejected(self) -> None:
        changes = (
            (archive.STATUS_URL, "status", 403),
            (archive.STATUS_URL, "content_type", "text/html"),
            (archive.CSV_URL, "content_type", "text/html"),
            (archive.CSV_URL, "content_encoding", "gzip"),
            (archive.CSV_URL, "content_length", "1"),
            (archive.CSV_URL, "content_length", "nonnumeric"),
        )
        for index, (url, change, value) in enumerate(changes):
            with self.subTest(change=change, url=url):
                test_dir = self.private_root / f"http-{index}"
                base = FakeOpener()

                def opener(requested: str, *, timeout: int):
                    response = base(requested, timeout=timeout)
                    if requested == url:
                        if change == "status":
                            response.status = value
                        elif change == "content_type":
                            response.headers["Content-Type"] = value
                        elif change == "content_encoding":
                            response.headers["Content-Encoding"] = value
                        elif change == "content_length":
                            response.headers["Content-Length"] = value
                    return response

                with patch.object(self, "run_dir", test_dir):
                    with self.assertRaises(ValueError):
                        archive.capture(test_dir, opener=opener, clock=lambda: NOW)
                    self.assertFalse((test_dir / "manifest.json").exists())

    def test_truncated_csv_transfer_is_rejected(self) -> None:
        base = FakeOpener()

        def opener(url: str, *, timeout: int):
            response = base(url, timeout=timeout)
            if url == archive.CSV_URL:
                response.headers["Content-Length"] = str(len(base.csv_body) + 10)
            return response

        with self.assertRaises(ValueError):
            archive.capture(self.run_dir, opener=opener, clock=lambda: NOW)
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_truncated_status_response_is_rejected_before_csv(self) -> None:
        base = FakeOpener()

        def opener(url: str, *, timeout: int):
            response = base(url, timeout=timeout)
            if url == archive.STATUS_URL:
                response.headers["Content-Length"] = str(len(base.status_before) + 10)
            return response

        with self.assertRaises(ValueError):
            archive.capture(self.run_dir, opener=opener, clock=lambda: NOW)
        self.assertEqual(base.calls, [archive.LIST_URL, archive.STATUS_URL])
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_stream_exceeding_byte_cap_with_no_declared_length(self) -> None:
        base = FakeOpener()

        def opener(url: str, *, timeout: int):
            response = base(url, timeout=timeout)
            if url == archive.CSV_URL:
                response.headers.pop("Content-Length")
            return response

        with patch.object(archive, "MAX_CSV_BYTES", 20):
            with self.assertRaises(ValueError):
                archive.capture(self.run_dir, opener=opener, clock=lambda: NOW)
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_existing_run_is_create_only_before_network(self) -> None:
        self.run_dir.mkdir()
        untouched = self.run_dir / "sentinel"
        untouched.write_bytes(b"untouched")

        def no_network(*_args, **_kwargs):
            self.fail("Capture opened the network for an existing run")

        with self.assertRaises(FileExistsError):
            archive.capture(self.run_dir, opener=no_network, clock=lambda: NOW)
        self.assertEqual(untouched.read_bytes(), b"untouched")

    def test_path_outside_private_root_rejects_before_network(self) -> None:
        def no_network(*_args, **_kwargs):
            self.fail("Unsafe path opened the network")

        with self.assertRaises(ValueError):
            archive.capture(
                self.private_root.parent / "outside",
                opener=no_network,
                clock=lambda: NOW,
            )

    def test_concurrent_capture_same_run_fails_create_only(self) -> None:
        entered = Event()
        release = Event()
        opener = FakeOpener()

        def blocking_opener(url: str, *, timeout: int):
            if url == archive.LIST_URL and not entered.is_set():
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("Synthetic network hold expired")
            return opener(url, timeout=timeout)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                archive.capture,
                self.run_dir,
                opener=blocking_opener,
                clock=lambda: NOW,
            )
            self.assertTrue(entered.wait(3))
            second = pool.submit(
                archive.capture,
                self.run_dir,
                opener=blocking_opener,
                clock=lambda: NOW,
            )
            try:
                with self.assertRaises(FileExistsError):
                    second.result(timeout=3)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3)["version"], 62)

    def test_offline_replay_rejects_tampered_raw_or_manifest(self) -> None:
        result = self.capture(FakeOpener())
        self.assertEqual(archive.replay(self.run_dir), result)
        raw = next(self.run_dir.glob("*.csv"))
        original = raw.read_bytes()
        raw.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            archive.replay(self.run_dir)
        raw.write_bytes(original)
        manifest = self.run_dir / "manifest.json"
        saved = json.loads(manifest.read_text())
        manifest.write_text(json.dumps({**saved, "version": 63}))
        with self.assertRaises(ValueError):
            archive.replay(self.run_dir)

    def test_offline_replay_rejects_semantic_status_tampering_even_with_new_hash(
        self,
    ) -> None:
        self.capture(FakeOpener())
        changed = _status(version=63)
        (self.run_dir / "status-before.json").write_bytes(changed)
        manifest_path = self.run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["requests"][1]["bytes"] = len(changed)
        manifest["requests"][1]["sha256"] = sha256(changed).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            archive.replay(self.run_dir)

    def test_offline_replay_rejects_request_and_environment_tampering(self) -> None:
        for index, change in enumerate(
            ("url", "chronology", "environment", "source_hash", "aggregate")
        ):
            with self.subTest(change=change):
                test_dir = self.private_root / f"replay-{index}"
                with patch.object(self, "run_dir", test_dir):
                    self.capture(FakeOpener())
                    manifest_path = test_dir / "manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    if change == "url":
                        manifest["requests"][2]["url"] = (
                            "https://other.example/rows.csv"
                        )
                    elif change == "chronology":
                        manifest["requests"][2]["retrieved_at_utc"] = (
                            "2025-01-01T00:00:00.000Z"
                        )
                    elif change == "environment":
                        manifest["environment_lock_sha256"] = "0" * 64
                    elif change == "source_hash":
                        manifest["source_snapshot_sha256"] = "0" * 64
                    else:
                        (test_dir / "aggregate.json").write_bytes(b"{}")
                    if change != "aggregate":
                        manifest_path.write_text(json.dumps(manifest))
                    with self.assertRaises(ValueError):
                        archive.replay(test_dir)

    def test_replay_requires_completed_manifest(self) -> None:
        with self.assertRaises(ValueError):
            archive.replay(self.run_dir)
        self.run_dir.mkdir()
        (self.run_dir / "archive.csv").write_bytes(_csv())
        with self.assertRaises(ValueError):
            archive.replay(self.run_dir)


if __name__ == "__main__":
    unittest.main()
