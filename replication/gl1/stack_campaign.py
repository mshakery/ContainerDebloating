from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import subprocess
import time
import urllib.request
from pathlib import Path

from replication.runner import envelope
from replication.gl1.measure import Meter
from replication.workloads import loadgen
from replication.stacks.apps.sockshop import _normalized_catalogue
from replication.stacks.apps.trainticket import _normalized_trips, _TRIPS_BODY, _fully_populated

ROOT = Path(__file__).resolve().parents[2]
MICROBENCH = Path(os.environ.get("MICROBENCH_DIR", str(ROOT / "replication" / "stacks" / "microbench")))
OV = Path(os.environ.get("OV_DIR", str(ROOT / "replication" / "stacks" / "overrides")))
OUT = ROOT / "experiments" / "new_runs" / "stack_warm"
DOCKER = "docker"
TREATMENTS = ["baseline", "slim", "blafs", "confine"]
STEADY_S = 30.0
COOLDOWN_S = 120


def _http(url, method="GET", data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _trip_post():
    return _http("http://127.0.0.1:12346/api/v1/travelservice/trips/left",
                 method="POST", data=json.dumps(_TRIPS_BODY).encode(),
                 headers={"Content-Type": "application/json"})


def _ready_hotel(t):
    url = "http://127.0.0.1:15000/user?username=Cornell_30&password=0000000000"
    s, b = _http(url, timeout=5)
    return s == 200 and b"Login successfully" in b

def _oracle_hotel():
    _, b = _http("http://127.0.0.1:15000/user?username=Cornell_30&password=0000000000")
    return hashlib.sha256(b.strip()).hexdigest()

def _ready_sock(state):
    s, b = _http("http://127.0.0.1:80/catalogue", timeout=5)
    if s != 200 or not b.strip().startswith(b"["):
        return False
    h = hashlib.sha256(_normalized_catalogue(b)).hexdigest()
    prev, state["h"] = state.get("h"), h
    return prev == h

def _oracle_sock():
    _, b = _http("http://127.0.0.1:80/catalogue")
    return hashlib.sha256(_normalized_catalogue(b)).hexdigest()

def _ready_shop(t):
    s, b = _http("http://127.0.0.1:8080/actuator/health", timeout=5)
    if not (s == 200 and b'"status":"UP"' in b):
        return False
    return _http("http://127.0.0.1:8080/api/v1/products?store=DEFAULT&lang=en&page=0&count=100", timeout=5)[0] == 200

def _oracle_shop():
    _, b = _http("http://127.0.0.1:8080/api/v1/products?store=DEFAULT&lang=en&page=0&count=100")
    return hashlib.sha256(b.strip()).hexdigest()

def _ready_train(t):
    try:
        s, b = _trip_post()
        return s == 200 and _fully_populated(json.loads(b).get("data") or [])
    except Exception:
        return False

def _oracle_train():
    _, b = _trip_post()
    return hashlib.sha256(_normalized_trips(json.loads(b).get("data") or [])).hexdigest()


STACKS = {
    "hotel-reservation": dict(
        compose=[f"{MICROBENCH}/hotelReservation/docker-compose.yml",
                 f"{MICROBENCH}/hotelres.ports.yml"],
        project="hr", timeout=300, ready=_ready_hotel, oracle=_oracle_hotel,
        load=dict(url="http://127.0.0.1:15000/hotels?inDate=2015-04-09&outDate=2015-04-10&lat=37.7867&lon=-122.4112",
                  concurrency=128)),
    "sock-shop": dict(
        compose=[f"{MICROBENCH}/sockshop/docker-compose.yml"],
        project="ss", timeout=300, ready=_ready_sock, oracle=_oracle_sock, ready_stateful=True,
        env={"MYSQL_ROOT_PASSWORD": "password"}, up_extra=["--scale", "user-sim=0"],
        load=dict(url="http://127.0.0.1:80/catalogue", concurrency=128)),
    "shopizer": dict(
        compose=[f"{MICROBENCH}/shopizer/docker-compose.yml"],
        project="sz", timeout=300, ready=_ready_shop, oracle=_oracle_shop,
        load=dict(url="http://127.0.0.1:8080/api/v1/products?store=DEFAULT&lang=en&page=0&count=100",
                  concurrency=128)),
    "train-ticket": dict(
        compose=[f"{MICROBENCH}/train-ticket/docker-compose.yml",
                 f"{MICROBENCH}/train-ticket/trainticket.dbpin.yml"],
        project="tt", timeout=1500, ready=_ready_train, oracle=_oracle_train,
        load=dict(url="http://127.0.0.1:12346/api/v1/travelservice/trips/left", method="POST",
                  body=json.dumps(_TRIPS_BODY), content_type="application/json", concurrency=96)),
}


def _files(stack_id, treatment):
    cfg = STACKS[stack_id]
    files = list(cfg["compose"])
    reg = OV / f"{stack_id}.{treatment if treatment != 'confine' else 'baseline'}.reg.yml"
    if reg.exists():
        files.append(str(reg))
    files.append(str(OV / f"{stack_id}.cpuset.yml"))


    if treatment == "confine":
        sec = OV / f"{stack_id}.confine.seccomp.yml"
        if sec.exists():
            files.append(str(sec))
    return files


def _compose(files, project, *rest, env=None, timeout=1800):
    cmd = [DOCKER, "compose", "-p", project]
    for f in files:
        cmd += ["-f", f]
    cmd += list(rest)
    import os
    e = {**os.environ, **(env or {})}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=e)


