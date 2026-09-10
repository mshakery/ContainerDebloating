from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

DOCKER = shutil.which("docker") or "docker"


class DockerError(RuntimeError):
    pass


def run_detached(
    image_ref: str,
    cpus: float,
    memory_mb: int,
    cpuset_cpu: int,
    extra_args: list[str],
    command: Optional[list[str]] = None,
    name: Optional[str] = None,
    auto_remove: bool = True,
    seccomp_profile: Optional[Path] = None,
) -> str:

    cmd = [DOCKER, "run", "-d"]
    if auto_remove:
        cmd.append("--rm")
    cmd += [
        f"--cpus={cpus}",
        f"--memory={memory_mb}m",
        f"--cpuset-cpus={cpuset_cpu}",
    ]
    if seccomp_profile is not None:
        cmd += ["--security-opt", f"seccomp={seccomp_profile}"]
    if name:
        cmd += ["--name", name]
    cmd += extra_args
    cmd += [image_ref]
    if command:
        cmd += command
    try:
        cid = subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError as e:
        raise DockerError(f"docker run failed for {image_ref}: {e}") from e
    return cid


def stop(container_id: str, timeout_s: int = 10) -> None:
    subprocess.run(
        [DOCKER, "stop", "-t", str(timeout_s), container_id],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def remove(container_id: str) -> None:
    subprocess.run(
        [DOCKER, "rm", "-f", container_id],
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def wait_exit(container_id: str, timeout_s: float) -> int:

    try:
        out = subprocess.check_output(
            [DOCKER, "wait", container_id], text=True, timeout=timeout_s,
        )
        return int(out.strip())
    except (subprocess.TimeoutExpired, ValueError):
        return -1


def exec_capture(container_id: str, argv: list[str], timeout_s: Optional[float] = None) -> tuple[int, str, str]:

    proc = subprocess.run(
        [DOCKER, "exec", container_id, *argv],
        capture_output=True, text=True, timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def is_running(container_id: str) -> bool:
    res = subprocess.run(
        [DOCKER, "inspect", "-f", "{{.State.Running}}", container_id],
        capture_output=True, text=True,
    )
    return res.returncode == 0 and res.stdout.strip() == "true"


def pull(image_ref: str) -> None:
    subprocess.check_call([DOCKER, "pull", image_ref], stdout=subprocess.DEVNULL)


def image_exists(image_ref: str) -> bool:
    res = subprocess.run([DOCKER, "image", "inspect", image_ref],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0


_CGROUP_CANDIDATES = (
    "/sys/fs/cgroup/system.slice/docker-{cid}.scope/memory.peak",
    "/sys/fs/cgroup/docker/{cid}/memory.peak",
)


def read_memory_peak_bytes(container_id: str) -> Optional[int]:

    for tpl in _CGROUP_CANDIDATES:
        p = Path(tpl.format(cid=container_id))
        if p.exists():
            try:
                return int(p.read_text().strip())
            except (OSError, ValueError):
                continue
    return None


def wait_for_tcp(host: str, port: int, timeout_s: float, interval_s: float = 0.1) -> None:

    import socket
    deadline = time.monotonic() + timeout_s
    last_err: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as e:
            last_err = e
            time.sleep(interval_s)
    raise TimeoutError(f"{host}:{port} not reachable within {timeout_s}s ({last_err})")
