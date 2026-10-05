"""Local form for the saved historical King County research checkpoint."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import queue
import re
import stat
import sys
import threading
import traceback
from typing import Callable, Mapping

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # Report the missing desktop dependency at startup.
    tk = None
    filedialog = None
    messagebox = None
    ttk = None

from scripts.king_historical_benchmark import NUMERIC_FEATURES
from scripts import king_research_predict as serving


FORM_FIELDS = (*NUMERIC_FEATURES, "zipcode")
FIELD_LABELS = (
    ("bedrooms", "Bedrooms (0–20)"),
    ("bathrooms", "Bathrooms (0–20)"),
    ("sqft_living", "Living area (sq ft)"),
    ("sqft_lot", "Lot area (sq ft)"),
    ("floors", "Floors (up to 8)"),
    ("waterfront", "Waterfront (0 or 1)"),
    ("view", "View rating (0–4)"),
    ("condition", "Condition (1–5)"),
    ("grade", "Grade (1–13)"),
    ("sqft_above", "Above-ground area (sq ft)"),
    ("sqft_basement", "Basement area (sq ft)"),
    ("yr_built", "Year built (1800–2015)"),
    ("lat", "Latitude (47–48)"),
    ("long", "Longitude (-123 to -121)"),
    ("zipcode", "King County ZIP code"),
)
SCOPE_WARNING = (
    "Historical research only: King County sales from January–February 2015. "
    "This is not a current valuation. It is not a 90-day estimate. "
    "No calibrated interval is available."
)
REFERENCE_PERIOD = "King County sales, January-February 2015"
MAX_REQUEST_BYTES = 8_000


def parse_form_values(
    raw: Mapping[str, str], feature_names: tuple[str, ...]
) -> dict[str, float | str]:
    """Convert fifteen text entries and apply the prediction service's guard."""
    if not isinstance(raw, Mapping) or set(raw) != set(FORM_FIELDS):
        raise ValueError("Form must contain exactly the 15 property fields")
    request: dict[str, object] = {}
    for name in FORM_FIELDS:
        value = raw[name]
        if not isinstance(value, str):
            raise ValueError(f"{name} must be entered as text")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{name} is required")
        if name == "zipcode":
            request[name] = stripped
            continue
        try:
            request[name] = float(stripped)
        except ValueError as error:
            raise ValueError(f"{name} must be a number") from error
    return serving.validate_request(request, feature_names)


def load_request_file(
    path: Path, feature_names: tuple[str, ...]
) -> dict[str, float | str]:
    """Read and validate one bounded JSON request before changing the form."""
    try:
        selected = Path(path)
        if selected.is_symlink():
            raise ValueError("Request file must not redirect")
        with selected.open("rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Request must be one regular file")
            raw = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request file exceeds the size limit")
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Request file must contain valid UTF-8 JSON") from error
    except OSError as error:
        raise ValueError("Request file could not be read") from error
    return serving.validate_request(request, feature_names)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate request field: {key}")
        result[key] = value
    return result


def predict_from_form(
    raw: Mapping[str, str],
    bundle_dir: Path,
    manifest_sha256: str,
    feature_names: tuple[str, ...],
) -> dict[str, object]:
    """Submit the validated request through the same service as the CLI."""
    request = parse_form_values(raw, feature_names)
    return serving.predict(bundle_dir, request, manifest_sha256)


def format_prediction(response: Mapping[str, object]) -> str:
    """Display only a compatible historical response and its evidence limits."""
    if not isinstance(response, Mapping) or any(
        (
            response.get("currency") != "USD",
            response.get("model") != "xgboost",
            response.get("status") != "historical_research_only",
            response.get("reference_period") != REFERENCE_PERIOD,
            response.get("certified_90_day_origin") is not False,
            response.get("g_us_gate") != "PENDING",
        )
    ):
        raise ValueError("Prediction response is incompatible with historical research")
    amount = response.get("amount")
    if type(amount) not in (int, float):
        raise ValueError("Prediction amount is invalid")
    try:
        number = float(amount)
    except OverflowError as error:
        raise ValueError("Prediction amount is invalid") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Prediction amount is invalid")
    lines = [f"Historical 2015 estimate: ${number:,.0f} USD"]
    hpi = response.get("experimental_hpi_adjustment")
    if hpi is not None:
        if not isinstance(hpi, Mapping) or hpi.get("status") != "research_only":
            raise ValueError("Experimental HPI response is incompatible")
        adjusted = hpi.get("amount")
        if type(adjusted) not in (int, float) or not math.isfinite(float(adjusted)):
            raise ValueError("Experimental HPI amount is invalid")
        lines.append(f"FHFA metro-indexed illustration: ${float(adjusted):,.0f} USD")
        lines.append(str(hpi.get("warning", "")))
    lines.append(SCOPE_WARNING)
    return "\n".join(lines)


def demo_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples/king-research-request.json"


