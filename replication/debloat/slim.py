from __future__ import annotations

import os
import shlex
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from replication.debloat.base import DebloaterError
from replication.runner import container as docker
from replication.runner.base import SubjectSpec


_ASSETS = (Path(__file__).resolve().parents[1] / "workloads" / "assets").resolve()
_SLIM = shutil.which("slim") or "slim"


_HTTP_TIMEOUT_S = 600
_ONESHOT_TIMEOUT_S = 900
_DATASTORE_TIMEOUT_S = 1200


def build_slim_image(spec: SubjectSpec) -> str:
    if shutil.which("slim") is None:
        raise DebloaterError("slim not found on PATH; install mintoolkit")

    tag = _slim_tag(spec)


    if docker.image_exists(tag):
        return tag

    args, timeout_s = _probe_args_for(spec)

    cmd = [
        _SLIM, "slim",
        "--target", spec.image_ref,
        "--tag", tag,
        "--http-probe-retry-wait", "2",
        "--http-probe-retry-count", "10",
        *args,
    ]


    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout_s,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise DebloaterError(
            f"slim build failed for {spec.id} (exit {proc.returncode}); "
            f"last stderr:\n{_tail(proc.stderr, 2000)}\n"
            f"last stdout:\n{_tail(proc.stdout, 2000)}"
        )

    if not docker.image_exists(tag):
        raise DebloaterError(
            f"slim reported success but {tag} is not present in the local "
            f"docker store; stdout tail:\n{_tail(proc.stdout, 2000)}"
        )

    return tag


def _slim_tag(spec: SubjectSpec) -> str:
    return f"{spec.image_ref}.slim"


def _tail(s: str, n: int) -> str:
    return s if len(s) <= n else "…" + s[-n:]


def _probe_args_for(spec: SubjectSpec) -> tuple[list[str], int]:

    from replication.workloads.datastore import _DatastoreBase
    from replication.workloads.http_service import HttpServiceWorkload
    from replication.workloads.oneshot import OneShotScriptWorkload

    workload = spec.workload_factory()
    if isinstance(workload, HttpServiceWorkload):
        return _http_args(workload), _HTTP_TIMEOUT_S
    if isinstance(workload, OneShotScriptWorkload):
        return _oneshot_args(workload), _ONESHOT_TIMEOUT_S
    if isinstance(workload, _DatastoreBase):
        return _datastore_args(workload), _DATASTORE_TIMEOUT_S
    raise DebloaterError(
        f"no slim probe template for {spec.id} "
        f"(workload class: {type(workload).__name__})"
    )


def _http_args(workload) -> list[str]:
    cfg = workload.config


    args: list[str] = [
        "--mount", f"{_ASSETS}:/work:ro",
        "--expose", str(cfg.container_port),
        "--http-probe-cmd", cfg.request_path,
        "--continue-after", "probe",
    ]
    if cfg.docroot_mount is not None:
        host_file, container_path = cfg.docroot_mount
        args += ["--mount", f"{_ASSETS / host_file}:{container_path}:ro"]
    if cfg.command_override:


        args += ["--cmd", " ".join(cfg.command_override)]
    return args


def _oneshot_args(workload) -> list[str]:


    cmd_str = " ".join(workload.config.command)
    return [
        "--mount", f"{_ASSETS}:/work:ro",
        "--cmd", cmd_str,
        "--http-probe-off",
        "--continue-after", "timeout-300",
    ]


def _datastore_args(workload) -> list[str]:


    cfg = workload.config
    venv_python = shlex.quote(sys.executable)
    root = str(Path(__file__).resolve().parents[2])
    pythonpath = shlex.quote(os.pathsep.join(filter(None, (root, os.environ.get("PYTHONPATH", "")))))
    args: list[str] = [
        "--publish-port", f"{cfg.host_port}:{cfg.container_port}",
        "--http-probe-off",
        "--host-exec",
        (f"env PYTHONPATH={pythonpath} {venv_python} "
         f"-m replication.debloat.probe {workload.subject_id} --timeout 240"),
        "--continue-after", "probe",
    ]
    for k, v in cfg.extra_env:
        args += ["--env", f"{k}={v}"]
    return args
