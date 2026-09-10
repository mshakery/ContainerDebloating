from __future__ import annotations

import csv
import threading
import time
from pathlib import Path
from typing import Optional

_POWERCAP = Path("/sys/class/powercap")


def _pkg_path(pkg: int) -> Path:
    return _POWERCAP / f"intel-rapl:{pkg}"


def _dram_path(pkg: int) -> Path:
    return _POWERCAP / f"intel-rapl:{pkg}:{0}"


def _read_int(p: Path) -> Optional[int]:
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


class _Domain:


    def __init__(self, name: str, energy_file: Path):
        self.name = name
        self.energy_file = energy_file
        self.range = _read_int(energy_file.parent / "max_energy_range_uj")
        self._last: Optional[int] = _read_int(energy_file)
        self.cumulative_uj = 0
        self.available = self._last is not None

    def sample(self) -> Optional[float]:
        raw = _read_int(self.energy_file)
        if raw is None:
            return None
        if self._last is not None:
            d = raw - self._last
            if d < 0 and self.range:
                d += self.range
            if d >= 0:
                self.cumulative_uj += d
        self._last = raw
        return self.cumulative_uj / 1e6


class RaplSampler(threading.Thread):


    def __init__(self, out_csv: Path, pkgs: tuple[int, ...] = (0, 1),
                 interval_s: float = 0.1):
        super().__init__(daemon=True)
        self.out_csv = out_csv
        self.interval_s = interval_s
        self._stop_evt = threading.Event()
        self._domains: list[tuple[str, _Domain]] = []
        for p in pkgs:
            d = _Domain(f"pkg{p}", _pkg_path(p) / "energy_uj")
            if d.available:
                self._domains.append((f"pkg{p}_j", d))
            dd = _Domain(f"dram{p}", _dram_path(p) / "energy_uj")
            if dd.available:
                self._domains.append((f"dram{p}_j", dd))

    @property
    def columns(self) -> list[str]:
        return ["wall_ms"] + [c for c, _ in self._domains]

    def run(self) -> None:
        self.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.out_csv.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(self.columns)
            while not self._stop_evt.is_set():
                row = [f"{time.time() * 1000:.0f}"]
                for _, d in self._domains:
                    j = d.sample()
                    row.append(f"{j:.6f}" if j is not None else "")
                w.writerow(row)
                fh.flush()
                self._stop_evt.wait(self.interval_s)

    def stop(self) -> None:
        self._stop_evt.set()
        self.join(timeout=2)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def energy_over_window(rows: list[dict[str, str]], start_wall_s: float,
                       end_wall_s: float, col: str) -> Optional[float]:

    a = start_wall_s * 1000.0
    b = end_wall_s * 1000.0

    def val(r: dict[str, str]) -> Optional[float]:
        v = r.get(col, "")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    inside = [r for r in rows
              if (t := _to_ms(r.get("wall_ms"))) is not None and a <= t <= b]
    if len(inside) < 2:
        return None
    first = next((v for r in inside if (v := val(r)) is not None), None)
    last = next((v for r in reversed(inside) if (v := val(r)) is not None), None)
    if first is None or last is None:
        return None
    return max(0.0, last - first)


def _to_ms(raw: Optional[str]) -> Optional[float]:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None
