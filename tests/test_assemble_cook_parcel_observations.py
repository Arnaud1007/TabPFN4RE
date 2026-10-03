"""Synthetic tests for the offline Cook parcel-observation staging boundary."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from scripts import assemble_cook_parcel_observations as stage
from scripts import capture_cook_sales_audit as capture


def _rows() -> list[dict]:
    return [
        {
            "row_id": f"row-{ordinal:03}",
            "pin": f"{ordinal:014}",
            "sale_date": "2024-01-01T00:00:00.000",
            "sale_price": "123456.78",
            "doc_no": "repeated-document" if ordinal <= 2 else f"doc-{ordinal}",
            "is_multisale": False,
            "num_parcels_sale": "1",
        }
        for ordinal in range(1, 201)
    ]


def _pages() -> list[dict]:
    return [
        {
            "file": f"rows-{cell.slug}-{page_index}.json",
            "sha256": sha256(f"page-{index}".encode()).hexdigest(),
            "retrieved_at": "2026-10-03T00:42:14Z",
            "row_ids": [
                f"row-{ordinal:03}"
                for ordinal in range(index * 10 + 1, index * 10 + 11)
            ],
        }
        for index, (cell, page_index) in enumerate(
            (item for cell in capture.CELLS for item in ((cell, 0), (cell, 1)))
        )
    ]


class BuildObservationTests(unittest.TestCase):
    def test_replays_captured_order_page_lineage_and_keeps_source_immutable(
        self,
    ) -> None:
        rows, pages = _rows(), _pages()
        original = deepcopy(rows)

        content = stage.build_observations(rows, pages)
        observations = [json.loads(line) for line in content.splitlines()]

        self.assertEqual(rows, original)
        self.assertEqual(len(observations), 200)
        self.assertEqual(
            [item["ordinal"] for item in observations], list(range(1, 201))
        )
        self.assertEqual(
            observations[0]["observation"]["raw_fields"]["row_id"], "row-001"
        )
        self.assertEqual(
            observations[9]["observation"]["response_sha256"], pages[0]["sha256"]
        )
        self.assertEqual(
            observations[10]["observation"]["response_sha256"], pages[1]["sha256"]
        )
        self.assertEqual(
            observations[0]["observation"]["raw_fields"]["doc_no"], "repeated-document"
        )
        self.assertEqual(
            observations[1]["observation"]["raw_fields"]["doc_no"], "repeated-document"
        )
        self.assertNotIn(b"eligible_prior_sale", content)
        self.assertNotIn(b"close_date", content)

    def test_rejects_unexpected_source_field_and_nested_value(self) -> None:
        for value in ("personal", {"nested": True}):
            with self.subTest(value=value):
                rows = _rows()
                rows[0]["unrequested"] = value
                with self.assertRaises(ValueError):
                    stage.build_observations(rows, _pages())

    def test_rejects_wrong_count_order_and_page_metadata(self) -> None:
        cases = [
            (_rows()[:-1], _pages()),
            (list(reversed(_rows())), _pages()),
            (_rows(), _pages()[:-1]),
            (_rows(), [{**_pages()[0], "sha256": "bad"}, *_pages()[1:]]),
            (_rows(), [{**_pages()[0], "retrieved_at": "tomorrow"}, *_pages()[1:]]),
        ]
        for rows, pages in cases:
            with self.subTest(case=(len(rows), len(pages))):
                with self.assertRaises(ValueError):
                    stage.build_observations(rows, pages)

    def test_rejects_oversize_private_observation_file(self) -> None:
        with patch.object(stage, "MAX_OBSERVATIONS_BYTES", 1024):
            with self.assertRaisesRegex(ValueError, "byte cap"):
                stage.build_observations(_rows(), _pages())


class SourceReplayTests(unittest.TestCase):
    def _manifest(self) -> bytes:
        return json.dumps(
            {
                "responses": [
                    {
                        field: value
                        for field, value in page.items()
                        if field != "row_ids"
                    }
                    for page in _pages()
                ],
                "sample_row_ids": [row["row_id"] for row in _rows()],
            }
        ).encode()

    def test_page_mapping_is_from_pinned_manifest_after_capture_replay(self) -> None:
        raw = self._manifest()
        with (
            patch.object(stage, "CAPTURE_SHA256", sha256(raw).hexdigest()),
            patch.object(stage.review, "_capture_rows", return_value=_rows()) as replay,
            patch.object(
                stage.private_io, "private_path", return_value=Path("manifest.json")
            ),
            patch.object(stage.review, "_bounded", return_value=raw),
        ):
            rows, pages = stage._source_rows()
        replay.assert_called_once_with()
        self.assertEqual(rows, _rows())
        self.assertEqual(pages, _pages())

    def test_source_schema_drift_fails_before_capture_replay(self) -> None:
        with (
            patch.object(stage, "CORE_SELECT_FIELDS", ("wrong",)),
            patch.object(stage.review, "_capture_rows") as replay,
        ):
            with self.assertRaisesRegex(ValueError, "fields differ"):
                stage._source_rows()
        replay.assert_not_called()

    def test_manifest_hash_and_inventory_tampering_fail(self) -> None:
        raw = self._manifest()
        cases = [
            (raw, "0" * 64),
            (b"{", sha256(b"{").hexdigest()),
            (b"[]", sha256(b"[]").hexdigest()),
            (json.dumps({"responses": [], "sample_row_ids": []}).encode(), None),
        ]
        for content, pinned in cases:
            with self.subTest(content=content[:20]):
                with (
                    patch.object(
                        stage, "CAPTURE_SHA256", pinned or sha256(content).hexdigest()
                    ),
                    patch.object(stage.review, "_capture_rows", return_value=_rows()),
                    patch.object(
                        stage.private_io,
                        "private_path",
                        return_value=Path("manifest.json"),
                    ),
                    patch.object(stage.review, "_bounded", return_value=content),
                ):
                    with self.assertRaises(ValueError):
                        stage._source_rows()

    def test_cli_reports_only_public_summary_or_generic_failure(self) -> None:
        summary = stage.public_summary(b"synthetic")
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(stage, "run", return_value=summary) as run,
            redirect_stdout(stdout),
        ):
            self.assertEqual(stage.main(["run", "--output", "synthetic.json"]), 0)
        run.assert_called_once_with(Path("synthetic.json"))
        self.assertEqual(json.loads(stdout.getvalue()), summary)
        with (
            patch.object(stage, "verify", side_effect=ValueError("private row-001")),
            redirect_stderr(stderr),
        ):
            self.assertEqual(stage.main(["verify", "--run-dir", "synthetic"]), 1)
        self.assertNotIn("row-001", stderr.getvalue())


class PersistenceTests(unittest.TestCase):
    def _private_patches(self, root: Path, rows: list[dict], pages: list[dict]):
        return (
            patch.object(stage, "RAW_ROOT", root),
            patch.object(stage, "_source_rows", return_value=(rows, pages)),
            patch.object(stage.private_io, "secure_directory"),
            patch.object(stage.private_io, "verify_acl"),
        )

    def test_run_is_create_only_and_verify_replays_exact_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            raw, public = base / "raw", base / "public"
            raw.mkdir()
            public.mkdir()
            output = public / "aggregate.json"
            rows, pages = _rows(), _pages()
            patches = self._private_patches(raw, rows, pages)
            with patches[0], patches[1], patches[2], patches[3]:
                summary = stage.run(output)
                self.assertEqual(summary, stage.verify(raw / stage.RUN_NAME))
                self.assertEqual(set(summary), stage.PUBLIC_FIELDS)
                self.assertEqual(summary["certified_sale_labels"], 0)
                self.assertEqual(summary["u0_gate"], "PENDING")
                self.assertNotIn("row-001", output.read_text(encoding="utf-8"))
                self.assertNotIn(
                    "repeated-document", output.read_text(encoding="utf-8")
                )
                with self.assertRaises(FileExistsError):
                    stage.run(public / "second.json")
                self.assertFalse((public / "second.json").exists())

    def test_interrupted_or_tampered_file_set_fails_without_public_summary(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            raw, public = base / "raw", base / "public"
            raw.mkdir()
            public.mkdir()
            rows, pages = _rows(), _pages()
            patches = self._private_patches(raw, rows, pages)
            with patches[0], patches[1], patches[2], patches[3]:
                stage.run(public / "initial.json")
                observation_path = raw / stage.RUN_NAME / "observations.jsonl"
                original = observation_path.read_bytes()
                observation_path.write_bytes(original.replace(b"row-001", b"row-999"))
                with self.assertRaises(ValueError):
                    stage.verify(raw / stage.RUN_NAME)
                observation_path.write_bytes(original)
                (raw / stage.RUN_NAME / "complete.json").unlink()
                with self.assertRaises(ValueError):
                    stage.verify(raw / stage.RUN_NAME)

    def test_source_replay_change_fails_verification(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            raw, public = base / "raw", base / "public"
            raw.mkdir()
            public.mkdir()
            rows, pages = _rows(), _pages()
            patches = self._private_patches(raw, rows, pages)
            with patches[0], patches[1], patches[2], patches[3]:
                stage.run(public / "initial.json")
                with patch.object(
                    stage, "_source_rows", return_value=(rows, _pages()[::-1])
                ):
                    with self.assertRaises(ValueError):
                        stage.verify(raw / stage.RUN_NAME)


if __name__ == "__main__":
    unittest.main()
