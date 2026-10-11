"""File d'ordonnancement liquide et rente de patience simulée."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Iterable

from .unbundling import Track


def _check_non_negative(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} doit être un nombre fini positif ou nul")


def _check_positive(value: float, field_name: str) -> None:
    _check_non_negative(value, field_name)
    if value == 0:
        raise ValueError(f"{field_name} doit être strictement positif")


def _check_rate(value: float, field_name: str, *, allow_zero: bool = True) -> None:
    if (
        not isinstance(value, (int, float))
        or not isfinite(value)
        or not allow_zero and value <= 0
        or allow_zero and value < 0
        or value > 1
    ):
        raise ValueError(f"{field_name} doit être compris entre 0 et 1")


@dataclass(frozen=True)
class QueueItem:
    """Élément ordonnançable avec score économique et badges de nécessité."""

    item_id: str
    priority: float = 0.5
    effort: float = 1.0
    track: Track = Track.SLOW
    requester: str = ""
    financial_stake: float = 0.0
    reputation: float = 0.0
    requested_duration: float = 1.0
    necessity_badges: tuple[str, ...] = ()
    role: str = ""
    roles: tuple[str, ...] = ()
    badge_boost: float = 0.25
    patience_rent: float = 0.0
    # Alias lisibles acceptés par les intégrations existantes.
    financial_bid: float | None = None
    duration_requested: float | None = None
    badges: tuple[str, ...] | None = None
    _economic_model: bool = field(default=False, init=False, repr=False)
    _bump_bonus: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("item_id doit être une chaîne non vide")
        _check_non_negative(self.priority, "priority")
        _check_non_negative(self.effort, "effort")
        _check_non_negative(self.financial_stake, "financial_stake")
        _check_non_negative(self.reputation, "reputation")
        _check_positive(self.requested_duration, "requested_duration")
        _check_rate(self.badge_boost, "badge_boost")
        _check_non_negative(self.patience_rent, "patience_rent")
        if self.financial_bid is not None:
            _check_non_negative(self.financial_bid, "financial_bid")
            object.__setattr__(self, "financial_stake", self.financial_bid)
        if self.duration_requested is not None:
            _check_positive(self.duration_requested, "duration_requested")
            object.__setattr__(self, "requested_duration", self.duration_requested)
        if self.badges is not None:
            object.__setattr__(self, "necessity_badges", tuple(self.badges))
        if not isinstance(self.track, Track):
            try:
                object.__setattr__(self, "track", Track(self.track))
            except ValueError as error:
                raise ValueError("track doit être fast, slow ou cold") from error
        if any(
            not isinstance(badge, str) or not badge.strip()
            for badge in self.necessity_badges
        ):
            raise ValueError("les badges de nécessité doivent être non vides")
        if any(not isinstance(role, str) or not role.strip() for role in self.roles):
            raise ValueError("les rôles doivent être des chaînes non vides")
        if self.role and not isinstance(self.role, str):
            raise TypeError("role doit être une chaîne")
        object.__setattr__(
            self,
            "_economic_model",
            bool(
                self.financial_bid is not None
                or self.duration_requested is not None
                or self.financial_stake
                or self.reputation
                or self.necessity_badges
            ),
        )

    @property
    def score(self) -> float:
        """Score dynamique : (mise + réputation) / durée, avec badge."""

        if self._economic_model:
            base = (self.financial_stake + self.reputation) / self.requested_duration
            base *= 1 + self.badge_boost * len(set(self.necessity_badges))
        else:
            # Compatibilité avec l'ancienne API fondée sur ``priority``.
            base = self.priority
        return base + self._bump_bonus

    @property
    def proof_of_waiting(self) -> float:
        """Rente de patience accumulée par les reculs subis."""

        return self.patience_rent


@dataclass(frozen=True)
class RedistributionResult:
    """Résultat d'une capacité d'exécution sur la file courante."""

    selected: tuple[QueueItem, ...]
    deferred: tuple[QueueItem, ...]
    capacity_used: float
    emergency_tax: float
    patience_rents: dict[str, float] = field(default_factory=dict)

    @property
    def proof_of_waiting(self) -> dict[str, float]:
        return self.patience_rents


@dataclass
class LiquidQueue:
    """File mutable triée par score, avec bump taxé et redistribution."""

    _items: dict[str, QueueItem] = field(default_factory=dict, init=False)
    _order: dict[str, int] = field(default_factory=dict, init=False)
    _next_order: int = field(default=0, init=False)
    emergency_tax_collected: float = field(default=0.0, init=False)
    patience_rent_distributed: float = field(default=0.0, init=False)
    last_bump_tax: float = field(default=0.0, init=False)

    def add(self, item: QueueItem) -> None:
        """Ajoute un élément et rejette les identifiants déjà présents."""

        if not isinstance(item, QueueItem):
            raise TypeError("item doit être un QueueItem")
        if item.item_id in self._items:
            raise ValueError(f"identifiant déjà présent: {item.item_id}")
        self._items[item.item_id] = item
        self._order[item.item_id] = self._next_order
        self._next_order += 1

    def extend(self, items: Iterable[QueueItem]) -> None:
        for item in items:
            self.add(item)

    def bump(
        self,
        item_id: str,
        amount: float,
        emergency_tax_rate: float = 0.0,
    ) -> QueueItem:
        """Bump autorisé seulement si une taxe d'urgence est effectivement payée."""

        _check_positive(amount, "amount")
        _check_rate(emergency_tax_rate, "emergency_tax_rate", allow_zero=False)
        if item_id not in self._items:
            raise KeyError(f"élément absent: {item_id}")

        before = self.ordered()
        current = self._items[item_id]
        tax = amount * emergency_tax_rate
        if current._economic_model:
            updated = replace(
                current,
                financial_stake=current.financial_stake + amount,
                financial_bid=None,
            )
            object.__setattr__(updated, "_economic_model", True)
            object.__setattr__(updated, "_bump_bonus", current._bump_bonus)
        else:
            updated = replace(current, priority=current.priority + amount)
            object.__setattr__(updated, "_bump_bonus", current._bump_bonus)
        self._items[item_id] = updated
        after = self.ordered()
        old_positions = {item.item_id: index for index, item in enumerate(before)}
        displaced = [
            item for index, item in enumerate(after)
            if item.item_id != item_id and index > old_positions[item.item_id]
        ]
        rent = tax / len(displaced) if displaced else 0.0
        for item in displaced:
            self._items[item.item_id] = replace(
                self._items[item.item_id],
                patience_rent=self._items[item.item_id].patience_rent + rent,
            )
        self.emergency_tax_collected += tax
        self.patience_rent_distributed += rent * len(displaced)
        self.last_bump_tax = tax
        return self._items[item_id]

    def ordered(self) -> tuple[QueueItem, ...]:
        """Retourne une vue priorisée sans retirer d'élément."""

        return tuple(
            sorted(
                self._items.values(),
                key=lambda item: (-item.score, self._order[item.item_id]),
            )
        )

    def pop_next(self) -> QueueItem:
        if not self._items:
            raise IndexError("la file est vide")
        item = self.ordered()[0]
        del self._items[item.item_id]
        del self._order[item.item_id]
        return item

    def __len__(self) -> int:
        return len(self._items)

    def redistribute(
        self,
        capacity: float,
        emergency_tax_rate: float = 0.0,
    ) -> RedistributionResult:
        """Sélectionne les tâches qui tiennent dans la capacité disponible."""

        result = redistribute(
            self.ordered(),
            capacity=capacity,
            emergency_tax_rate=emergency_tax_rate,
        )
        for item in result.selected:
            self._items.pop(item.item_id, None)
            self._order.pop(item.item_id, None)
        self.emergency_tax_collected += result.emergency_tax
        return result


