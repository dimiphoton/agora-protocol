import pytest

from core_engine.dynamic_queue import LiquidQueue, QueueItem
from core_engine.stress_test import StressParameters, run_stress_test
from core_engine.triangulation import Preference, triangulate_preferences
from core_engine.unbundling import Track, WorkItem, unbundle


def test_triangulation_is_weighted_and_reports_disagreement() -> None:
    result = triangulate_preferences(
        [
            Preference("requester", "value", 1.0),
            Preference("oracle", "value", 0.0),
        ]
    )

    assert result.consensus["value"] == pytest.approx(0.5)
    assert result.disagreement["value"] == pytest.approx(0.5)
    assert result.confidence["value"] == pytest.approx(0.5)


def test_unbundle_routes_explicit_and_implicit_tracks() -> None:
    bundle = unbundle(
        [
            WorkItem("urgent", urgency=0.9),
            WorkItem("stable", urgency=0.1, volatility=0.1),
            WorkItem("normal", urgency=0.5),
            WorkItem("forced", track=Track.COLD),
        ]
    )

    assert [item.item_id for item in bundle.fast] == ["urgent"]
    assert [item.item_id for item in bundle.slow] == ["normal"]
    assert [item.item_id for item in bundle.cold] == ["stable", "forced"]


def test_liquid_queue_bump_and_redistribution() -> None:
    queue = LiquidQueue()
    queue.add(QueueItem("slow", priority=0.2, effort=1.0))
    queue.add(QueueItem("fast", priority=0.5, effort=1.0, track=Track.FAST))
    queue.bump("slow", amount=0.5, emergency_tax_rate=0.1)

    result = queue.redistribute(capacity=1.0, emergency_tax_rate=0.2)

    assert [item.item_id for item in result.selected] == ["slow"]
    assert [item.item_id for item in result.deferred] == ["fast"]
    assert result.emergency_tax == pytest.approx(0.0)
    assert queue.emergency_tax_collected == pytest.approx(0.05)


def test_stress_test_is_reproducible_and_validates_parameters() -> None:
    parameters = StressParameters(iterations=2, item_count=5, capacity=3, seed=7)

    first = run_stress_test(parameters)
    second = run_stress_test(parameters)

    assert first == second
    with pytest.raises(ValueError):
        StressParameters(iterations=0)

