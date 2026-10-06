from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import verify_king_xgboost_json as verifier


FIXTURE = Path(__file__).parent / "fixtures/xgboost_3_2_numeric_gbtree.json"


class VerifyKingXGBoostJsonTests(unittest.TestCase):
    def test_rows_include_seeded_random_and_every_threshold_boundary(self) -> None:
        document = json.loads(FIXTURE.read_bytes())
        rows = verifier._verification_rows(document, 2)

        internal_nodes = [
            (tree, node)
            for tree in document["learner"]["gradient_booster"]["model"]["trees"]
            for node, left in enumerate(tree["left_children"])
            if left != -1
        ]
        self.assertEqual(len(rows), 1_000 + 3 * len(internal_nodes))
        self.assertEqual(rows, verifier._verification_rows(document, 2))
        boundary_rows = rows[1_000:]
        for index, (tree, node) in enumerate(internal_nodes):
            for row in boundary_rows[index * 3 : index * 3 + 3]:
                self.assertTrue(verifier._reaches_node(tree, row, node))
        for threshold in (47.5328, -2.5, 0.0):
            boundaries = verifier._float32_boundaries(threshold)
            self.assertEqual(len({verifier._f32_hex(v) for v in boundaries}), 3)
            self.assertLess(boundaries[0], boundaries[1])
            self.assertLess(boundaries[1], boundaries[2])

    def test_model_reader_requires_regular_hash_matched_bounded_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model.json"
            content = FIXTURE.read_bytes()
            model.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()

            self.assertEqual(verifier._read_model(model, digest), content)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verifier._read_model(model, "0" * 64)
            with self.assertRaisesRegex(ValueError, "regular"):
                verifier._read_model(root / "missing.json", digest)


if __name__ == "__main__":
    unittest.main()
