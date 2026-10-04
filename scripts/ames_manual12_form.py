"""Local input form for the historical, 12-field Ames prediction prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import traceback
from typing import Callable, Mapping

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # The command reports this dependency clearly at startup.
    tk = None
    ttk = None

from scripts.ames_dev_prototype import (
    MANUAL12_FEATURES,
    MANUAL12_PROTOCOL,
    REQUIRED_REQUEST,
    predict,
    validate_request,
)

NUMERIC_FIELDS = frozenset(MANUAL12_FEATURES) - {"Neighborhood", "KitchenQual"}
FIELD_LABELS = (
    ("GrLivArea", "Living area (sq ft) *"),
    ("OverallQual", "Overall quality (1-10) *"),
    ("Neighborhood", "Ames neighborhood code *"),
    ("YearBuilt", "Year built"),
    ("TotalBsmtSF", "Basement area (sq ft)"),
    ("GarageCars", "Garage capacity (cars)"),
    ("FullBath", "Full bathrooms"),
    ("BedroomAbvGr", "Bedrooms above ground"),
    ("LotArea", "Lot area (sq ft)"),
    ("OverallCond", "Overall condition (1-10)"),
    ("KitchenQual", "Kitchen quality (Ex/Gd/TA/Fa/Po)"),
    ("Fireplaces", "Fireplaces"),
)
SCOPE_WARNING = (
    "Historical Ames engineering prototype. It is not a current US valuation "
    "and has no calibrated interval. * Required input."
)


def parse_form_values(raw: Mapping[str, str]) -> dict[str, object]:
    """Convert displayed text to the exact guarded manual12 request schema."""
    if not isinstance(raw, Mapping) or set(raw) != set(MANUAL12_FEATURES):
        raise ValueError("Form must contain exactly the 12 trained feature names")
    values: dict[str, object] = {}
    for name in MANUAL12_FEATURES:
        text = raw[name]
        if not isinstance(text, str):
            raise ValueError(f"{name} must be entered as text")
        stripped = text.strip()
        if not stripped:
            if name in REQUIRED_REQUEST:
                raise ValueError(f"{name} is required")
            values[name] = None
        elif name in NUMERIC_FIELDS:
            try:
                values[name] = float(stripped)
            except ValueError as error:
                raise ValueError(f"{name} must be a number") from error
        else:
            values[name] = stripped
    return validate_request(values, MANUAL12_FEATURES, NUMERIC_FIELDS)


def format_result(response: Mapping[str, object]) -> str:
    """Show an approximate point estimate with its limited evidence scope."""
    if (
        response.get("protocol") != MANUAL12_PROTOCOL
        or response.get("status") != "historical_prototype"
        or response.get("currency") != "USD"
    ):
        raise ValueError("Prediction response is incompatible with this form")
    if response.get("support_status") not in ("schema_supported", "unseen_category"):
        raise ValueError("Prediction support status is unsupported")
    amount = float(response["amount"])
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Prediction amount is invalid")
    lines = [
        f"Estimated sale price: ${amount:,.0f} USD",
        "Historical Ames prototype; no calibrated interval or current-market validation.",
    ]
    missing = int(response.get("missing_feature_count", 0))
    if missing:
        lines.append(f"{missing} missing input(s) were imputed; accuracy may differ.")
    unseen = response.get("unseen_category_features", [])
    if unseen:
        lines.append(f"Unseen category in {', '.join(str(name) for name in unseen)}.")
    return "\n".join(lines)


def validate_form_bundle(bundle: Mapping[str, object]) -> None:
    """Reject a different feature profile before opening the manual form."""
    if (
        bundle.get("profile") != "manual12"
        or bundle.get("protocol") != MANUAL12_PROTOCOL
        or bundle.get("features") != list(MANUAL12_FEATURES)
    ):
        raise ValueError("Bundle is not compatible with the 12-field form")


def demo_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples/ames-manual12-request.json"


class AmesManual12Form:
    """Tkinter shell; all modelling and bundle checks stay in ``predict``."""

    def __init__(
        self,
        root: tk.Tk,
        bundle_dir: Path,
        bundle_sha256: str,
        prediction_service: Callable[
            [Path, Mapping[str, object], str], Mapping[str, object]
        ] = predict,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is unavailable in this Python installation")
        self.root = root
        self.bundle_dir = bundle_dir
        self.bundle_sha256 = bundle_sha256
        self.prediction_service = prediction_service
        self.entries: dict[str, ttk.Entry] = {}
        self.result_var = tk.StringVar(master=root, value="")
        self.status_var = tk.StringVar(
            master=root, value="Enter a property or load the synthetic demo."
        )
        root.title("Ames sale-price prototype")
        root.minsize(760, 500)
        panel = ttk.Frame(root, padding=16)
        panel.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.columnconfigure(3, weight=1)
        ttk.Label(panel, text=SCOPE_WARNING, wraplength=760).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12)
        )
        for position, (name, label) in enumerate(FIELD_LABELS):
            row, pair = position // 2, position % 2
            column = pair * 2
            ttk.Label(panel, text=label).grid(
                row=row + 1, column=column, sticky="w", padx=(0, 8), pady=5
            )
            entry = ttk.Entry(panel, width=19)
            entry.grid(
                row=row + 1, column=column + 1, sticky="ew", padx=(0, 18), pady=5
            )
            self.entries[name] = entry
        root.after_idle(self.entries["GrLivArea"].focus_set)
        ttk.Button(panel, text="Load synthetic demo", command=self.load_demo).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(14, 10)
        )
        self.predict_button = ttk.Button(panel, text="Predict", command=self.submit)
        self.predict_button.grid(
            row=7, column=2, columnspan=2, sticky="e", pady=(14, 10)
        )
        ttk.Label(panel, textvariable=self.result_var, wraplength=760).grid(
            row=8, column=0, columnspan=4, sticky="w", pady=(4, 10)
        )
        ttk.Label(panel, textvariable=self.status_var, wraplength=760).grid(
            row=9, column=0, columnspan=4, sticky="w"
        )

    def load_demo(self) -> None:
        self.result_var.set("")
        try:
            example = json.loads(demo_path().read_text(encoding="utf-8"))
            if not isinstance(example, dict):
                raise ValueError("Synthetic demo must be a JSON object")
            validated = validate_request(example, MANUAL12_FEATURES, NUMERIC_FIELDS)
        except (OSError, ValueError, TypeError) as error:
            self.status_var.set(f"Synthetic demo unavailable: {error}")
            return
        for name in MANUAL12_FEATURES:
            entry = self.entries[name]
            entry.delete(0, "end")
            entry.insert(0, "" if validated[name] is None else str(validated[name]))
        self.status_var.set(
            "Synthetic example loaded. Edit fields for your own request."
        )
        self.entries["GrLivArea"].focus_set()

    def submit(self) -> None:
        self.result_var.set("")
        try:
            request = parse_form_values(
                {name: self.entries[name].get() for name in MANUAL12_FEATURES}
            )
            response = self.prediction_service(
                self.bundle_dir, request, self.bundle_sha256
            )
            display = format_result(response)
        except ValueError as error:
            self.status_var.set(f"Input or bundle error: {error}")
            for name, _ in FIELD_LABELS:
                if name in str(error):
                    self.entries[name].focus_set()
                    break
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.status_var.set(
                "Prediction unavailable. Inspect the terminal for details."
            )
        else:
            self.result_var.set(display)
            self.status_var.set(
                "Prediction complete. This remains a historical prototype."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    arguments = parser.parse_args()
    if tk is None:
        parser.error("Tkinter is unavailable in this Python installation")
    if not re.fullmatch(r"[0-9a-f]{64}", arguments.bundle_sha256):
        parser.error("Bundle SHA-256 must be 64 lowercase hexadecimal characters")
    bundle_path = arguments.bundle / "bundle.json"
    if not bundle_path.is_file():
        parser.error("Model bundle is unavailable at the supplied path")
    with bundle_path.open("rb") as stream:
        bundle_bytes = stream.read(100_001)
    if len(bundle_bytes) > 100_000:
        parser.error("Model bundle exceeds its size limit")
    if hashlib.sha256(bundle_bytes).hexdigest() != arguments.bundle_sha256:
        parser.error("Model bundle digest does not match the supplied SHA-256")
    try:
        bundle = json.loads(bundle_bytes.decode("utf-8"))
        if not isinstance(bundle, dict):
            raise ValueError("Bundle must be a JSON object")
        validate_form_bundle(bundle)
    except (UnicodeError, ValueError) as error:
        parser.error(str(error))
    try:
        root = tk.Tk()
    except tk.TclError as error:
        parser.error(f"Local display is unavailable: {error}")
    AmesManual12Form(root, arguments.bundle, arguments.bundle_sha256)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
