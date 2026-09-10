from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from replication.runner import envelope

HEY = (os.environ.get("HEY_BIN")
       or (os.path.expanduser("~/hey") if os.path.exists(os.path.expanduser("~/hey")) else None)
       or shutil.which("hey")
       or os.path.expanduser("~/hey"))

_RPS_RE = re.compile(r"Requests/sec:\s*([0-9.]+)")
_TOTAL_RE = re.compile(r"Total:\s*([0-9.]+) secs")


@dataclass
class LoadResult:
    requests: int
    rps: Optional[float]
    duration_s: Optional[float]
    status_dist: dict[str, int]
    ok: bool
    raw: str


def hey_load(url: str, duration_s: float, *, concurrency: int = 200,
             method: str = "GET", body: Optional[str] = None,
             content_type: Optional[str] = None,
             headers: Optional[list[str]] = None,
             cpuset: str = envelope.LOADGEN_CPUSET,
             loadgen_cpus: Optional[int] = None,
             disable_keepalive: bool = False,
             timeout_s: Optional[float] = None) -> LoadResult:

    if loadgen_cpus is None:
        loadgen_cpus = _cpuset_count(cpuset)
    cmd = ["taskset", "-c", cpuset, HEY,
           "-z", f"{duration_s:.0f}s", "-c", str(concurrency),
           "-cpus", str(loadgen_cpus), "-q", "0"]
    if disable_keepalive:
        cmd.append("-disable-keepalive")
    if method != "GET":
        cmd += ["-m", method]
    if body is not None:
        cmd += ["-d", body]
    if content_type is not None:
        cmd += ["-T", content_type]
    for h in (headers or []):
        cmd += ["-H", h]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=(timeout_s or duration_s + 120))
        out = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as e:
        return LoadResult(0, None, None, {}, False, f"timeout: {e}")
    return _parse(out, proc.returncode == 0)


def _parse(out: str, rc_ok: bool) -> LoadResult:
    rps = float(m.group(1)) if (m := _RPS_RE.search(out)) else None
    dur = float(m.group(1)) if (m := _TOTAL_RE.search(out)) else None
    status: dict[str, int] = {}
    in_status = False
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Status code distribution"):
            in_status = True
            continue
        if in_status:
            m = re.match(r"\[(\d+)\]\s+(\d+)\s+responses", s)
            if m:
                status[m.group(1)] = int(m.group(2))
            elif s and not s.startswith("["):
                in_status = False
    total = sum(status.values())
    ok = rc_ok and total > 0 and set(status) <= {"200", "201", "204"}
    return LoadResult(total, rps, dur, status, ok, out[-2000:])


def _cpuset_count(cpuset: str) -> int:
    n = 0
    for part in cpuset.split(","):
        if "-" in part:
            a, b = part.split("-")
            n += int(b) - int(a) + 1
        elif part.strip():
            n += 1
    return max(1, n)
