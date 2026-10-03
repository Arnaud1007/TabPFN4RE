"""Synthetic, offline unittest checks for the bounded PTAX-203 probe."""

from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from scripts import probe_illinois_ptax203 as probe


def metadata(*, updated: int = 123) -> bytes:
    columns = [
        {"fieldName": name, "id": index + 1}
        for index, name in enumerate(sorted(probe.ROW_FIELDS))
    ]
    identifier = next(
        col["id"] for col in columns if col["fieldName"] == "declaration_id"
    )
    return json.dumps(
        {
            "id": probe.DATASET_ID,
            "publicationStage": "published",
            "provenance": "official",
            "licenseId": "PUBLIC_DOMAIN",
            "rowsUpdatedAt": updated,
            "viewLastModified": 456,
            "rowIdentifierColumnId": identifier,
            "columns": columns,
        }
    ).encode()


class PtaxProbeTests(unittest.TestCase):
    def test_selection_preserves_exact_documents(self):
        rows = [
            {"year": "2024", "doc_no": "A'B", "row_id": "one"},
            {"year": "2025", "doc_no": "A'B", "row_id": "two"},
            {"year": "2025", "doc_no": " A ", "row_id": "three"},
            {"year": "2019", "doc_no": "old"},
            {"year": "2024", "doc_no": ""},
        ]
        selected = probe.select_documents(rows, expected_rows=3)
        self.assertEqual(list(selected), [" A ", "A'B"])
        self.assertEqual(selected["A'B"], ("one", "two"))
        self.assertEqual(selected[" A "], ("three",))
        self.assertEqual(
            len(probe._batches({f"D{i:03d}": (str(i),) for i in range(100)})), 10
        )
        with self.assertRaises(ValueError):
            probe._batches({})
        for invalid in (
            [],
            [{"year": "2024", "doc_no": 12}],
            [{"year": "2024", "doc_no": "x\n"}],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.select_documents(invalid, expected_rows=1)

    def test_exact_queries_allowlist_and_type_errors(self):
        docs = ["A'B", "\u00e9\U0001f642"]
        count = parse_qs(urlsplit(probe.query_url(docs, count=True)).query)
        rows = parse_qs(urlsplit(probe.query_url(docs, count=False)).query)
        self.assertEqual(
            count["$where"], ["document_number IN ('A''B','\u00e9\U0001f642')"]
        )
        self.assertEqual(count["$select"], ["count(*) as matched_count"])
        self.assertEqual(rows["$select"], [",".join(probe.ROW_FIELDS)])
        self.assertEqual(rows["$order"], ["declaration_id"])
        self.assertEqual(rows["$limit"], ["100"])
        for invalid in ([str(i) for i in range(11)], [["bad"]], ["x", "x"]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.query_url(invalid, count=False)

    def test_metadata_schema_licence_and_stability(self):
        self.assertEqual(
            probe.metadata_identity(metadata()), probe.metadata_identity(metadata())
        )
        with self.assertRaises(ValueError):
            probe.metadata_identity(metadata(updated=0))
        with self.assertRaises(ValueError):
            probe.check_metadata_pair(metadata(), metadata(updated=124))
        for field, value in (("licenseId", "unknown"), ("rowIdentifierColumnId", -1)):
            broken = json.loads(metadata())
            broken[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.metadata_identity(json.dumps(broken).encode())
        broken = json.loads(metadata())
        broken["columns"] = broken["columns"][:-1]
        with self.assertRaises(ValueError):
            probe.metadata_identity(json.dumps(broken).encode())

    def test_count_and_rows_reject_unrequested_nested_data(self):
        self.assertEqual(probe.parse_count(b'[{"matched_count":"0"}]'), 0)
        good = b'[{"document_number":"A","declaration_id":"d1"}]'
        self.assertEqual(len(probe.parse_rows(good, ("A",), expected_count=1)), 1)
        bad_rows = (
            b'[{"document_number":"B","declaration_id":"d1"}]',
            b'[{"document_number":"A","declaration_id":"d1","buyer_name":"secret"}]',
            b'[{"document_number":"A","declaration_id":"d1","status":{"buyer_name":"secret"}}]',
            b'[{"document_number":"A","declaration_id":"d1"},{"document_number":"A","declaration_id":"d1"}]',
        )
        for content in bad_rows:
            with self.subTest(content=content), self.assertRaises(ValueError):
                probe.parse_rows(content, ("A",), expected_count=1)
        for content in (
            b"{}",
            b'[{"matched_count":-1}]',
            b'[{"matched_count":"101"}]',
            b"not-json",
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                probe.parse_count(content)

    def test_unexpected_body_is_hashed_not_saved(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            directory.mkdir()
            bad = b'[{"document_number":"A","declaration_id":"d1","status":{"buyer_name":"secret"}}]'
            with patch.object(
                probe, "_fetch", return_value=(bad, 200, 0.01, "2026-10-03T00:00:00Z")
            ):
                with self.assertRaises(probe.CaptureFailure):
                    probe._request(
                        directory,
                        0,
                        probe.query_url(("A",), count=False),
                        probe.MAX_ROWS,
                        lambda body: probe.parse_rows(body, ("A",), expected_count=1),
                    )
            self.assertFalse((directory / "response-00.json").exists())
            event = json.loads((directory / "event-00.json").read_text())
            self.assertIs(event["body_saved"], False)
            self.assertEqual(event["response_sha256"], probe._hash(bad))
            self.assertNotIn("secret", json.dumps(event))

    def test_capture_replay_privacy_and_tamper_detection(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "ptax"
            root.mkdir()
            directory = root / "run"
            directory.mkdir()
            rows = [
                {"year": "2024", "doc_no": f"D{i:03d}", "row_id": f"r{i:03d}"}
                for i in range(100)
            ]
            answers = [metadata()]
            for _ in probe._batches(probe.select_documents(rows)):
                answers.extend((b'[{"matched_count":"0"}]', b"[]"))
            answers.append(metadata())
            requested: list[str] = []

            def fake_fetch(url, _cap):
                requested.append(url)
                return answers[len(requested) - 1], 200, 0.01, "2026-10-03T00:00:00Z"

            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(probe.cook, "_capture_rows", return_value=rows)
                )
                stack.enter_context(
                    patch.object(probe, "_new_run", return_value=directory)
                )
                stack.enter_context(
                    patch.object(probe, "_private_root", return_value=root)
                )
                stack.enter_context(
                    patch.object(probe.private_io, "verify_acl", return_value=None)
                )
                stack.enter_context(
                    patch.object(probe, "_fetch", side_effect=fake_fetch)
                )
                self.assertEqual(probe.capture(), directory)
                self.assertEqual(len(requested), 22)
                summary = probe.verify(directory)
                self.assertEqual(summary["selected_cook_rows"], 100)
                self.assertEqual(summary["returned_declarations"], "suppressed")
                self.assertNotIn("document_match_counts", summary)
                self.assertEqual(summary["certified_sale_labels"], 0)
                output = Path(temporary) / "aggregate.json"
                self.assertEqual(
                    probe.main(
                        ["verify", "--run-dir", str(directory), "--output", str(output)]
                    ),
                    0,
                )
                public = output.read_text()
                for forbidden in (
                    "D000",
                    "r000",
                    "buyer_name",
                    "document_match_counts",
                ):
                    self.assertNotIn(forbidden, public)
                (directory / "response-01.json").write_bytes(b'[{"matched_count":"1"}]')
                with self.assertRaisesRegex(ValueError, "ledger"):
                    probe.verify(directory)
                self.assertEqual(
                    probe.main(
                        [
                            "verify",
                            "--run-dir",
                            str(directory),
                            "--output",
                            str(Path(temporary) / "bad.json"),
                        ]
                    ),
                    1,
                )

    def test_failed_count_leaves_incomplete_run(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / "run"
            directory.mkdir()
            answers = iter([metadata(), b'[{"matched_count":"101"}]'])
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(
                        probe.cook,
                        "_capture_rows",
                        return_value=[{"year": "2025", "doc_no": "D", "row_id": "r"}],
                    )
                )
                stack.enter_context(
                    patch.object(probe, "select_documents", return_value={"D": ("r",)})
                )
                stack.enter_context(
                    patch.object(probe, "_new_run", return_value=directory)
                )
                stack.enter_context(
                    patch.object(
                        probe,
                        "_fetch",
                        side_effect=lambda *_: (
                            next(answers),
                            200,
                            0.01,
                            "2026-10-03T00:00:00Z",
                        ),
                    )
                )
                with self.assertRaises(probe.CaptureFailure):
                    probe.capture()
            self.assertFalse((directory / "complete.json").exists())
            self.assertFalse((directory / "response-01.json").exists())

    def test_second_capture_rejected_before_get(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            with ExitStack() as stack:
                stack.enter_context(patch.object(probe, "PRIVATE_ROOT", root))
                stack.enter_context(
                    patch.object(
                        probe.private_io, "secure_directory", return_value=None
                    )
                )
                stack.enter_context(
                    patch.object(probe.private_io, "verify_acl", return_value=None)
                )
                stack.enter_context(
                    patch.object(
                        probe.cook,
                        "_capture_rows",
                        return_value=[{"year": "2025", "doc_no": "D", "row_id": "r"}],
                    )
                )
                stack.enter_context(
                    patch.object(probe, "select_documents", return_value={"D": ("r",)})
                )
                fetch = stack.enter_context(
                    patch.object(probe, "_fetch", side_effect=OSError("offline"))
                )
                self.assertEqual(probe._private_root(), root)
                directory = probe._new_run()
                self.assertEqual(directory.parent, root)
                with self.assertRaises(FileExistsError):
                    probe.capture()
                fetch.assert_not_called()

    def test_http_fetch_rejects_broad_and_error_bodies_without_network(self):
        with self.assertRaises(probe.CaptureFailure) as redirect:
            probe._NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, probe.METADATA_URL
            )
        self.assertEqual(redirect.exception.status, 302)

        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}

            def __init__(self, url):
                self.url = url

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def geturl(self):
                return self.url

            def read(self, _):
                return b"private-error-body"

        class Opener:
            def __init__(self, failing=False):
                self.failing = failing

            def open(self, url, timeout):
                if timeout != probe.TIMEOUT:
                    raise AssertionError("Probe timeout changed")
                if self.failing:
                    raise HTTPError(
                        url, 429, "too many", {}, BytesIO(b"private-error-body")
                    )
                return Response(url)

        for invalid in (
            "http://invalid.example/data",
            f"https://{probe.HOST}:8443/api/views/{probe.DATASET_ID}.json",
            f"https://{probe.HOST}/other.json",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe._fetch(invalid, 100)
        with patch.object(probe, "_OPENER", Opener()):
            with self.assertRaises(probe.CaptureFailure) as error:
                probe._fetch(probe.METADATA_URL, 100)
        self.assertEqual(error.exception.body_hash, probe._hash(b"private-error-body"))
        with patch.object(probe, "_OPENER", Opener(failing=True)):
            with self.assertRaises(probe.CaptureFailure) as error:
                probe._fetch(probe.METADATA_URL, 100)
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(error.exception.body_hash, probe._hash(b"private-error-body"))


if __name__ == "__main__":
    unittest.main()
