from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


SLICE_NAME = "microbench.slice"
SLICE_CGROUP = Path("/sys/fs/cgroup") / SLICE_NAME


@dataclass
class StackTrialContext:

    steady_duration_s: float
    provisioning_timeout_s: float


    override_files: list[Path] = field(default_factory=list)
    project_name: Optional[str] = None


    extra_up_args: list[str] = field(default_factory=list)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def http_request(url: str, *, method: str = "GET", data: Optional[bytes] = None,
                 headers: Optional[dict[str, str]] = None, timeout: float = 15.0
                 ) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def http_get(url: str, *, headers: Optional[dict[str, str]] = None,
             timeout: float = 15.0) -> tuple[int, bytes]:
    return http_request(url, method="GET", headers=headers, timeout=timeout)


def http_post_json(url: str, payload: dict, *, headers: Optional[dict[str, str]] = None,
                   timeout: float = 15.0) -> tuple[int, bytes]:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    return http_request(url, method="POST", data=json.dumps(payload).encode(),
                        headers=h, timeout=timeout)


def drive_load(request_fn: Callable[[], None], duration_s: float,
               concurrency: int = 16) -> int:

    deadline = time.monotonic() + duration_s
    counter = {"n": 0}
    lock = threading.Lock()

    def worker() -> None:
        local = 0
        while time.monotonic() < deadline:
            try:
                request_fn()
            except Exception:
                pass
            local += 1
        with lock:
            counter["n"] += local

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter["n"]


def poll_until(predicate: Callable[[], bool], timeout_s: float,
               interval_s: float = 1.0, desc: str = "") -> None:

    deadline = time.monotonic() + timeout_s
    last_err: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as e:
            last_err = e
        time.sleep(interval_s)
    raise TimeoutError(f"readiness '{desc}' not met within {timeout_s}s (last error: {last_err})")


class StackApp(ABC):


    id: str
    category: str = "microservices"
    project_dir: Path
    compose_files: list[Path]
    compose_env: dict[str, str]
    up_extra_args: list[str]
    teardown_volumes: bool
    entry_port: int

    provisioning_timeout_s: float = 600.0


    @abstractmethod
    def is_bespoke(self, image_ref: str) -> bool:
        pass


    @abstractmethod
    def wait_ready(self, timeout_s: float) -> None:
        pass

    @abstractmethod
    def cold_start(self) -> str:
        pass

    @abstractmethod
    def steady_state(self, duration_s: float) -> str:
        pass


    def pre_oracle_setup(self) -> None:
        return None
