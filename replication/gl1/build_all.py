from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from replication.workloads.registry import SUBJECTS
from replication.runner.container import image_exists

ROOT = Path(__file__).resolve().parents[2]
REG = os.environ.get("REGISTRY", "127.0.0.1:5000")
LOG = ROOT / "experiments" / "build_all_results.json"


def _run(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def ensure_registry():
    r = _run("docker", "inspect", "-f", "{{.State.Running}}", "pullbench-registry")
    if r.stdout.strip() != "true":
        _run("docker", "start", "pullbench-registry")
        time.sleep(3)


def size(ref):
    r = _run("docker", "image", "inspect", "-f", "{{.Size}}", ref)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def push(ref, name):
    ensure_registry()
    tag = f"{REG}/{name}:latest"
    _run("docker", "tag", ref, tag, check=True)
    subject, treatment = name.rsplit("__", 1)
    _run("docker", "tag", ref, f"campaign/{subject}:{treatment}", check=True)
    _run("docker", "push", tag, check=True)
    return True


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    results = json.loads(LOG.read_text()) if LOG.exists() else {}
    from replication.debloat.slim import build_slim_image
    from replication.debloat.blafs import build_blafs_image

    for spec in SUBJECTS:
        sid = spec.id
        base = spec.image_ref
        slim_ref = base + ".slim"
        blafs_ref = base + "-baffs"


        _run("docker", "pull", base, check=True)
        push(base, f"{sid}__baseline")
        results[f"{sid}__baseline"] = {"ref": base, "size": size(base)}
        print(f"[{sid}] baseline size={size(base)}", flush=True)


        key = f"{sid}__slim"
        if image_exists(slim_ref):
            push(slim_ref, key)
            results[key] = {"ref": slim_ref, "size": size(slim_ref), "skipped": True}
            print(f"[{sid}] slim EXISTS size={size(slim_ref)}", flush=True)
        else:
            try:
                r = build_slim_image(spec)
                push(r, key)
                results[key] = {"ref": r, "size": size(r)}
                print(f"[{sid}] slim OK size={size(r)}", flush=True)
            except Exception as e:
                results[key] = {"error": str(e).replace(chr(10), " ")[:250]}
                print(f"[{sid}] slim FAIL {str(e)[:120]}", flush=True)
        LOG.write_text(json.dumps(results, indent=2))


        key = f"{sid}__blafs"
        if image_exists(blafs_ref):
            push(blafs_ref, key)
            results[key] = {"ref": blafs_ref, "size": size(blafs_ref), "skipped": True}
            print(f"[{sid}] blafs EXISTS size={size(blafs_ref)}", flush=True)
        else:
            try:
                r = build_blafs_image(spec)
                push(r, key)
                results[key] = {"ref": r, "size": size(r)}
                print(f"[{sid}] blafs OK size={size(r)}", flush=True)
            except Exception as e:
                results[key] = {"error": str(e).replace(chr(10), " ")[:250]}
                print(f"[{sid}] blafs FAIL {str(e)[:120]}", flush=True)
        LOG.write_text(json.dumps(results, indent=2))

    print("BUILD_ALL_DONE", flush=True)


if __name__ == "__main__":
    main()
