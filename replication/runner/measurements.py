from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .base import Phase, PhaseWindow


csv.field_size_limit(10 ** 9)


_TIME_KEYS = ("Time", "time", "Timestamp", "timestamp")
_PKG_ENERGY_KEYS = ("PACKAGE_ENERGY (J)", "CPU_PACKAGE_ENERGY (J)", "Package Energy (J)")
_DRAM_ENERGY_KEYS = ("DRAM_ENERGY (J)", "Dram Energy (J)")
_CPU_USAGE_KEYS = ("CPU_USAGE", "TOTAL_CPU_USAGE", "USED_CPU%")


def _first_present(row: dict[str, str], keys: tuple[str, ...]) -> Optional[str]:
    for k in keys:
        if k in row:
            return row[k]
    return None


@dataclass
class PhaseMetrics:
    phase: Phase
    duration_s: float
    energy_pkg_j: Optional[float]
    energy_dram_j: Optional[float]
    cpu_pct_mean: Optional[float]
    n_samples: int = 0


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _row_time_s(row: dict[str, str]) -> Optional[float]:
    raw = _first_present(row, _TIME_KEYS)
    if raw is None:
        return None
    try:
        v = float(raw)
    except ValueError:
        return None

    return v / 1000.0 if v > 1e11 else v


def _row_float(row: dict[str, str], keys: tuple[str, ...]) -> Optional[float]:
    raw = _first_present(row, keys)
    if raw in (None, "", "n/a"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _slice_by_wall(rows: list[dict[str, str]], t_start: float, t_end: float) -> list[dict[str, str]]:
    return [r for r in rows if (ts := _row_time_s(r)) is not None and t_start <= ts <= t_end]


def aggregate_phase(rows: list[dict[str, str]], window: PhaseWindow) -> PhaseMetrics:
    slab = _slice_by_wall(rows, window.start_wall, window.end_wall)
    duration = window.duration_s

    def _cumulative_delta(keys: tuple[str, ...]) -> Optional[float]:
        first = next((v for r in slab if (v := _row_float(r, keys)) is not None), None)
        last = next((v for r in reversed(slab) if (v := _row_float(r, keys)) is not None), None)
        if first is None or last is None:
            return None
        return max(0.0, last - first)

    pkg = _cumulative_delta(_PKG_ENERGY_KEYS)
    dram = _cumulative_delta(_DRAM_ENERGY_KEYS)

    cpu_vals = [v for r in slab if (v := _row_float(r, _CPU_USAGE_KEYS)) is not None]
    cpu_mean = (sum(cpu_vals) / len(cpu_vals)) if cpu_vals else None

    return PhaseMetrics(
        phase=window.phase,
        duration_s=duration,
        energy_pkg_j=pkg,
        energy_dram_j=dram,
        cpu_pct_mean=cpu_mean,
        n_samples=len(slab),
    )
