from __future__ import annotations

import json
from pathlib import Path

from replication.stacks.base import (
    StackApp, drive_load, http_post_json, poll_until, sha,
)

_REPO = Path("/root/microbench/train-ticket")
_TRAVEL = "http://127.0.0.1:12346"
_TRIPS_URL = f"{_TRAVEL}/api/v1/travelservice/trips/left"


_TRIPS_BODY = {"departureTime": "2026-12-01", "startingPlace": "Shang Hai", "endPlace": "Su Zhou"}


_VOLATILE = {"economyClass", "confortClass", "comfortClass",
             "startTime", "endTime", "startingTime", "endingTime"}


def _query_trips() -> list:
    status, body = http_post_json(_TRIPS_URL, _TRIPS_BODY, timeout=20)
    if status != 200:
        raise RuntimeError(f"trip query status {status}")
    data = json.loads(body).get("data")
    return data if isinstance(data, list) else []


def _fully_populated(trips: list) -> bool:

    if not trips:
        return False
    for t in trips:
        if not isinstance(t, dict):
            return False
        if not t.get("trainTypeId") or not t.get("priceForEconomyClass"):
            return False
    return True


def _normalized_trips(trips: list) -> bytes:
    cleaned = []
    for t in trips:
        if not isinstance(t, dict):
            continue
        cleaned.append({k: v for k, v in t.items() if k not in _VOLATILE})
    cleaned.sort(key=lambda d: json.dumps(d.get("tripId"), sort_keys=True))
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":")).encode()


class TrainTicket(StackApp):
    id = "train-ticket"
    project_dir = _REPO
    compose_files = [
        _REPO / "docker-compose.yml",


        Path("/root/microbench/compose/overrides/trainticket.dbpin.yml"),
    ]
    compose_env: dict[str, str] = {}
    up_extra_args: list[str] = []
    teardown_volumes = True
    entry_port = 8080
    provisioning_timeout_s = 1500.0

    def is_bespoke(self, image_ref: str) -> bool:
        return image_ref.startswith("codewisdom/")

    def wait_ready(self, timeout_s: float) -> None:


        poll_until(lambda: _fully_populated(_query_trips()),
                   timeout_s, interval_s=5.0, desc="train-ticket trip query fully populated")

    def cold_start(self) -> str:
        return sha(_normalized_trips(_query_trips()))

    def steady_state(self, duration_s: float) -> str:
        drive_load(_query_trips, duration_s, concurrency=16)
        return sha(_normalized_trips(_query_trips()))
