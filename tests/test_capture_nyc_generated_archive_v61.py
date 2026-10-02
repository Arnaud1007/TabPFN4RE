"""Offline tests for the separate pinned NYC version-61 archive capture."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_generated_archive as v62  # noqa: E402
import capture_nyc_generated_archive_v61 as v61  # noqa: E402


NOW = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
CSV = b"BOROUGH,ADDRESS,SALE PRICE,SALE DATE\r\n1,Synthetic Lane,100000,2026-01-01\r\n"


def archive_list(*, version=61, created=None, start=60, visible=True) -> bytes:
    return json.dumps(
        [
            {
                "createdAt": created or "2026-01-27T14:48:20.467Z",
                "version": version,
                "startVersion": start,
                "visible": visible,
            }
        ]
    ).encode()


def status(
    *,
    kind="done",
    version=61,
    dataset="foxtrot.67157",
    row_path="compressed/materializations/v3/foxtrot.67157/61/rows",
    column_path="compressed/materializations/v3/foxtrot.67157/61/columns",
    ref_size=4473824,
    gzipped=True,
    extra=False,
) -> bytes:
    return json.dumps(
        {
            "type": kind,
            "value": {
                "datasetName": dataset,
                "version": version,
                "rowLocation": row_path,
                "columnLocation": column_path,
                "refSize": ref_size,
                "gzipped": gzipped,
                **({"unexpected": "x"} if extra else {}),
            },
        }
    ).encode()


class FakeResponse(BytesIO):
    def __init__(self, body: bytes, url: str, content_type: str):
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
        list_before: bytes | None = None,
        list_after: bytes | None = None,
        status_before: bytes | None = None,
        status_after: bytes | None = None,
        csv_body: bytes = CSV,
    ):
        self.list_before = archive_list() if list_before is None else list_before
        self.list_after = self.list_before if list_after is None else list_after
        self.status_before = status() if status_before is None else status_before
        self.status_after = self.status_before if status_after is None else status_after
        self.csv_body = csv_body
        self.calls: list[str] = []
        self.redirect_csv = False

    def __call__(self, url: str, *, timeout: int):
        if not 0 < timeout <= 30:
            raise AssertionError("Unbounded timeout")
        self.calls.append(url)
        if url == v61.LIST_URL:
            body = self.list_before if self.calls.count(url) == 1 else self.list_after
            return FakeResponse(body, url, "application/json")
        if url == v61.STATUS_URL:
            body = (
                self.status_before if self.calls.count(url) == 1 else self.status_after
            )
            return FakeResponse(body, url, "application/json")
        if url == v61.CSV_URL:
            response_url = "https://other.example/data" if self.redirect_csv else url
            return FakeResponse(self.csv_body, response_url, "text/csv")
        raise AssertionError(f"Unexpected URL: {url}")


class Version61CaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        private_root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        private_root.mkdir(parents=True)
        self.run_dir = private_root / "v61-test"
        for target, name, value in (
            (v62, "PRIVATE_ROOT", private_root),
            (v62, "_git_state", lambda: ("a" * 40, False)),
            (v62, "_check_git_ignored", lambda _path: None),
            (v62.private_review_io, "secure_directory", lambda _path: None),
            (v62.private_review_io, "verify_acl", lambda _path: None),
        ):
            replacement = patch.object(target, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def capture(self, opener: FakeOpener):
        return v61.capture(self.run_dir, opener=opener, clock=lambda: NOW)

    def test_fixed_five_get_plan_does_not_change_v62(self):
        old_plan = v62.plan()
        self.assertEqual(
            sha256(Path(v62.__file__).read_bytes()).hexdigest(),
            "b075536b39478cb08df57079de076b4f6498eb977c502a3bb2ef8be3cfa53f97",
        )
        plan = v61.plan()
        self.assertEqual(v61.VERSION, 61)
        self.assertEqual(plan["version"], 61)
        self.assertEqual(
            [item["url"] for item in plan["requests"]],
            [v61.LIST_URL, v61.STATUS_URL, v61.CSV_URL, v61.STATUS_URL, v61.LIST_URL],
        )
        self.assertEqual({item["method"] for item in plan["requests"]}, {"GET"})
        self.assertEqual(v62.plan(), old_plan)
        self.assertEqual(v62.VERSION, 62)

    def test_capture_and_replay_inventory_without_sale_certification(self):
        opener = FakeOpener()
        result = self.capture(opener)
        self.assertEqual(opener.calls, [item["url"] for item in v61.plan()["requests"]])
        self.assertEqual(result["version"], 61)
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertFalse(result["historical_asof_eligible"])
        self.assertEqual(v61.replay(self.run_dir), result)

    def test_wrong_or_hidden_revision_rejects_before_csv(self):
        invalid = (
            archive_list(version=60),
            archive_list(created="2026-01-28T14:48:20.467Z"),
            archive_list(start=59),
            archive_list(visible=False),
            b"[]",
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                self.run_dir = self.run_dir.parent / f"list-{index}"
                opener = FakeOpener(list_before=body)
                with self.assertRaises(ValueError):
                    self.capture(opener)
                self.assertEqual(opener.calls, [v61.LIST_URL])
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_not_ready_or_malformed_status_rejects_before_csv(self):
        invalid = (
            status(kind="not_started"),
            status(version=62),
            status(dataset="wrong"),
            status(row_path="other/rows"),
            status(column_path="other/columns"),
            status(ref_size=0),
            status(ref_size=128 * 1024 * 1024 + 1),
            status(gzipped=False),
            status(extra=True),
        )
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                self.run_dir = self.run_dir.parent / f"status-{index}"
                opener = FakeOpener(status_before=body)
                with self.assertRaises(ValueError):
                    self.capture(opener)
                self.assertEqual(opener.calls, [v61.LIST_URL, v61.STATUS_URL])
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_change_after_csv_leaves_incomplete_run(self):
        for index, change in enumerate(("status", "list")):
            self.run_dir = self.run_dir.parent / f"changed-{index}"
            opener = FakeOpener(
                status_after=status(ref_size=5000000) if change == "status" else None,
                list_after=archive_list(created="2026-01-28T14:48:20.467Z")
                if change == "list"
                else None,
            )
            with self.assertRaises(ValueError):
                self.capture(opener)
            self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_redirect_and_tampered_replay_reject(self):
        opener = FakeOpener()
        opener.redirect_csv = True
        with self.assertRaises(ValueError):
            self.capture(opener)
        self.assertFalse((self.run_dir / "manifest.json").exists())

        self.run_dir = self.run_dir.parent / "tamper"
        self.capture(FakeOpener())
        manifest = self.run_dir / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        manifest.write_text(json.dumps({**saved, "version": 62}), encoding="utf-8")
        with self.assertRaises(ValueError):
            v61.replay(self.run_dir)

    def test_create_only_and_replay_reject_v62_artifacts(self):
        self.capture(FakeOpener())
        with self.assertRaises(FileExistsError):
            self.capture(FakeOpener())
        manifest = self.run_dir / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        manifest.write_text(
            json.dumps({**saved, "protocol": v62.PROTOCOL}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            v61.replay(self.run_dir)

    def test_transport_type_encoding_and_length_are_guarded(self):
        cases = (
            (v61.STATUS_URL, "status", 403),
            (v61.STATUS_URL, "Content-Type", "text/html"),
            (v61.CSV_URL, "Content-Type", "text/html"),
            (v61.CSV_URL, "Content-Encoding", "gzip"),
            (v61.CSV_URL, "Content-Length", "1"),
            (v61.LIST_URL, "Content-Length", "nonnumeric"),
        )
        for index, (target, field, value) in enumerate(cases):
            with self.subTest(index=index):
                self.run_dir = self.run_dir.parent / f"transport-{index}"
                source = FakeOpener()

                def opener(url: str, *, timeout: int):
                    response = source(url, timeout=timeout)
                    if url == target:
                        if field == "status":
                            response.status = value
                        else:
                            response.headers[field] = value
                    return response

                with self.assertRaises(ValueError):
                    self.capture(opener)
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_csv_grammar_and_size_integrity_are_guarded(self):
        cases = (
            b"BOROUGH,ADDRESS,SALE PRICE,OTHER\r\n1,A,1,2026-01-01\r\n",
            b"BOROUGH,ADDRESS,SALE PRICE,SALE DATE\r\n",
            b"BOROUGH,ADDRESS,SALE PRICE,SALE DATE\r\n1,A,1\r\n",
            b"BOROUGH,ADDRESS,SALE PRICE,SALE DATE\r\n\xff\r\n",
        )
        for index, body in enumerate(cases):
            with self.subTest(index=index):
                self.run_dir = self.run_dir.parent / f"csv-{index}"
                with self.assertRaises(ValueError):
                    self.capture(FakeOpener(csv_body=body))
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_replay_rejects_tampered_content_and_provenance(self):
        cases = (
            "raw",
            "request_url",
            "request_time",
            "source_hash",
            "helper_hash",
            "aggregate",
        )
        for index, change in enumerate(cases):
            with self.subTest(change=change):
                self.run_dir = self.run_dir.parent / f"replay-{index}"
                self.capture(FakeOpener())
                manifest_path = self.run_dir / "manifest.json"
                saved = json.loads(manifest_path.read_text(encoding="utf-8"))
                if change == "raw":
                    (self.run_dir / "archive.csv").write_bytes(CSV + b"\n")
                elif change == "request_url":
                    saved["requests"][2]["url"] = v62.CSV_URL
                elif change == "request_time":
                    saved["requests"][2]["retrieved_at_utc"] = (
                        "2025-01-01T00:00:00.000Z"
                    )
                elif change == "source_hash":
                    saved["source_snapshot_sha256"] = "0" * 64
                elif change == "helper_hash":
                    saved["helper_code_sha256"] = "0" * 64
                else:
                    (self.run_dir / "aggregate.json").write_bytes(b"{}")
                if change not in ("raw", "aggregate"):
                    manifest_path.write_text(json.dumps(saved), encoding="utf-8")
                with self.assertRaises(ValueError):
                    v61.replay(self.run_dir)


if __name__ == "__main__":
    unittest.main()
