"""Synthetic offline tests for the single-GET NYC archive metadata probe."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import probe_nyc_archives as probe  # noqa: E402


CREATED_AT = "2026-09-15T15:57:00.489Z"
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def entry(version: int, start: int = 0, **overrides) -> dict:
    return {
        "createdAt": CREATED_AT,
        "version": version,
        "startVersion": start,
        "visible": True,
        **overrides,
    }


class ArchiveProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.private_root.mkdir(parents=True)
        self.run_dir = self.private_root / "archive-test"
        for name, value in (
            ("PRIVATE_ROOT", self.private_root),
            ("_secure_directory", lambda *_: None),
            ("_verify_directory_acl", lambda *_: None),
        ):
            bound = patch.object(probe, name, value)
            bound.start()
            self.addCleanup(bound.stop)

    def capture(self, body: bytes, **kwargs) -> dict:
        return probe.capture(
            self.run_dir,
            transport=lambda *_: (
                200,
                body,
                {"Content-Type": "application/json; charset=utf-8"},
            ),
            clock=lambda: NOW,
            **kwargs,
        )

    def test_observed_array_shape_with_zero_start_version(self) -> None:
        body = json.dumps([entry(53), entry(65, 64)]).encode()
        self.assertEqual(
            probe.extract_metadata(body)["versions"],
            [
                {
                    "version": 65,
                    "start_version": 64,
                    "created_at": CREATED_AT,
                    "visible": True,
                },
                {
                    "version": 53,
                    "start_version": 0,
                    "created_at": CREATED_AT,
                    "visible": True,
                },
            ],
        )

    def test_hidden_revision_is_validated_but_not_reported(self) -> None:
        parsed = probe.extract_metadata(
            json.dumps([entry(53, visible=False), entry(65, 64)]).encode()
        )
        self.assertEqual([row["version"] for row in parsed["versions"]], [65])

    def test_one_fixed_metadata_get_and_private_bytes_before_parse(self) -> None:
        calls = []
        body = json.dumps([entry(53), entry(54), entry(65, 64)]).encode()

        def transport(method, url, timeout):
            calls.append((method, url, timeout))
            return (
                200,
                body,
                {"Content-Type": "application/json", "Set-Cookie": "secret"},
            )

        result = probe.capture(self.run_dir, transport=transport, clock=lambda: NOW)
        self.assertEqual(calls, [("GET", probe.metadata_url(), 15)])
        self.assertEqual((self.run_dir / "metadata.bin").read_bytes(), body)
        self.assertEqual(result["metadata_sha256"], sha256(body).hexdigest())
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["content_type"], "application/json")
        self.assertEqual(result["captured_at_utc"], "2026-09-29T12:00:00+00:00")
        self.assertEqual(result["archive_availability"], "unverified")
        self.assertEqual(result["certification"], "none")
        self.assertEqual([x["version"] for x in result["versions"]], [65, 54, 53])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(probe.replay(self.run_dir), result)

    def test_invalid_metadata_remains_private_and_has_no_report(self) -> None:
        body = b'{"wrong":"shape"}'
        with self.assertRaisesRegex(ValueError, "array"):
            self.capture(body)
        self.assertEqual((self.run_dir / "metadata.bin").read_bytes(), body)
        self.assertTrue((self.run_dir / "manifest.json").is_file())
        with self.assertRaisesRegex(ValueError, "array"):
            probe.replay(self.run_dir)

    def test_http_error_status_is_recorded_as_incomplete_without_retry(self) -> None:
        calls = []

        def transport(method, url, timeout):
            calls.append((method, url, timeout))
            return 404, b"", {"Content-Type": "text/html", "Set-Cookie": "secret"}

        with self.assertRaisesRegex(ValueError, "404"):
            probe.capture(self.run_dir, transport=transport, clock=lambda: NOW)
        self.assertEqual(calls, [("GET", probe.metadata_url(), 15)])
        self.assertFalse((self.run_dir / "metadata.bin").exists())
        manifest = json.loads((self.run_dir / "manifest.json").read_text())
        self.assertEqual(manifest["http_status"], 404)
        self.assertEqual(manifest["content_type"], "text/html")
        self.assertEqual(manifest["run_status"], "incomplete_http_error")
        self.assertNotIn("secret", json.dumps(manifest))

    def test_strict_entry_validation_and_thirteen_entry_cap(self) -> None:
        invalid = (
            [entry(1), entry(1)],
            [entry(1, -1)],
            [entry(0)],
            [entry(True)],
            [entry(1, "0")],
            [entry(1, visible="true")],
            [entry(1, createdAt="2026-09-15T15:57:00")],
            [entry(1, createdAt="2026-09-15")],
            [entry(1, createdAt="2026-99-99T00:00:00Z")],
            [entry(1), "bad"],
            [entry(x) for x in range(1, 15)],
        )
        for records in invalid:
            with self.subTest(records=records), self.assertRaises(ValueError):
                probe.extract_metadata(json.dumps(records).encode())
        self.assertEqual(
            len(
                probe.extract_metadata(
                    json.dumps([entry(x) for x in range(1, 14)]).encode()
                )["versions"]
            ),
            13,
        )

    def test_metadata_body_and_response_caps(self) -> None:
        for body in (b"", b"{", b'"string"', b"x" * (probe.MAX_RESPONSE_BYTES + 1)):
            with self.subTest(body=body[:10]), self.assertRaises(ValueError):
                probe.extract_metadata(body)
        for timeout in (0, 16, True, "15"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                probe.BoundedClient(timeout=timeout)
        for response in (
            (302, b"[]"),
            (404, b"[]"),
            (True, b"[]"),
            (200, "[]"),
            (200,),
            [],
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                probe.BoundedClient(lambda *_: response).request(
                    "GET", probe.metadata_url()
                )
        with self.assertRaises(ValueError):
            probe.BoundedClient(
                lambda *_: (200, b"x" * (probe.MAX_RESPONSE_BYTES + 1))
            ).request("GET", probe.metadata_url())
        with self.assertRaisesRegex(ValueError, "content type"):
            probe.BoundedClient(
                lambda *_: (
                    200,
                    b"[]",
                    {"Content-Type": "application/json\r\nSet-Cookie: secret"},
                )
            ).request("GET", probe.metadata_url())
        with self.assertRaisesRegex(ValueError, "JSON content type"):
            probe.BoundedClient(
                lambda *_: (200, b"[]", {"Content-Type": "text/html"})
            ).request("GET", probe.metadata_url())

    def test_no_head_post_other_host_path_or_second_get(self) -> None:
        client = probe.BoundedClient(lambda *_: (200, b"[]"))
        for method, url in (
            ("HEAD", probe.metadata_url()),
            ("POST", probe.metadata_url()),
            ("PUT", probe.metadata_url()),
            ("GET", "https://example.com/api/archival?id=usep-8jbt&version=1"),
            (
                "GET",
                "https://data.cityofnewyork.us/api/archival.csv?id=usep-8jbt&version=1",
            ),
            ("GET", probe.metadata_url() + "&other=1"),
        ):
            with self.subTest(method=method, url=url), self.assertRaises(ValueError):
                client.request(method, url)
        self.assertEqual(client.count, 0)
        self.assertEqual(client.request("GET", probe.metadata_url())[0], b"[]")
        with self.assertRaisesRegex(ValueError, "cap"):
            client.request("GET", probe.metadata_url())

    def test_http_transport_streams_limit_and_no_redirect(self) -> None:
        test_case = self

        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __init__(self, body: bytes):
                self.stream = BytesIO(body)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self, size: int) -> bytes:
                return self.stream.read(size)

        class Opener:
            def __init__(self, body: bytes):
                self.body = body

            def open(self, request, *, timeout):
                test_case.assertEqual(request.get_method(), "GET")
                test_case.assertEqual(timeout, 15)
                return Response(self.body)

        with patch.object(probe, "build_opener", return_value=Opener(b"[]")) as builder:
            self.assertEqual(
                probe._http_get("GET", probe.metadata_url(), 15)[:2], (200, b"[]")
            )
            self.assertTrue(
                any(
                    isinstance(handler, ProxyHandler) and handler.proxies == {}
                    for handler in builder.call_args.args
                )
            )
        with patch.object(
            probe,
            "build_opener",
            return_value=Opener(b"x" * (probe.MAX_RESPONSE_BYTES + 1)),
        ):
            with self.assertRaisesRegex(ValueError, "byte cap"):
                probe._http_get("GET", probe.metadata_url(), 15)
        with patch.object(probe, "build_opener") as builder:
            builder.return_value.open.side_effect = HTTPError(
                probe.metadata_url(),
                404,
                "",
                {"Content-Type": "application/json", "Set-Cookie": "secret"},
                None,
            )
            self.assertEqual(
                probe._http_get("GET", probe.metadata_url(), 15),
                (404, b"", {"Content-Type": "application/json"}),
            )
        with self.assertRaisesRegex(ValueError, "redirect"):
            probe._NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://invalid.test"
            )

    def test_report_filters_content_type_and_never_overwrites(self) -> None:
        body = json.dumps([entry(53)]).encode()
        report_path = self.private_root.parent.parent.parent / "report.json"
        result = self.capture(body, report_path=report_path)
        self.assertEqual(json.loads(report_path.read_text()), result)
        with self.assertRaises(FileExistsError):
            self.capture(body)
        with self.assertRaises(FileExistsError):
            probe.replay(self.run_dir, report_path=report_path)
        self.assertNotIn("Content-Disposition", report_path.read_text())

    def test_private_path_and_replay_integrity(self) -> None:
        with self.assertRaises(ValueError):
            probe.capture(
                self.private_root.parent / "outside",
                transport=lambda *_: self.fail("network"),
            )
        with self.assertRaises(ValueError):
            probe.replay(self.run_dir)
        self.capture(json.dumps([entry(53)]).encode())
        (self.run_dir / "metadata.bin").write_bytes(b"[]")
        with self.assertRaisesRegex(ValueError, "hash"):
            probe.replay(self.run_dir)

    def test_replay_rejects_incomplete_manifest_with_matching_hash(self) -> None:
        self.capture(json.dumps([entry(53)]).encode())
        manifest_path = self.run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest_path.write_text(
            json.dumps({**manifest, "run_status": "incomplete_http_error"})
        )
        with self.assertRaisesRegex(ValueError, "status"):
            probe.replay(self.run_dir)

    def test_cli_plan_and_offline_replay(self) -> None:
        output = StringIO()
        with (
            patch.object(sys, "argv", ["probe_nyc_archives.py", "plan"]),
            patch("sys.stdout", output),
        ):
            probe.main()
        self.assertEqual(json.loads(output.getvalue())["request_cap"], 1)
        self.capture(json.dumps([entry(53)]).encode())
        output = StringIO()
        with (
            patch.object(
                sys, "argv", ["probe_nyc_archives.py", "replay", str(self.run_dir)]
            ),
            patch("sys.stdout", output),
        ):
            probe.main()
        self.assertEqual(json.loads(output.getvalue())["versions"][0]["version"], 53)


if __name__ == "__main__":
    unittest.main()
