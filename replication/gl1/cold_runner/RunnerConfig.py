from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.OperationType import OperationType
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from EventManager.EventSubscriptionController import EventSubscriptionController
from EventManager.Models.RunnerEvents import RunnerEvents
from Plugins.Profilers.EnergiBridge import EnergiBridge
from ProgressManager.Output.OutputProcedure import OutputProcedure as output

from replication.runner import rapl

REG = os.environ.get("REGISTRY", "127.0.0.1:5000")
DOCKER = "docker"
ROOT = Path(__file__).resolve().parents[3]
OV = Path(os.environ.get("OV_DIR", str(ROOT / "replication" / "stacks" / "overrides")))


DOCKER_HOST = os.environ.get("COLD_DOCKER_HOST", "unix:///var/run/docker-cold.sock")
os.environ["DOCKER_HOST"] = DOCKER_HOST

SINGLE_SUBJECTS = ["nginx", "openresty", "php-apache", "node", "alpine", "busybox",
                   "python-3.12-alpine", "node-20-alpine", "r-base", "rocker-r-ver",
                   "tensorflow", "pytorch", "influxdb", "memcached", "neo4j", "cassandra"]
STACK_SUBJECTS = ["hotel-reservation", "shopizer", "sock-shop", "train-ticket"]

TREATMENTS = ["baseline", "slim", "blafs"]


MISSING = {("cassandra", "slim"), ("cassandra", "blafs"), ("tensorflow", "blafs")}

SAMPLE_INTERVAL_MS = 100
WARMUP_S = 600
REPETITIONS = 20


COOLDOWN_MS = 120_000


def _sh(*a, timeout=2400):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout)


def _is_stack(subject: str) -> bool:
    return subject in STACK_SUBJECTS


def _manifest(subject: str, treatment: str) -> Path:
    return OV / f"{subject}.{treatment}.pull.yml"


def _benign_eb_stderr(msg: str) -> bool:

    body = msg.split(":", 1)[-1]
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return bool(lines) and all("Interval must be at least" in ln for ln in lines)


