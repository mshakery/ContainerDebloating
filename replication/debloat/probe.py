from __future__ import annotations

import argparse
from pathlib import Path

from replication.runner.base import TrialContext
from replication.workloads.registry import SUBJECTS_BY_ID


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("subject_id", help="datastore subject id (memcached, influxdb, neo4j, cassandra)")
    p.add_argument("--timeout", type=float, default=180.0,
                   help="readiness timeout in seconds")
    args = p.parse_args()

    if args.subject_id not in SUBJECTS_BY_ID:
        p.error(f"unknown subject {args.subject_id!r}")

    workload = SUBJECTS_BY_ID[args.subject_id].workload_factory()


    ctx = TrialContext(
        image_ref="(unused-during-slim-probe)",
        assets_dir=Path("/tmp"),
        cpus=1.0, memory_mb=1792, cpuset_cpu=2,
        steady_duration_s=0.0,
        provisioning_timeout_s=args.timeout,
    )

    workload.wait_ready(ctx)
    workload.cold_start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