def run_stack_trial(stack_id, treatment, meter, do_pull=True):
    cfg = STACKS[stack_id]
    files = _files(stack_id, treatment)
    env = cfg.get("env")
    w = {}
    cold = steady = None
    load = None
    up_ok = False
    try:
        if do_pull:
            _compose(files, cfg["project"], "pull", env=env)
        with meter:
            t0m, t0w = time.monotonic(), time.time()
            up = _compose(files, cfg["project"], "up", "-d", "--remove-orphans",
                          *cfg.get("up_extra", []), env=env, timeout=cfg["timeout"] + 300)
            if up.returncode != 0:
                raise RuntimeError(f"up failed: {(up.stderr or '')[-400:]}")
            up_ok = True
            deadline = t0m + cfg["timeout"]
            state = {}
            rf = cfg["ready"]
            while time.monotonic() < deadline:
                try:
                    ok = rf(state) if cfg.get("ready_stateful") else rf(treatment)
                    if ok:
                        break
                except Exception:
                    pass
                time.sleep(3.0)
            else:
                raise TimeoutError("stack not ready")
            t1m, t1w = time.monotonic(), time.time()
            w["provisioning"] = (t0w, t1w, t1m - t0m)
            cold = cfg["oracle"]()
            t2m, t2w = time.monotonic(), time.time()
            w["cold_start"] = (t1w, t2w, max(t2m - t1m, 1e-6))
            ld = cfg["load"]
            load = loadgen.hey_load(ld["url"], STEADY_S, concurrency=ld.get("concurrency", 128),
                                    method=ld.get("method", "GET"), body=ld.get("body"),
                                    content_type=ld.get("content_type"))
            steady = cfg["oracle"]()
            t3m, t3w = time.monotonic(), time.time()
            w["steady_state"] = (t2w, t3w, t3m - t2m)
    finally:
        _compose(files, cfg["project"], "down", "-v", "--remove-orphans", "-t", "20", env=env, timeout=600)
    return _assemble(meter, w, cold, steady, load)


def _assemble(meter, windows, cold, steady, load):
    row = {"cold_output_hash": cold, "steady_output_hash": steady,
           "steady_requests": (load.requests if load else None),
           "steady_rps": (load.rps if load else None), "load_ok": (load.ok if load else None)}
    for ph, (t0w, t1w, dur) in windows.items():
        for k, v in meter.phase(t0w, t1w, dur).items():
            row[f"{ph}_{k}"] = v
    if "steady_state" in windows:
        t0w, t1w, _ = windows["steady_state"]
        row.update(meter.cpu(t0w, t1w))
    return row


def _clear():
    for p in STACKS.values():
        subprocess.run([DOCKER, "compose", "-p", p["project"], "down", "-v", "--remove-orphans", "-t", "10"],
                       capture_output=True)
    ids = subprocess.run([DOCKER, "ps", "-aq"], capture_output=True, text=True).stdout.split()
    if ids:
        subprocess.run([DOCKER, "rm", "-f", *ids], capture_output=True)


