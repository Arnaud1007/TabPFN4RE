"""New-only orchestration for exact HCPA prospective releases."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import io
import json
import sys
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

import scripts.capture_hcpa_release as capture


NOW = datetime(2026, 10, 6, 12, 0, 0, 123456, tzinfo=UTC)
LISTED = {
    "allsales": {
        "filename": "allsales_09_25_2026.zip",
        "displayed_size": "69 MB",
        "displayed_last_updated": "9/25/2026 7:14AM",
    },
    "parcels": {
        "filename": "parcels_10_02_2026.zip",
        "displayed_size": "148 MB",
        "displayed_last_updated": "10/2/2026 11:41AM",
    },
}


def entry(family: str, filename: str) -> dict[str, str]:
    return {"family": family, "listed_filename": filename}


class HcpaNewReleaseCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.opener = Mock()
        self.events: list[str] = []

        @contextmanager
        def session_lock():
            self.events.append("lock_enter")
            try:
                yield
            finally:
                self.events.append("lock_exit")

        patches = (
            patch.object(capture, "prepare_private_root"),
            patch.object(capture, "_capture_session_lock", session_lock),
            patch.object(
                capture,
                "_resume_pending_registrations",
                side_effect=lambda: self.events.append("resume"),
            ),
            patch.object(
                capture.hcpa_listing,
                "fetch_listing",
                side_effect=lambda _opener: self.events.append("listing") or b"page",
            ),
            patch.object(
                capture.hcpa_listing,
                "parse_listing",
                side_effect=lambda _raw: dict(LISTED),
            ),
            patch.object(capture.secrets, "token_hex", return_value="11111111"),
        )
        for mocked in patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def run_new(self, represented: list[dict[str, str]], *, force: bool = False):
        captured: list[tuple[str, str, bool]] = []

        def exact(run_dir, family, filename, **kwargs):
            self.events.append(f"capture_{family}")
            captured.append((family, filename, kwargs["register_ledger"]))
            return {"family": family, "filename": filename}

        with (
            patch.object(
                capture,
                "replay",
                side_effect=lambda *_args: self.events.append("replay") or represented,
            ),
            patch.object(capture, "_capture_locked", side_effect=exact),
        ):
            result = capture.capture_new_releases(
                opener=self.opener, clock=lambda: NOW, force=force
            )
        return result, captured

    def test_first_check_captures_both_in_deterministic_order_under_one_lock(
        self,
    ) -> None:
        result, calls = self.run_new([])
        self.assertEqual(
            calls,
            [
                ("allsales", LISTED["allsales"]["filename"], True),
                ("parcels", LISTED["parcels"]["filename"], True),
            ],
        )
        self.assertEqual(result["captured_families"], ["allsales", "parcels"])
        self.assertEqual(result["skipped_existing_families"], [])
        self.assertEqual(
            self.events,
            [
                "lock_enter",
                "resume",
                "listing",
                "replay",
                "capture_allsales",
                "capture_parcels",
                "lock_exit",
            ],
        )

    def test_unchanged_filenames_skip_all_exact_downloads(self) -> None:
        represented = [
            entry("allsales", LISTED["allsales"]["filename"]),
            entry("parcels", LISTED["parcels"]["filename"]),
        ]
        result, calls = self.run_new(represented)
        self.assertEqual(calls, [])
        self.assertEqual(result["captured_families"], [])
        self.assertEqual(result["skipped_existing_families"], ["allsales", "parcels"])
        self.assertEqual(result["rechecked_existing_families"], [])

    def test_historical_membership_skips_only_represented_family(self) -> None:
        represented = [
            entry("allsales", LISTED["allsales"]["filename"]),
            entry("allsales", "allsales_10_02_2026.zip"),
        ]
        result, calls = self.run_new(represented)
        self.assertEqual(calls, [("parcels", LISTED["parcels"]["filename"], True)])
        self.assertEqual(result["captured_families"], ["parcels"])
        self.assertEqual(result["skipped_existing_families"], ["allsales"])

    def test_force_rechecks_existing_filenames_explicitly(self) -> None:
        represented = [
            entry("allsales", LISTED["allsales"]["filename"]),
            entry("parcels", LISTED["parcels"]["filename"]),
        ]
        result, calls = self.run_new(represented, force=True)
        self.assertEqual([item[0] for item in calls], ["allsales", "parcels"])
        self.assertEqual(result["rechecked_existing_families"], ["allsales", "parcels"])

        first_result, _first_calls = self.run_new([], force=True)
        self.assertEqual(first_result["rechecked_existing_families"], [])

    def test_singular_parcel_listing_fails_before_exact_download(self) -> None:
        malformed = {
            **LISTED,
            "parcels": {**LISTED["parcels"], "filename": "parcel_10_02_2026.zip"},
        }
        with (
            patch.object(capture.hcpa_listing, "parse_listing", return_value=malformed),
            patch.object(capture, "replay") as replay,
            patch.object(capture, "_capture_locked") as exact,
            self.assertRaises(ValueError),
        ):
            capture.capture_new_releases(opener=self.opener, clock=lambda: NOW)
        replay.assert_not_called()
        exact.assert_not_called()

    def test_partial_failure_aborts_later_family_and_retry_skips_registered(
        self,
    ) -> None:
        represented: list[dict[str, str]] = []
        calls: list[str] = []
        parcel_attempts = 0

        def partial_then_retry(_run_dir, family, filename, **_kwargs):
            nonlocal parcel_attempts
            calls.append(family)
            if family == "parcels":
                parcel_attempts += 1
                if parcel_attempts == 1:
                    raise RuntimeError("download failed")
            represented.append(entry(family, filename))
            return {"family": family, "filename": filename}

        with (
            patch.object(
                capture, "replay", side_effect=lambda *_args: list(represented)
            ),
            patch.object(capture, "_capture_locked", side_effect=partial_then_retry),
        ):
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                capture.capture_new_releases(opener=self.opener, clock=lambda: NOW)
            self.assertEqual(calls, ["allsales", "parcels"])
            self.assertEqual(
                represented,
                [entry("allsales", LISTED["allsales"]["filename"])],
            )
            calls.clear()
            result = capture.capture_new_releases(opener=self.opener, clock=lambda: NOW)
        self.assertEqual(calls, ["parcels"])
        self.assertEqual(result["skipped_existing_families"], ["allsales"])

    def test_summary_has_exact_privacy_safe_schema(self) -> None:
        result, _calls = self.run_new([])
        self.assertEqual(
            set(result),
            {
                "status",
                "source_url",
                "checked_at_utc",
                "observed_filenames",
                "captured_families",
                "skipped_existing_families",
                "rechecked_existing_families",
                "certified_sale_labels",
                "g_us_gate",
            },
        )
        self.assertEqual(result["certified_sale_labels"], 0)
        self.assertEqual(result["g_us_gate"], "PENDING")

    def test_cli_new_only_emits_safe_summary(self) -> None:
        expected = {
            "status": "complete",
            "captured_families": [],
            "skipped_existing_families": ["allsales", "parcels"],
        }
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["capture_hcpa_release", "--new-only"]),
            patch.object(capture, "capture_new_releases", return_value=expected) as run,
            redirect_stdout(output),
        ):
            self.assertEqual(capture.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), expected)
        self.assertFalse(run.call_args.kwargs["force"])


if __name__ == "__main__":
    unittest.main()