class KingResearchForm:
    """Tkinter shell for a local, historical-only prediction request."""

    def __init__(
        self,
        root: tk.Tk,
        bundle_dir: Path,
        manifest_sha256: str,
        feature_names: tuple[str, ...],
        predictor: Callable[[Mapping[str, object]], dict[str, object]] | None = None,
        loading: bool = False,
        fhfa_source: Path | None = None,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is unavailable in this Python installation")
        self.root = root
        self.bundle_dir = bundle_dir
        self.manifest_sha256 = manifest_sha256
        self.feature_names = feature_names
        self._predict = predictor
        self.fhfa_source = fhfa_source
        self.entries: dict[str, ttk.Entry] = {}
        self.entry_vars: dict[str, tk.StringVar] = {}
        self._responses: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._pending = loading
        self.startup_exit_code = 0
        self.result_var = tk.StringVar(master=root, value="")
        self.status_var = tk.StringVar(
            master=root,
            value=(
                "Loading and verifying the historical model..."
                if loading
                else "Enter a property or load the synthetic example."
            ),
        )
        root.title("King County historical research estimate")
        root.minsize(800, 570)
        self._build_widgets()
        self._set_pending(loading)
        if not loading:
            root.after_idle(self.entries["bedrooms"].focus_set)

    def _build_widgets(self) -> None:
        panel = ttk.Frame(self.root, padding=16)
        panel.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(3, weight=1)
        ttk.Label(panel, text=SCOPE_WARNING, wraplength=760).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12)
        )
        for position, (name, label_text) in enumerate(FIELD_LABELS):
            row, pair = divmod(position, 2)
            column = pair * 2
            label = ttk.Label(panel, text=label_text)
            label.grid(row=row + 1, column=column, sticky="w", padx=(0, 8), pady=4)
            entry_var = tk.StringVar(master=self.root)
            entry_var.trace_add("write", self._invalidate_result)
            entry = ttk.Entry(panel, width=18, textvariable=entry_var)
            entry.grid(
                row=row + 1, column=column + 1, sticky="ew", padx=(0, 18), pady=4
            )
            entry.bind("<Return>", self._submit_on_enter)
            label.bind("<Button-1>", lambda _event, widget=entry: widget.focus_set())
            self.entry_vars[name] = entry_var
            self.entries[name] = entry
        self._build_actions(panel)

    def _invalidate_result(self, *_args: object) -> None:
        if self.result_var.get():
            self.result_var.set("")
            self.status_var.set(
                "Inputs changed. Predict again for an updated estimate."
            )

    def _build_actions(self, panel: ttk.Frame) -> None:
        row = (len(FIELD_LABELS) + 1) // 2 + 1
        self.demo_button = ttk.Button(
            panel, text="Load synthetic example", command=self.load_demo
        )
        self.demo_button.grid(row=row, column=0, sticky="w", pady=(14, 10))
        self.load_button = ttk.Button(
            panel, text="Load request JSON...", command=self.load_request_dialog
        )
        self.load_button.grid(row=row, column=1, columnspan=2, pady=(14, 10))
        self.predict_button = ttk.Button(panel, text="Predict", command=self.submit)
        self.predict_button.grid(row=row, column=3, sticky="e", pady=(14, 10))
        self.predict_button.bind("<Return>", self._submit_on_enter)
        ttk.Label(panel, textvariable=self.result_var, wraplength=760).grid(
            row=row + 1, column=0, columnspan=4, sticky="w", pady=(4, 10)
        )
        ttk.Label(panel, textvariable=self.status_var, wraplength=760).grid(
            row=row + 2, column=0, columnspan=4, sticky="w"
        )

    def load_demo(self) -> None:
        if self._pending:
            return
        self.result_var.set("")
        try:
            example = json.loads(demo_path().read_text(encoding="utf-8"))
            serving.validate_request(example, self.feature_names)
        except (OSError, ValueError, TypeError) as error:
            self.status_var.set(f"Synthetic example unavailable: {error}")
            return
        for name in FORM_FIELDS:
            entry = self.entries[name]
            entry.delete(0, "end")
            entry.insert(0, str(example[name]))
        self.status_var.set("Synthetic example loaded. Edit fields before prediction.")
        self.entries["bedrooms"].focus_set()

    def load_request_dialog(self) -> None:
        if self._pending or filedialog is None:
            return
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Load King County property request",
            filetypes=(("JSON request", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self.load_request(Path(selected))

    def load_request(self, path: Path) -> None:
        """Atomically populate entries from a validated request file."""
        if self._pending:
            return
        try:
            request = load_request_file(path, self.feature_names)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            self._show_error(error)
            return
        display_values = {name: str(request[name]) for name in FORM_FIELDS}
        self.result_var.set("")
        for name, value in display_values.items():
            self.entries[name].delete(0, "end")
            self.entries[name].insert(0, value)
        self.status_var.set("Request loaded. Review the fields, then select Predict.")
        self.entries["bedrooms"].focus_set()

    def submit(self) -> None:
        if self._pending:
            return
        self.result_var.set("")
        try:
            raw = {name: self.entries[name].get() for name in FORM_FIELDS}
            request = parse_form_values(raw, self.feature_names)
        except (ValueError, OSError, TypeError, KeyError, IndexError) as error:
            self._show_error(error)
            return
        self._set_pending(True)
        self.status_var.set("Predicting from the historical 2015 checkpoint...")
        self.root.after(25, self._poll_prediction)
        threading.Thread(
            target=self._predict_worker, args=(request,), daemon=True
        ).start()

    def start_loading(self) -> None:
        """Load and verify the checkpoint without blocking the Tk event loop."""
        self.root.after(25, self._poll_startup)
        threading.Thread(target=self._load_predictor_worker, daemon=True).start()

    def _load_predictor_worker(self) -> None:
        try:
            predictor = serving.load_predictor(
                self.bundle_dir, self.manifest_sha256, self.fhfa_source
            )
        except Exception as error:
            self._responses.put(("startup_error", error))
        else:
            self._responses.put(("ready", predictor))

    def _poll_startup(self) -> None:
        try:
            outcome, payload = self._responses.get_nowait()
        except queue.Empty:
            self.root.after(25, self._poll_startup)
            return
        if outcome == "startup_error":
            self._show_startup_error(payload)
            return
        if outcome != "ready" or not isinstance(payload, serving.LoadedPredictor):
            self._show_startup_error(RuntimeError("Loaded model response is invalid"))
            return
        self.feature_names = payload.feature_names
        self._predict = payload.predict
        self._set_pending(False)
        self.status_var.set(
            "Historical model ready. Enter a property or load the example."
        )
        self.entries["bedrooms"].focus_set()

    def _set_pending(self, pending: bool) -> None:
        self._pending = pending
        state = "disabled" if pending else "!disabled"
        for widget in (
            self.predict_button,
            self.demo_button,
            self.load_button,
            *self.entries.values(),
        ):
            widget.state([state])

    def _submit_on_enter(self, _event: object) -> str:
        self.submit()
        return "break"

    def _predict_worker(self, request: Mapping[str, object]) -> None:
        try:
            if self._predict is None:
                if self.fhfa_source is None:
                    response = serving.predict(
                        self.bundle_dir, request, self.manifest_sha256
                    )
                else:
                    response = serving.predict(
                        self.bundle_dir,
                        request,
                        self.manifest_sha256,
                        self.fhfa_source,
                    )
            else:
                response = self._predict(request)
        except Exception as error:
            self._responses.put(("error", error))
        else:
            self._responses.put(("result", response))

    def _poll_prediction(self) -> None:
        try:
            outcome, payload = self._responses.get_nowait()
        except queue.Empty:
            if self._pending:
                self.root.after(25, self._poll_prediction)
            return
        self._set_pending(False)
        if outcome == "error":
            self._show_error(payload)
            return
        try:
            display = format_prediction(payload)
        except (ValueError, TypeError, KeyError, IndexError) as error:
            self._show_error(error)
            return
        self.result_var.set(display)
        self.status_var.set("Historical research prediction complete.")
        messagebox.showinfo("King County research estimate", display, parent=self.root)

    def _show_error(self, error: object) -> None:
        if isinstance(error, (ValueError, OSError, TypeError, KeyError, IndexError)):
            detail = str(error)
            status = f"Input or bundle error: {detail}"
        else:
            if isinstance(error, BaseException):
                traceback.print_exception(error, file=sys.stderr)
            detail = "Prediction unavailable. Inspect the terminal for details."
            status = detail
        self.status_var.set(status)
        messagebox.showerror(
            "King County prediction unavailable", status, parent=self.root
        )
        self._focus_invalid_field(detail)

    def _show_startup_error(self, error: object) -> None:
        if isinstance(error, BaseException):
            detail = str(error) or error.__class__.__name__
        else:
            detail = "Unknown model-loading failure"
        status = f"Historical model unavailable: {detail}"
        self.startup_exit_code = 2
        self.status_var.set(status)
        messagebox.showerror("King County model unavailable", status, parent=self.root)

    def _focus_invalid_field(self, message: str) -> None:
        for name in FORM_FIELDS:
            if name in message:
                self.entries[name].focus_set()
                break


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--fhfa-source", type=Path)
    args = parser.parse_args()
    if tk is None:
        parser.error("Tkinter is unavailable in this Python installation")
    if not re.fullmatch(r"[0-9a-f]{64}", args.manifest_sha256):
        parser.error("Manifest SHA-256 must be 64 lowercase hexadecimal characters")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        parser.error(f"Local display is unavailable: {error}")
    form = KingResearchForm(
        root,
        args.bundle,
        args.manifest_sha256,
        (),
        loading=True,
        fhfa_source=args.fhfa_source,
    )
    form.start_loading()
    root.mainloop()
    return form.startup_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
