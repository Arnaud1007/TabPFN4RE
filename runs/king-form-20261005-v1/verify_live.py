"""Replay the King research form against this workstation's saved checkpoint.

The checkpoint lives in ignored private storage. A fresh clone must first
rebuild it and substitute its own verified bundle path and manifest digest.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
import tkinter as tk
from unittest.mock import patch

from scripts.king_research_form import KingResearchForm


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "data/raw/king-benchmark/king-validation-20261004-v1"
MANIFEST_SHA256 = "32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9"
EXPECTED = json.loads(
    (ROOT / "runs/king-serving-20261004-v1/example_prediction.json").read_text(
        encoding="utf-8"
    )
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        window_started = time.monotonic()
        form = KingResearchForm(
            root,
            BUNDLE,
            MANIFEST_SHA256,
            (),
            loading=True,
        )
        form_construction_seconds = time.monotonic() - window_started
        with (
            patch("tkinter.messagebox.showinfo") as info,
            patch("tkinter.messagebox.showerror") as error,
        ):
            model_started = time.monotonic()
            form.start_loading()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and form.predict_button.instate(
                ["disabled"]
            ):
                root.update()
                time.sleep(0.025)
            model_ready_seconds = time.monotonic() - model_started
            require(form_construction_seconds < 0.5, "Form construction was delayed")
            require(not error.called, "Model startup reported an error")
            require(
                not form.predict_button.instate(["disabled"]),
                "Model did not become ready",
            )
            form.load_demo()
            started = time.monotonic()
            form.submit()
            submit_seconds = time.monotonic() - started
            require(submit_seconds < 0.5, "Submit blocked the window")
            require(form.predict_button.instate(["disabled"]), "Predict stayed enabled")
            require(
                all(entry.instate(["disabled"]) for entry in form.entries.values()),
                "Property inputs stayed editable during prediction",
            )

            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not form.result_var.get():
                root.update()
                time.sleep(0.025)
            completion_seconds = time.monotonic() - started
            display = form.result_var.get()
            require(
                f"${EXPECTED['amount']:,.0f}" in display, "Wrong displayed estimate"
            )
            require("Historical research only" in display, "Missing research scope")
            require("not a current valuation" in display, "Missing current warning")
            require("not a 90-day estimate" in display, "Missing origin warning")
            require("No calibrated interval" in display, "Missing interval warning")
            require(info.call_count == 1 and error.call_count == 0, "Wrong dialogs")
            require(
                not form.predict_button.instate(["disabled"]), "Predict stayed disabled"
            )
            require(
                all(not entry.instate(["disabled"]) for entry in form.entries.values()),
                "Property inputs stayed locked after prediction",
            )

            form.load_demo()
            repeated_started = time.monotonic()
            form.submit()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not form.result_var.get():
                root.update()
                time.sleep(0.01)
            repeated_seconds = time.monotonic() - repeated_started
            require(form.result_var.get(), "Repeated prediction did not complete")
            require(repeated_seconds < 1, "Repeated prediction exceeded one second")

            form.entries["sqft_living"].delete(0, "end")
            require(not form.result_var.get(), "Stale result survived a field edit")
            require("changed" in form.status_var.get().lower(), "Edit status missing")
            form.submit()
            require(not form.result_var.get(), "Stale result survived invalid input")
            require("sqft_living" in form.status_var.get(), "Wrong input error")
            require(error.call_count == 1, "Missing error dialog")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "historical_scope": True,
                    "model_output_matches_saved_example_when_rounded": True,
                    "nonblocking_submit_under_half_second": True,
                    "loaded_model_reused": True,
                    "responsive_loading_form": True,
                    "invalid_input_rejected_without_stale_result": True,
                    "edited_input_clears_result": True,
                    "form_construction_seconds": round(form_construction_seconds, 4),
                    "model_ready_seconds": round(model_ready_seconds, 4),
                    "submit_seconds": round(submit_seconds, 4),
                    "completion_seconds": round(completion_seconds, 4),
                    "repeated_prediction_seconds": round(repeated_seconds, 4),
                },
                sort_keys=True,
            )
        )
    finally:
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
