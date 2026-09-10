from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from replication.runner import container as docker
from replication.runner.base import (
    Phase, PhaseWindow, TrialContext, Workload, WorkloadOutcome,
)


@dataclass
class HttpServiceConfig:
    subject_id: str
    container_port: int
    request_path: str
    docroot_mount: Optional[tuple[Path, str]] = None
    extra_run_args: tuple[str, ...] = ()
    command_override: tuple[str, ...] = ()
    host_port: int = 18080


class HttpServiceWorkload(Workload):
    def __init__(self, config: HttpServiceConfig):
        self.config = config
        self.subject_id = config.subject_id

    def _run_args(self, assets_dir: Path) -> list[str]:
        args: list[str] = [
            "-p", f"127.0.0.1:{self.config.host_port}:{self.config.container_port}",
            "-v", f"{assets_dir}:/work:ro",
        ]
        if self.config.docroot_mount is not None:
            host_path, container_path = self.config.docroot_mount
            args += ["-v", f"{assets_dir / host_path}:{container_path}:ro"]
        args += list(self.config.extra_run_args)
        return args

    def _command(self) -> Optional[list[str]]:
        return list(self.config.command_override) if self.config.command_override else None

    def _url(self) -> str:
        return f"http://127.0.0.1:{self.config.host_port}{self.config.request_path}"

    def _one_request(self) -> bytes:
        with urllib.request.urlopen(self._url(), timeout=10) as r:
            return r.read()

    def _first_request(self, deadline_mono: float) -> bytes:


        last_err: Optional[BaseException] = None
        while time.monotonic() < deadline_mono:
            try:
                return self._one_request()
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
                time.sleep(0.1)
        raise TimeoutError(f"HTTP service did not become ready: {last_err}")

    def execute(self, ctx: TrialContext) -> WorkloadOutcome:
        out = WorkloadOutcome()
        cid: Optional[str] = None
        try:

            t0_mono, t0_wall = time.monotonic(), time.time()
            cid = docker.run_detached(
                image_ref=ctx.image_ref,
                cpus=ctx.cpus, memory_mb=ctx.memory_mb, cpuset_cpu=ctx.cpuset_cpu,
                extra_args=self._run_args(ctx.assets_dir),
                command=self._command(),
                seccomp_profile=ctx.seccomp_profile,
            )
            docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                                timeout_s=ctx.provisioning_timeout_s)
            t1_mono, t1_wall = time.monotonic(), time.time()
            out.windows[Phase.PROVISIONING] = PhaseWindow(
                Phase.PROVISIONING, t0_mono, t1_mono, t0_wall, t1_wall)


            body = self._first_request(deadline_mono=t0_mono + ctx.provisioning_timeout_s)
            t2_mono, t2_wall = time.monotonic(), time.time()
            out.cold_output_hash = hashlib.sha256(body).hexdigest()
            out.windows[Phase.COLD_START] = PhaseWindow(
                Phase.COLD_START, t1_mono, t2_mono, t1_wall, t2_wall)


            count = 0
            deadline_mono = t2_mono + ctx.steady_duration_s
            while time.monotonic() < deadline_mono:
                self._one_request()
                count += 1
            steady_body = self._one_request()
            t3_mono, t3_wall = time.monotonic(), time.time()
            out.steady_output_hash = hashlib.sha256(steady_body).hexdigest()
            out.windows[Phase.STEADY_STATE] = PhaseWindow(
                Phase.STEADY_STATE, t2_mono, t3_mono, t2_wall, t3_wall)
            out.extra["steady_request_count"] = count

            out.peak_memory_bytes = docker.read_memory_peak_bytes(cid)

        except Exception as e:
            out.error = f"{type(e).__name__}: {e}"
        finally:
            if cid is not None:
                docker.stop(cid)
        return out


def make_nginx() -> HttpServiceWorkload:
    return HttpServiceWorkload(HttpServiceConfig(
        subject_id="nginx",
        container_port=80,
        request_path="/index.html",
        docroot_mount=(Path("static.html"), "/usr/share/nginx/html/index.html"),
    ))


def make_openresty() -> HttpServiceWorkload:
    return HttpServiceWorkload(HttpServiceConfig(
        subject_id="openresty",
        container_port=80,
        request_path="/index.html",
        docroot_mount=(Path("static.html"), "/usr/local/openresty/nginx/html/index.html"),
    ))


def make_php_apache() -> HttpServiceWorkload:
    return HttpServiceWorkload(HttpServiceConfig(
        subject_id="php-apache",
        container_port=80,
        request_path="/info.php",
        docroot_mount=(Path("info.php"), "/var/www/html/info.php"),
    ))


def make_node_http() -> HttpServiceWorkload:


    return HttpServiceWorkload(HttpServiceConfig(
        subject_id="node",
        container_port=8080,
        request_path="/",
        command_override=("node", "/work/node_server.js"),
    ))
