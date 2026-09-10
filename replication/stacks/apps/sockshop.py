from __future__ import annotations

import json
from pathlib import Path

from replication.stacks.base import (
    StackApp, drive_load, http_get, poll_until, sha,
)

_DIR = Path("/root/microbench/compose/sockshop")
_BASE = "http://127.0.0.1:80"
_CATALOGUE_URL = f"{_BASE}/catalogue"


def _normalized_catalogue(body: bytes) -> bytes:

    items = json.loads(body)
    for it in items:
        it.pop("count", None)
    items.sort(key=lambda x: x.get("id", ""))
    return json.dumps(items, sort_keys=True, separators=(",", ":")).encode()


class SockShop(StackApp):
    id = "sock-shop"
    project_dir = _DIR
    compose_files = [_DIR / "docker-compose.yml"]
    compose_env = {"MYSQL_ROOT_PASSWORD": "password"}
    up_extra_args = ["--scale", "user-sim=0"]
    teardown_volumes = True
    entry_port = 80

    def is_bespoke(self, image_ref: str) -> bool:

        return image_ref.startswith("weaveworksdemos/") and "load-test" not in image_ref

    def wait_ready(self, timeout_s: float) -> None:


        last = {"h": None}

        def stable() -> bool:
            status, body = http_get(_CATALOGUE_URL, timeout=5)
            if status != 200 or not body.strip().startswith(b"["):
                return False
            h = sha(_normalized_catalogue(body))
            prev, last["h"] = last["h"], h
            return prev == h
        poll_until(stable, timeout_s, interval_s=2.0, desc="sock-shop catalogue seed-stable")

    def cold_start(self) -> str:
        status, body = http_get(_CATALOGUE_URL, timeout=10)
        if status != 200:
            raise RuntimeError(f"cold catalogue status {status}")
        return sha(_normalized_catalogue(body))

    def steady_state(self, duration_s: float) -> str:


        urls = [
            _CATALOGUE_URL,
            f"{_BASE}/",
            f"{_BASE}/catalogue/size",
            f"{_BASE}/tags",
            f"{_BASE}/category.html",
        ]
        state = {"i": 0}

        def one() -> None:
            http_get(urls[state["i"] % len(urls)], timeout=10)
            state["i"] += 1
        drive_load(one, duration_s, concurrency=16)
        status, body = http_get(_CATALOGUE_URL, timeout=10)
        if status != 200:
            raise RuntimeError(f"steady probe status {status}")
        return sha(_normalized_catalogue(body))
