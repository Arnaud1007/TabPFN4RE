"""Fold-scoped training guards for future model wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


_FORBIDDEN_FEATURES = {
    "saleprice",
    "sale_price",
    "target",
    "f172",
    "f349",
    "f350",
    "rendement_locatif",
    "note_attractivite_marche",
    "note_potentiel_d_investissement",
    "future_market_average",
    "final_days_on_market",
}


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    dependencies: tuple[str, ...] = ()
    modes: tuple[str, ...] = ("OFF",)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name
            or self.name != self.name.strip()
        ):
            raise ValueError("Feature name must be canonical")
        if not isinstance(self.dependencies, tuple) or not isinstance(
            self.modes, tuple
        ):
            raise ValueError("Feature dependencies and modes must be immutable tuples")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Feature dependencies must be unique")
        if not self.modes or any(mode not in {"OFF", "ON"} for mode in self.modes):
            raise ValueError("Feature modes must be OFF or ON")


def validate_feature_columns(
    names: Sequence[str],
    definitions: Mapping[str, FeatureDefinition],
    *,
    mode: str = "OFF",
) -> None:
    """Fail closed when a predictive input or its dependency is disallowed."""
    if mode not in {"OFF", "ON"}:
        raise ValueError("Unsupported information mode")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate model feature")
    visiting: set[str] = set()
    validated: set[str] = set()

    def visit(name: str) -> None:
        if not isinstance(name, str):
            raise ValueError("Feature name must be a string")
        lowered = name.casefold()
        if lowered in _FORBIDDEN_FEATURES or lowered.startswith(
            (
                "saleprice_",
                "sale_price_",
                "target_",
                "f172_",
                "f349_",
                "f350_",
            )
        ):
            raise ValueError(f"Forbidden model feature: {name}")
        if name in visiting:
            raise ValueError(f"Feature dependency cycle: {name}")
        if name in validated:
            return
        definition = definitions.get(name)
        if definition is None or definition.name != name:
            raise ValueError(f"Unregistered model feature: {name}")
        if mode not in definition.modes and not (
            mode == "ON" and "OFF" in definition.modes
        ):
            raise ValueError(f"Feature {name} is unavailable in {mode}")
        visiting.add(name)
        for dependency in definition.dependencies:
            visit(dependency)
        visiting.remove(name)
        validated.add(name)

    for name in names:
        visit(name)


@dataclass(frozen=True)
class TrainingPartition:
    train_row_ids: frozenset[str]
    reserved_row_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.train_row_ids, frozenset) or not isinstance(
            self.reserved_row_ids, frozenset
        ):
            raise ValueError("Partition membership must use immutable frozensets")
        if not self.train_row_ids or not self.reserved_row_ids:
            raise ValueError("Training and reserved row IDs must be nonempty")
        if self.train_row_ids & self.reserved_row_ids:
            raise ValueError("Training and reserved row IDs overlap")
        if any(
            not isinstance(row_id, str) or not row_id or row_id != row_id.strip()
            for row_id in self.train_row_ids | self.reserved_row_ids
        ):
            raise ValueError("Partition row IDs must be nonempty strings")


@dataclass(frozen=True)
class GuardedCategoryEncoder:
    categories: tuple[str, ...]
    unknown_code: int = -1

    def __post_init__(self) -> None:
        if not isinstance(self.categories, tuple):
            raise ValueError("Encoder vocabulary must be an immutable tuple")
        if len(set(self.categories)) != len(self.categories) or any(
            not isinstance(value, str) or not value for value in self.categories
        ):
            raise ValueError("Encoder categories must be unique nonempty strings")
        if type(self.unknown_code) is not int or self.unknown_code >= 0:
            raise ValueError("Unknown category code must be a negative integer")

    @classmethod
    def fit(
        cls,
        values: Sequence[str],
        *,
        row_ids: Sequence[str],
        partition: TrainingPartition,
    ) -> GuardedCategoryEncoder:
        if not values or len(values) != len(row_ids):
            raise ValueError("Encoder fit needs aligned nonempty values and row IDs")
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("Encoder fit row IDs must be unique")
        if set(row_ids) & partition.reserved_row_ids or not set(row_ids).issubset(
            partition.train_row_ids
        ):
            raise ValueError("Encoder fit includes reserved or unregistered row IDs")
        if any(not isinstance(value, str) for value in values):
            raise ValueError("Categories must be strings")
        return cls(categories=tuple(sorted(set(values))))

    def transform(self, values: Sequence[str]) -> tuple[int, ...]:
        lookup = {value: index for index, value in enumerate(self.categories)}
        return tuple(lookup.get(value, self.unknown_code) for value in values)
