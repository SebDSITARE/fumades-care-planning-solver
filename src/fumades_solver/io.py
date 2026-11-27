from __future__ import annotations
import csv, json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def minutes(value: str) -> int:
    if value is None or value == "":
        raise ValueError("Heure vide")
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def hhmm(value: int | None) -> str:
    if value is None:
        return ""
    return f"{value // 60:02d}:{value % 60:02d}"


def load_problem(input_dir: Path, parameter_dir: Path, config_path: Path) -> dict:
    return {
        "config": load_json(config_path),
        "stays": read_csv(input_dir / "stays.csv"),
        "requests": read_csv(input_dir / "care_requests.csv"),
        "care_types": read_csv(parameter_dir / "care_types.csv"),
        "resources": read_csv(parameter_dir / "resources.csv"),
        "compatibilities": read_csv(parameter_dir / "care_resource_compatibility.csv"),
        "transitions": read_csv(parameter_dir / "transitions.csv"),
        "workforce": read_csv(parameter_dir / "workforce_pools.csv"),
    }