def main() -> int:
    global STEADY_S, COOLDOWN_S
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--stacks", default=",".join(STACKS))
    ap.add_argument("--treatments", default=",".join(TREATMENTS))
    ap.add_argument("--steady", type=float, default=STEADY_S)
    ap.add_argument("--cooldown", type=float, default=COOLDOWN_S)
    ap.add_argument("--no-pull", action="store_true",
                    help="skip per-trial compose pull (use pre-warmed local store; no tunnel needed)")
    ap.add_argument("--prewarm", action="store_true",
                    help="only pull all (stack x treatment) images to the local store, then exit (run with tunnel up)")
    ap.add_argument("--outdir", default=str(OUT))
    args = ap.parse_args()
    STEADY_S = args.steady
    COOLDOWN_S = args.cooldown
    stacks = [s for s in args.stacks.split(",") if s in STACKS]
    treatments = [t for t in args.treatments.split(",") if t in TREATMENTS]

    if args.prewarm:
        pull_treats = [t for t in treatments if t != "confine"] or ["baseline"]
        for s in stacks:
            for t in pull_treats:
                files = _files(s, t)
                r = _compose(files, STACKS[s]["project"], "pull", env=STACKS[s].get("env"))
                print(f"  prewarm {s}/{t}: {'ok' if r.returncode == 0 else 'FAIL ' + (r.stderr or '')[-200:]}", flush=True)
        print("PREWARM_DONE", flush=True)
        return 0

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    run_csv = outdir / "run_table.csv"
    baseline_hashes = {}

    _phases = ("provisioning", "cold_start", "steady_state")
    _pm = ("duration_s", "energy_pkg0_eb_j", "energy_pkg0_sysfs_j",
           "energy_pkg1_j", "energy_node_j", "power_pkg0_w")
    csv_fields = (["subject", "treatment", "rep", "kind", "ok", "error",
                   "cold_output_hash", "steady_output_hash", "cold_match", "steady_match",
                   "steady_requests", "steady_rps", "load_ok",
                   "cpu_sut_0_7_pct", "cpu_loadgen_8_15_pct"]
                  + [f"{p}_{m}" for p in _phases for m in _pm])

    trials = [(s, t, r) for r in range(args.reps) for s in stacks for t in treatments]
    random.Random(42).shuffle(trials)
    header_exists = run_csv.exists()
    fh = run_csv.open("a", newline="")
    writer = csv.DictWriter(fh, fieldnames=csv_fields, restval="", extrasaction="ignore")
    if not header_exists:
        writer.writeheader()
    print(f"[stack-campaign] {len(trials)} trials  {envelope.summary()}", flush=True)
    for i, (s, t, rep) in enumerate(trials):
        _clear()
        result = {"subject": s, "treatment": t, "rep": rep, "kind": "stack", "ok": False, "error": None}
        try:


            meter = Meter(outdir / s / t / f"rep-{rep}")
            r = run_stack_trial(s, t, meter, do_pull=not args.no_pull)
            result.update(r); result["ok"] = True
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"[:300]
        if t == "baseline" and result["ok"]:
            baseline_hashes.setdefault(s, (result.get("cold_output_hash"), result.get("steady_output_hash")))
        if s in baseline_hashes and result["ok"]:
            bc, bs = baseline_hashes[s]
            result["cold_match"] = result.get("cold_output_hash") == bc
            result["steady_match"] = result.get("steady_output_hash") == bs
        (outdir / s / t / f"rep-{rep}").mkdir(parents=True, exist_ok=True)
        (outdir / s / t / f"rep-{rep}" / "trial.json").write_text(json.dumps(result, indent=2, default=str))
        writer.writerow(result); fh.flush()
        print(f"[{i+1}/{len(trials)}] {s}/{t}/r{rep} ok={result['ok']} err={result['error']} "
              f"sat={result.get('cpu_sut_0_7_pct')}", flush=True)
        if i + 1 < len(trials):
            time.sleep(COOLDOWN_S)
    fh.close()
    print("STACK_CAMPAIGN_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
