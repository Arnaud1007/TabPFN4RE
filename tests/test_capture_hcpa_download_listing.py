"""HCPA listing captures are immutable observations, not sale availability."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.capture_hcpa_download_listing as listing


def page(
    *, allsales: str = "allsales_09_18_2026.zip", parcel: str = "parcels_10_02_2026.zip"
) -> bytes:
    return f"""<html><script>allsales_01_01_2000.zip</script>
    <table id="other"><tr><td>allsales_01_01_2000.zip</td><td>1 MB</td><td>1/1/2000 1:00AM</td></tr></table>
    <table id="grdFiles_ctl00">
      <tr><td><a href="javascript:ignored()">{allsales}</a></td><td>68 MB</td><td>9/18/2026 7:14AM</td></tr>
      <tr><td><a href="javascript:ignored()">{parcel}</a></td><td>148 MB</td><td>10/2/2026 11:41AM</td></tr>
    </table></html>""".encode()


class Response(BytesIO):
    def __init__(
        self,
        body: bytes,
        *,
        url: str | None = None,
        content_type: str = "text/html",
        length: str | None = None,
    ):
        super().__init__(body)
        self.url = url or listing.SOURCE_URL
        self.status = 200
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": length or str(len(body)),
        }

    def geturl(self) -> str:
        return self.url


class HcpaListingCaptureTests(unittest.TestCase):
    def test_parser_uses_only_expected_file_table_and_exact_families(self) -> None:
        observed = listing.parse_listing(page())
        self.assertEqual(observed["allsales"]["filename"], "allsales_09_18_2026.zip")
        self.assertEqual(
            observed["parcels"]["displayed_last_updated"], "10/2/2026 11:41AM"
        )
        self.assertNotIn("2000", json.dumps(observed))

    def test_parser_rejects_missing_duplicate_and_malformed_rows(self) -> None:
        cases = (
            page(allsales="allsales_bad.zip"),
            page().replace(
                b"</table></html>",
                b"<tr><td>allsales_09_18_2026.zip</td><td>68 MB</td><td>9/18/2026 7:14AM</td></tr></table></html>",
            ),
            page().replace(b"68 MB", b"bad size"),
            page().replace(b"9/18/2026 7:14AM", b"13/40/2026 7:14AM"),
            page().replace(b"<td>68 MB</td>", b""),
            page().replace(b"</table></html>", b"</html>"),
            (
                b'<table id="grdFiles_ctl00"><tr><td>allsales_09_18_2026.zip</td>'
                b"<td>68 MB</td><td>9/18/2026 7:14AM</td></tr><tr></table>"
                b'<table id="other"><td>parcels_10_02_2026.zip</td>'
                b"<td>148 MB</td><td>10/2/2026 11:41AM</td></tr></table>"
            ),
            (
                b'<table id="grdFiles_ctl00"><tr><td>allsales_09_18_2026.zip</td>'
                b"<td>68 MB</td><td>9/18/2026 7:14AM</td></tr>"
                b'<table id="other"><tr><td>parcels_10_02_2026.zip</td>'
                b"<td>148 MB</td><td>10/2/2026 11:41AM</td></tr></table>"
            ),
        )
        for payload in cases:
            with self.subTest(payload=payload[:60]), self.assertRaises(ValueError):
                listing.parse_listing(payload)

    def test_fetch_is_fixed_url_bounded_and_rejects_redirects(self) -> None:
        calls: list[tuple[str, int]] = []

        def opener(url: str, *, timeout: int) -> Response:
            calls.append((url, timeout))
            return Response(page())

        self.assertEqual(listing.fetch_listing(opener), page())
        self.assertEqual(calls, [(listing.SOURCE_URL, listing.TIMEOUT_SECONDS)])
        for response in (
            Response(page(), url="https://example.org/redirect"),
            Response(page(), content_type="application/octet-stream"),
            Response(page(), length=str(listing.MAX_HTML_BYTES + 1)),
            Response(b"x" * (listing.MAX_HTML_BYTES + 1)),
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                listing.fetch_listing(lambda _url, *, timeout: response)

    def test_saved_observation_is_private_safe_and_replay_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(listing, "PRIVATE_ROOT", root / "private"),
                patch.object(listing, "PUBLIC_ROOT", root / "runs"),
                patch.object(listing, "secure_directory"),
                patch.object(listing, "verify_acl"),
            ):
                (root / "runs").mkdir()
                started = datetime(2026, 10, 4, 19, 45, tzinfo=UTC)
                first_id = "u0-hcpa-listing-20261004T194500Z-12345678"
                second_id = "u0-hcpa-listing-20261004T194500Z-87654321"
                first = listing.save_capture(page(), first_id, started, started)
                second = listing.save_capture(page(), second_id, started, started)
                self.assertEqual(first["raw_html_sha256"], sha256(page()).hexdigest())
                self.assertEqual(first["status"], "observed_not_qualified")
                self.assertFalse(first["first_public_availability_verified"])
                self.assertNotIn("javascript:", json.dumps(first))
                self.assertNotEqual(
                    first["raw_html_private_path"], second["raw_html_private_path"]
                )
                self.assertEqual(
                    listing.verify_capture(
                        root / "runs" / first_id / "observation.json"
                    ),
                    first,
                )
                observation_path = root / "runs" / first_id / "observation.json"
                for change in (
                    {"status": "qualified"},
                    {"first_public_availability_verified": True},
                    {"certified_sale_labels": 100},
                    {"capture_completed_at_utc": "bad"},
                    {"code_commit": "bad"},
                    {"unregistered_field": "surprise"},
                ):
                    with self.subTest(change=change):
                        observation_path.write_text(json.dumps({**first, **change}))
                        with self.assertRaises(ValueError):
                            listing.verify_capture(observation_path)
                observation_path.write_text(json.dumps(first))
                with self.assertRaises(FileExistsError):
                    listing.save_capture(page(), first_id, started, started)
                third_id = "u0-hcpa-listing-20261004T194500Z-abcdef12"

                original_new_file = listing.new_file

                def fail_manifest(path: Path, content: bytes) -> None:
                    if path.name.endswith(".manifest.sha256"):
                        raise RuntimeError("simulated sidecar write failure")
                    original_new_file(path, content)

                with patch.object(listing, "new_file", side_effect=fail_manifest):
                    with self.assertRaises(RuntimeError):
                        listing.save_capture(page(), third_id, started, started)
                self.assertTrue((root / "runs" / third_id / ".incomplete").exists())
                self.assertFalse(
                    (root / "runs" / third_id / "observation.json").exists()
                )
                (root / "private" / f"{first_id}.html").write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "hash|size"):
                    listing.verify_capture(
                        root / "runs" / first_id / "observation.json"
                    )

    def test_verification_does_not_create_missing_private_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            with (
                patch.object(listing, "PRIVATE_ROOT", root / "missing-private"),
                patch.object(listing, "PUBLIC_ROOT", root / "runs"),
            ):
                run_id = "u0-hcpa-listing-20261004T194500Z-12345678"
                with self.assertRaises(ValueError):
                    listing.verify_capture(root / "runs" / run_id / "observation.json")
                self.assertFalse((root / "missing-private").exists())


if __name__ == "__main__":
    unittest.main()
