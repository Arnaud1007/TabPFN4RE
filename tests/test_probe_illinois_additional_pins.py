"""Synthetic, offline tests for the bounded Illinois Additional PINs capture."""

from __future__ import annotations

from contextlib import ExitStack
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler

from scripts import probe_illinois_additional_pins as probe


def metadata(*, rows_updated: int = 1790506807) -> bytes:
    observed_ids = (610418722, 610418723, 610418724, 610418725, 610418727)
    return json.dumps(
        {
            "id": probe.DATASET_ID,
            "publicationStage": "published",
            "provenance": "official",
            "licenseId": "PUBLIC_DOMAIN",
            "rowsUpdatedAt": rows_updated,
            "viewLastModified": 1789611867,
            "columns": [
                {"fieldName": name, "id": identifier, "dataTypeName": "text"}
                for name, identifier in zip(probe.ROW_FIELDS, observed_ids)
            ],
        }
    ).encode()


def sources() -> tuple[list[dict], list[dict], dict]:
    cook = [{"row_id": f"r{i}"} for i in range(100)]
    ptax = [{"declaration_id": f"d{i:03d}"} for i in range(80)]
    info = {
        "cook_capture_sha256": probe.COOK_SHA256,
        "response_set_sha256": probe.PTAX_SHA256,
    }
    return cook, ptax, info


