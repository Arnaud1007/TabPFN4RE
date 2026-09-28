"""Fold-scoped training guards for future model wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


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
