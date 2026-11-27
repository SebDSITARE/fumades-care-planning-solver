from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable


TRUE_VALUES = {"1", "true", "yes", "oui", "vrai", "y"}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _pick(row: dict[str, str], *names: str, default: str = "") -> str:
    normalized = {_norm(k): (v or "").strip() for k, v in row.items() if k is not None}
    for name in names:
        if _norm(name) in normalized:
            return normalized[_norm(name)]
    return default


def as_bool(value: str | bool | None) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def time_to_minutes(value: str | None) -> int | None:
    if value is None or not str(value).strip():
        return None
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Heure invalide: {value!r}")
    hour, minute = (int(x) for x in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Heure invalide: {value!r}")
    return hour * 60 + minute


def minutes_to_time(value: int | None) -> str:
    if value is None:
        return ""
    value %= 24 * 60
    return f"{value // 60:02d}:{value % 60:02d}"


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class Stay:
    stay_id: str
    client_ref: str
    start_date: date
    end_date: date
    primary_orientation: str
    secondary_orientation: str = ""
    package_primary: str = ""
    package_secondary: str = ""
    earliest_start: int = 0
    preferred_day_start: int = 0
    latest_start: int = 23 * 60 + 55
    pmr_level: int = 0
    planning_communicated: bool = False


@dataclass(frozen=True)
class CareRequest:
    request_id: str
    stay_id: str
    service_date: date
    care_code: str
    sector: str
    mode_plan: str
    preferred_start: int | None = None
    locked_start: int | None = None
    locked_resource: str = ""
    medical_override: bool = False
    catchup_reason: str = ""

    @property
    def has_slot(self) -> bool:
        return _norm(self.mode_plan) not in {"sans_creneau", "no_slot", "none"}


@dataclass(frozen=True)
class CareType:
    care_code: str
    duration_minutes: int
    provisional: bool = False
    dry_care: bool = False


@dataclass
class Parameters:
    care_types: dict[str, CareType] = field(default_factory=dict)
    compatibility: dict[str, list[str]] = field(default_factory=dict)
    resource_sector: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def care(self, code: str) -> CareType:
        if code in self.care_types:
            return self.care_types[code]
        duration = FALLBACK_DURATIONS.get(code, 5)
        return CareType(
            code,
            duration,
            provisional=code in FALLBACK_PROVISIONAL,
            dry_care=code in FALLBACK_DRY,
        )

    def resources_for(self, request: CareRequest) -> list[str]:
        resources = list(self.compatibility.get(request.care_code, []))
        if request.locked_resource:
            return [request.locked_resource]
        if request.sector and resources:
            sector_matches = [
                r for r in resources
                if not self.resource_sector.get(r)
                or self.resource_sector.get(r) in {request.sector, "MIXTE", "ALL"}
            ]
            if sector_matches:
                resources = sector_matches
        if resources:
            return sorted(set(resources))
        fallback = FALLBACK_RESOURCES.get((request.care_code, request.sector))
        if fallback:
            return list(fallback)
        fallback = FALLBACK_RESOURCES.get((request.care_code, ""))
        if fallback:
            return list(fallback)
        return [f"AUTO-{request.care_code}-{request.sector or 'GEN'}"]


FALLBACK_DURATIONS = {
    "0206": 15,
    "0301": 5,
    "0304": 5,
    "0306": 10,
    "0307": 5,
    "0308": 6,
    "0324": 5,
    "0327": 10,
    "0408": 15,
    "0507": 0,
    "0513": 15,
    "0601": 10,
    "0701": 10,
}
FALLBACK_PROVISIONAL = {"0308", "0701"}
FALLBACK_DRY = {"0408"}
FALLBACK_RESOURCES: dict[tuple[str, str], tuple[str, ...]] = {
    ("0206", "RH"): ("B1RH",),
    ("0206", "DER"): ("B1D",),
    ("0301", "DER"): ("DER_GENERAL",),
    ("0304", "DER"): ("DJD1",),
    ("0306", "RH"): ("PISC_RH",),
    ("0307", "RH"): ("TH1", "TH2"),
    ("0308", "RH"): ("DP1R",),
    ("0324", "DER"): ("PULV_DER_1", "PULV_DER_2"),
    ("0327", "VR"): ("VR01",),
    ("0408", "RH"): ("CA01", "CA02"),
    ("0513", "RH"): ("PM",),
    ("0601", "RH"): ("MOB_RH",),
}


def load_input(input_dir: str | Path) -> tuple[list[Stay], list[CareRequest]]:
    root = Path(input_dir)
    stays: list[Stay] = []
    for row in _rows(root / "stays.csv"):
        legacy_preferred = time_to_minutes(_pick(row, "preferred_start"))
        earliest = time_to_minutes(_pick(row, "earliest_start"))
        preferred = time_to_minutes(_pick(row, "preferred_day_start"))
        latest = time_to_minutes(_pick(row, "latest_start"))
        # Backward compatibility: V1.1 preferred_start becomes the V1.1.1
        # earliest/preferred anchor when the new fields are absent.
        anchor = legacy_preferred if legacy_preferred is not None else 7 * 60
        stays.append(Stay(
            stay_id=_pick(row, "stay_id"),
            client_ref=_pick(row, "client_ref"),
            start_date=date.fromisoformat(_pick(row, "start_date")),
            end_date=date.fromisoformat(_pick(row, "end_date")),
            primary_orientation=_pick(row, "primary_orientation"),
            secondary_orientation=_pick(row, "secondary_orientation"),
            package_primary=_pick(row, "package_primary"),
            package_secondary=_pick(row, "package_secondary"),
            earliest_start=earliest if earliest is not None else anchor,
            preferred_day_start=preferred if preferred is not None else anchor,
            latest_start=latest if latest is not None else 12 * 60,
            pmr_level=int(_pick(row, "pmr_level", default="0") or 0),
            planning_communicated=as_bool(_pick(row, "planning_communicated")),
        ))

    requests: list[CareRequest] = []
    for row in _rows(root / "care_requests.csv"):
        requests.append(CareRequest(
            request_id=_pick(row, "request_id"),
            stay_id=_pick(row, "stay_id"),
            service_date=date.fromisoformat(_pick(row, "service_date")),
            care_code=_pick(row, "care_code"),
            sector=_pick(row, "sector"),
            mode_plan=_pick(row, "mode_plan", default="AVEC_RESSOURCE"),
            preferred_start=time_to_minutes(_pick(row, "preferred_start")),
            locked_start=time_to_minutes(_pick(row, "locked_start")),
            locked_resource=_pick(row, "locked_resource"),
            medical_override=as_bool(_pick(row, "medical_override")),
            catchup_reason=_pick(row, "catchup_reason"),
        ))
    return stays, requests


def load_parameters(parameter_dir: str | Path, config_path: str | Path | None = None) -> Parameters:
    root = Path(parameter_dir)
    result = Parameters()
    if config_path and Path(config_path).exists():
        result.config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    for row in _rows(root / "care_types.csv"):
        code = _pick(row, "care_code", "code_soin", "code")
        if not code:
            continue
        duration_text = _pick(
            row,
            "duration_minutes",
            "duration_min",
            "duree_minutes",
            "duree_min",
            "patient_duration_min",
            "slot_minutes",
        )
        duration = int(float(duration_text)) if duration_text else FALLBACK_DURATIONS.get(code, 5)
        status = _pick(row, "status", "statut", "parameter_status")
        provisional = as_bool(_pick(row, "provisional", "provisoire")) or "provis" in _norm(status)
        dry = as_bool(_pick(row, "dry_care", "soin_sec", "is_dry")) or "sec" in _norm(_pick(row, "family", "famille"))
        result.care_types[code] = CareType(code, duration, provisional, dry)

    for row in _rows(root / "resources.csv"):
        resource = _pick(row, "resource_id", "ressource_id", "resource", "ressource", "post_id")
        if resource:
            result.resource_sector[resource] = _pick(row, "sector", "secteur").upper()

    for row in _rows(root / "care_resource_compatibility.csv"):
        code = _pick(row, "care_code", "code_soin", "code")
        resource = _pick(row, "resource_id", "ressource_id", "resource", "ressource", "post_id")
        if code and resource and not as_bool(_pick(row, "disabled", "inactive")):
            result.compatibility.setdefault(code, []).append(resource)

    return result


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

# Public compatibility helper used by the V1.2.0 indicators.


# --- V1.2.0 autonomous io compatibility API ---

def minutes(value):
    """Convert ``HH:MM`` or an integer count to minutes.

    Integer inputs are returned unchanged. For compatibility with earlier
    patch output, time/datetime objects, numeric strings and values beginning
    with an ISO date or containing seconds are also accepted.
    """
    if isinstance(value, bool):
        raise ValueError("a boolean is not a valid time")
    if isinstance(value, int):
        return value
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)
    if value is None:
        raise ValueError("time value is required")
    text = str(value).strip()
    if not text:
        raise ValueError("time value is required")
    if text.lstrip("+-").isdigit():
        return int(text)
    clock = text.rsplit("T", 1)[-1].rsplit(" ", 1)[-1]
    parts = clock.split(":")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"invalid time value: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"invalid time value: {value!r}")
    return hour * 60 + minute


