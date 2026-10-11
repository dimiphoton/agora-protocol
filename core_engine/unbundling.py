"""Découplage des tâches entre Fast, Slow et Cold Track."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable


class Track(str, Enum):
    """Voie d'exécution d'une tâche."""

    FAST = "fast"
    SLOW = "slow"
    COLD = "cold"


def _check_score(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} doit être un nombre fini")
    if not 0 <= value <= 1:
        raise ValueError(f"{field_name} doit être compris entre 0 et 1")


@dataclass(frozen=True)
class WorkItem:
    """Unité de travail avec des signaux de routage normalisés."""

    item_id: str
    description: str = ""
    urgency: float = 0.5
    complexity: float = 0.5
    volatility: float = 0.5
    dependencies: tuple[str, ...] = ()
    track: Track | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("item_id doit être une chaîne non vide")
        for value, name in (
            (self.urgency, "urgency"),
            (self.complexity, "complexity"),
            (self.volatility, "volatility"),
        ):
            _check_score(value, name)
        if self.track is not None and not isinstance(self.track, Track):
            try:
                object.__setattr__(self, "track", Track(self.track))
            except ValueError as error:
                raise ValueError("track doit être fast, slow ou cold") from error
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        if any(
            not isinstance(dependency, str) or not dependency.strip()
            for dependency in self.dependencies
        ):
            raise ValueError("les dépendances doivent être des identifiants non vides")


@dataclass(frozen=True)
class TrackBundle:
    """Résultat du découplage, conservant l'ordre d'entrée de chaque voie."""

    fast: tuple[WorkItem, ...] = ()
    slow: tuple[WorkItem, ...] = ()
    cold: tuple[WorkItem, ...] = ()

    def for_track(self, track: Track | str) -> tuple[WorkItem, ...]:
        """Retourne les tâches d'une voie donnée."""

        selected_track = Track(track)
        return {
            Track.FAST: self.fast,
            Track.SLOW: self.slow,
            Track.COLD: self.cold,
        }[selected_track]

    def executable(
        self,
        blocked_tracks: Iterable[Track | str] = (),
    ) -> tuple[WorkItem, ...]:
        """Retourne les voies disponibles sans propager un blocage.

        Un blocage Slow ou Cold ne retire donc jamais les tâches Fast.
        """

        blocked = {Track(track) for track in blocked_tracks}
        return tuple(
            item
            for track in (Track.FAST, Track.SLOW, Track.COLD)
            if track not in blocked
            for item in self.for_track(track)
        )

    @property
    def all_items(self) -> tuple[WorkItem, ...]:
        return self.fast + self.slow + self.cold


def classify_track(item: WorkItem) -> Track:
    """Classe une tâche selon ses signaux, sauf si une voie est imposée.

    Une tâche urgente et peu volatile est traitée rapidement. Une tâche peu
    urgente et stable peut rester froide ; les autres vont en Slow Track.
    """

    if not isinstance(item, WorkItem):
        raise TypeError("item doit être un WorkItem")
    if item.track is not None:
        return item.track
    if item.urgency >= 0.7:
        return Track.FAST
    if item.urgency <= 0.3 and item.volatility <= 0.3:
        return Track.COLD
    return Track.SLOW


def unbundle(items: Iterable[WorkItem]) -> TrackBundle:
    """Répartit les tâches sans les dupliquer ni les réordonner par voie."""

    fast: list[WorkItem] = []
    slow: list[WorkItem] = []
    cold: list[WorkItem] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, WorkItem):
            raise TypeError("items doit contenir des WorkItem")
        if item.item_id in seen_ids:
            raise ValueError(f"identifiant dupliqué: {item.item_id}")
        seen_ids.add(item.item_id)
        track = classify_track(item)
        if track is Track.FAST:
            fast.append(item)
        elif track is Track.SLOW:
            slow.append(item)
        else:
            cold.append(item)
    return TrackBundle(tuple(fast), tuple(slow), tuple(cold))


decouple_tracks = unbundle


def executable_tracks(
    items: Iterable[WorkItem],
    blocked_tracks: Iterable[Track | str] = (),
) -> tuple[WorkItem, ...]:
    """Route et exécute logiquement les voies non bloquées."""

    return unbundle(items).executable(blocked_tracks)

