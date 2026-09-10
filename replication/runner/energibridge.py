from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional


ENERGIBRIDGE = shutil.which("energibridge") or "energibridge"


class EnergiBridgeError(RuntimeError):
    pass


class EnergiBridgeSession:


    def __init__(self, output_csv: Path, sample_interval_ms: int = 100):
        self.output_csv = output_csv
        self.sample_interval_ms = sample_interval_ms
        self._proc: Optional[subprocess.Popen] = None
        self.t_started_monotonic: Optional[float] = None
        self.t_started_wall: Optional[float] = None

    def __enter__(self) -> "EnergiBridgeSession":
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)


        cmd = [
            ENERGIBRIDGE,
            "--interval", str(self.sample_interval_ms),
            "--output", str(self.output_csv),
            "--",
            "sleep", "86400",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except FileNotFoundError as e:
            raise EnergiBridgeError(
                "energibridge not found on PATH; install it on the testbed"
            ) from e

        time.sleep(0.25)
        if self._proc.poll() is not None:
            err = (self._proc.stderr.read() or b"").decode(errors="replace") if self._proc.stderr else ""
            raise EnergiBridgeError(f"energibridge exited immediately: {err}")
        self.t_started_monotonic = time.monotonic()
        self.t_started_wall = time.time()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._proc is None:
            return
        try:
            if os.name == "nt":
                self._proc.terminate()
            else:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        finally:
            self._proc = None
