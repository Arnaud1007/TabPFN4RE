"""Input, service, and display contract for the local King research form."""

from __future__ import annotations

import builtins
import io
import json
import math
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from scripts import king_research_form as form
from scripts import king_research_predict as serving
from scripts import king_prospective_enrollment as enrollment
from scripts.king_historical_benchmark import NUMERIC_FEATURES

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

    def test_load_request_file_accepts_only_a_bounded_valid_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
            loaded = form.load_request_file(path, FEATURE_NAMES)
            self.assertEqual(loaded, serving.validate_request(EXAMPLE, FEATURE_NAMES))

            invalid = (
                b"{not json",
                json.dumps(EXAMPLE).encode("utf-16"),
                json.dumps(EXAMPLE)
                .replace('"bedrooms": 3', '"bedrooms": 3, "bedrooms": 4')
                .encode(),
                json.dumps({**EXAMPLE, "asking_price": 350000}).encode(),
                json.dumps({**EXAMPLE, "zipcode": "99999"}).encode(),
                b" " * (form.MAX_REQUEST_BYTES + 1),
            )
            for index, content in enumerate(invalid):
                with self.subTest(index=index):
                    path.write_bytes(content)
                    with self.assertRaises((ValueError, OSError, TypeError)):
                        form.load_request_file(path, FEATURE_NAMES)

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

    def test_formats_exact_absolute_bundle_response_with_conditional_scope(
        self,
    ) -> None:
        bundle = serving.VerifiedBundle(
            FEATURE_NAMES,
            b"model",
            "a" * 64,
            "b" * 64,
            serving.ABSOLUTE_PROTOCOL,
            "reg:absoluteerror",
            "2015-03-01",
            "King County sales before March 2015",
            "King County sales, November 2014-February 2015",
        )
        response = serving._prediction_response(200_000.25, bundle)
        display = form.format_prediction(response).lower()
        self.assertIn("$200,000", display)
        self.assertIn("median-like", display)
        self.assertIn("conditional", display)
        self.assertIn("within 90 days", display)
        self.assertIn("does not certify", display)

    def test_scope_warning_tracks_loaded_bundle_protocol(self) -> None:
        absolute = form.scope_warning(serving.ABSOLUTE_PROTOCOL)
        legacy = form.scope_warning("king_historical_sale_date_v1")

        self.assertIn("median-like", absolute)
        self.assertIn("within 90 days", absolute)
        self.assertIn("does not certify", absolute)
        self.assertIn("January–February 2015", legacy)
        self.assertNotEqual(absolute, legacy)

    def test_formats_experimental_fhfa_illustration_and_warning(self) -> None:
        response = {
            **RESPONSE,
            "experimental_hpi_adjustment": {
                "amount": 434_813.40,
                "status": "research_only",
                "warning": (
                    "Research only: this applies average market appreciation and is "
                    "not a current valuation, not a 90-day estimate, and not "
                    "property-specific."
                ),
            },
        }

        display = form.format_prediction(response).lower()

        self.assertIn("fhfa metro-indexed illustration: $434,813 usd", display)
        self.assertIn("average market appreciation", display)
        self.assertIn("not a current valuation", display)
        self.assertIn("not a 90-day estimate", display)
        self.assertIn("not property-specific", display)

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

    def test_startup_reuses_one_verified_model_for_two_tk_submissions(self) -> None:
        root, ui_instances = self._empty_tk_root()
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        loaded_models = []
        predicted_models = []
        observed: dict[str, object] = {}
        bundle = serving.VerifiedBundle(
            FEATURE_NAMES, b"mock model bytes", "a" * 64, "b" * 64
        )
        fake_xgboost = ModuleType("xgboost")

        class CountingRegressor:
            def load_model(self, content):
                self.assert_bytes = bytes(content)
                started.set()
                release.wait(timeout=1.5)
                loaded_models.append(self)

            def predict(self, _matrix):
                predicted_models.append(self)
                return [math.log(200_000 + 50_000 * (len(predicted_models) - 1))]

        fake_xgboost.XGBRegressor = CountingRegressor

        real_form_class = form.KingResearchForm

        def capture_form(*args, **kwargs):
            ui = real_form_class(*args, **kwargs)
            ui_instances.append(ui)
            return ui

        def run_form_flow():
            observed["window_delay"] = time.monotonic() - began
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline and not started.is_set():
                root.update()
                time.sleep(0.01)
            observed["model_load_started"] = started.is_set()
            observed["model_loads_at_open"] = len(loaded_models)
            ui = ui_instances[0]
            observed["loading_status"] = ui.status_var.get().lower()
            observed["controls_disabled"] = all(
                widget.instate(["disabled"])
                for widget in (
                    ui.predict_button,
                    ui.demo_button,
                    ui.load_button,
                    *ui.entries.values(),
                )
            )
            release.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.predict_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.01)
            self.assertFalse(ui.predict_button.instate(["disabled"]))
            for name, value in self.raw.items():
                ui.entries[name].delete(0, "end")
                ui.entries[name].insert(0, value)
            for expected in ("$200,000", "$250,000"):
                ui.submit()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not ui.result_var.get():
                    root.update()
                    time.sleep(0.01)
                display = ui.result_var.get()
                self.assertIn(expected, display)
                self.assertIn("2015", display)
                self.assertIn("no calibrated interval", display.lower())

        argv = [
            "king_research_form",
            "--bundle",
            "unused-bundle",
            "--manifest-sha256",
            "a" * 64,
        ]
        began = time.monotonic()
        with (
            patch.object(sys, "argv", argv),
            patch.object(serving, "load_bundle", return_value=bundle) as load_bundle,
            patch.dict(sys.modules, {"xgboost": fake_xgboost}),
            patch.object(form.tk, "Tk", return_value=root),
            patch.object(form, "KingResearchForm", side_effect=capture_form),
            patch.object(enrollment, "find_pending_receipts", return_value=()),
            patch.object(root, "mainloop", side_effect=run_form_flow),
            patch("tkinter.messagebox.showinfo"),
            patch("tkinter.messagebox.showerror"),
        ):
            self.assertEqual(form.main(), 0)

        with self.subTest("window and loading controls appear before model load"):
            self.assertLess(observed["window_delay"], 0.5)
            self.assertTrue(observed["model_load_started"])
            self.assertEqual(observed["model_loads_at_open"], 0)
            self.assertRegex(observed["loading_status"], r"load|prepar|initializ")
            self.assertTrue(observed["controls_disabled"])
        with self.subTest("one verified bundle and model across both requests"):
            self.assertEqual(load_bundle.call_count, 1)
            self.assertEqual(len(loaded_models), 1)
            self.assertEqual(loaded_models[0].assert_bytes, bundle.model_bytes)
        with self.subTest("same model served both form requests"):
            self.assertEqual(len(predicted_models), 2)
            self.assertIs(predicted_models[0], predicted_models[1])

    def test_cli_still_produces_historical_response_with_verified_model(self) -> None:
        bundle = serving.VerifiedBundle(
            FEATURE_NAMES, b"mock model bytes", "a" * 64, "b" * 64
        )
        fake_xgboost = ModuleType("xgboost")

        class FakeRegressor:
            def load_model(self, content):
                self.assert_bytes = bytes(content)

            def predict(self, _matrix):
                return [math.log(200_000)]

        fake_xgboost.XGBRegressor = FakeRegressor
        with tempfile.TemporaryDirectory() as directory:
            request_path = Path(directory) / "request.json"
            request_path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
            argv = [
                "king_research_predict",
                "--bundle",
                "unused-bundle",
                "--manifest-sha256",
                "a" * 64,
                "--request",
                str(request_path),
            ]
            output = io.StringIO()
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    serving, "load_bundle", return_value=bundle
                ) as load_bundle,
                patch.dict(sys.modules, {"xgboost": fake_xgboost}),
                redirect_stdout(output),
            ):
                self.assertEqual(serving.main(), 0)

        load_bundle.assert_called_once_with(Path("unused-bundle"), "a" * 64)
        response = json.loads(output.getvalue())
        self.assertAlmostEqual(response["amount"], 200_000, places=5)
        self.assertEqual(response["status"], "historical_research_only")
        self.assertEqual(response["reference_period"], RESPONSE["reference_period"])
        self.assertFalse(response["certified_90_day_origin"])

    def _empty_tk_root(self) -> tuple[tk.Tk, list[form.KingResearchForm]]:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"A local Tk display is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        root.update()
        return root, []

    def test_tk_demo_populates_all_fifteen_fields(self) -> None:
        _root, ui = self.make_hidden_form()
        for entry in ui.entries.values():
            entry.delete(0, "end")
        ui.load_demo()
        self.assertEqual(
            {name: entry.get() for name, entry in ui.entries.items()}, self.raw
        )
        self.assertIn("Synthetic example loaded", ui.status_var.get())

    def test_tk_json_load_is_atomic_and_preserves_values_on_failure(self) -> None:
        _root, ui = self.make_hidden_form()
        before = {name: entry.get() for name, entry in ui.entries.items()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            changed = {**EXAMPLE, "bedrooms": 4}
            path.write_text(json.dumps(changed), encoding="utf-8")
            ui.load_request(path)
            self.assertEqual(ui.entries["bedrooms"].get(), "4.0")
            self.assertIn("Request loaded", ui.status_var.get())

            valid = {name: entry.get() for name, entry in ui.entries.items()}
            path.write_text(json.dumps({**EXAMPLE, "zipcode": "99999"}))
            with patch("tkinter.messagebox.showerror"):
                ui.load_request(path)
            self.assertEqual(
                {name: entry.get() for name, entry in ui.entries.items()}, valid
            )
            self.assertNotEqual(valid, before)

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

    def test_tk_enrollment_reuses_loaded_predictor_and_completes_off_thread(
        self,
    ) -> None:
        root, _unused = self._empty_tk_root()
        loaded_predictor = Mock(return_value=RESPONSE)
        completed = enrollment.EnrollmentResult(
            receipt_path=Path("private-receipt.json"),
            commitment_path=Path("public-commitment.json"),
            prediction=RESPONSE,
            commitment={"commitment_id": "a1b2c3d4e5f60718293a4b5c"},
        )
        enroller = Mock(return_value=completed)
        ui = form.KingResearchForm(
            root,
            Path("unused-bundle"),
            "a" * 64,
            FEATURE_NAMES,
            predictor=loaded_predictor,
            enroller=enroller,
        )
        for name, value in self.raw.items():
            ui.entries[name].insert(0, value)
        ui.enrollment_reference_var.set("prospect-0001")

        with (
            patch("tkinter.messagebox.showinfo") as info,
            patch("tkinter.messagebox.showerror") as error,
        ):
            ui.capture_prospective()
            self.assertTrue(ui.capture_button.instate(["disabled"]))
            ui.capture_prospective()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.capture_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.01)

        enroller.assert_called_once()
        self.assertIs(enroller.call_args.kwargs["predictor"], loaded_predictor)
        loaded_predictor.assert_not_called()
        self.assertIn("$200,000", ui.result_var.get())
        self.assertIn("commitment created", ui.status_var.get().lower())
        self.assertNotIn("prospect-0001", ui.status_var.get())
        self.assertNotIn("98103", ui.status_var.get())
        self.assertFalse(ui.capture_button.instate(["disabled"]))
        info.assert_called_once()
        error.assert_not_called()

    def test_tk_pending_commitment_retries_without_new_prediction(self) -> None:
        root, _unused = self._empty_tk_root()
        receipt_path = Path("private/never-display-this-receipt.json")
        enroller = Mock(
            side_effect=enrollment.EnrollmentCommitmentPending(receipt_path)
        )
        digest = "a" * 64
        public_directory = tempfile.TemporaryDirectory()
        self.addCleanup(public_directory.cleanup)
        commitment_path = (
            Path(public_directory.name) / f"king-research-commitment-{digest}.json"
        )
        commitment_path.write_text("{}", encoding="utf-8")
        committed = enrollment.EnrollmentResult(
            receipt_path=receipt_path,
            commitment_path=commitment_path,
            prediction=None,
            commitment={
                "commitment_id": digest[:24],
                "receipt_sha256": digest,
            },
        )
        committer = Mock(return_value=committed)
        loaded_predictor = Mock(return_value=RESPONSE)
        ui = form.KingResearchForm(
            root,
            Path("unused-bundle"),
            "a" * 64,
            FEATURE_NAMES,
            predictor=loaded_predictor,
            enroller=enroller,
            committer=committer,
        )
        for name, value in self.raw.items():
            ui.entries[name].insert(0, value)
        ui.enrollment_reference_var.set("prospect-0001")

        with (
            patch("tkinter.messagebox.showinfo"),
            patch("tkinter.messagebox.showerror") as error,
            patch.object(enrollment, "verify_commitment_result", return_value=True),
        ):
            ui.capture_prospective()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.retry_button.instate(["disabled"]):
                root.update()
                time.sleep(0.01)
            self.assertFalse(ui.retry_button.instate(["disabled"]))
            self.assertTrue(ui.capture_button.instate(["disabled"]))
            status = ui.status_var.get()
            self.assertIn("commitment pending", status.lower())
            self.assertNotIn(str(receipt_path), status)
            self.assertNotIn("prospect-0001", status)
            ui.retry_commitment()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.retry_button.instate(["disabled"]):
                root.update()
                time.sleep(0.01)

        enroller.assert_called_once()
        committer.assert_called_once_with(receipt_path, enrollment.PUBLIC_OUTPUT_DIR)
        loaded_predictor.assert_not_called()
        self.assertIn("commitment created", ui.status_var.get().lower())
        self.assertTrue(ui.retry_button.instate(["disabled"]))
        error.assert_called_once()

    def test_tk_restores_pending_commitment_and_blocks_new_capture(self) -> None:
        root, _unused = self._empty_tk_root()
        pending = Path("private/pending-receipt.json")
        enroller = Mock()
        ui = form.KingResearchForm(
            root,
            Path("unused-bundle"),
            "a" * 64,
            FEATURE_NAMES,
            predictor=Mock(return_value=RESPONSE),
            enroller=enroller,
            pending_receipts=(pending,),
        )
        for name, value in self.raw.items():
            ui.entries[name].insert(0, value)
        ui.enrollment_reference_var.set("prospect-0002")

        self.assertTrue(ui.capture_button.instate(["disabled"]))
        self.assertFalse(ui.retry_button.instate(["disabled"]))
        ui.capture_prospective()
        enroller.assert_not_called()

    def test_tk_capture_error_keeps_ui_generic_but_records_safe_traceback(self) -> None:
        root, _unused = self._empty_tk_root()
        sensitive = "secret/receipt-path.json ZIP=98103 prospect-0001"
        ui = form.KingResearchForm(
            root,
            Path("unused-bundle"),
            "a" * 64,
            FEATURE_NAMES,
            predictor=Mock(return_value=RESPONSE),
            enroller=Mock(side_effect=RuntimeError(sensitive)),
        )
        for name, value in self.raw.items():
            ui.entries[name].insert(0, value)
        ui.enrollment_reference_var.set("prospect-0001")

        with (
            patch("tkinter.messagebox.showerror"),
            patch.object(form.traceback, "print_tb") as print_tb,
        ):
            ui.capture_prospective()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and ui.capture_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.01)

        print_tb.assert_called_once()
        self.assertNotIn(sensitive, ui.status_var.get())
        self.assertNotIn("98103", ui.status_var.get())

    def test_main_shows_bad_bundle_as_a_controlled_ui_error(self) -> None:
        with patch.object(
            serving, "load_bundle", side_effect=ValueError("checksum mismatch")
        ):
            status, disabled = self._startup_error_in_window()
        self.assertIn("checksum mismatch", status)
        self.assertTrue(disabled)

    def test_missing_xgboost_shows_a_controlled_ui_error(self) -> None:
        bundle = serving.VerifiedBundle(
            FEATURE_NAMES, b"mock model bytes", "a" * 64, "b" * 64
        )
        real_import = builtins.__import__

        def without_xgboost(name, *args, **kwargs):
            if name == "xgboost" or name.startswith("xgboost."):
                raise ImportError("No module named xgboost")
            return real_import(name, *args, **kwargs)

        with (
            patch.object(serving, "load_bundle", return_value=bundle),
            patch.object(builtins, "__import__", side_effect=without_xgboost),
        ):
            status, disabled = self._startup_error_in_window()
        self.assertIn("xgboost", status.lower())
        self.assertRegex(status.lower(), r"unavailable|missing|install")
        self.assertTrue(disabled)

    def _startup_error_in_window(self) -> tuple[str, bool]:
        root, ui_instances = self._empty_tk_root()
        real_form_class = form.KingResearchForm
        observed: dict[str, object] = {}

        def capture_form(*args, **kwargs):
            ui = real_form_class(*args, **kwargs)
            ui_instances.append(ui)
            return ui

        def inspect_window():
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not error_dialog.called:
                root.update()
                time.sleep(0.01)
            ui = ui_instances[0]
            observed["status"] = ui.status_var.get()
            observed["disabled"] = all(
                widget.instate(["disabled"])
                for widget in (
                    ui.predict_button,
                    ui.demo_button,
                    ui.load_button,
                    *ui.entries.values(),
                )
            )

        argv = [
            "king_research_form",
            "--bundle",
            "unused-bundle",
            "--manifest-sha256",
            "a" * 64,
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(form.tk, "Tk", return_value=root),
            patch.object(form, "KingResearchForm", side_effect=capture_form),
            patch.object(root, "mainloop", side_effect=inspect_window),
            patch("tkinter.messagebox.showerror") as error_dialog,
        ):
            try:
                self.assertEqual(form.main(), 2)
            except (ImportError, SystemExit) as error:
                self.fail(f"Startup crashed instead of showing an error: {error}")
        error_dialog.assert_called_once()
        return str(observed["status"]), bool(observed["disabled"])

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
