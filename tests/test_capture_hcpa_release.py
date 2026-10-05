"""Offline checks for a bounded capture of one current HCPA ZIP release."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.request import Request
from zipfile import ZIP_DEFLATED, ZipFile

import scripts.capture_hcpa_release as capture


NOW = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
ALLSALES = "allsales_09_18_2026.zip"
PARCELS = "parcels_10_02_2026.zip"


def html(*, allsales: str = ALLSALES, action: str = "./Default.aspx") -> bytes:
    return f"""<html><body>
<form method="post" action="{action}" id="form1">
<input type="hidden" name="__EVENTTARGET" value="" />
<input type="hidden" name="__EVENTARGUMENT" value="" />
<input type="hidden" name="__VIEWSTATE" value="view+/=" />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="CA0B0334" />
<input type="hidden" name="__EVENTVALIDATION" value="event+/=" />
<table id="grdFiles_ctl00">
<tr><td><a href="javascript:__doPostBack(&#39;grdFiles$ctl00$ctl04$ctl00&#39;,&#39;&#39;)">{allsales}</a></td><td>68 MB</td><td>9/18/2026 7:14AM</td></tr>
<tr><td><a href="javascript:__doPostBack(&#39;grdFiles$ctl00$ctl20$ctl00&#39;,&#39;&#39;)">{PARCELS}</a></td><td>148 MB</td><td>10/2/2026 11:41AM</td></tr>
</table></form></body></html>""".encode()


def zip_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("sample.txt", "synthetic public-record fixture\n")
    return output.getvalue()


ZIP = zip_bytes()


class Response(BytesIO):
    def __init__(
        self,
        body: bytes,
        url: str,
        content_type: str,
        *,
        status: int = 200,
        length: str | None = "auto",
    ) -> None:
        super().__init__(body)
        self._url = url
        self.status = status
        self.headers = {"Content-Type": content_type}
        if content_type == "application/zip":
            self.headers["Content-Disposition"] = f"attachment; filename={ALLSALES}"
        if length == "auto":
            self.headers["Content-Length"] = str(len(body))
        elif length is not None:
            self.headers["Content-Length"] = length

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if size <= 0 or size > 256 * 1024 + 1:
            raise AssertionError("Network responses must be read in bounded chunks")
        return super().read(size)


class Opener:
    def __init__(self, page: bytes = html(), archive: bytes = ZIP) -> None:
        self.page = page
        self.archive = archive
        self.calls: list[tuple[str, bytes | None]] = []
        self.list_response: Response | None = None
        self.zip_response: Response | None = None

    def __call__(self, request: str | Request, *, timeout: int) -> Response:
        if not 0 < timeout <= 60:
            raise AssertionError("Unbounded network timeout")
        url = request.full_url if isinstance(request, Request) else request
        body = request.data if isinstance(request, Request) else None
        self.calls.append((url, body))
        if len(self.calls) == 1:
            if body is not None:
                raise AssertionError("Listing must be retrieved with GET")
            return self.list_response or Response(self.page, url, "text/html")
        if len(self.calls) == 2:
            if body is None:
                raise AssertionError("ZIP must be retrieved with POST")
            return self.zip_response or Response(self.archive, url, "application/zip")
        raise AssertionError("Unexpected third network request")


class HcpaReleaseCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "private"
        self.private_root.mkdir()
        self.run_dir = self.private_root / "capture-1"
        for name, value in (
            ("PRIVATE_ROOT", self.private_root),
            ("secure_directory", lambda _path: None),
            ("verify_acl", lambda _path: None),
        ):
            mocked = patch.object(capture, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def run_capture(self, opener: Opener, family: str = "allsales") -> dict:
        filename = ALLSALES if family == "allsales" else PARCELS
        return capture.capture(
            self.run_dir, family, filename, opener=opener, clock=lambda: NOW
        )

    def test_form_binds_whitelisted_filename_to_its_own_postback(self) -> None:
        selected = capture.parse_form(html(), "allsales", ALLSALES)
        self.assertEqual(selected["url"], capture.SOURCE_URL)
        self.assertEqual(
            selected["fields"],
            {
                "__EVENTTARGET": "grdFiles$ctl00$ctl04$ctl00",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": "view+/=",
                "__VIEWSTATEGENERATOR": "CA0B0334",
                "__EVENTVALIDATION": "event+/=",
            },
        )
        parcel = capture.parse_form(html(), "parcels", PARCELS)
        self.assertEqual(
            parcel["fields"]["__EVENTTARGET"], "grdFiles$ctl00$ctl20$ctl00"
        )

    def test_capture_streams_exact_zip_and_private_timestamped_manifest(self) -> None:
        opener = Opener()
        result = self.run_capture(opener)
        self.assertEqual([url for url, _ in opener.calls], [capture.SOURCE_URL] * 2)
        self.assertEqual(
            parse_qs(opener.calls[1][1].decode(), keep_blank_values=True)[
                "__EVENTTARGET"
            ],
            ["grdFiles$ctl00$ctl04$ctl00"],
        )
        self.assertEqual((self.run_dir / ALLSALES).read_bytes(), ZIP)
        self.assertEqual((self.run_dir / "listing.html").read_bytes(), html())
        self.assertEqual(result["listing_html_sha256"], sha256(html()).hexdigest())
        self.assertEqual(result["raw_zip_sha256"], sha256(ZIP).hexdigest())
        self.assertEqual(result["raw_zip_bytes"], len(ZIP))
        self.assertEqual(result["filename"], ALLSALES)
        self.assertRegex(result["code_commit"], r"\A[0-9a-f]{40}\Z")
        self.assertIs(type(result["dirty_tree_at_capture"]), bool)
        self.assertRegex(result["script_sha256"], r"\A[0-9a-f]{64}\Z")
        self.assertEqual(result["capture_completed_at_utc"], "2026-10-05T09:00:00Z")
        self.assertFalse(result["first_public_availability_verified"])
        self.assertEqual(result["certified_sale_labels"], 0)
        self.assertEqual(
            json.loads((self.run_dir / "manifest.json").read_text()), result
        )
        with self.assertRaises(FileExistsError):
            self.run_capture(Opener())

    def test_changed_or_malformed_listing_rejects_before_post(self) -> None:
        cases = (
            html(allsales="allsales_10_05_2026.zip"),
            html(action="https://other.example/Default.aspx"),
            html().replace(b'name="__VIEWSTATE"', b'name="OTHER"'),
            html().replace(b"grdFiles$ctl00$ctl04$ctl00", b"other$ctl00"),
            html().replace(b"</table>", b"</table><table id='grdFiles_ctl00'></table>"),
        )
        for index, page in enumerate(cases):
            with self.subTest(index=index):
                self.run_dir = self.private_root / f"bad-listing-{index}"
                opener = Opener(page=page)
                with self.assertRaises(ValueError):
                    self.run_capture(opener)
                self.assertEqual(len(opener.calls), 1)
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_unsafe_family_or_filename_rejects_without_network(self) -> None:
        for family, filename in (
            ("other", ALLSALES),
            ("allsales", "../" + ALLSALES),
            ("allsales", "C:\\temp\\bad.zip"),
            ("allsales", PARCELS),
        ):
            with self.subTest(family=family, filename=filename):
                opener = Opener()
                with self.assertRaises(ValueError):
                    capture.capture(
                        self.run_dir,
                        family,
                        filename,
                        opener=opener,
                        clock=lambda: NOW,
                    )
                self.assertEqual(opener.calls, [])

    def test_redirect_bad_status_type_magic_and_oversize_leave_no_manifest(
        self,
    ) -> None:
        wrong_name = Response(ZIP, capture.SOURCE_URL, "application/zip")
        wrong_name.headers["Content-Disposition"] = f"attachment; filename={PARCELS}"
        cases = (
            (
                "listing redirect",
                Response(html(), "https://other.example", "text/html"),
                None,
            ),
            (
                "zip redirect",
                None,
                Response(ZIP, "https://other.example", "application/zip"),
            ),
            (
                "zip status",
                None,
                Response(ZIP, capture.SOURCE_URL, "application/zip", status=403),
            ),
            ("zip type", None, Response(ZIP, capture.SOURCE_URL, "text/html")),
            (
                "zip magic",
                None,
                Response(b"not a ZIP", capture.SOURCE_URL, "application/zip"),
            ),
            ("wrong valid ZIP", None, wrong_name),
            (
                "zip size",
                None,
                Response(ZIP, capture.SOURCE_URL, "application/zip", length=None),
            ),
        )
        for index, (name, listing_response, zip_response) in enumerate(cases):
            with self.subTest(name=name):
                self.run_dir = self.private_root / f"bad-response-{index}"
                opener = Opener()
                opener.list_response = listing_response
                opener.zip_response = zip_response
                if name == "zip size":
                    with patch.object(capture, "MAX_ZIP_BYTES", len(ZIP) - 1):
                        with self.assertRaises(ValueError):
                            self.run_capture(opener)
                else:
                    with self.assertRaises(ValueError):
                        self.run_capture(opener)
                self.assertFalse((self.run_dir / "manifest.json").exists())

    def test_filename_outside_file_table_is_rejected(self) -> None:
        malformed = html().replace(
            f">{ALLSALES}</a>".encode(),
            f"></table>{ALLSALES}</a><table>".encode(),
        )
        with self.assertRaises(ValueError):
            capture.parse_form(malformed, "allsales", ALLSALES)

    def test_private_root_is_created_on_fresh_clone(self) -> None:
        root = self.private_root / "fresh-clone"
        (root / "data").mkdir(parents=True)
        with (
            patch.object(capture, "ROOT", root),
            patch.object(
                capture, "PRIVATE_ROOT", root / "data/raw/hcpa/prospective-releases"
            ),
        ):
            capture.prepare_private_root()
            self.assertTrue(capture.PRIVATE_ROOT.is_dir())


if __name__ == "__main__":
    unittest.main()
