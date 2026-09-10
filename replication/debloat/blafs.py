from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from replication.debloat.base import DebloaterError
from replication.runner import container as docker
from replication.runner.base import SubjectSpec, TrialContext


_ASSETS = (Path(__file__).resolve().parents[1] / "workloads" / "assets").resolve()
_BAFFS = shutil.which("baffs") or "baffs"


_PROFILE_CPUS = 1.0
_PROFILE_MEM_MB = 1792
_PROFILE_CPUSET = 2
_PROFILE_STEADY_S = 8.0


_PROFILE_PROVISION_TIMEOUT_S = 900.0


_PROFILE_ATTEMPTS = 3


_BAFFS_TIMEOUT_S = 900


def build_blafs_image(spec: SubjectSpec) -> str:
    if shutil.which("baffs") is None:
        raise DebloaterError(
            "baffs not found on PATH; build + install BLAFS "
            "(make -C /root/BLAFS install)"
        )

    tag = _baffs_tag(spec)


    if docker.image_exists(tag):
        return tag


    docker.pull(spec.image_ref)

    profile_err: Optional[str] = "<profiling did not run>"
    try:
        _baffs(["shadow", f"--images={spec.image_ref}"])
        profile_err = _profile(spec)
    finally:


        _baffs(["debloat", f"--images={spec.image_ref}"])

    if profile_err is not None:


        _force_rmi(tag)
        raise DebloaterError(
            f"BLAFS profiling run did not exercise {spec.id} cleanly: "
            f"{profile_err}"
        )

    if not docker.image_exists(tag):
        raise DebloaterError(
            f"baffs debloat reported success but {tag} is not present in the "
            f"local docker store"
        )
    return tag


def _baffs_tag(spec: SubjectSpec) -> str:
    return f"{spec.image_ref}-baffs"


def _profile(spec: SubjectSpec) -> Optional[str]:

    workload = spec.workload_factory()
    ctx = TrialContext(
        image_ref=spec.image_ref,
        assets_dir=_ASSETS,
        cpus=_PROFILE_CPUS, memory_mb=_PROFILE_MEM_MB, cpuset_cpu=_PROFILE_CPUSET,
        steady_duration_s=_PROFILE_STEADY_S,
        provisioning_timeout_s=_PROFILE_PROVISION_TIMEOUT_S,
    )
    last_err = "profiling phases incomplete"
    for _ in range(_PROFILE_ATTEMPTS):
        outcome = workload.execute(ctx)
        if outcome.ok:
            return None
        last_err = outcome.error or "profiling phases incomplete"
    return f"{last_err} (after {_PROFILE_ATTEMPTS} attempts)"


def _baffs(args: list[str]) -> None:
    try:
        proc = subprocess.run(
            [_BAFFS, *args], capture_output=True, text=True,
            timeout=_BAFFS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise DebloaterError(
            f"baffs {' '.join(args)} timed out after {_BAFFS_TIMEOUT_S}s"
        ) from e
    if proc.returncode != 0:
        raise DebloaterError(
            f"baffs {' '.join(args)} failed (exit {proc.returncode}); "
            f"stderr:\n{_tail(proc.stderr, 2000)}"
        )


def _force_rmi(tag: str) -> None:
    subprocess.run(
        [docker.DOCKER, "rmi", "-f", tag],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _tail(s: str, n: int) -> str:
    return s if len(s) <= n else "…" + s[-n:]
