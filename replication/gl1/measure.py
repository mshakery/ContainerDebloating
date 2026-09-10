from __future__ import annotations

import statistics
from pathlib import Path
from typing import Optional

from replication.runner import envelope, rapl
from replication.runner.energibridge import EnergiBridgeSession
from replication.runner.measurements import load_csv as eb_load_csv, _row_time_s, _row_float


class Meter:


    def __init__(self, outdir: Path, sample_interval_ms: int = 100):
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.eb_csv = self.outdir / "energibridge.csv"
        self.rapl_csv = self.outdir / "rapl_socket.csv"
        self._eb = EnergiBridgeSession(self.eb_csv, sample_interval_ms=sample_interval_ms)
        self._rs = rapl.RaplSampler(self.rapl_csv, pkgs=envelope.RAPL_PKGS, interval_s=0.1)
        self._eb_rows = None
        self._rp_rows = None

    def __enter__(self) -> "Meter":
        self._eb.__enter__()
        self._rs.start()
        return self

    def __exit__(self, *exc):
        self._rs.stop()
        self._eb.__exit__(*exc)

    def _load(self):
        if self._eb_rows is None:
            self._eb_rows = eb_load_csv(self.eb_csv) if self.eb_csv.exists() else []
            self._rp_rows = rapl.load_csv(self.rapl_csv) if self.rapl_csv.exists() else []

    def phase(self, t0_wall: float, t1_wall: float, dur: float) -> dict:

        self._load()
        eb = self._eb_pkg(t0_wall, t1_wall)
        p0 = rapl.energy_over_window(self._rp_rows, t0_wall, t1_wall, "pkg0_j")
        p1 = rapl.energy_over_window(self._rp_rows, t0_wall, t1_wall, "pkg1_j")
        node = (p0 + p1) if (p0 is not None and p1 is not None) else None
        return {
            "duration_s": dur,
            "energy_pkg0_eb_j": eb,
            "energy_pkg0_sysfs_j": p0,
            "energy_pkg1_j": p1,
            "energy_node_j": node,
            "power_pkg0_w": (eb / dur) if (eb is not None and dur > 0) else None,
        }

    def cpu(self, t0_wall: float, t1_wall: float) -> dict:
        self._load()
        return {
            "cpu_sut_0_7_pct": self._mean_cpu(range(0, 8), t0_wall, t1_wall),
            "cpu_loadgen_8_15_pct": self._mean_cpu(range(8, 16), t0_wall, t1_wall),
        }

    def _eb_pkg(self, t0w, t1w) -> Optional[float]:
        first = last = None
        for r in self._eb_rows:
            ts = _row_time_s(r)
            if ts is None or not (t0w <= ts <= t1w):
                continue
            v = _row_float(r, ("PACKAGE_ENERGY (J)",))
            if v is None:
                continue
            first = v if first is None else first
            last = v
        return (last - first) if (first is not None and last is not None) else None

    def _mean_cpu(self, cores, t0w, t1w) -> Optional[float]:
        per = []
        for r in self._eb_rows:
            ts = _row_time_s(r)
            if ts is None or not (t0w <= ts <= t1w):
                continue
            vals = [v for c in cores if (v := _row_float(r, (f"CPU_USAGE_{c}",))) is not None]
            if vals:
                per.append(sum(vals) / len(vals))
        return round(statistics.mean(per), 1) if per else None
