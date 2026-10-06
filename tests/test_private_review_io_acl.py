from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import private_review_io as private


SID = "S-1-5-21-1"


class PrivateReviewAclBatchTests(unittest.TestCase):
    def test_windows_batch_uses_one_sid_and_one_acl_process(self) -> None:
        directories = (Path(r"C:\private"), Path(r"C:\private\bundle"))
        acl = json.dumps(
            [
                {"protected": True, "entries": [SID]},
                {"protected": True, "entries": [SID, "S-1-5-18"]},
            ]
        )
        responses = (
            SimpleNamespace(stdout=f'"USER","{SID}"\n'),
            SimpleNamespace(stdout=acl),
        )
        with patch.object(private.subprocess, "run", side_effect=responses) as run:
            private.verify_acl_many(directories)

        self.assertEqual(run.call_count, 2)
        powershell = run.call_args_list[1]
        self.assertEqual(powershell.args[0][0], "powershell")
        self.assertEqual(
            json.loads(powershell.kwargs["env"]["TABPFN_ACL_DIRS"]),
            [str(path) for path in directories],
        )

    def test_windows_batch_rejects_any_invalid_or_malformed_result(self) -> None:
        directories = (Path(r"C:\private"), Path(r"C:\private\bundle"))
        invalid = (
            [{"protected": True, "entries": [SID]}],
            [
                {"protected": True, "entries": [SID]},
                {"protected": False, "entries": [SID]},
            ],
            [
                {"protected": True, "entries": [SID]},
                {"protected": True, "entries": ["S-1-5-21-999"]},
            ],
            [
                {"protected": True, "entries": [SID]},
                {"protected": True, "entries": SID},
            ],
            {"protected": True, "entries": [SID]},
        )
        for value in invalid:
            with (
                self.subTest(value=value),
                patch.object(private, "user_sid", return_value=SID),
                patch.object(private, "_powershell_acl_many", return_value=value),
                self.assertRaisesRegex(ValueError, "ACL verification"),
            ):
                private.verify_acl_many(directories)

    def test_empty_batch_is_rejected(self) -> None:
        with patch.object(private, "user_sid") as user_sid:
            with self.assertRaisesRegex(ValueError, "requires a directory"):
                private.verify_acl_many(())
        user_sid.assert_not_called()

    def test_paths_are_json_data_and_malformed_process_output_fails(self) -> None:
        path = Path('C:/private/quote";Write-Host injected\nnext')
        with patch.object(
            private.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="not-json"),
        ) as run:
            with self.assertRaisesRegex(ValueError, "ACL verification"):
                private._powershell_acl_many((path,), SID)
        command = run.call_args.args[0][-1]
        environment = run.call_args.kwargs["env"]
        self.assertNotIn(str(path), command)
        self.assertEqual(json.loads(environment["TABPFN_ACL_DIRS"]), [str(path)])