class AdditionalPinsProbeTests(unittest.TestCase):
    def test_selection_is_exact_and_bounded(self):
        ids = probe.select_declarations(sources()[1])
        self.assertEqual(len(ids), 80)
        self.assertEqual(ids[:2], ("d000", "d001"))
        self.assertEqual(len(probe._batches(ids)), 8)
        self.assertEqual(tuple(map(len, probe._batches(ids))), (10,) * 8)
        for malformed in (
            [],
            [{"declaration_id": "d"}],
            [{"declaration_id": "d\n"}] * 80,
            [{"declaration_id": "d"}] * 80,
            [{"declaration_id": 3}] * 80,
        ):
            with self.subTest(malformed=malformed[:1]), self.assertRaises(ValueError):
                probe.select_declarations(malformed)

    def test_exact_query_escapes_quotes_and_requests_only_five_fields(self):
        batch = ("A'B", "é🙂")
        count = parse_qs(urlsplit(probe.query_url(batch, count=True)).query)
        rows = parse_qs(urlsplit(probe.query_url(batch, count=False)).query)
        self.assertEqual(count["$where"], ["declaration_id IN ('A''B','é🙂')"])
        self.assertEqual(count["$select"], ["count(*) as matched_count"])
        self.assertEqual(rows["$select"], [",".join(probe.ROW_FIELDS)])
        self.assertEqual(rows["$order"], [",".join(probe.ROW_FIELDS)])
        self.assertEqual(rows["$limit"], ["100"])
        for invalid in ((), ("a", "a"), tuple(str(i) for i in range(11)), ("a\n",)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.query_url(invalid, count=False)

    def test_metadata_pins_schema_licence_and_versions(self):
        self.assertEqual(
            probe.check_metadata_pair(metadata(), metadata())["rows_updated_at"],
            1790506807,
        )
        with self.assertRaises(ValueError):
            probe.check_metadata_pair(metadata(), metadata(rows_updated=1790506808))
        for field, value in (
            ("licenseId", "unknown"),
            ("rowIdentifierColumnId", 1),
            ("rowsUpdatedAt", 0),
            ("viewLastModified", 1),
            ("id", "other"),
        ):
            broken = json.loads(metadata())
            broken[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.metadata_identity(json.dumps(broken).encode())
        broken = json.loads(metadata())
        broken["columns"].append({"fieldName": "buyer_name", "id": 99})
        with self.assertRaises(ValueError):
            probe.metadata_identity(json.dumps(broken).encode())
        broken = json.loads(metadata())
        broken["columns"][0]["id"] = broken["columns"][1]["id"]
        with self.assertRaises(ValueError):
            probe.metadata_identity(json.dumps(broken).encode())
        broken = json.loads(metadata())
        broken["rowIdentifierColumnId"] = None
        with self.assertRaises(ValueError):
            probe.metadata_identity(json.dumps(broken).encode())

    def test_v2_protocol_accepts_absent_row_key_and_pins_observed_column_mapping(self):
        self.assertEqual(probe.PROTOCOL, "illinois-ptax203-additional-pins-v2")
        self.assertEqual(probe.RUN_NAME, "ptax-additional-v2-130b5169ff81ccbc")
        self.assertEqual(
            probe.metadata_identity(metadata())["columns"],
            {
                "declaration_id": (610418722, "text"),
                "pin": (610418723, "text"),
                "lot_size_or_acreage": (610418724, "text"),
                "lot_size_units": (610418725, "text"),
                "split_parcel": (610418727, "text"),
            },
        )
        for field, value in (("id", 999), ("dataTypeName", "number")):
            wrong = json.loads(metadata())
            wrong["columns"][1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.metadata_identity(json.dumps(wrong).encode())

    def test_metadata_pair_detects_stable_name_column_id_and_type_drift(self):
        original = metadata()
        for field, value in (("id", 99), ("dataTypeName", "number")):
            changed = json.loads(original)
            changed["columns"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.check_metadata_pair(original, json.dumps(changed).encode())

    def test_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        for content in (b'{"a":1,"a":2}', b'{"n":NaN}', b'{"n":Infinity}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                probe._json(content)

    def test_default_proxy_environment_is_not_used(self):
        with patch.dict(
            os.environ,
            {
                "https_proxy": "http://proxy.invalid:9999",
                "http_proxy": "http://proxy.invalid:9999",
            },
        ):
            opener = probe._build_opener()
        for candidate in (probe._OPENER, opener):
            handlers = [
                handler
                for handler in candidate.handlers
                if isinstance(handler, ProxyHandler)
            ]
            self.assertEqual(handlers, [])

    def test_parse_preserves_zero_one_multiple_and_identical_rows(self):
        self.assertEqual(probe.parse_count(b'[{"matched_count":"0"}]'), 0)
        self.assertEqual(probe.parse_rows(b"[]", ("d",), expected_count=0), [])
        one = [{"declaration_id": "d", "pin": "PT / ROW", "lot_size_or_acreage": None}]
        body = json.dumps(one).encode()
        self.assertEqual(probe.parse_rows(body, ("d",), expected_count=1), one)
        duplicates = one * 2
        self.assertEqual(
            probe.parse_rows(json.dumps(duplicates).encode(), ("d",), expected_count=2),
            duplicates,
        )

    def test_rows_reject_outside_membership_unrequested_or_nested_fields(self):
        invalid_rows = (
            ([{"declaration_id": "other", "pin": "x"}], ("d",), 1),
            ([{"declaration_id": "d", "buyer_name": "secret"}], ("d",), 1),
            ([{"declaration_id": "d", "pin": {"secret": "x"}}], ("d",), 1),
            ([{"declaration_id": "d", "pin": "x" * 257}], ("d",), 1),
            ([{"declaration_id": "d", "pin": "x"}], ("d",), 0),
        )
        for rows, batch, count in invalid_rows:
            with self.subTest(rows=rows[:1]), self.assertRaises(ValueError):
                probe.parse_rows(json.dumps(rows).encode(), batch, expected_count=count)
        for count_body in (
            b"{}",
            b"not json",
            b'[{"matched_count":"101"}]',
            b'[{"matched_count":-1}]',
        ):
            with self.subTest(count_body=count_body), self.assertRaises(ValueError):
                probe.parse_count(count_body)

    def test_count_rejects_unrequested_source_fields_before_storage(self):
        with self.assertRaises(ValueError):
            probe.parse_count(b'[{"matched_count":"0","buyer_name":"secret"}]')

    def test_validator_failure_saves_hash_not_body_or_query(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bad = b'[{"declaration_id":"secret-id","buyer_name":"secret-name"}]'
            with patch.object(
                probe, "_fetch", return_value=(bad, 200, 0.01, "2026-10-03T00:00:00Z")
            ):
                with self.assertRaises(probe.CaptureFailure):
                    probe._request(
                        directory,
                        0,
                        probe.query_url(("secret-id",), count=False),
                        probe.MAX_ROWS,
                        lambda body: probe.parse_rows(
                            body, ("secret-id",), expected_count=1
                        ),
                    )
            self.assertFalse((directory / "response-00.json").exists())
            event = json.loads((directory / "event-00.json").read_text())
            self.assertEqual(event["response_sha256"], probe._hash(bad))
            self.assertFalse(event["body_saved"])
            self.assertNotIn("secret-id", json.dumps(event))
            self.assertNotIn("secret-name", json.dumps(event))

    def test_capture_replay_preserves_multiplicity_and_public_allowlist(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "raw"
            root.mkdir(mode=0o700)
            directory = root / probe.RUN_NAME
            directory.mkdir(mode=0o700)
            source = root / "source"
            source.mkdir(mode=0o700)
            offline = root / "offline"
            offline.mkdir(mode=0o700)
            expected = [metadata()]
            for number in range(8):
                if number == 0:
                    row = {"declaration_id": "d000", "pin": "secret-PIN"}
                    expected.extend(
                        (b'[{"matched_count":"2"}]', json.dumps([row, row]).encode())
                    )
                else:
                    expected.extend((b'[{"matched_count":"0"}]', b"[]"))
            expected.append(metadata())
            seen: list[str] = []

            def fake_fetch(url, _cap):
                seen.append(url)
                return expected[len(seen) - 1], 200, 0.01, "2026-10-03T00:00:00Z"

            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(probe, "_load_sources", return_value=sources())
                )
                stack.enter_context(
                    patch.object(probe, "_verify_offline", return_value=None)
                )
                stack.enter_context(
                    patch.object(probe, "_new_run", return_value=directory)
                )
                stack.enter_context(
                    patch.object(probe, "_private_root", return_value=root)
                )
                stack.enter_context(
                    patch.object(probe, "_source_dir", return_value=source)
                )
                stack.enter_context(
                    patch.object(probe, "_offline_dir", return_value=offline)
                )
                stack.enter_context(
                    patch.object(probe.private_io, "verify_acl", return_value=None)
                )
                stack.enter_context(
                    patch.object(probe, "_fetch", side_effect=fake_fetch)
                )
                self.assertEqual(probe.capture(), directory)
                self.assertEqual(len(seen), 18)
                self.assertEqual(len(probe._replay(directory)["rows"]), 2)
                summary = probe.verify(directory)
                self.assertEqual(summary["selected_cook_rows"], 100)
                self.assertEqual(summary["selected_declarations"], 80)
                self.assertEqual(summary["certified_sale_labels"], 0)
                self.assertEqual(summary["u0_gate"], "PENDING")
                self.assertNotIn("returned_rows", summary)
                output = Path(temporary) / "aggregate.json"
                self.assertEqual(
                    probe.main(
                        ["verify", "--run-dir", str(directory), "--output", str(output)]
                    ),
                    0,
                )
                public = output.read_text()
                for forbidden in (
                    "secret-PIN",
                    "d000",
                    "matched_count",
                    "response-",
                    "?",
                    "url",
                ):
                    self.assertNotIn(forbidden, public)
                (directory / "response-01.json").write_bytes(b'[{"matched_count":"1"}]')
                with self.assertRaises(ValueError):
                    probe.verify(directory)

    def test_crash_before_complete_is_not_replayed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "run"
            directory.mkdir(mode=0o700)
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(probe, "_load_sources", return_value=sources())
                )
                stack.enter_context(
                    patch.object(probe, "_verify_offline", return_value=None)
                )
                stack.enter_context(
                    patch.object(probe, "_new_run", return_value=directory)
                )
                stack.enter_context(
                    patch.object(probe, "_fetch", side_effect=OSError("secret-url"))
                )
                with self.assertRaises(probe.CaptureFailure):
                    probe.capture()
            self.assertFalse((directory / "complete.json").exists())
            self.assertNotIn("secret-url", (directory / "event-00.json").read_text())
            with patch.object(probe, "_private_root", return_value=root):
                with self.assertRaises(ValueError):
                    probe.verify(directory)

    def test_existing_run_prevents_second_capture_before_any_get(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "private"
            with ExitStack() as stack:
                stack.enter_context(patch.object(probe, "PRIVATE_ROOT", root))
                stack.enter_context(
                    patch.object(probe, "_load_sources", return_value=sources())
                )
                stack.enter_context(
                    patch.object(
                        probe.private_io, "secure_directory", return_value=None
                    )
                )
                stack.enter_context(
                    patch.object(probe.private_io, "verify_acl", return_value=None)
                )
                fetch = stack.enter_context(patch.object(probe, "_fetch"))
                first = probe._new_run()
                self.assertEqual(first, root / probe.RUN_NAME)
                with self.assertRaises(FileExistsError):
                    probe.capture()
                fetch.assert_not_called()

    def test_saturated_batch_fails_without_a_completed_run(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            answers = iter((metadata(), b'[{"matched_count":"101"}]'))
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(probe, "_load_sources", return_value=sources())
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

    def test_request_artifact_and_public_destination_caps(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(probe, "_fetch") as fetch:
                with self.assertRaises(ValueError):
                    probe._request(
                        directory, 18, probe.METADATA_URL, 1, probe.metadata_identity
                    )
                fetch.assert_not_called()
            with self.assertRaises(ValueError):
                probe._write(
                    directory, "oversized.json", b"x" * (probe.MAX_PRIVATE + 1)
                )
            self.assertFalse((directory / "oversized.json").exists())
            with self.assertRaises(ValueError):
                probe._public_destination(directory / "public.json", directory)

    def test_prior_offline_evidence_must_match_pinned_hashes(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            offline = Path(temporary) / "offline"
            with patch.object(
                probe.audit, "verify", return_value={"cook_capture_sha256": "0" * 64}
            ):
                with self.assertRaises(ValueError):
                    probe._verify_offline(source, offline)

    def test_http_guards_reject_host_redirect_content_type_and_cap(self):
        with self.assertRaises(probe.CaptureFailure):
            probe._NoRedirect().redirect_request(
                None, None, 302, "", {}, probe.METADATA_URL
            )

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
                self_outer = self
                if timeout != probe.TIMEOUT:
                    raise AssertionError("Probe timeout changed")
                if self_outer.failing:
                    raise HTTPError(
                        url, 429, "too many", {}, BytesIO(b"private-error-body")
                    )
                return Response(url)

        for invalid in (
            "http://other.invalid/",
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

        class OversizedResponse(Response):
            headers = {"Content-Type": "application/json"}

            def read(self, _):
                return b"x" * 101

        class OversizedOpener(Opener):
            def open(self, url, timeout):
                return OversizedResponse(url)

        with patch.object(probe, "_OPENER", OversizedOpener()):
            with self.assertRaises(probe.CaptureFailure) as error:
                probe._fetch(probe.METADATA_URL, 100)
        self.assertTrue(error.exception.truncated)

    def test_http_error_body_is_closed(self):
        body = BytesIO(b"private-error-body")
        error = HTTPError(probe.METADATA_URL, 429, "limited", {}, body)

        class FailingOpener:
            def open(self, _url, timeout):
                self.assert_timeout = timeout
                raise error

        with patch.object(probe, "_OPENER", FailingOpener()):
            with self.assertRaises(probe.CaptureFailure):
                probe._fetch(probe.METADATA_URL, 100)
        self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
