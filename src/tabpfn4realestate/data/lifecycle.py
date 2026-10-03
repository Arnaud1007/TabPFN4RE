"""Conservative, synthetic property and listing-episode resolution for US04.

This module does not turn a listing status into a verified transaction label.
It requires source-backed first availability before an event enters a
historical view and never infers a dwelling from a multiunit address.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence


_EVENT_TYPES = {"published", "price_change", "pending", "withdrawn", "expired", "sold"}
_TERMINAL = {"withdrawn", "expired", "sold"}


def _id(value: str, name: str, *, namespace_part: bool = False) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty canonical string")
    if namespace_part and ":" in value:
        raise ValueError(f"{name} cannot contain ':'")


def _instant(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class PropertyIdentity:
    property_id: str
    address_key: str | None
    parcel_key: str | None
    unit_key: str | None
    valid_from: datetime
    valid_to: datetime | None
    available_at: datetime

    def __post_init__(self) -> None:
        _id(self.property_id, "property_id")
        if self.address_key is None and self.parcel_key is None:
            raise ValueError("Property identity needs address or parcel evidence")
        for name in ("address_key", "parcel_key", "unit_key"):
            value = getattr(self, name)
            if value is not None:
                _id(value, name)
        _instant(self.valid_from, "valid_from")
        _instant(self.available_at, "available_at")
        if self.valid_to is not None:
            _instant(self.valid_to, "valid_to")
            if _utc(self.valid_to) <= _utc(self.valid_from):
                raise ValueError("valid_to must follow valid_from")


@dataclass(frozen=True)
class ListingObservation:
    source_id: str
    event_id: str
    source_listing_id: str
    address_key: str | None
    parcel_key: str | None
    unit_key: str | None
    event_type: str
    event_at: datetime
    available_at: datetime | None
    ingested_at: datetime
    amount: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "event_id", "source_listing_id"):
            _id(getattr(self, name), name, namespace_part=name != "event_id")
        if self.address_key is None and self.parcel_key is None:
            raise ValueError("Listing observation needs address or parcel evidence")
        for name in ("address_key", "parcel_key", "unit_key"):
            value = getattr(self, name)
            if value is not None:
                _id(value, name)
        if self.event_type not in _EVENT_TYPES:
            raise ValueError("Unsupported listing event type")
        _instant(self.event_at, "event_at")
        _instant(self.ingested_at, "ingested_at")
        if self.available_at is not None:
            _instant(self.available_at, "available_at")
        if self.event_type in {"published", "price_change"}:
            if (
                not isinstance(self.amount, Decimal)
                or not self.amount.is_finite()
                or self.amount <= 0
            ):
                raise ValueError(
                    "Publication and price change need positive asking amount"
                )
        elif self.amount is not None:
            raise ValueError("Status events cannot carry an asking amount")


@dataclass(frozen=True)
class VerifiedListingAlias:
    source_id: str
    source_listing_id: str
    canonical_listing_id: str
    evidence_id: str
    available_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "source_id",
            "source_listing_id",
            "canonical_listing_id",
            "evidence_id",
        ):
            _id(getattr(self, name), name)
        _instant(self.available_at, "alias available_at")


@dataclass(frozen=True)
class QuarantinedObservation:
    reason: str
    source_events: tuple[ListingObservation, ...]


@dataclass(frozen=True)
class ResolvedEvent:
    event_type: str
    event_at: datetime
    amount: Decimal | None
    source_events: tuple[ListingObservation, ...]


@dataclass(frozen=True)
class ListingEpisode:
    property_id: str
    canonical_listing_id: str
    generation: int
    status: str
    asking_price: Decimal
    events: tuple[ResolvedEvent, ...]
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LifecycleResolution:
    episodes: tuple[ListingEpisode, ...]
    quarantined: tuple[QuarantinedObservation, ...]
    source_events: tuple[ListingObservation, ...]


def _event_order(row: ListingObservation) -> tuple[str, ...]:
    """Order conflicting copies independently of caller sequence."""
    return (
        row.source_id,
        row.event_id,
        row.source_listing_id,
        row.address_key or "",
        row.parcel_key or "",
        row.unit_key or "",
        row.event_type,
        _utc(row.event_at).isoformat(),
        _utc(row.available_at).isoformat() if row.available_at else "",
        _utc(row.ingested_at).isoformat(),
        str(row.amount) if row.amount is not None else "",
    )


def _source_facts(row: ListingObservation) -> tuple[object, ...]:
    """Local ingestion is provenance, not a change to the upstream event."""
    return (
        row.source_id,
        row.event_id,
        row.source_listing_id,
        row.address_key,
        row.parcel_key,
        row.unit_key,
        row.event_type,
        _utc(row.event_at),
        _utc(row.available_at) if row.available_at else None,
        row.amount,
    )


def _property_match(
    row: ListingObservation, properties: Sequence[PropertyIdentity], origin: datetime
) -> tuple[str | None, str | None]:
    candidates = tuple(
        prop
        for prop in properties
        if _utc(prop.available_at) <= origin
        and _utc(prop.valid_from) <= _utc(row.event_at)
        and (prop.valid_to is None or _utc(row.event_at) < _utc(prop.valid_to))
        and (row.parcel_key is None or prop.parcel_key == row.parcel_key)
        and (row.address_key is None or prop.address_key == row.address_key)
        and (row.unit_key is None or prop.unit_key == row.unit_key)
    )
    if row.unit_key is None and any(prop.unit_key is not None for prop in candidates):
        return None, "unit_missing_ambiguous"
    if not candidates:
        return None, "property_not_found"
    if len(candidates) != 1:
        return None, "property_ambiguous"
    return candidates[0].property_id, None


def _canonical_events(
    rows: Sequence[ListingObservation],
) -> tuple[ResolvedEvent, ...] | None:
    by_instant: dict[datetime, set[tuple[str, Decimal | None]]] = {}
    by_fact: dict[tuple[datetime, str, Decimal | None], list[ListingObservation]] = {}
    for row in rows:
        instant = _utc(row.event_at)
        by_instant.setdefault(instant, set()).add((row.event_type, row.amount))
        by_fact.setdefault((instant, row.event_type, row.amount), []).append(row)
    if any(len(facts) > 1 for facts in by_instant.values()):
        return None
    return tuple(
        ResolvedEvent(
            event_type=event_type,
            event_at=instant,
            amount=amount,
            source_events=tuple(
                sorted(by_fact[(instant, event_type, amount)], key=_event_order)
            ),
        )
        for instant, event_type, amount in sorted(by_fact, key=lambda key: key[0])
    )


def _build_episodes(
    property_id: str, listing_id: str, events: tuple[ResolvedEvent, ...]
) -> tuple[ListingEpisode, ...] | None:
    episodes: list[ListingEpisode] = []
    current: list[ResolvedEvent] = []
    status: str | None = None
    asking_price: Decimal | None = None
    for item in events:
        if item.event_type == "published":
            if status is not None and status not in _TERMINAL:
                return None
            if current:
                assert status is not None and asking_price is not None
                episodes.append(
                    ListingEpisode(
                        property_id,
                        listing_id,
                        len(episodes) + 1,
                        status,
                        asking_price,
                        tuple(current),
                    )
                )
            current = [item]
            status = "active"
            asking_price = item.amount
            continue
        if not current or status in _TERMINAL:
            return None
        current.append(item)
        if item.event_type == "price_change":
            asking_price = item.amount
        elif item.event_type != "price_change":
            status = item.event_type if item.event_type != "pending" else "pending"
    if not current or status is None or asking_price is None:
        return None
    episodes.append(
        ListingEpisode(
            property_id,
            listing_id,
            len(episodes) + 1,
            status,
            asking_price,
            tuple(current),
        )
    )
    return tuple(episodes)


def _flag_overlaps(
    episodes: tuple[ListingEpisode, ...], origin: datetime
) -> tuple[ListingEpisode, ...]:
    flagged: list[ListingEpisode] = []
    for episode in episodes:
        start = _utc(episode.events[0].event_at)
        end = (
            _utc(episode.events[-1].event_at) if episode.status in _TERMINAL else origin
        )
        overlaps = any(
            other is not episode
            and other.property_id == episode.property_id
            and other.canonical_listing_id != episode.canonical_listing_id
            and start
            <= (
                _utc(other.events[-1].event_at) if other.status in _TERMINAL else origin
            )
            and _utc(other.events[0].event_at) <= end
            for other in episodes
        )
        flagged.append(
            replace(episode, flags=("overlapping_listings",) if overlaps else ())
        )
    return tuple(flagged)


def _available_aliases(
    aliases: Sequence[VerifiedListingAlias], cutoff: datetime
) -> dict[tuple[str, str], str]:
    alias_map: dict[tuple[str, str], str] = {}
    for alias in aliases:
        if _utc(alias.available_at) > cutoff:
            continue
        key = alias.source_id, alias.source_listing_id
        previous = alias_map.get(key)
        if previous is not None and previous != alias.canonical_listing_id:
            raise ValueError("Conflicting reviewed listing aliases")
        alias_map[key] = alias.canonical_listing_id
    return alias_map


def _visible_observations(
    observations: Sequence[ListingObservation], cutoff: datetime
) -> tuple[tuple[ListingObservation, ...], tuple[QuarantinedObservation, ...]]:
    quarantined: list[QuarantinedObservation] = []
    visible: list[ListingObservation] = []
    for row in observations:
        if _utc(row.event_at) > cutoff:
            continue
        if row.available_at is None:
            quarantined.append(QuarantinedObservation("availability_unknown", (row,)))
        elif _utc(row.available_at) <= cutoff:
            visible.append(row)
    return tuple(visible), tuple(quarantined)


def _deduplicate_source_events(
    visible: Sequence[ListingObservation],
) -> tuple[tuple[ListingObservation, ...], tuple[QuarantinedObservation, ...]]:
    by_source_event: dict[tuple[str, str], list[ListingObservation]] = {}
    for row in visible:
        by_source_event.setdefault((row.source_id, row.event_id), []).append(row)
    unique: list[ListingObservation] = []
    quarantined: list[QuarantinedObservation] = []
    for rows in by_source_event.values():
        if any(_source_facts(row) != _source_facts(rows[0]) for row in rows[1:]):
            quarantined.append(
                QuarantinedObservation(
                    "source_event_id_conflict", tuple(sorted(rows, key=_event_order))
                )
            )
        else:
            unique.extend(rows)
    return tuple(unique), tuple(quarantined)


def _link_observations(
    rows: Sequence[ListingObservation],
    properties: Sequence[PropertyIdentity],
    alias_map: dict[tuple[str, str], str],
    cutoff: datetime,
) -> tuple[
    dict[str, list[tuple[str, ListingObservation]]], tuple[QuarantinedObservation, ...]
]:
    grouped: dict[str, list[tuple[str, ListingObservation]]] = {}
    quarantined: list[QuarantinedObservation] = []
    for row in rows:
        property_id, reason = _property_match(row, properties, cutoff)
        if reason is not None:
            quarantined.append(QuarantinedObservation(reason, (row,)))
            continue
        assert property_id is not None
        key = row.source_id, row.source_listing_id
        listing_id = (
            f"reviewed:{alias_map[key]}"
            if key in alias_map
            else f"source:{key[0]}:{key[1]}"
        )
        grouped.setdefault(listing_id, []).append((property_id, row))
    return grouped, tuple(quarantined)


def _resolve_groups(
    grouped: dict[str, list[tuple[str, ListingObservation]]],
) -> tuple[tuple[ListingEpisode, ...], tuple[QuarantinedObservation, ...]]:
    episodes: list[ListingEpisode] = []
    quarantined: list[QuarantinedObservation] = []
    for listing_id, linked in sorted(grouped.items()):
        rows = tuple(row for _, row in linked)
        if len({property_id for property_id, _ in linked}) != 1:
            quarantined.append(
                QuarantinedObservation(
                    "listing_alias_property_conflict",
                    tuple(sorted(rows, key=_event_order)),
                )
            )
            continue
        events = _canonical_events(rows)
        if events is None:
            quarantined.append(
                QuarantinedObservation(
                    "conflicting_simultaneous_events",
                    tuple(sorted(rows, key=_event_order)),
                )
            )
            continue
        built = _build_episodes(linked[0][0], listing_id, events)
        if built is None:
            quarantined.append(
                QuarantinedObservation(
                    "invalid_episode_sequence", tuple(sorted(rows, key=_event_order))
                )
            )
            continue
        episodes.extend(built)
    return tuple(episodes), tuple(quarantined)


def resolve_lifecycle(
    properties: Sequence[PropertyIdentity],
    observations: Sequence[ListingObservation],
    *,
    aliases: Sequence[VerifiedListingAlias] = (),
    origin: datetime,
) -> LifecycleResolution:
    """Resolve one as-of view; ambiguities are quarantined, never guessed."""
    _instant(origin, "origin")
    cutoff = _utc(origin)
    alias_map = _available_aliases(aliases, cutoff)
    visible, unavailable = _visible_observations(observations, cutoff)
    unique, duplicates = _deduplicate_source_events(visible)
    grouped, unmatched = _link_observations(unique, properties, alias_map, cutoff)
    episodes, invalid = _resolve_groups(grouped)
    ordered = tuple(
        sorted(
            episodes,
            key=lambda e: (e.property_id, e.canonical_listing_id, e.generation),
        )
    )
    return LifecycleResolution(
        episodes=_flag_overlaps(ordered, cutoff),
        quarantined=tuple(
            sorted(
                (*unavailable, *duplicates, *unmatched, *invalid),
                key=lambda q: (q.reason, tuple(map(_event_order, q.source_events))),
            )
        ),
        source_events=tuple(sorted(visible, key=_event_order)),
    )
