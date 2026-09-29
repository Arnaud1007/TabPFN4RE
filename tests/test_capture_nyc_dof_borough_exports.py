"""Offline contract tests for the bounded official borough workbook capture."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_dof_borough_exports as capture  # noqa: E402


WHEN = datetime(2026, 9, 29, 12, 30, tzinfo=timezone.utc)
PROVENANCE = {
    "code_commit": "a" * 40,
    "dirty_tree": False,
    "environment_lock_sha256": "b" * 64,
}


def workbook(*, names=None) -> bytes:
    members = names or (
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/worksheets/sheet1.xml",
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name in members:
            archive.writestr(name, b"<x>synthetic</x>")
    return buffer.getvalue()


class FakeResponse(BytesIO):
    def __init__(self, body, url, *, status=200, headers=None, final_url=None):
        super().__init__(body)
        self.status = status
        self.headers = {
            "Content-Type": capture.MIME,
            "Content-Length": str(len(body)),
            **(headers or {}),
        }
        self.final_url = final_url or url

    def geturl(self):
        return self.final_url


class FakeTransport:
    def __init__(self, body=None, response_factory=None):
        self.body = workbook() if body is None else body
        self.response_factory = response_factory
        self.calls = []

    @contextmanager
    def __call__(self, method, url, timeout):
        self.calls.append((method, url, timeout))
        result = (
            self.response_factory(url)
            if self.response_factory
            else FakeResponse(self.body, url)
        )
        with result:
            yield result


class CaptureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.private_root.mkdir(parents=True)
        self.run_dir = self.run_path(1)
        patcher = patch.object(capture, "PRIVATE_ROOT", self.private_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call_capture(self, transport=None, **kwargs):
        options = {"provenance": PROVENANCE, **kwargs}
        return capture.capture_bundle(
            self.run_dir,
            transport=transport or FakeTransport(),
            clock=lambda: WHEN,
            **options,
        )

    def run_path(self, nonce: int):
        return self.private_root / f"official-exports-20260929T123000Z-{nonce:012x}"

    def test_run_id_requires_valid_utc_stamp_and_bounded_hex_nonce(self):
        invalid = (
            "official-exports-test",
            "official-exports-20260929T123000Z-home-address",
            "official-exports-20260929T123000Z-abcdef0123456789abcdef",
            "official-exports-20269999T123000Z-abcdef012345",
            "official-exports-20260929T123000+0200-abcdef012345",
            "official-exports-20260929T123000Z-ABCDEF012345",
        )
        for name in invalid:
            with self.subTest(name=name):
                fake = FakeTransport()
                with self.assertRaises(ValueError):
                    capture.capture_bundle(
                        self.private_root / name,
                        transport=fake,
                        clock=lambda: WHEN,
                        provenance=PROVENANCE,
                    )
                self.assertEqual(fake.calls, [])
                self.assertFalse((self.private_root / name).exists())

    def test_collector_specific_environment_lock_is_required_and_hashed(self):
        project = self.private_root.parents[2]
        lock = project / "locks" / "nyc-borough-capture-environment.json"
        lock.parent.mkdir()
        results = iter(
            (
                SimpleNamespace(stdout="c" * 40 + "\n"),
                SimpleNamespace(stdout=""),
            )
        )
        fake = FakeTransport()
        with (
            patch.object(capture, "PROJECT_ROOT", project),
            patch.object(
                capture.subprocess, "run", side_effect=lambda *a, **k: next(results)
            ),
        ):
            with self.assertRaises(FileNotFoundError):
                capture.capture_bundle(self.run_dir, transport=fake, clock=lambda: WHEN)
        self.assertEqual(fake.calls, [])
        self.assertFalse(self.run_dir.exists())
        lock_bytes = b'{"collector": "nyc-official-borough-xlsx-v2"}\n'
        lock.write_bytes(lock_bytes)
        results = iter(
            (
                SimpleNamespace(stdout="c" * 40 + "\n"),
                SimpleNamespace(stdout=""),
            )
        )
        with (
            patch.object(capture, "PROJECT_ROOT", project),
            patch.object(
                capture.subprocess, "run", side_effect=lambda *a, **k: next(results)
            ),
            patch.object(capture, "_secure_directory"),
            patch.object(capture, "_verify_directory_acl"),
        ):
            self.call_capture(fake, provenance=None)
        manifest = json.loads((self.run_dir / "manifest.json").read_bytes())
        self.assertEqual(manifest["environment_lock_sha256"], capture._sha(lock_bytes))

    def test_plan_fixes_five_urls_without_disk_or_network(self):
        plan = capture.plan()
        self.assertEqual(
            [item["borough"] for item in plan["requests"]],
            ["Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"],
        )
        self.assertEqual(plan["request_cap"], 5)
        self.assertFalse(self.run_dir.exists())

    def test_capture_is_exactly_five_gets_and_replay_is_offline(self):
        fake = FakeTransport()
        report = self.call_capture(fake)
        self.assertEqual(fake.calls, [("GET", url, 30) for _, url in capture.BOROUGHS])
        self.assertEqual(report["bundle_status"], "bytes_captured_content_unqualified")
        self.assertEqual(set(report["files"]), {name for name, _ in capture.BOROUGHS})
        self.assertNotIn("synthetic", json.dumps(report))
        self.assertTrue((self.run_dir / "intent.json").is_file())
        self.assertTrue((self.run_dir / "manifest.json").is_file())
        self.assertEqual(len(list(self.run_dir.glob("receipt-*.json"))), 5)
        for name, _ in capture.BOROUGHS:
            self.assertEqual(
                (self.run_dir / f"{name.lower().replace(' ', '_')}.xlsx").read_bytes(),
                fake.body,
            )
        replayed = capture.replay(self.run_dir)
        self.assertEqual(replayed, report)

    def test_v2_intent_and_manifest_bind_exact_user_agent(self):
        self.call_capture()
        intent = json.loads((self.run_dir / "intent.json").read_bytes())
        manifest = json.loads((self.run_dir / "manifest.json").read_bytes())
        self.assertEqual(intent["protocol"], "nyc-official-borough-xlsx-v2")
        self.assertEqual(manifest["protocol"], intent["protocol"])
        self.assertEqual(intent["user_agent"], "TabPFN4RealEstate-U0/1.0")
        self.assertEqual(manifest["user_agent"], intent["user_agent"])

    def test_replay_rejects_changed_user_agent_and_v1_even_with_matching_hashes(self):
        for nonce, protocol, agent in (
            (60, "nyc-official-borough-xlsx-v2", "DifferentAgent/1.0"),
            (61, "nyc-official-borough-xlsx-v1", "TabPFN4RealEstate-U0/1.0"),
        ):
            with self.subTest(protocol=protocol, agent=agent):
                run_dir = self.run_path(nonce)
                capture.capture_bundle(
                    run_dir,
                    transport=FakeTransport(),
                    clock=lambda: WHEN,
                    provenance=PROVENANCE,
                )
                intent_file = run_dir / "intent.json"
                manifest_file = run_dir / "manifest.json"
                intent = json.loads(intent_file.read_bytes())
                manifest = json.loads(manifest_file.read_bytes())
                intent.update({"protocol": protocol, "user_agent": agent})
                manifest.update(
                    {
                        "protocol": protocol,
                        "user_agent": agent,
                        "intent_sha256": capture._sha(capture._json_bytes(intent)),
                    }
                )
                intent_file.write_bytes(capture._json_bytes(intent))
                manifest_file.write_bytes(capture._json_bytes(manifest))
                with self.assertRaises(ValueError):
                    capture.replay(run_dir)

    def test_intent_precedes_first_get_and_receipts_follow_each_file(self):
        calls = []
        base = FakeTransport()

        @contextmanager
        def transport(method, url, timeout):
            calls.append(url)
            self.assertTrue((self.run_dir / "intent.json").is_file())
            self.assertEqual(
                len(list(self.run_dir.glob("receipt-*.json"))), len(calls) - 1
            )
            with base(method, url, timeout) as response:
                yield response

        self.call_capture(transport)
        self.assertEqual(len(calls), 5)

    def test_existing_directory_is_rejected_before_request(self):
        self.run_dir.mkdir()
        fake = FakeTransport()
        with self.assertRaises(FileExistsError):
            self.call_capture(fake)
        self.assertEqual(fake.calls, [])

    def test_new_v2_run_preserves_old_v1_private_artifacts(self):
        old_run = self.run_path(62)
        old_run.mkdir()
        old_intent = b'{"protocol":"nyc-official-borough-xlsx-v1"}\n'
        old_failure = b'{"run_status":"incomplete"}\n'
        (old_run / "intent.json").write_bytes(old_intent)
        (old_run / "failure.json").write_bytes(old_failure)
        self.call_capture()
        self.assertEqual((old_run / "intent.json").read_bytes(), old_intent)
        self.assertEqual((old_run / "failure.json").read_bytes(), old_failure)
        self.assertEqual(
            set(path.name for path in old_run.iterdir()),
            {"intent.json", "failure.json"},
        )

    def test_failure_preserves_intent_and_prior_receipts_without_manifest(self):
        count = 0

        @contextmanager
        def transport(method, url, timeout):
            nonlocal count
            count += 1
            if count == 2:
                raise TimeoutError("synthetic timeout")
            with FakeResponse(workbook(), url) as response:
                yield response

        with self.assertRaises(TimeoutError):
            self.call_capture(transport)
        self.assertEqual(count, 2)
        self.assertTrue((self.run_dir / "intent.json").is_file())
        self.assertEqual(len(list(self.run_dir.glob("receipt-*.json"))), 1)
        self.assertFalse((self.run_dir / "manifest.json").exists())
        failure = json.loads((self.run_dir / "failure.json").read_bytes())
        self.assertEqual(failure["run_status"], "incomplete")
        self.assertEqual(failure["error_class"], "TimeoutError")
        self.assertEqual(failure["request_ordinal"], 2)
        self.assertNotIn("synthetic timeout", json.dumps(failure))
        with self.assertRaises(ValueError):
            capture.replay(self.run_dir)

    def test_failure_record_write_error_preserves_original_exception(self):
        original_write = capture._write_new

        def write(path, body):
            if path.name == "failure.json":
                raise OSError("secondary failure")
            return original_write(path, body)

        @contextmanager
        def fail_transport(method, url, timeout):
            raise TimeoutError("primary failure")
            yield  # pragma: no cover

        with patch.object(capture, "_write_new", side_effect=write):
            with self.assertRaisesRegex(TimeoutError, "primary failure"):
                self.call_capture(fail_transport)
        self.assertTrue((self.run_dir / "intent.json").exists())
        self.assertFalse((self.run_dir / "failure.json").exists())

    def test_http_error_records_only_safe_status_in_private_failure(self):
        marker = "private-query-value"
        body = BytesIO(b"secret response body")

        @contextmanager
        def transport(method, url, timeout):
            raise HTTPError(
                url + "?token=" + marker,
                403,
                "secret reason",
                {"X-Private": "secret header"},
                body,
            )
            yield  # pragma: no cover

        with self.assertRaises(HTTPError):
            self.call_capture(transport)
        failure_bytes = (self.run_dir / "failure.json").read_bytes()
        failure = json.loads(failure_bytes)
        self.assertEqual(failure["http_status"], 403)
        self.assertEqual(failure["request_ordinal"], 1)
        self.assertEqual(failure["error_class"], "OSError")
        for forbidden in (
            marker,
            "secret reason",
            "secret header",
            "secret response body",
        ):
            self.assertNotIn(forbidden.encode(), failure_bytes)
        self.assertEqual(body.tell(), 0)

    def test_non_http_failure_and_invalid_http_codes_omit_status(self):
        for nonce, code in ((70, 99), (71, 600), (72, True), (73, "403")):
            with self.subTest(code=code):
                run_dir = self.run_path(nonce)

                @contextmanager
                def transport(method, url, timeout):
                    raise HTTPError(url, code, "synthetic", {}, BytesIO())
                    yield  # pragma: no cover

                with self.assertRaises(HTTPError):
                    capture.capture_bundle(
                        run_dir,
                        transport=transport,
                        clock=lambda: WHEN,
                        provenance=PROVENANCE,
                    )
                failure = json.loads((run_dir / "failure.json").read_bytes())
                self.assertNotIn("http_status", failure)
        run_dir = self.run_path(74)

        @contextmanager
        def timeout(method, url, duration):
            raise TimeoutError("synthetic")
            yield  # pragma: no cover

        with self.assertRaises(TimeoutError):
            capture.capture_bundle(
                run_dir, transport=timeout, clock=lambda: WHEN, provenance=PROVENANCE
            )
        self.assertNotIn(
            "http_status", json.loads((run_dir / "failure.json").read_bytes())
        )

    def test_http_error_status_accepts_exact_integer_boundaries(self):
        for nonce, status in ((75, 100), (76, 599)):
            with self.subTest(status=status):
                run_dir = self.run_path(nonce)

                @contextmanager
                def transport(method, url, timeout):
                    raise HTTPError(url, status, "synthetic", {}, BytesIO())
                    yield  # pragma: no cover

                with self.assertRaises(HTTPError):
                    capture.capture_bundle(
                        run_dir,
                        transport=transport,
                        clock=lambda: WHEN,
                        provenance=PROVENANCE,
                    )
                failure = json.loads((run_dir / "failure.json").read_bytes())
                self.assertEqual(failure["http_status"], status)

    def test_wrong_url_or_extra_call_is_rejected(self):
        client = capture.BoundedClient(FakeTransport())
        with self.assertRaises(ValueError):
            with client.request("GET", "https://example.org/file.xlsx"):
                pass
        with self.assertRaises(ValueError):
            with client.request("HEAD", capture.BOROUGHS[0][1]):
                pass
        for _, url in capture.BOROUGHS:
            with client.request("GET", url) as response:
                self.assertEqual(response.status, 200)
        with self.assertRaises(ValueError):
            with client.request("GET", capture.BOROUGHS[0][1]):
                pass

    def test_response_rejects_redirect_status_mime_encoding_and_lengths(self):
        scenarios = (
            {"status": 302},
            {"final_url": "https://example.org/redirect"},
            {"headers": {"Content-Type": "text/html"}},
            {"headers": {"Content-Type": capture.MIME + "; charset=utf-8"}},
            {"headers": {"Content-Encoding": "gzip"}},
            {"headers": {"Content-Length": "abc"}},
            {"headers": {"Content-Length": "-1"}},
            {"headers": {"Content-Length": "1"}},
        )
        for values in scenarios:
            with self.subTest(values=values):
                run_dir = self.run_path(100 + len(list(self.private_root.iterdir())))
                fake = FakeTransport(
                    response_factory=lambda url: FakeResponse(workbook(), url, **values)
                )
                with self.assertRaises((ValueError, TimeoutError)):
                    capture.capture_bundle(
                        run_dir,
                        transport=fake,
                        clock=lambda: WHEN,
                        provenance=PROVENANCE,
                    )
                self.assertEqual(len(fake.calls), 1)
                self.assertFalse((run_dir / "manifest.json").exists())

    def test_declared_length_missing_is_allowed(self):
        fake = FakeTransport(
            response_factory=lambda url: FakeResponse(
                workbook(), url, headers={"Content-Length": None}
            )
        )
        report = self.call_capture(fake)
        self.assertEqual(report["bundle_status"], "bytes_captured_content_unqualified")

    def test_file_and_bundle_caps_apply_to_actual_bytes(self):
        body = workbook()
        with patch.object(capture, "MAX_FILE_BYTES", len(body) - 1):
            with self.assertRaises(ValueError):
                self.call_capture()
        other = self.run_path(20)
        with patch.object(capture, "MAX_BUNDLE_BYTES", len(body) * 4):
            with self.assertRaises(ValueError):
                capture.capture_bundle(
                    other,
                    transport=FakeTransport(),
                    clock=lambda: WHEN,
                    provenance=PROVENANCE,
                )
        self.assertFalse((other / "manifest.json").exists())

    def test_missing_declared_length_still_hits_actual_byte_limit(self):
        body = workbook()
        fake = FakeTransport(
            response_factory=lambda url: FakeResponse(
                body, url, headers={"Content-Length": None}
            )
        )
        with patch.object(capture, "MAX_FILE_BYTES", len(body) - 1):
            with self.assertRaises(ValueError):
                self.call_capture(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_invalid_zip_variants_fail_without_complete_manifest(self):
        variants = (
            b"not a zip",
            workbook(names=("[Content_Types].xml", "_rels/.rels")),
            workbook(
                names=(
                    "[Content_Types].xml",
                    "_rels/.rels",
                    "xl/workbook.xml",
                    "../escape",
                )
            ),
            workbook(
                names=(
                    "[Content_Types].xml",
                    "_rels/.rels",
                    "xl/workbook.xml",
                    "xl/../evil",
                )
            ),
            workbook(
                names=(
                    "[Content_Types].xml",
                    "_rels/.rels",
                    "xl/workbook.xml",
                    "xl/workbook.xml",
                )
            ),
        )
        for index, body in enumerate(variants):
            with self.subTest(index=index):
                run_dir = self.run_path(30 + index)
                with self.assertRaises(ValueError):
                    capture.capture_bundle(
                        run_dir,
                        transport=FakeTransport(body),
                        clock=lambda: WHEN,
                        provenance=PROVENANCE,
                    )
                self.assertFalse((run_dir / "manifest.json").exists())

    def test_zip_member_count_declared_size_and_symlink_rejected(self):
        body = workbook()
        with patch.object(capture, "MAX_MEMBERS", 3):
            with self.assertRaises(ValueError):
                self.call_capture(FakeTransport(body))
        link = BytesIO()
        with ZipFile(link, "w") as archive:
            for name in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"):
                info = ZipInfo(name)
                if name == "xl/workbook.xml":
                    info.create_system = 3
                    info.external_attr = 0o120777 << 16
                archive.writestr(info, b"x")
        run_dir = self.run_path(40)
        with self.assertRaises(ValueError):
            capture.capture_bundle(
                run_dir,
                transport=FakeTransport(link.getvalue()),
                clock=lambda: WHEN,
                provenance=PROVENANCE,
            )
        self.assertFalse((run_dir / "manifest.json").exists())

    def test_zip_expansion_crc_and_fake_required_directory_are_rejected(self):
        body = workbook()
        with patch.object(capture, "MAX_MEMBER_BYTES", 5):
            with self.assertRaises(ValueError):
                self.call_capture(FakeTransport(body))
        stored = BytesIO()
        with ZipFile(stored, "w", ZIP_STORED) as archive:
            for name in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"):
                archive.writestr(name, b"unique-original-payload")
        damaged = stored.getvalue().replace(
            b"unique-original-payload", b"unique-original-payloXd", 1
        )
        other = self.run_path(41)
        with self.assertRaises(ValueError):
            capture.capture_bundle(
                other,
                transport=FakeTransport(damaged),
                clock=lambda: WHEN,
                provenance=PROVENANCE,
            )
        required_dir = workbook(
            names=("[Content_Types].xml/", "_rels/.rels", "xl/workbook.xml")
        )
        other = self.run_path(42)
        with self.assertRaises(ValueError):
            capture.capture_bundle(
                other,
                transport=FakeTransport(required_dir),
                clock=lambda: WHEN,
                provenance=PROVENANCE,
            )

    def test_required_part_with_unix_directory_mode_is_rejected(self):
        data = BytesIO()
        with ZipFile(data, "w", ZIP_STORED) as archive:
            for name in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"):
                info = ZipInfo(name)
                info.create_system = 3
                mode = (
                    stat.S_IFDIR | 0o755
                    if name == "xl/workbook.xml"
                    else stat.S_IFREG | 0o644
                )
                info.external_attr = mode << 16
                archive.writestr(info, b"x")
        with self.assertRaises(ValueError):
            self.call_capture(FakeTransport(data.getvalue()))
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_replay_detects_tamper_and_never_calls_transport(self):
        self.call_capture()
        file_path = self.run_dir / "manhattan.xlsx"
        file_path.write_bytes(file_path.read_bytes() + b"X")
        with self.assertRaises(ValueError):
            capture.replay(self.run_dir)

    def test_replay_rejects_missing_receipt_and_incomplete_manifest(self):
        self.call_capture()
        (self.run_dir / "receipt-bronx.json").unlink()
        with self.assertRaises(ValueError):
            capture.replay(self.run_dir)

    def test_replay_rejects_changed_receipt_and_acl_failure(self):
        self.call_capture()
        receipt = self.run_dir / "receipt-bronx.json"
        data = json.loads(receipt.read_bytes())
        data["bytes"] += 1
        receipt.write_bytes(capture._json_bytes(data))
        with self.assertRaises(ValueError):
            capture.replay(self.run_dir)
        with patch.object(
            capture, "_verify_directory_acl", side_effect=ValueError("ACL")
        ):
            with self.assertRaisesRegex(ValueError, "ACL"):
                capture.replay(self.run_dir)

    def test_replay_rejects_failure_artifact_even_with_manifest(self):
        self.call_capture()
        (self.run_dir / "failure.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            capture.replay(self.run_dir)

    def test_private_root_symlink_and_acl_failure_stop_before_request(self):
        linked = self.private_root.parent / "linked"
        fake = FakeTransport()
        original_reparse = capture._reparse
        with (
            patch.object(capture, "PRIVATE_ROOT", linked),
            patch.object(
                capture,
                "_reparse",
                side_effect=lambda path: path == linked or original_reparse(path),
            ),
        ):
            with self.assertRaises(ValueError):
                self.call_capture(fake)
        self.assertEqual(fake.calls, [])
        run_dir = self.run_path(50)
        with patch.object(capture, "_secure_directory", side_effect=ValueError("ACL")):
            with self.assertRaisesRegex(ValueError, "ACL"):
                capture.capture_bundle(
                    run_dir, transport=fake, clock=lambda: WHEN, provenance=PROVENANCE
                )
        self.assertEqual(fake.calls, [])

    def test_request_timeout_and_total_clock_caps_are_validated(self):
        with self.assertRaises(ValueError):
            capture.BoundedClient(FakeTransport(), timeout=31)
        with self.assertRaises(ValueError):
            capture.BoundedClient(FakeTransport(), timeout=True)
        with self.assertRaises(ValueError):
            capture.capture_bundle(
                self.run_dir,
                transport=FakeTransport(),
                clock=lambda: datetime(2026, 9, 29),
                provenance=PROVENANCE,
            )
        self.assertFalse(self.run_dir.exists())

    def test_elapsed_transfer_limit_preserves_incomplete_run(self):
        ticks = iter(range(100))
        with patch.object(capture, "MAX_TRANSFER_SECONDS", 1):
            with self.assertRaises(TimeoutError):
                capture.capture_bundle(
                    self.run_dir,
                    transport=FakeTransport(),
                    clock=lambda: WHEN,
                    timer=lambda: next(ticks),
                    provenance=PROVENANCE,
                )
        self.assertTrue((self.run_dir / "intent.json").exists())
        self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_zip_validation_counts_against_total_capture_time(self):
        path = self.private_root / "synthetic.xlsx"
        path.write_bytes(workbook())
        ticks = iter(range(100))
        with patch.object(capture, "MAX_TOTAL_SECONDS", 2):
            with self.assertRaises(TimeoutError):
                capture._zip_stats(path, timer=lambda: next(ticks), total_start=0)

    def test_default_transport_has_no_proxy_or_credentials(self):
        handlers = []
        seen = []

        class Opener:
            @contextmanager
            def open(self, request, timeout):
                self_outer.assertEqual(request.get_method(), "GET")
                self_outer.assertEqual(
                    {key.lower(): value for key, value in request.header_items()},
                    {"user-agent": "TabPFN4RealEstate-U0/1.0"},
                )
                self_outer.assertEqual(timeout, 30)
                seen.append(request.full_url)
                with FakeResponse(workbook(), request.full_url) as response:
                    yield response

        self_outer = self

        def builder(*installed):
            handlers.extend(installed)
            return Opener()

        with patch.object(capture, "build_opener", side_effect=builder):
            for _, url in capture.BOROUGHS:
                with capture._http_transport("GET", url, 30):
                    pass
        self.assertEqual(seen, [url for _, url in capture.BOROUGHS])
        self.assertTrue(all(handlers[index].proxies == {} for index in range(0, 10, 2)))
        with self.assertRaises(ValueError):
            handlers[1].redirect_request(
                None, None, 302, "redirect", {}, "https://other.test"
            )

    def test_create_new_writer_does_not_replace_existing_artifact(self):
        path = self.private_root / "existing.json"
        path.write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            capture._write_new(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
