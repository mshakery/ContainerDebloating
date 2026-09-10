from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from replication.runner import container as docker
from replication.runner.base import (
    Phase, PhaseWindow, TrialContext, Workload, WorkloadOutcome,
)


@dataclass
class OneShotConfig:
    subject_id: str
    iterations: int

    command: tuple[str, ...]
    extra_run_args: tuple[str, ...] = ()


class OneShotScriptWorkload(Workload):
    def __init__(self, config: OneShotConfig):
        self.config = config
        self.subject_id = config.subject_id

    def _run_args(self, assets_dir: Path) -> list[str]:
        return ["-v", f"{assets_dir}:/work:ro", *self.config.extra_run_args]

    def execute(self, ctx: TrialContext) -> WorkloadOutcome:
        out = WorkloadOutcome()
        cid: Optional[str] = None
        try:
            t0_mono, t0_wall = time.monotonic(), time.time()


            cid = docker.run_detached(
                image_ref=ctx.image_ref,
                cpus=ctx.cpus, memory_mb=ctx.memory_mb, cpuset_cpu=ctx.cpuset_cpu,
                extra_args=self._run_args(ctx.assets_dir),
                command=list(self.config.command),
                auto_remove=False,
                seccomp_profile=ctx.seccomp_profile,
            )


            proc = subprocess.Popen(
                [docker.DOCKER, "logs", "-f", cid],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )

            cold_hash: Optional[str] = None
            steady_hash: Optional[str] = None
            t_cold_mono: Optional[float] = None
            t_cold_wall: Optional[float] = None
            t_steady_mono: Optional[float] = None
            t_steady_wall: Optional[float] = None

            deadline = time.monotonic() + ctx.provisioning_timeout_s + ctx.steady_duration_s * 3 + 60
            assert proc.stdout is not None
            for line in proc.stdout:
                now_m, now_w = time.monotonic(), time.time()
                line = line.strip()
                if line.startswith("COLD "):
                    cold_hash = line.split(" ", 1)[1].strip()
                    t_cold_mono, t_cold_wall = now_m, now_w
                elif line.startswith("STEADY "):
                    steady_hash = line.split(" ", 1)[1].strip()
                    t_steady_mono, t_steady_wall = now_m, now_w


                    out.peak_memory_bytes = docker.read_memory_peak_bytes(cid)
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f"oneshot trial exceeded {deadline - t0_mono:.0f}s")

            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

            if cold_hash is None or steady_hash is None:
                raise RuntimeError("workload did not emit COLD/STEADY markers")

            out.cold_output_hash = cold_hash
            out.steady_output_hash = steady_hash
            out.windows[Phase.PROVISIONING] = PhaseWindow(
                Phase.PROVISIONING, t0_mono, t_cold_mono, t0_wall, t_cold_wall)


            out.windows[Phase.COLD_START] = PhaseWindow(
                Phase.COLD_START, t_cold_mono, t_cold_mono + 1e-6,
                t_cold_wall, t_cold_wall + 1e-6)
            out.windows[Phase.STEADY_STATE] = PhaseWindow(
                Phase.STEADY_STATE, t_cold_mono, t_steady_mono,
                t_cold_wall, t_steady_wall)


            if out.peak_memory_bytes is None:
                out.peak_memory_bytes = docker.read_memory_peak_bytes(cid)
            out.extra["iterations"] = self.config.iterations

        except Exception as e:
            out.error = f"{type(e).__name__}: {e}"
        finally:
            if cid is not None:
                docker.remove(cid)
        return out


def make_alpine() -> OneShotScriptWorkload:
    n = 100_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="alpine", iterations=n,
        command=("sh", "/work/loop.sh", str(n)),
    ))


def make_busybox() -> OneShotScriptWorkload:
    n = 100_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="busybox", iterations=n,
        command=("sh", "/work/loop.sh", str(n)),
    ))


def make_python_alpine() -> OneShotScriptWorkload:
    n = 30_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="python-3.12-alpine", iterations=n,
        command=("python", "/work/parse_json.py", str(n)),
    ))


def make_node_alpine() -> OneShotScriptWorkload:
    n = 50_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="node-20-alpine", iterations=n,
        command=("node", "/work/parse_json.js", str(n)),
    ))


def make_r_base() -> OneShotScriptWorkload:
    n = 300
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="r-base", iterations=n,
        command=("Rscript", "/work/lr.R", str(n)),
    ))


def make_rocker_r_ver() -> OneShotScriptWorkload:
    n = 300
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="rocker-r-ver", iterations=n,
        command=("Rscript", "/work/lr.R", str(n)),
    ))


def make_tensorflow() -> OneShotScriptWorkload:
    n = 1_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="tensorflow", iterations=n,
        command=("python", "/work/tf_infer.py", str(n)),
    ))


def make_pytorch() -> OneShotScriptWorkload:
    n = 1_000
    return OneShotScriptWorkload(OneShotConfig(
        subject_id="pytorch", iterations=n,
        command=("python", "/work/torch_infer.py", str(n)),
    ))
