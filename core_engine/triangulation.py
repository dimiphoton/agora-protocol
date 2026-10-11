"""Croisement traçable des trois vecteurs de préférence Emergent."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any, Iterable, Mapping


def _check_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("le nom du rôle doit être une chaîne non vide")


@dataclass(frozen=True)
class Negotiator:
    """Rôle qui rapproche les préférences et explicite les compromis."""

    name: str
    mandate: str = ""

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class Requester:
    """Rôle qui porte le besoin initial."""

    name: str
    need: str = ""

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class NeedOracle:
    """Rôle qui vérifie que le besoin est explicite et mesurable."""

    name: str
    criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class Certifier:
    """Rôle qui confirme qu'une proposition respecte les critères."""

    name: str
    certification_scope: str = ""

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class RedTeamer:
    """Rôle qui cherche activement les failles d'une décision."""

    name: str
    focus: str = ""

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class Auditor:
    """Rôle qui vérifie la traçabilité et les règles d'exécution."""

    name: str
    audit_scope: str = ""

    def __post_init__(self) -> None:
        _check_name(self.name)


@dataclass(frozen=True)
class Preference:
    """Signal numérique d'un acteur sur un critère, dans l'intervalle [0, 1]."""

    actor: str
    criterion: str
    value: float
    weight: float = 1.0
    confidence: float = 1.0
    source: str = "legacy"

    def __post_init__(self) -> None:
        _check_name(self.actor)
        _check_name(self.criterion)
        _check_unit_interval(self.value, "value")
        if not isfinite(self.weight) or self.weight <= 0:
            raise ValueError("weight doit être un nombre strictement positif")
        _check_unit_interval(self.confidence, "confidence")
        _check_name(self.source)


class DeclarativePreference(Preference):
    """Préférence déclarée, issue du langage naturel (NLP)."""


class InstinctivePreference(Preference):
    """Préférence observée sous pression ou dans un jeu stratégique."""


class BudgetaryPreference(Preference):
    """Préférence révélée par une allocation de ressources limitée."""


@dataclass(frozen=True)
class TriangulationResult:
    """Matrice réelle, métriques de consensus et traces des trois vecteurs."""

    consensus: dict[str, float]
    confidence: dict[str, float]
    disagreement: dict[str, float]
    real_preference_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    trace: dict[str, dict[str, tuple[dict[str, Any], ...]]] = field(
        default_factory=dict
    )

    @property
    def scores(self) -> dict[str, float]:
        """Alias lisible pour le consensus numérique."""

        return self.consensus

    @property
    def preference_matrix(self) -> dict[str, dict[str, float]]:
        """Nom anglais court de la Matrice de Préférences Réelles."""

        return self.real_preference_matrix

    @property
    def matrix(self) -> dict[str, dict[str, float]]:
        return self.real_preference_matrix

    @property
    def traceability(self) -> dict[str, dict[str, tuple[dict[str, Any], ...]]]:
        return self.trace


def _check_unit_interval(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} doit être un nombre fini")
    if not 0 <= value <= 1:
        raise ValueError(f"{field_name} doit être compris entre 0 et 1")


def _from_mapping(
    preferences: Mapping[str, Mapping[str, float]],
    source: str,
) -> list[Preference]:
    """Convertit ``acteur -> critère -> valeur`` vers des signaux typés."""

    signals: list[Preference] = []
    for actor, actor_preferences in preferences.items():
        if not isinstance(actor_preferences, Mapping):
            raise TypeError("chaque préférence d'acteur doit être un mapping")
        for criterion, value in actor_preferences.items():
            signals.append(Preference(actor, criterion, value, source=source))
    return signals


def _signal_from_item(item: Any, source: str) -> Preference:
    if isinstance(item, Preference):
        return replace(item, source=source)
    if isinstance(item, Mapping):
        try:
            return Preference(
                actor=item["actor"],
                criterion=item["criterion"],
                value=item["value"],
                weight=item.get("weight", 1.0),
                confidence=item.get("confidence", 1.0),
                source=source,
            )
        except KeyError as error:
            raise ValueError(
                "un signal doit contenir actor, criterion et value"
            ) from error
    raise TypeError("les signaux doivent être des Preference ou des mappings")


def _normalise_vector(vector: Any, source: str) -> list[Preference]:
    if vector is None:
        return []
    if isinstance(vector, Mapping):
        return _from_mapping(vector, source)
    return [_signal_from_item(item, source) for item in vector]


def triangulate_preferences(
    preferences: Iterable[Preference]
    | Mapping[str, Mapping[str, float]]
    | None = None,
    *,
    declarative: Iterable[Preference]
    | Mapping[str, Mapping[str, float]]
    | None = None,
    instinctive: Iterable[Preference]
    | Mapping[str, Mapping[str, float]]
    | None = None,
    budgetary: Iterable[Preference]
    | Mapping[str, Mapping[str, float]]
    | None = None,
) -> TriangulationResult:
    """Produit une matrice réelle à partir des trois vecteurs distincts.

    Chaque vecteur peut être un mapping ``acteur -> critère -> valeur`` ou une
    liste de signaux. Les entrées sont conservées dans ``trace`` pour rendre
    le calcul auditable.
    """

    signals: list[Preference] = []
    if preferences is not None:
        signals.extend(_normalise_vector(preferences, "legacy"))
    for vector, source in (
        (declarative, "declarative_nlp"),
        (instinctive, "instinctive_game_theory"),
        (budgetary, "budgetary_allocation"),
    ):
        signals.extend(_normalise_vector(vector, source))
    if not signals:
        raise ValueError("au moins une préférence est nécessaire")

    by_actor_criterion: dict[tuple[str, str], list[Preference]] = {}
    by_criterion: dict[str, list[Preference]] = {}
    for signal in signals:
        by_actor_criterion.setdefault(
            (signal.actor, signal.criterion), []
        ).append(signal)
        by_criterion.setdefault(signal.criterion, []).append(signal)

    def weighted_mean(group: list[Preference]) -> float:
        weights = [signal.weight * signal.confidence for signal in group]
        return sum(
            signal.value * weight for signal, weight in zip(group, weights)
        ) / sum(weights)

    matrix: dict[str, dict[str, float]] = {}
    trace: dict[str, dict[str, tuple[dict[str, Any], ...]]] = {}
    for (actor, criterion), group in by_actor_criterion.items():
        matrix.setdefault(actor, {})[criterion] = weighted_mean(group)
        trace.setdefault(actor, {})[criterion] = tuple(
            {
                "source": signal.source,
                "value": signal.value,
                "weight": signal.weight,
                "confidence": signal.confidence,
            }
            for signal in group
        )

    consensus: dict[str, float] = {}
    confidence: dict[str, float] = {}
    disagreement: dict[str, float] = {}
    for criterion, group in by_criterion.items():
        weights = [signal.weight * signal.confidence for signal in group]
        mean = sum(
            signal.value * weight for signal, weight in zip(group, weights)
        ) / sum(weights)
        mean_deviation = sum(
            weight * abs(signal.value - mean)
            for signal, weight in zip(group, weights)
        ) / sum(weights)
        consensus[criterion] = mean
        disagreement[criterion] = mean_deviation
        confidence[criterion] = max(0.0, min(1.0, 1.0 - mean_deviation))

    return TriangulationResult(
        consensus,
        confidence,
        disagreement,
        matrix,
        trace,
    )


triangulate = triangulate_preferences
DeclarativeSignal = DeclarativePreference
InstinctiveSignal = InstinctivePreference
BudgetarySignal = BudgetaryPreference
Demandeur = Requester
OracleDeBesoin = NeedOracle
Certifieur = Certifier

