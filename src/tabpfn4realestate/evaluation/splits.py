"""Distinguish operational repeat-property tests from unseen-property tests."""

from __future__ import annotations

from typing import Sequence


def validate_property_split(
    train_property_ids: Sequence[str],
    test_property_ids: Sequence[str],
    protocol: str,
) -> None:
    if protocol not in {"unseen_property", "future_sales"}:
        raise ValueError(f"Unknown property split protocol: {protocol}")
    if not train_property_ids or not test_property_ids:
        raise ValueError("Both split partitions need property IDs")
    if any(
        not isinstance(value, str) or not value or value != value.strip()
        for value in (*train_property_ids, *test_property_ids)
    ):
        raise ValueError("Property IDs must be nonempty strings")
    if protocol == "unseen_property" and set(train_property_ids) & set(
        test_property_ids
    ):
        raise ValueError("Unseen-property split contains a repeat property")
