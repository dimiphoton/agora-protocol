"""Stress-test paramétrique et audit de viabilité du cœur Emergent."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random

from .dynamic_queue import LiquidQueue, QueueItem
from .unbundling import WorkItem, classify_track


def _check_finite_non_negative(value: float, field_name: str) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} doit être fini et positif ou nul")


@dataclass(frozen=True)
class StressParameters:
    """Paramètres bornés d'une campagne de stress reproductible."""

    iterations: int = 10
    item_count: int = 100
    capacity: float = 25.0
    min_effort: float = 0.25
    max_effort: float = 2.0
    emergency_tax_rate: float = 0.05
    seed: int = 0
    budget: float | None = None
    required_budget: float = 0.0
    physical_capacity: float | None = None
    physical_demand: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.iterations, int) or self.iterations <= 0:
            raise ValueError("iterations doit être un entier strictement positif")
        if not isinstance(self.item_count, int) or self.item_count <= 0:
            raise ValueError("item_count doit être un entier strictement positif")
        _check_finite_non_negative(self.capacity, "capacity")
        _check_finite_non_negative(self.min_effort, "min_effort")
        _check_finite_non_negative(self.max_effort, "max_effort")
        if self.min_effort == 0 or self.max_effort < self.min_effort:
            raise ValueError("les bornes d'effort sont invalides")
        if not isinstance(self.emergency_tax_rate, (int, float)) or not 0 <= self.emergency_tax_rate <= 1:
            raise ValueError("emergency_tax_rate doit être compris entre 0 et 1")
        if self.budget is not None:
            _check_finite_non_negative(self.budget, "budget")
        _check_finite_non_negative(self.required_budget, "required_budget")
        if self.physical_capacity is not None:
            _check_finite_non_negative(self.physical_capacity, "physical_capacity")
        _check_finite_non_negative(self.physical_demand, "physical_demand")


@dataclass(frozen=True)
class ViabilityAudit:
    """Audit explicite de solvabilité et de faisabilité physique."""

    solvent: bool
    physically_feasible: bool
    violations: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.solvent and self.physically_feasible

    @property
    def feasible(self) -> bool:
        return self.valid


def audit_viability(
    *,
    budget: float | None = None,
    required_budget: float = 0.0,
    physical_capacity: float | None = None,
    physical_demand: float = 0.0,
) -> ViabilityAudit:
    """Vérifie sans effet de bord qu'un accord est solvable et réalisable."""

    for value, name in ((required_budget, "required_budget"), (physical_demand, "physical_demand")):
        _check_finite_non_negative(value, name)
    if budget is not None:
        _check_finite_non_negative(budget, "budget")
    if physical_capacity is not None:
        _check_finite_non_negative(physical_capacity, "physical_capacity")
    violations: list[str] = []
    solvent = budget is None or budget >= required_budget
    physically_feasible = (
        physical_capacity is None or physical_capacity >= physical_demand
    )
    if budget is not None and not solvent:
        violations.append(
            f"insolvabilité budgétaire: {budget} disponible pour {required_budget}"
        )
    if physical_capacity is not None and not physically_feasible:
        violations.append(
            "contrainte physique impossible: "
            f"{physical_demand} demandé pour {physical_capacity}"
        )
    return ViabilityAudit(solvent, physically_feasible, tuple(violations))


audit_agreement = audit_viability
audit_stress = audit_viability


@dataclass(frozen=True)
class StressReport:
    """Mesures agrégées d'une campagne de stress."""

    iterations: int
    generated_items: int
    completed_items: int
    deferred_items: int
    completion_rate: float
    average_completed_per_iteration: float
    emergency_tax: float
    max_queue_size: int
    audit: ViabilityAudit | None = None

    @property
    def violations(self) -> tuple[str, ...]:
        return () if self.audit is None else self.audit.violations


def run_stress_test(
    parameters: StressParameters | None = None,
    *,
    seed: int | None = None,
) -> StressReport:
    """Exécute une campagne locale et rejette un scénario non viable."""

    settings = parameters or StressParameters()
    if not isinstance(settings, StressParameters):
        raise TypeError("parameters doit être un StressParameters")
    audit = None
    if settings.budget is not None or settings.physical_capacity is not None:
        audit = audit_viability(
            budget=settings.budget,
            required_budget=settings.required_budget,
            physical_capacity=settings.physical_capacity,
            physical_demand=settings.physical_demand,
        )
        if not audit.valid:
            raise ValueError("; ".join(audit.violations))

    random = Random(settings.seed if seed is None else seed)
    generated_items = settings.iterations * settings.item_count
    completed_items = 0
    deferred_items = 0
    emergency_tax = 0.0
    max_queue_size = 0

    for iteration in range(settings.iterations):
        queue = LiquidQueue()
        for index in range(settings.item_count):
            work_item = WorkItem(
                item_id=f"stress-{iteration}-{index}",
                urgency=random.random(),
                complexity=random.random(),
                volatility=random.random(),
            )
            queue.add(
                QueueItem(
                    item_id=work_item.item_id,
                    priority=work_item.urgency,
                    effort=random.uniform(settings.min_effort, settings.max_effort),
                    track=classify_track(work_item),
                )
            )
        max_queue_size = max(max_queue_size, len(queue))
        result = queue.redistribute(
            settings.capacity,
            emergency_tax_rate=settings.emergency_tax_rate,
        )
        completed_items += len(result.selected)
        deferred_items += len(result.deferred)
        emergency_tax += result.emergency_tax

    return StressReport(
        iterations=settings.iterations,
        generated_items=generated_items,
        completed_items=completed_items,
        deferred_items=deferred_items,
        completion_rate=completed_items / generated_items,
        average_completed_per_iteration=completed_items / settings.iterations,
        emergency_tax=emergency_tax,
        max_queue_size=max_queue_size,
        audit=audit,
    )


stress_test = run_stress_test

