"""V1.1 compatibility smoke test kept under the historical filename."""

from pathlib import Path


def test_v1_1_1_overlay_contains_demo() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "data" / "demo" / "stays.csv").exists()
    assert (root / "data" / "demo" / "care_requests.csv").exists()
