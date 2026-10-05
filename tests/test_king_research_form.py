"""Input, service, and display contract for the local King research form."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from scripts.king_historical_benchmark import NUMERIC_FEATURES
from scripts import king_research_predict as serving
from scripts import king_research_form as form


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads(
    (ROOT / "examples/king-research-request.json").read_text(encoding="utf-8")
)
FEATURE_NAMES = (*NUMERIC_FEATURES, f"zipcode={EXAMPLE['zipcode']}")
RESPONSE = {
    "amount": 200_000.25,
    "currency": "USD",
    "model": "xgboost",
    "status": "historical_research_only",
    "reference_period": "King County sales, January-February 2015",
    "certified_90_day_origin": False,
    "g_us_gate": "PENDING",
    "manifest_sha256": "a" * 64,
    "model_sha256": "b" * 64,
}


class KingResearchFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {name: str(value) for name, value in EXAMPLE.items()}

    def test_form_exposes_exactly_the_trained_fifteen_property_fields(self) -> None:
        self.assertEqual(len(form.FORM_FIELDS), 15)
        self.assertEqual(tuple(form.FORM_FIELDS), tuple(EXAMPLE))
        self.assertEqual(set(form.FORM_FIELDS), {*NUMERIC_FEATURES, "zipcode"})
        self.assertFalse(
            {"price", "asking_price", "target_price"} & set(form.FORM_FIELDS)
        )

    def test_parses_text_then_uses_the_existing_request_validator(self) -> None:
        with patch.object(
            serving, "validate_request", wraps=serving.validate_request
        ) as validate:
            parsed = form.parse_form_values(self.raw, FEATURE_NAMES)

        validate.assert_called_once()
        request, feature_names = validate.call_args.args
        self.assertEqual(feature_names, FEATURE_NAMES)
        self.assertEqual(tuple(request), tuple(EXAMPLE))
        self.assertEqual(request["zipcode"], EXAMPLE["zipcode"])
        self.assertTrue(
            all(type(request[name]) in (int, float) for name in NUMERIC_FEATURES)
        )
        self.assertEqual(parsed, serving.validate_request(EXAMPLE, FEATURE_NAMES))

    def test_rejects_missing_extra_invalid_and_unsupported_fields(self) -> None:
        invalid = (
            {**self.raw, "asking_price": "350000"},
            {**self.raw, "target_price": "350000"},
            {name: value for name, value in self.raw.items() if name != "bedrooms"},
            {**self.raw, "sqft_living": ""},
            {**self.raw, "sqft_living": "NaN"},
            {**self.raw, "bedrooms": "three"},
            {**self.raw, "waterfront": "2"},
            {**self.raw, "lat": "0"},
            {**self.raw, "zipcode": "99999"},
            {**self.raw, "zipcode": "9810"},
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                form.parse_form_values(raw, FEATURE_NAMES)

    def test_rejects_non_text_form_values(self) -> None:
        with self.assertRaises(ValueError):
            form.parse_form_values({**self.raw, "bedrooms": 3}, FEATURE_NAMES)

    def test_formats_estimate_with_full_historical_scope_warning(self) -> None:
        display = form.format_prediction(RESPONSE)

        self.assertIn("$200,000", display)
        self.assertIn("2015", display)
        self.assertRegex(display.lower(), r"historical research only")
        self.assertRegex(display.lower(), r"no calibrated interval")
        self.assertRegex(display.lower(), r"not (?:a )?current")
        self.assertRegex(display.lower(), r"not (?:a )?90.day")

    def test_rejects_incompatible_service_responses(self) -> None:
        incompatible = (
            {**RESPONSE, "status": "commercial"},
            {**RESPONSE, "certified_90_day_origin": True},
            {**RESPONSE, "currency": "EUR"},
            {**RESPONSE, "reference_period": "King County sales, 2026"},
            {**RESPONSE, "amount": -1},
            {**RESPONSE, "amount": float("nan")},
            {**RESPONSE, "amount": True},
            {name: value for name, value in RESPONSE.items() if name != "status"},
        )
        for response in incompatible:
            with self.subTest(response=response), self.assertRaises(ValueError):
                form.format_prediction(response)

    def test_headless_submit_flow_calls_the_cli_prediction_service(self) -> None:
        bundle_dir = Path("private-king-bundle")
        manifest_sha256 = "a" * 64
        with patch.object(serving, "predict", return_value=RESPONSE) as predict:
            response = form.predict_from_form(
                self.raw, bundle_dir, manifest_sha256, FEATURE_NAMES
            )

        predict.assert_called_once_with(
            bundle_dir,
            serving.validate_request(EXAMPLE, FEATURE_NAMES),
            manifest_sha256,
        )
        self.assertIn("$200,000", form.format_prediction(response))

    def test_tk_demo_populates_all_fifteen_fields(self) -> None:
        _root, ui = self.make_hidden_form()
        for entry in ui.entries.values():
            entry.delete(0, "end")
        ui.load_demo()
        self.assertEqual(
            {name: entry.get() for name, entry in ui.entries.items()}, self.raw
        )
        self.assertIn("Synthetic example loaded", ui.status_var.get())

    def test_tk_worker_error_reenables_controls_and_announces_failure(self) -> None:
        root, ui = self.make_hidden_form()
        with (
            patch.object(
                serving, "predict", side_effect=ValueError("bundle checksum mismatch")
            ),
            patch("tkinter.messagebox.showerror") as error_dialog,
        ):
            ui.submit()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.predict_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.01)
            self.assertFalse(ui.predict_button.instate(["disabled"]))
            self.assertIn("checksum mismatch", ui.status_var.get())
            self.assertFalse(ui.result_var.get())
            error_dialog.assert_called_once()

    def test_main_rejects_bad_bundle_before_opening_the_window(self) -> None:
        argv = [
            "king_research_form",
            "--bundle",
            "unused-bundle",
            "--manifest-sha256",
            "a" * 64,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                serving, "load_bundle", side_effect=ValueError("checksum mismatch")
            ),
            patch.object(form.tk, "Tk") as create_window,
            self.assertRaises(SystemExit) as exit_status,
        ):
            form.main()
        self.assertEqual(exit_status.exception.code, 2)
        create_window.assert_not_called()

    def make_hidden_form(self) -> tuple[tk.Tk, form.KingResearchForm]:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"A local Tk display is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        ui = form.KingResearchForm(root, Path("unused-bundle"), "a" * 64, FEATURE_NAMES)
        for name, value in self.raw.items():
            ui.entries[name].delete(0, "end")
            ui.entries[name].insert(0, value)
        root.update()  # Drain the initial focus callback before spying on field focus.
        return root, ui

    def test_tk_submit_stays_responsive_and_completes_on_the_main_thread(self) -> None:
        root, ui = self.make_hidden_form()
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        main_thread = threading.get_ident()
        result_threads: list[int] = []
        status_threads: list[int] = []
        set_result = ui.result_var.set
        set_status = ui.status_var.set

        def slow_predict(_bundle, _request, _digest):
            started.set()
            if not release.wait(timeout=1.5):
                raise TimeoutError("Mock prediction was not released")
            return RESPONSE

        def record_result(value: str) -> None:
            if value:
                result_threads.append(threading.get_ident())
            set_result(value)

        def record_status(value: str) -> None:
            status_threads.append(threading.get_ident())
            set_status(value)

        with (
            patch.object(serving, "predict", side_effect=slow_predict) as predict,
            patch.object(ui.result_var, "set", side_effect=record_result),
            patch.object(ui.status_var, "set", side_effect=record_status),
            patch("tkinter.messagebox.showinfo"),
            patch("tkinter.messagebox.showerror"),
        ):
            began = time.monotonic()
            ui.submit()
            self.assertLess(time.monotonic() - began, 0.5)
            self.assertTrue(started.wait(timeout=0.5))
            self.assertTrue(ui.predict_button.instate(["disabled"]))
            self.assertRegex(ui.status_var.get().lower(), r"predict|working|running")
            self.assertEqual(ui.result_var.get(), "")

            ui.submit()
            self.assertEqual(predict.call_count, 1)
            release.set()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not ui.result_var.get():
                root.update()
                time.sleep(0.01)
            self.assertIn("$200,000", ui.result_var.get())
            self.assertFalse(ui.predict_button.instate(["disabled"]))
            self.assertTrue(result_threads)
            self.assertEqual(set(result_threads), {main_thread})
            self.assertEqual(set(status_threads), {main_thread})

    def test_tk_locks_property_inputs_until_pending_result_finishes(self) -> None:
        root, ui = self.make_hidden_form()
        release = threading.Event()
        self.addCleanup(release.set)

        def slow_predict(_bundle, _request, _digest):
            if not release.wait(timeout=1.5):
                raise TimeoutError("Mock prediction was not released")
            return RESPONSE

        with (
            patch.object(serving, "predict", side_effect=slow_predict),
            patch("tkinter.messagebox.showinfo"),
        ):
            ui.submit()
            self.assertTrue(ui.predict_button.instate(["disabled"]))
            self.assertTrue(
                all(entry.instate(["disabled"]) for entry in ui.entries.values())
            )
            release.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.predict_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.01)
            self.assertFalse(ui.predict_button.instate(["disabled"]))
            self.assertTrue(
                all(not entry.instate(["disabled"]) for entry in ui.entries.values())
            )

    def test_tk_edit_after_result_clears_stale_estimate(self) -> None:
        root, ui = self.make_hidden_form()
        with (
            patch.object(serving, "predict", return_value=RESPONSE),
            patch("tkinter.messagebox.showinfo"),
        ):
            ui.submit()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not ui.result_var.get():
                root.update()
                time.sleep(0.01)
        self.assertIn("$200,000", ui.result_var.get())
        ui.entries["bedrooms"].delete(0, "end")
        ui.entries["bedrooms"].insert(0, "5")
        self.assertEqual(ui.result_var.get(), "")
        self.assertIn("changed", ui.status_var.get().lower())

    def test_tk_invalid_values_name_and_focus_the_field(self) -> None:
        root, ui = self.make_hidden_form()
        invalid = (
            ("waterfront", "2", r"0.*1"),
            ("lat", "0", r"47.*48"),
            ("bedrooms", "3.5", r"whole|integer"),
            ("zipcode", "99999", r"supported|training"),
        )
        with (
            patch.object(serving, "predict") as predict,
            patch("tkinter.messagebox.showinfo"),
            patch("tkinter.messagebox.showerror"),
        ):
            for name, bad_value, hint in invalid:
                with self.subTest(field=name):
                    for field, valid_value in self.raw.items():
                        ui.entries[field].delete(0, "end")
                        ui.entries[field].insert(0, valid_value)
                    predict.reset_mock()
                    entry = ui.entries[name]
                    entry.delete(0, "end")
                    entry.insert(0, bad_value)
                    with patch.object(entry, "focus_set") as focus:
                        ui.submit()
                    message = ui.status_var.get().lower()
                    self.assertIn(name, message)
                    self.assertRegex(message, hint)
                    self.assertEqual(ui.result_var.get(), "")
                    focus.assert_called_once_with()
                    predict.assert_not_called()
                    root.update()


if __name__ == "__main__":
    unittest.main()
