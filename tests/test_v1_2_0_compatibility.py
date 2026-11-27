"""Regression guards for the additive V1.2.0 couple patch."""

from datetime import datetime, time

from fumades_solver.export import export_result
from fumades_solver.io import minutes


def test_minutes_public_compatibility_helper():
    assert minutes("00:00") == 0
    assert minutes("07:45") == 465
    assert minutes("08:30:00") == 510
    assert minutes("2026-01-01T09:05:00") == 545
    assert minutes(600) == 600
    assert minutes(time(10, 15)) == 615
    assert minutes(datetime(2026, 1, 1, 11, 20)) == 680


def test_v1_1_1_export_result_api_is_preserved():
    # The complete behavioural contract remains covered by tests/test_v1_1_1.py.
    assert callable(export_result)
