"""Synthetic, offline contract tests for NYC source system-time aggregates."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import private_review_io  # noqa: E402
import probe_nyc_system_timestamps as probe  # noqa: E402


DATASET_IDS = ("usep-8jbt", "w2pb-icbu")
EARLY = "2026-09-01T00:00:00.000Z"
LATE = "2026-09-02T00:00:00.000Z"
SELECT = (
    "count(*) as row_count,"
    "count(:created_at) as created_count,"
    "count(:updated_at) as updated_count,"
    "min(:created_at) as min_created_at,"
    "max(:created_at) as max_created_at,"
    "min(:updated_at) as min_updated_at,"
    "max(:updated_at) as max_updated_at"
)


def aggregate(**changes: object) -> dict[str, object]:
    return {
        "row_count": 2,
        "created_count": 2,
        "updated_count": 2,
        "min_created_at": EARLY,
        "max_created_at": LATE,
        "min_updated_at": EARLY,
        "max_updated_at": LATE,
        **changes,
    }


def body(**changes: object) -> bytes:
    raw = {
        **aggregate(),
        "row_count": "2",
        "created_count": "2",
        "updated_count": "2",
        **changes,
    }
    return json.dumps([raw]).encode("utf-8")


def metadata(dataset_id: str, *, revision: int = 42) -> bytes:
    return json.dumps(
        {"id": dataset_id, "rowsUpdatedAt": revision, "viewLastModified": 43}
    ).encode("utf-8")


class ParseAggregateTests(unittest.TestCase):
    def test_accepts_exact_aggregate_for_both_fixed_sources(self) -> None:
        for dataset_id in DATASET_IDS:
            with self.subTest(dataset_id=dataset_id):
                self.assertEqual(probe.parse_aggregate(dataset_id, body()), aggregate())

    def test_rejects_unapproved_source_identifier(self) -> None:
        for dataset_id in ("other-id", "usep-8jbt/../other", "", None):
            with self.subTest(dataset_id=dataset_id):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(dataset_id, body())

    def test_rejects_invalid_or_oversized_response_bytes(self) -> None:
        cases = (
            None,
            "[]",
            b"",
            b"\xff",
            b"{",
            b" " * (probe.MAX_RESPONSE_BYTES + 1),
        )
        for value in cases:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], value)

    def test_requires_one_object_in_an_array(self) -> None:
        cases = (
            b"{}",
            b"[]",
            b"[null]",
            b"[1]",
            json.dumps([aggregate(), aggregate()]).encode(),
        )
        for value in cases:
            with self.subTest(value=value[:30]):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], value)

    def test_requires_exact_aggregate_columns_without_row_data(self) -> None:
        for value in (
            body(address="10 Example St"),
            body(sale_price="100"),
            json.dumps([{"n": 1}]).encode(),
            body().replace(b'"row_count": "2"', b'"row_count": "2", "row_count": "2"'),
        ):
            with self.subTest(value=value[:40]):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], value)

    def test_count_must_be_positive_integer_not_boolean(self) -> None:
        for value in (0, -1, True, 2.0, "0", "-1", " 2", "2.0", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], body(row_count=value))

    def test_both_nonnull_counts_must_match_row_count(self) -> None:
        for changes in ({"created_count": 1}, {"updated_count": 1}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], body(**changes))

    def test_requires_canonical_utc_timestamps(self) -> None:
        for value in (
            "2026-09-01T00:00:00+00:00",
            "2026-09-01T00:00:00.000+00:00",
            "2026-09-01T00:00:00",
            "2026-02-30T00:00:00.000Z",
            "2026-09-01",
            1,
            None,
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], body(min_created_at=value))

    def test_rejects_inverted_created_updated_ranges(self) -> None:
        for changes in (
            {"min_created_at": LATE, "max_created_at": EARLY},
            {"min_updated_at": LATE, "max_updated_at": EARLY},
            {"min_created_at": LATE, "min_updated_at": EARLY},
            {"max_created_at": LATE, "max_updated_at": EARLY},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    probe.parse_aggregate(DATASET_IDS[0], body(**changes))


class ProbeUrlTests(unittest.TestCase):
    def test_only_fixed_sources_and_aggregate_query(self) -> None:
        for dataset_id in DATASET_IDS:
            with self.subTest(dataset_id=dataset_id):
                url = probe.build_url(dataset_id)
                parsed = urlsplit(url)
                self.assertEqual(parsed.scheme, "https")
                self.assertEqual(parsed.netloc, "data.cityofnewyork.us")
                self.assertEqual(parsed.path, f"/resource/{dataset_id}.json")
                self.assertEqual(parse_qs(parsed.query), {"$select": [SELECT]})
                self.assertEqual(parsed.fragment, "")

    def test_other_identifiers_cannot_select_other_resources(self) -> None:
        for dataset_id in ("other-id", "usep-8jbt?x=1", "", None):
            with self.subTest(dataset_id=dataset_id):
                with self.assertRaises(ValueError):
                    probe.build_url(dataset_id)


class FakeSocket:
    def __init__(self, *, adjustable: bool = True) -> None:
        self.adjustable = adjustable
        self.timeouts: list[float] = []

    def settimeout(self, seconds: float) -> None:
        if not self.adjustable:
            raise OSError("synthetic socket timeout failure")
        self.timeouts.append(seconds)


class FakeHttpResponse(BytesIO):
    def __init__(
        self,
        content: bytes,
        url: str,
        *,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
        connection: FakeSocket | None = None,
    ) -> None:
        super().__init__(content)
        self.url = url
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.read_sizes: list[int] = []
        self.connection = connection or FakeSocket()
        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self.connection))
        self.read_timeouts: list[float | None] = []

    def geturl(self) -> str:
        return self.url

    def read1(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        self.read_timeouts.append(
            self.connection.timeouts[-1] if self.connection.timeouts else None
        )
        return super().read1(size)


class HttpBoundaryTests(unittest.TestCase):
    def test_fixed_get_accepts_json_and_reads_in_bounded_chunks(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        response = FakeHttpResponse(body(), url)
        with patch.object(probe.HTTP, "open", return_value=response) as opened:
            self.assertEqual(probe._http_get(url), body())
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.kwargs["timeout"], probe.TIMEOUT_SECONDS)
        self.assertEqual(opened.call_args.args[0].get_full_url(), url)
        self.assertTrue(response.read_sizes)
        self.assertLessEqual(max(response.read_sizes), 64 * 1024)

    def test_unlisted_url_is_rejected_before_http_open(self) -> None:
        with patch.object(probe.HTTP, "open") as opened:
            with self.assertRaises(ValueError):
                probe._http_get("https://data.cityofnewyork.us/resource/other.json")
        opened.assert_not_called()

    def test_status_redirect_and_content_type_are_rejected(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        responses = (
            FakeHttpResponse(body(), url, status=206),
            FakeHttpResponse(body(), "https://example.invalid/redirect"),
            FakeHttpResponse(body(), url, content_type="text/html"),
        )
        for response in responses:
            with self.subTest(status=response.status, url=response.url):
                with patch.object(probe.HTTP, "open", return_value=response):
                    with self.assertRaises(ValueError):
                        probe._http_get(url)

    def test_oversized_http_response_is_rejected(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        response = FakeHttpResponse(b" " * (probe.MAX_RESPONSE_BYTES + 1), url)
        with patch.object(probe.HTTP, "open", return_value=response):
            with self.assertRaises(ValueError):
                probe._http_get(url)
        self.assertLessEqual(max(response.read_sizes), probe.MAX_RESPONSE_BYTES + 1)

    def test_wall_clock_deadline_stops_response(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        response = FakeHttpResponse(body(), url)
        with (
            patch.object(probe.HTTP, "open", return_value=response),
            patch.object(
                probe.time,
                "monotonic",
                side_effect=(0.0, probe.TIMEOUT_SECONDS + 1.0),
            ),
        ):
            with self.assertRaises(TimeoutError):
                probe._http_get(url)

    def test_slow_open_reduces_socket_timeout_before_each_read(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        response = FakeHttpResponse(body(), url)
        ticks = iter((0.0,))

        def clock() -> float:
            return next(ticks, 12.25)

        with (
            patch.object(probe.HTTP, "open", return_value=response),
            patch.object(probe.time, "monotonic", side_effect=clock),
        ):
            self.assertEqual(probe._http_get(url), body())
        self.assertTrue(response.connection.timeouts)
        self.assertTrue(response.read_timeouts)
        self.assertTrue(all(value is not None for value in response.read_timeouts))
        self.assertTrue(all(0 < value <= 17.75 for value in response.read_timeouts))

    def test_socket_timeout_adjustment_failure_stops_before_read(self) -> None:
        url = probe.build_url(DATASET_IDS[0])
        response = FakeHttpResponse(
            body(), url, connection=FakeSocket(adjustable=False)
        )
        with patch.object(probe.HTTP, "open", return_value=response):
            with self.assertRaises((OSError, TimeoutError, ValueError)):
                probe._http_get(url)
        self.assertEqual(response.read_sizes, [])

    def test_git_ignore_check_rejects_unignored_path(self) -> None:
        with patch.object(
            probe.subprocess, "run", return_value=SimpleNamespace(returncode=1)
        ):
            with self.assertRaises(ValueError):
                probe._check_git_ignored(Path("data/raw/nyc_dof/probe"))


class CaptureReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.private_root.mkdir(parents=True)
        self.output_dir = self.private_root / "private-probe"
        private_root_patch = patch.object(
            probe, "PRIVATE_ROOT", self.private_root, create=True
        )
        private_root_patch.start()
        self.addCleanup(private_root_patch.stop)
        for target, attribute in (
            (probe, "_check_git_ignored"),
            (private_review_io, "secure_directory"),
            (private_review_io, "verify_acl"),
        ):
            bound = patch.object(target, attribute, return_value=None, create=True)
            bound.start()
            self.addCleanup(bound.stop)

    def test_capture_requests_two_fixed_aggregates_and_replays_offline(self) -> None:
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            parts = urlsplit(url)
            dataset_id = next(x for x in DATASET_IDS if x in parts.path)
            return body() if parts.query else metadata(dataset_id)

        captured = probe.capture(self.output_dir, fetch=fetch)
        self.assertEqual(
            calls,
            [
                url
                for dataset_id in DATASET_IDS
                for url in (
                    probe.metadata_url(dataset_id),
                    probe.build_url(dataset_id),
                    probe.metadata_url(dataset_id),
                )
            ],
        )
        self.assertTrue((self.output_dir / "manifest.json").is_file())
        for dataset_id in DATASET_IDS:
            self.assertEqual(
                (self.output_dir / f"{dataset_id}-aggregate.json").read_bytes(),
                body(),
            )
            self.assertEqual(
                (self.output_dir / f"{dataset_id}-before.json").read_bytes(),
                metadata(dataset_id),
            )
            self.assertEqual(
                (self.output_dir / f"{dataset_id}-after.json").read_bytes(),
                metadata(dataset_id),
            )
        with patch.object(
            socket, "create_connection", side_effect=AssertionError("network")
        ):
            self.assertEqual(probe.replay(self.output_dir), captured)
        self.assertEqual(len(calls), 6)

    def test_changed_source_revision_is_inconclusive(self) -> None:
        seen = {dataset_id: 0 for dataset_id in DATASET_IDS}

        def fetch(url: str) -> bytes:
            parts = urlsplit(url)
            dataset_id = next(x for x in DATASET_IDS if x in parts.path)
            if parts.query:
                return body()
            seen[dataset_id] += 1
            revision = (
                43 if dataset_id == DATASET_IDS[0] and seen[dataset_id] == 2 else 42
            )
            return metadata(dataset_id, revision=revision)

        result = probe.capture(self.output_dir, fetch=fetch)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(probe.replay(self.output_dir)["status"], "inconclusive")

    def test_existing_output_is_not_overwritten(self) -> None:
        probe.capture(self.output_dir, fetch=self._fixture_fetch)
        original = (self.output_dir / "manifest.json").read_bytes()
        with self.assertRaises((FileExistsError, ValueError)):
            probe.capture(self.output_dir, fetch=lambda _: b"bad")
        self.assertEqual((self.output_dir / "manifest.json").read_bytes(), original)

    def test_capture_rejects_directory_outside_private_root_before_fetch(self) -> None:
        outside = self.private_root.parent / "public-probe"
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return body()

        with self.assertRaises(ValueError):
            probe.capture(outside, fetch=fetch)
        self.assertFalse(outside.exists())
        self.assertEqual(calls, [])

    def test_capture_rejects_unignored_private_root_before_fetch(self) -> None:
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return body()

        with patch.object(
            probe,
            "_check_git_ignored",
            side_effect=ValueError("private root is not Git ignored"),
        ):
            with self.assertRaises(ValueError):
                probe.capture(self.output_dir, fetch=fetch)
        self.assertFalse(self.output_dir.exists())
        self.assertEqual(calls, [])

    def test_replay_uses_bounded_reads_for_private_raw_files(self) -> None:
        captured = probe.capture(self.output_dir, fetch=self._fixture_fetch)
        original_read_bytes = Path.read_bytes

        def guarded_read_bytes(path: Path) -> bytes:
            if path.name.endswith(("-before.json", "-aggregate.json", "-after.json")):
                raise AssertionError("Unbounded raw read is forbidden")
            return original_read_bytes(path)

        with patch.object(Path, "read_bytes", guarded_read_bytes):
            self.assertEqual(probe.replay(self.output_dir), captured)

    def test_replay_rejects_oversized_raw_file(self) -> None:
        probe.capture(self.output_dir, fetch=self._fixture_fetch)
        raw_path = self.output_dir / "usep-8jbt-aggregate.json"
        raw_path.write_bytes(b" " * (probe.MAX_RESPONSE_BYTES + 1))
        with self.assertRaises(ValueError):
            probe.replay(self.output_dir)

    def test_replay_rejects_tampered_manifest_provenance(self) -> None:
        probe.capture(self.output_dir, fetch=self._fixture_fetch)
        manifest_path = self.output_dir / "manifest.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        changes = (
            ("source_snapshot_sha256", "0" * 64),
            ("configuration_sha256", "0" * 64),
            ("run_id", "another-run"),
        )
        for key, value in changes:
            with self.subTest(key=key):
                tampered = {**original, key: value}
                manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    probe.replay(self.output_dir)
        manifest_path.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(probe.replay(self.output_dir)["status"], "diagnostic_only")

    def test_replay_rejects_future_retrieval_timestamp(self) -> None:
        probe.capture(self.output_dir, fetch=self._fixture_fetch)
        manifest_path = self.output_dir / "manifest.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        requests = [dict(item) for item in original["requests"]]
        requests[0]["retrieved_at_utc"] = "9999-12-31T23:59:59.999Z"
        manifest_path.write_text(
            json.dumps({**original, "requests": requests}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            probe.replay(self.output_dir)

    def test_replay_rejects_tampered_raw_aggregate(self) -> None:
        probe.capture(self.output_dir, fetch=self._fixture_fetch)
        raw_path = self.output_dir / "usep-8jbt-aggregate.json"
        raw_path.write_bytes(body(row_count="3"))
        with self.assertRaises(ValueError):
            probe.replay(self.output_dir)

    def test_failure_remains_incomplete_and_cannot_replay(self) -> None:
        calls = 0

        def fetch(_: str) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic source failure")
            return metadata(DATASET_IDS[0])

        with self.assertRaises(OSError):
            probe.capture(self.output_dir, fetch=fetch)
        self.assertFalse((self.output_dir / "manifest.json").exists())
        with self.assertRaises(ValueError):
            probe.replay(self.output_dir)

    @staticmethod
    def _fixture_fetch(url: str) -> bytes:
        parts = urlsplit(url)
        dataset_id = next(x for x in DATASET_IDS if x in parts.path)
        return body() if parts.query else metadata(dataset_id)


if __name__ == "__main__":
    unittest.main()