def redistribute(
    items: Iterable[QueueItem],
    capacity: float,
    emergency_tax_rate: float = 0.0,
) -> RedistributionResult:
    """Répartit une capacité limitée selon le score décroissant."""

    _check_non_negative(capacity, "capacity")
    _check_rate(emergency_tax_rate, "emergency_tax_rate")
    candidates = list(items)
    if not all(isinstance(item, QueueItem) for item in candidates):
        raise TypeError("items doit contenir des QueueItem")
    if len({item.item_id for item in candidates}) != len(candidates):
        raise ValueError("les identifiants de la file doivent être uniques")

    selected: list[QueueItem] = []
    deferred: list[QueueItem] = []
    remaining = float(capacity)
    for item in candidates:
        if item.effort <= remaining:
            selected.append(item)
            remaining -= item.effort
        else:
            deferred.append(item)
    emergency_tax = sum(
        item.effort * emergency_tax_rate
        for item in selected
        if item.track is Track.FAST
    )
    return RedistributionResult(
        selected=tuple(selected),
        deferred=tuple(deferred),
        capacity_used=float(capacity) - remaining,
        emergency_tax=emergency_tax,
    )


def bump_item(
    items: Iterable[QueueItem],
    item_id: str,
    amount: float,
    emergency_tax_rate: float = 0.0,
) -> tuple[QueueItem, ...]:
    """Version fonctionnelle de ``LiquidQueue.bump`` pour les scripts."""

    queue = LiquidQueue()
    queue.extend(items)
    queue.bump(item_id, amount, emergency_tax_rate)
    return queue.ordered()