class RunnerConfig:
    ROOT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

    name: str = "cold_pull_campaign"
    results_output_path: Path = ROOT / "experiments" / "new_runs"
    operation_type: OperationType = OperationType.AUTO
    time_between_runs_in_ms: int = COOLDOWN_MS

    def __init__(self):
        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.BEFORE_EXPERIMENT, self.before_experiment),
            (RunnerEvents.BEFORE_RUN, self.before_run),
            (RunnerEvents.START_RUN, self.start_run),
            (RunnerEvents.START_MEASUREMENT, self.start_measurement),
            (RunnerEvents.INTERACT, self.interact),
            (RunnerEvents.STOP_MEASUREMENT, self.stop_measurement),
            (RunnerEvents.STOP_RUN, self.stop_run),
            (RunnerEvents.POPULATE_RUN_DATA, self.populate_run_data),
            (RunnerEvents.AFTER_EXPERIMENT, self.after_experiment),
        ])
        self.run_table_model = None
        self.profiler = None
        self.rapl_sampler = None
        self._t0 = None
        self._t1 = None
        self._ok = False
        self._ref = ""
        self._note = ""
        output.console_log("cold-pull config loaded")


    def create_run_table_model(self) -> RunTableModel:
        subject = FactorModel("subject", SINGLE_SUBJECTS + STACK_SUBJECTS)
        treatment = FactorModel("treatment", TREATMENTS)
        exclude = [{subject: [s], treatment: [t]} for s, t in sorted(MISSING)]
        self.run_table_model = RunTableModel(
            factors=[subject, treatment],
            exclude_combinations=exclude,
            repetitions=REPETITIONS,
            shuffle=True,
            data_columns=["kind", "ok", "pull_seconds",
                          "energy_node_j", "rapl_pkg0_j", "rapl_pkg1_j",
                          "eb_pkg0_j", "power_node_w", "size_mb", "ref", "note"],
        )
        return self.run_table_model


    def before_experiment(self) -> None:

        self._require_registry()
        missing = [str(_manifest(s, t)) for s in STACK_SUBJECTS for t in TREATMENTS
                   if not _manifest(s, t).exists()]
        if missing:
            raise RuntimeError("missing stack manifests, run make_stack_manifests.py: "
                               + ", ".join(missing))

        output.console_log(f"warm-up: {WARMUP_S}s synthetic load")


        try:
            n = len(os.sched_getaffinity(0))
        except AttributeError:
            n = os.cpu_count() or 8
        procs = [subprocess.Popen(
            ["bash", "-c", "while :; do :; done"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(n)]
        try:
            time.sleep(WARMUP_S)
        finally:
            for p in procs:
                p.kill()
            for p in procs:
                p.wait(timeout=10)
        output.console_log("warm-up done")

    def before_run(self) -> None:
        pass


    def start_run(self, context: RunnerContext) -> None:

        subject = context.execute_run["subject"]
        treatment = context.execute_run["treatment"]
        self._ok, self._note = False, ""
        self._t0 = self._t1 = None


        self._require_registry()
        self._require_docker()

        _sh(DOCKER, "system", "prune", "-af", timeout=900)

        self._ref = (f"{REG}/{subject}__{treatment}:latest"
                     if not _is_stack(subject) else f"stack:{subject}")
        if not _is_stack(subject):


            if _sh(DOCKER, "image", "inspect", self._ref).returncode == 0:
                self._note = "image still present after prune"

    def start_measurement(self, context: RunnerContext) -> None:

        eb_csv = context.run_dir / "energibridge.csv"
        rapl_csv = context.run_dir / "rapl.csv"

        self.rapl_sampler = rapl.RaplSampler(rapl_csv, pkgs=(0, 1),
                                             interval_s=SAMPLE_INTERVAL_MS / 1000)
        self.rapl_sampler.start()

        self.profiler = EnergiBridge(
            sample_frequency=SAMPLE_INTERVAL_MS,
            out_file=eb_csv,
            summary=True,
            target_program="sleep 86400",
        )
        self.profiler.start()
        time.sleep(0.3)

    def interact(self, context: RunnerContext) -> None:

        subject = context.execute_run["subject"]
        treatment = context.execute_run["treatment"]

        self._t0 = time.time()
        if _is_stack(subject):
            r = _sh(DOCKER, "compose", "-p", f"cold-{subject}",
                    "-f", str(_manifest(subject, treatment)), "pull", timeout=2400)
        else:
            r = _sh(DOCKER, "pull", self._ref)
        self._t1 = time.time()
        self._ok = r.returncode == 0
        if not self._ok:
            tail = (r.stderr or "").strip().splitlines()
            self._note = (self._note + "; pull failed: "
                          + (tail[-1][:160] if tail else "no stderr")).strip("; ")

    def stop_measurement(self, context: RunnerContext) -> None:
        time.sleep(0.3)
        if self.profiler is not None:
            try:
                self.profiler.stop(wait=False)
            except Exception as e:
                if not _benign_eb_stderr(str(e)):
                    self._note = (self._note + f"; energibridge stop: {e}").strip("; ")
        if self.rapl_sampler is not None:
            self.rapl_sampler.stop()

    def stop_run(self, context: RunnerContext) -> None:
        pass


    def populate_run_data(self, context: RunnerContext) -> Optional[Dict[str, Any]]:
        subject = context.execute_run["subject"]
        treatment = context.execute_run["treatment"]
        secs = (self._t1 - self._t0) if (self._t0 and self._t1) else None

        p0 = p1 = None
        rapl_csv = context.run_dir / "rapl.csv"
        if rapl_csv.exists() and secs:
            rows = rapl.load_csv(rapl_csv)
            p0 = rapl.energy_over_window(rows, self._t0, self._t1, "pkg0_j")
            p1 = rapl.energy_over_window(rows, self._t0, self._t1, "pkg1_j")
        node = (p0 + p1) if (p0 is not None and p1 is not None) else None

        eb = self._energibridge_window(context.run_dir / "energibridge.csv")
        size = self._size_mb(subject, treatment) if self._ok else None

        return {
            "kind": "stack" if _is_stack(subject) else "single",
            "ok": self._ok,
            "pull_seconds": _r(secs),
            "energy_node_j": _r(node),
            "rapl_pkg0_j": _r(p0),
            "rapl_pkg1_j": _r(p1),
            "eb_pkg0_j": _r(eb),
            "power_node_w": _r(node / secs if node and secs else None),
            "size_mb": _r(size),
            "ref": self._ref,
            "note": self._note,
        }

    def after_experiment(self) -> None:
        output.console_log("COLD_CAMPAIGN_DONE")


    def _size_mb(self, subject: str, treatment: str) -> Optional[float]:

        if not _is_stack(subject):
            r = _sh(DOCKER, "image", "inspect", "-f", "{{.Size}}", self._ref)
            if r.returncode == 0 and r.stdout.strip():
                return int(r.stdout.strip()) / 1e6
            return None

        refs = []
        try:
            for line in _manifest(subject, treatment).read_text().splitlines():
                if "image:" in line:
                    refs.append(line.split("image:", 1)[1].strip())
        except OSError:
            return None
        if not refs:
            return None
        r = _sh(DOCKER, "image", "inspect", "-f", "{{.Size}}", *refs)
        if r.returncode != 0:
            return None
        total = 0
        for ln in r.stdout.split():
            try:
                total += int(ln)
            except ValueError:
                return None
        return total / 1e6

    def _require_registry(self) -> None:
        try:
            urllib.request.urlopen(f"http://{REG}/v2/", timeout=15)
        except Exception as e:
            raise RuntimeError(f"registry {REG} unreachable ({e})") from e

    def _require_docker(self) -> None:
        r = _sh(DOCKER, "version", "--format", "{{.Server.Version}}", timeout=60)
        if r.returncode != 0:
            raise RuntimeError(
                f"cold docker daemon at {DOCKER_HOST} is not responding "
                f"({(r.stderr or '').strip()[:200]}); start it with: dockerd "
                f"--data-root /var/lib/docker-cold -H {DOCKER_HOST} "
                f"--pidfile /var/run/docker-cold.pid --bridge=none --iptables=false")

    def _energibridge_window(self, csv_path: Path) -> Optional[float]:

        if not csv_path.exists() or not (self._t0 and self._t1):
            return None
        import csv as _csv
        col, tcol = "PACKAGE_ENERGY (J)", "Time"
        vals: List[float] = []
        try:
            with csv_path.open(newline="") as fh:
                for row in _csv.DictReader(fh):
                    try:
                        t = float(row[tcol]) / 1000.0
                        v = float(row[col])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if self._t0 <= t <= self._t1:
                        vals.append(v)
        except OSError:
            return None
        if len(vals) < 2:
            return None
        delta = vals[-1] - vals[0]
        if delta < 0:
            self._note = (self._note + "; eb counter wrapped").strip("; ")
            return None
        return delta

    experiment_path: Path = None


def _r(x, n=2):
    return round(x, n) if isinstance(x, (int, float)) and not isinstance(x, bool) else x