def hhmm(value):
    """Convert integer minutes to a zero-padded 24-hour ``HH:MM`` string."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer minutes, got {value!r}")
    value %= 24 * 60
    return f"{value // 60:02d}:{value % 60:02d}"


def _v120_read_rows(path):
    """Read one CSV while reusing the branch's existing ``_rows`` loader."""
    path = Path(path)
    existing_loader = globals().get("_rows")
    if callable(existing_loader):
        return existing_loader(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _v120_parameter_table(root, filenames, required_columns, label):
    """Load a named table, with a header-based fallback for legacy filenames."""
    root = Path(root)
    candidates = []
    for filename in filenames:
        path = root / filename
        if path.is_file() and path not in candidates:
            candidates.append(path)
    for path in sorted(root.glob("*.csv")):
        if path not in candidates:
            candidates.append(path)

    required = set(required_columns)
    for path in candidates:
        rows = _v120_read_rows(path)
        if rows and required.issubset(rows[0]):
            return rows
        if not rows and path.is_file():
            with path.open(newline="", encoding="utf-8-sig") as handle:
                fields = set((csv.DictReader(handle).fieldnames or ()))
            if required.issubset(fields):
                return []
    raise FileNotFoundError(
        f"cannot locate {label} in {root}; required columns: {sorted(required)!r}"
    )


def load_problem(input_dir, parameter_dir, config_path):
    """Load the raw dictionary problem consumed by V1.2 validation and solvers.

    The public signature matches ``cli.py`` and both acceptance-test suites.
    Existing CSV loading behaviour is reused through ``_rows``. Parameter
    tables are selected by their canonical filename first and by required
    headers second, allowing the stable V1.1.1 filenames to remain unchanged.
    """
    input_root = Path(input_dir)
    parameter_root = Path(parameter_dir)
    config_file = Path(config_path)

    stays = _v120_read_rows(input_root / "stays.csv")
    requests = _v120_read_rows(input_root / "care_requests.csv")
    if not stays:
        raise FileNotFoundError(f"missing or empty stays.csv in {input_root}")
    if not requests:
        raise FileNotFoundError(f"missing or empty care_requests.csv in {input_root}")
    if not config_file.is_file():
        raise FileNotFoundError(f"missing solver configuration: {config_file}")
    config = json.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"solver configuration must be a JSON object: {config_file}")

    return {
        "stays": stays,
        "requests": requests,
        "care_types": _v120_parameter_table(
            parameter_root,
            ("care_types.csv", "types_soins.csv"),
            ("care_code", "mode_plan", "allowed_sectors", "occupancy_minutes"),
            "care types",
        ),
        "resources": _v120_parameter_table(
            parameter_root,
            ("resources.csv", "ressources.csv"),
            ("resource_id", "capacity", "open_start", "open_end"),
            "resources",
        ),
        "compatibilities": _v120_parameter_table(
            parameter_root,
            ("care_resource_compatibility.csv", "compatibilities.csv", "compatibilites.csv"),
            ("care_code", "sector", "resource_id"),
            "care/resource compatibilities",
        ),
        "transitions": _v120_parameter_table(
            parameter_root,
            ("sector_transitions.csv", "transitions.csv", "transition_times.csv"),
            ("from_sector", "to_sector", "minutes"),
            "sector transitions",
        ),
        "workforce": _v120_parameter_table(
            parameter_root,
            ("workforce_pools.csv", "workforce.csv", "staff_pools.csv"),
            ("pool_id", "capacity"),
            "workforce pools",
        ),
        "config": config,
    }

# --- end V1.2.0 autonomous io compatibility API ---
