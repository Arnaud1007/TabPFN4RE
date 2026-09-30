"""Synthetic, offline checks for one-home NYC source lookups."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_nyc_review_lookups_v1 as lookup  # noqa: E402
import profile_nyc_rolling_snapshot as profile  # noqa: E402
from scripts import review_nyc_sample as review  # noqa: E402


def _jsonl(rows: list[dict]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


class LookupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.raw = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.raw.mkdir(parents=True)
        self.review_dir = self.raw / "manual-review-v1"
        self.review_dir.mkdir()
        rows = []
        for borough, block in ((1, 10), (2, 20), (5, 30)):
            row = dict.fromkeys(profile.HEADER, "")
            row.update(
                {
                    "BOROUGH": str(borough),
                    "BLOCK": str(block),
                    "LOT": "1",
                    "SALE DATE": "01/01/2026",
                    "SALE PRICE": "123456",
                }
            )
            rows.append(row)
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=profile.HEADER)
        writer.writeheader()
        writer.writerows(rows)
        source_body = stream.getvalue().encode()
        self.source = self.raw / "source.csv"
        self.source.write_bytes(source_body)
        source_hash = sha256(source_body).hexdigest()
        sample_rows = [
            {
                "ordinal": ordinal,
                "rank": sha256(
                    f"nyc-review-v1|{source_hash}|42|{ordinal}".encode()
                ).hexdigest(),
                "structural_cell": f"{row['BOROUGH']}:candidate",
            }
            for ordinal, row in enumerate(rows, 1)
        ]
        sample_body = _jsonl(sample_rows)
        self.sample = self.raw / "sample.jsonl"
        self.sample.write_bytes(sample_body)
        self.ledger = self.review_dir / "reviews.jsonl"
        self.ledger.write_bytes(b"")
        self.manifest = self.review_dir / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "ledger_id": "synthetic-ledger",
                    "protocol": review.PROTOCOL,
                    "source_sha256": source_hash,
                    "sample_sha256": sha256(sample_body).hexdigest(),
                    "created_at": "2026-09-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        codes = [
            {"doc__type": kind, "doc__type_description": kind}
            for kind in ("DEED", "DEEDP", "DEEDO", "DEED, RC", "CDEC")
        ]
        code_body = json.dumps(codes).encode()
        self.codes = self.raw / "codes.json"
        self.codes.write_bytes(code_body)
        self.run_dir = self.raw / "lookup-v1-test"
        for module, name, value in (
            (review, "RAW_ROOT", self.raw),
            (review, "SOURCE_SHA256", source_hash),
            (review, "SAMPLE_SHA256", sha256(sample_body).hexdigest()),
            (review, "SOURCE_ROWS", 3),
            (review, "SAMPLE_COUNT", 3),
            (lookup, "CODE_TABLE_SHA256", sha256(code_body).hexdigest()),
            (lookup, "CODE_ROWS", 5),
        ):
            applied = patch.object(module, name, value)
            applied.start()
            self.addCleanup(applied.stop)
        for module, name in (
            (review.private_io, "verify_acl"),
            (lookup, "_secure_directory"),
            (lookup, "_verify_directory_acl"),
        ):
            applied = patch.object(module, name, return_value=None)
            applied.start()
            self.addCleanup(applied.stop)

    def _run(self, opener):
        return lookup.run_lookup(
            self.source,
            self.sample,
            self.ledger,
            self.manifest,
            self.codes,
            self.run_dir,
            opener=opener,
            sleep=lambda _: None,
        )

    def _responses(self, *, duplicate_master=False, saturated_bbl=False):
        calls = []

        def opener(url, timeout):
            self.assertEqual(timeout, 30)
            calls.append(url)
            query = parse_qs(urlsplit(url).query)
            where = query["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                block = where.split("block=")[1].split()[0]
                base = {
                    "document_id": "D1",
                    "borough": borough,
                    "block": block,
                    "lot": "1",
                }
                return json.dumps([base] * (251 if saturated_bbl else 1)).encode()
            if "bnx9-e6tj" in url:
                row = {
                    "document_id": "D1",
                    "doc_type": "DEED",
                    "document_date": "2026-01-02",
                }
                return json.dumps([row, row] if duplicate_master else [row]).encode()
            return json.dumps(
                [
                    {
                        "document_id": "D1",
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "",
                    }
                ]
            ).encode()

        return opener, calls

    def test_selects_lowest_ranked_unreviewed_acris_row(self):
        selected = lookup.choose_next(
            self.source, self.sample, self.ledger, self.manifest
        )
        self.assertIn(selected["borough"], (1, 2))
        self.assertEqual(
            selected["ordinal"],
            min(
                (1, 2),
                key=lambda n: sha256(
                    f"nyc-review-v1|{review.SOURCE_SHA256}|42|{n}".encode()
                ).hexdigest(),
            ),
        )
        self.assertNotIn("price", selected)

    def test_capture_replay_and_public_redaction(self):
        opener, calls = self._responses()
        result = self._run(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual(result["http_requests"], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("D1", json.dumps(result))
        self.assertNotIn("123456", json.dumps(result))
        replayed = lookup.replay_lookup(
            self.source, self.sample, self.codes, self.run_dir
        )
        self.assertEqual(replayed, result)
        self.assertEqual(len(calls), 3)
        self.assertEqual(self._run(lambda *_: self.fail("network")), result)

    def test_tampered_source_stops_before_network_or_run_creation(self):
        self.source.write_bytes(self.source.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_bad_sample_rank_stops_before_network(self):
        body = self.sample.read_text(encoding="utf-8").replace(
            '"rank": "', '"rank": "x', 1
        )
        self.sample.write_text(body, encoding="utf-8")
        with self.assertRaises(ValueError):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_duplicate_master_is_unresolved_and_bytes_are_saved(self):
        opener, calls = self._responses(duplicate_master=True)
        result = self._run(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertTrue((self.run_dir / "response-002.bin").is_file())
        self.assertEqual(
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir),
            result,
        )

    def test_saturated_bbl_remains_unresolved_without_master_query(self):
        opener, calls = self._responses(saturated_bbl=True)
        result = self._run(opener)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["document_triage_finished"])
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_offline_replay_rejects_response_tampering(self):
        self._run(self._responses()[0])
        path = self.run_dir / "response-001.bin"
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir)


if __name__ == "__main__":
    unittest.main()
