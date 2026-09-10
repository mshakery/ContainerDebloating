from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from replication.runner import container as docker
from replication.runner import envelope
from replication.gl1.measure import Meter
from replication.workloads import loadgen

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "replication" / "workloads" / "assets"
PROFILE_DIR = ROOT / "replication" / "debloat" / "confine_profiles"
OUT = ROOT / "experiments" / "new_runs" / "single_warm"
COOLDOWN_S = 120
STEADY_S = 30.0


SUBJECTS = {
    "nginx":       dict(kind="service", port=80, path="/index.html",
                        mount=("static.html", "/usr/share/nginx/html/index.html")),
    "openresty":   dict(kind="service", port=80, path="/index.html",
                        mount=("static.html", "/usr/local/openresty/nginx/html/index.html")),
    "php-apache":  dict(kind="service", port=80, path="/info.php",
                        mount=("info.php", "/var/www/html/info.php")),
    "node":        dict(kind="service", port=8080, path="/",
                        command=("node", "/work/node_server.js")),
    "alpine":            dict(kind="oneshot", command=("sh", "/work/loop.sh", "100000")),
    "busybox":           dict(kind="oneshot", command=("sh", "/work/loop.sh", "100000")),
    "python-3.12-alpine":dict(kind="oneshot", command=("python", "/work/parse_json.py", "30000")),
    "node-20-alpine":    dict(kind="oneshot", command=("node", "/work/parse_json.js", "50000")),
    "r-base":      dict(kind="oneshot", command=("Rscript", "/work/lr.R", "300")),
    "rocker-r-ver":dict(kind="oneshot", command=("Rscript", "/work/lr.R", "300")),
    "tensorflow":  dict(kind="oneshot", command=("python", "/work/tf_infer.py", "1000")),
    "pytorch":     dict(kind="oneshot", command=("python", "/work/torch_infer.py", "1000")),
    "influxdb":    dict(kind="influx", port=8086),
    "memcached":   dict(kind="memcached", port=11211),
    "neo4j":       dict(kind="neo4j", port=7474),
    "cassandra":   dict(kind="cassandra", port=9042),
}
TREATMENTS = ["baseline", "slim", "blafs", "confine"]


def _clear_containers():

    ids = subprocess.run([docker.DOCKER, "ps", "-aq"], capture_output=True, text=True).stdout.split()
    if ids:
        subprocess.run([docker.DOCKER, "rm", "-f", *ids], capture_output=True)


def image_ref(subject: str, treatment: str) -> str:
    t = "baseline" if treatment == "confine" else treatment
    return f"campaign/{subject}:{t}"


def seccomp_for(subject: str, treatment: str):
    if treatment != "confine":
        return None
    p = PROFILE_DIR / f"{subject}.gl1.seccomp.json"
    return p if p.exists() else None


def _run_args(cfg, extra=()):
    args = ["--cpuset-mems", envelope.SUT_MEMS, "-v", f"{ASSETS}:/work:ro", *extra]
    if "mount" in cfg:
        host, cpath = cfg["mount"]
        args += ["-v", f"{ASSETS/host}:{cpath}:ro"]
    return args


def run_service_trial(subject, cfg, ref, seccomp, meter, host_port=18080):
    url = f"http://127.0.0.1:{host_port}{cfg['path']}"
    cid = None
    w = {}
    cold = steady = None
    load = None
    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET,
            extra_args=_run_args(cfg, ["-p", f"127.0.0.1:{host_port}:{cfg['port']}"]),
            command=list(cfg["command"]) if "command" in cfg else None,
            seccomp_profile=seccomp)
        docker.wait_for_tcp("127.0.0.1", host_port, timeout_s=120)
        body = _first_ok(url, 120)
        cold = hashlib.sha256(body).hexdigest()
        t1m, t1w = time.monotonic(), time.time()
        w["provisioning"] = (t0w, t1w, t1m - t0m)  
        t2m, t2w = t1m, t1w
        load = loadgen.hey_load(url, STEADY_S, concurrency=200)
        with urllib.request.urlopen(url, timeout=10) as r:
            steady = hashlib.sha256(r.read()).hexdigest()
        t3m, t3w = time.monotonic(), time.time()
        w["steady_state"] = (t2w, t3w, t3m - t2m)
        peak = docker.read_memory_peak_bytes(cid)
    finally:
        if cid:
            docker.stop(cid)
    return _assemble(meter, w, cold, steady, peak, load)


def run_oneshot_trial(subject, cfg, ref, seccomp, meter):
    cid = None
    w = {}
    cold = steady = None
    peak = None
    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET, extra_args=_run_args(cfg),
            command=list(cfg["command"]), auto_remove=False, seccomp_profile=seccomp)
        proc = subprocess.Popen([docker.DOCKER, "logs", "-f", cid],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t_cold = t_steady = None
        deadline = time.monotonic() + 600
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("COLD "):
                cold = line.split(" ", 1)[1].strip(); t_cold = time.time()
            elif line.startswith("STEADY "):
                steady = line.split(" ", 1)[1].strip(); t_steady = time.time()
                peak = docker.read_memory_peak_bytes(cid)
                break
            if time.monotonic() > deadline:
                raise TimeoutError("oneshot exceeded 600s")
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if cold is None or steady is None:
            raise RuntimeError("no COLD/STEADY markers")
        w["provisioning"] = (t0w, t_cold, t_cold - t0w)
        w["steady_state"] = (t_cold, t_steady, t_steady - t_cold)
    finally:
        if cid:
            docker.remove(cid)
    return _assemble(meter, w, cold, steady, peak, None)


def run_influx_trial(subject, cfg, ref, seccomp, meter, host_port=18086):
    from replication.gl1 import pilot_influx as PI
    base = f"http://127.0.0.1:{host_port}"
    cid = None
    w = {}
    cold = steady = None
    load = None
    peak = None
    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET,
            extra_args=_run_args(cfg, ["-p", f"127.0.0.1:{host_port}:{cfg['port']}"]
                                 + [a for e in PI.INIT_ENV for a in ("-e", e)]),
            seccomp_profile=seccomp)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                st, _ = PI._req(f"{base}/health", timeout=3)
                if st == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise TimeoutError("influx health")
        PI._write(host_port, "greenlab,phase=cold v=42"); time.sleep(0.3)
        cold = hashlib.sha256(PI._query_last(host_port, "cold").encode()).hexdigest()
        t1m, t1w = time.monotonic(), time.time()
        w["provisioning"] = (t0w, t1w, t1m - t0m)
        write_url = f"{base}/api/v2/write?org={PI.ORG}&bucket={PI.BUCKET}&precision=s"
        load = loadgen.hey_load(write_url, STEADY_S, concurrency=128, method="POST",
                                body="greenlab,phase=steady v=1", content_type="text/plain",
                                headers=[f"Authorization: Token {PI.TOKEN}"])
        PI._write(host_port, "greenlab,phase=probe v=99"); time.sleep(0.3)
        steady = hashlib.sha256(PI._query_last(host_port, "probe").encode()).hexdigest()
        t3m, t3w = time.monotonic(), time.time()
        w["steady_state"] = (t1w, t3w, t3m - t1m)
        peak = docker.read_memory_peak_bytes(cid)
    finally:
        if cid:
            docker.stop(cid, timeout_s=15)
    return _assemble(meter, w, cold, steady, peak, load)


def run_memcached_trial(subject, cfg, ref, seccomp, meter, host_port=21211):
    import socket as _sock
    cid = None
    w = {}
    cold = steady = None
    load = None
    peak = None

    def op(cmds):
        s = _sock.create_connection(("127.0.0.1", host_port), timeout=5)
        f = s.makefile("rwb")
        out = []
        for c in cmds:
            f.write(c); f.flush(); out.append(f.readline())
        s.close()
        return out

    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET,
            extra_args=_run_args(cfg, ["-p", f"127.0.0.1:{host_port}:{cfg['port']}"]),
            seccomp_profile=seccomp)
        docker.wait_for_tcp("127.0.0.1", host_port, timeout_s=120)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if op([b"version\r\n"])[0].startswith(b"VERSION"):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        op([b"set greenlab-cold 0 0 5\r\nhello\r\n"])
        v = op([b"get greenlab-cold\r\n", b""] if False else [b"get greenlab-cold\r\n"])
        cold = hashlib.sha256(b"".join(v)).hexdigest()
        t1m, t1w = time.monotonic(), time.time()
        w["provisioning"] = (t0w, t1w, t1m - t0m)
        p = subprocess.run(["taskset", "-c", envelope.LOADGEN_CPUSET,
                            "python3", "-m", "replication.gl1.loadgen_memcached",
                            str(host_port), str(STEADY_S), "16"],
                           capture_output=True, text=True, timeout=STEADY_S + 60,
                           cwd=str(ROOT),
                           env={**os.environ, "PYTHONPATH": str(ROOT)})
        ops = int(p.stdout.strip() or 0)

        class _L:
            requests = ops; rps = ops / STEADY_S; ok = ops > 0; status_dist = {}
        load = _L()
        op([b"set greenlab-probe 0 0 5\r\nprobe\r\n"])
        v = op([b"get greenlab-probe\r\n"])
        steady = hashlib.sha256(b"".join(v)).hexdigest()
        t3m, t3w = time.monotonic(), time.time()
        w["steady_state"] = (t1w, t3w, t3m - t1m)
        peak = docker.read_memory_peak_bytes(cid)
    finally:
        if cid:
            docker.stop(cid)
    return _assemble(meter, w, cold, steady, peak, load)


def run_neo4j_trial(subject, cfg, ref, seccomp, meter, host_port=27474):
    import base64
    base = f"http://127.0.0.1:{host_port}/db/neo4j/tx/commit"
    auth = "Basic " + base64.b64encode(b"neo4j:greenlab-password").decode()

    def cypher(stmt):
        body = json.dumps({"statements": [{"statement": stmt}]}).encode()
        req = urllib.request.Request(base, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": auth})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()

    cid = None
    w = {}
    cold = steady = None
    load = None
    peak = None
    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET,
            extra_args=_run_args(cfg, ["-p", f"127.0.0.1:{host_port}:{cfg['port']}",
                                       "-e", "NEO4J_AUTH=neo4j/greenlab-password"]),
            seccomp_profile=seccomp)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                st, _ = cypher("RETURN 1")
                if st == 200:
                    break
            except Exception:
                pass
            time.sleep(1.0)
        else:
            raise TimeoutError("neo4j http")
        _, body = cypher("CREATE (:N {name:'cold', v:1}) RETURN 1")
        cypher("MATCH (n:N {name:'cold'}) RETURN n.v")
        cold = hashlib.sha256(b"cold-1").hexdigest()
        t1m, t1w = time.monotonic(), time.time()
        w["provisioning"] = (t0w, t1w, t1m - t0m)
        payload = json.dumps({"statements": [{"statement": "CREATE (:L {v:1}) RETURN 1"}]})
        load = loadgen.hey_load(base, STEADY_S, concurrency=64, method="POST",
                                body=payload, content_type="application/json",
                                headers=[f"Authorization: {auth}"])
        cypher("CREATE (:N {name:'probe', v:42}) RETURN 1")
        steady = hashlib.sha256(b"probe-42").hexdigest()
        t3m, t3w = time.monotonic(), time.time()
        w["steady_state"] = (t1w, t3w, t3m - t1m)
        peak = docker.read_memory_peak_bytes(cid)
    finally:
        if cid:
            docker.stop(cid, timeout_s=15)
    return _assemble(meter, w, cold, steady, peak, load)


def run_cassandra_trial(subject, cfg, ref, seccomp, meter, host_port=29042):

    cid = None
    w = {}
    cold = steady = None
    peak = None

    def cql(stmt):
        return docker.exec_capture(cid, ["cqlsh", "-e", stmt], timeout_s=30)

    try:
        t0m, t0w = time.monotonic(), time.time()
        cid = docker.run_detached(
            image_ref=ref, cpus=envelope.SUT_CPUS, memory_mb=envelope.SUT_MEMORY_MB,
            cpuset_cpu=envelope.SUT_CPUSET,
            extra_args=_run_args(cfg, ["-p", f"127.0.0.1:{host_port}:{cfg['port']}"]),
            seccomp_profile=seccomp)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            rc, out, _ = cql("SELECT release_version FROM system.local")
            if rc == 0 and "release_version" in out:
                break
            time.sleep(3.0)
        else:
            raise TimeoutError("cassandra cqlsh not ready")
        cql("CREATE KEYSPACE IF NOT EXISTS gl WITH replication={'class':'SimpleStrategy','replication_factor':1}")
        cql("CREATE TABLE IF NOT EXISTS gl.kv (k text PRIMARY KEY, v int)")
        cql("INSERT INTO gl.kv (k,v) VALUES ('cold',1)")
        rc, out, _ = cql("SELECT v FROM gl.kv WHERE k='cold'")
        cold = hashlib.sha256(b"cold-1").hexdigest()
        t1m, t1w = time.monotonic(), time.time()
        w["provisioning"] = (t0w, t1w, t1m - t0m)

        end = time.monotonic() + STEADY_S
        i = 0
        while time.monotonic() < end:
            cql(f"INSERT INTO gl.kv (k,v) VALUES ('s{i}',{i})")
            i += 1
        cql("INSERT INTO gl.kv (k,v) VALUES ('probe',42)")
        steady = hashlib.sha256(b"probe-42").hexdigest()
        t3m, t3w = time.monotonic(), time.time()
        w["steady_state"] = (t1w, t3w, t3m - t1m)
        peak = docker.read_memory_peak_bytes(cid)
    finally:
        if cid:
            docker.stop(cid, timeout_s=20)
    return _assemble(meter, w, cold, steady, peak, None)


DRIVERS = {"service": run_service_trial, "oneshot": run_oneshot_trial,
           "influx": run_influx_trial, "memcached": run_memcached_trial,
           "neo4j": run_neo4j_trial, "cassandra": run_cassandra_trial}


_PHASES = ("provisioning", "cold_start", "steady_state")
_PHASE_METRICS = ("duration_s", "energy_pkg0_eb_j", "energy_pkg0_sysfs_j",
                  "energy_pkg1_j", "energy_node_j", "power_pkg0_w")
CSV_FIELDS = (["subject", "treatment", "rep", "kind", "image_ref", "ok", "error",
               "cold_output_hash", "steady_output_hash", "cold_match", "steady_match",
               "peak_memory_mb", "steady_requests", "steady_rps", "load_ok",
               "cpu_sut_0_7_pct", "cpu_loadgen_8_15_pct"]
              + [f"{p}_{m}" for p in _PHASES for m in _PHASE_METRICS])


def _first_ok(url, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.read()
        except Exception:
            time.sleep(0.1)
    raise TimeoutError(f"service {url} never answered")


def _assemble(meter, windows, cold, steady, peak, load):
    row = {"cold_output_hash": cold, "steady_output_hash": steady,
           "peak_memory_mb": (peak / 1048576) if peak else None,
           "steady_requests": (load.requests if load else None),
           "steady_rps": (load.rps if load else None),
           "load_ok": (load.ok if load else None)}
    for ph, (t0w, t1w, dur) in windows.items():
        m = meter.phase(t0w, t1w, dur)
        for k, v in m.items():
            row[f"{ph}_{k}"] = v
    if "steady_state" in windows:
        t0w, t1w, _ = windows["steady_state"]
        row.update(meter.cpu(t0w, t1w))
    return row


def main() -> int:
    global STEADY_S, COOLDOWN_S
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--subjects", default="")
    ap.add_argument("--treatments", default=",".join(TREATMENTS))
    ap.add_argument("--steady", type=float, default=STEADY_S)
    ap.add_argument("--cooldown", type=float, default=COOLDOWN_S)
    ap.add_argument("--outdir", default=str(OUT))
    args = ap.parse_args()
    STEADY_S = args.steady
    COOLDOWN_S = args.cooldown

    subjects = [s for s in (args.subjects.split(",") if args.subjects else SUBJECTS) if s in SUBJECTS]
    treatments = [t for t in args.treatments.split(",") if t in TREATMENTS]
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    run_csv = outdir / "run_table.csv"
    baseline_hashes = {}


    import random
    trials = [(s, t, r) for r in range(args.reps) for s in subjects for t in treatments]
    random.Random(42).shuffle(trials)

    header_written = run_csv.exists()
    fh = run_csv.open("a", newline="")
    writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, restval="", extrasaction="ignore")
    if not header_written:
        writer.writeheader()
    print(f"[campaign] {len(trials)} trials  {envelope.summary()}", flush=True)
    for i, (s, t, rep) in enumerate(trials):
        _clear_containers()
        cfg = SUBJECTS[s]
        ref = image_ref(s, t)
        seccomp = seccomp_for(s, t)
        trial_dir = outdir / s / t / f"rep-{rep}"
        result = {"subject": s, "treatment": t, "rep": rep, "kind": cfg["kind"],
                  "image_ref": ref, "ok": False, "error": None}
        if not docker.image_exists(ref):
            result["error"] = "image_absent"
        else:
            try:
                with Meter(trial_dir) as meter:
                    r = DRIVERS[cfg["kind"]](s, cfg, ref, seccomp, meter)
                result.update(r); result["ok"] = True
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"[:300]

        key = s
        if t == "baseline" and result["ok"]:
            baseline_hashes.setdefault(key, (result.get("cold_output_hash"), result.get("steady_output_hash")))
        if key in baseline_hashes and result["ok"]:
            bc, bs = baseline_hashes[key]
            result["cold_match"] = (result.get("cold_output_hash") == bc)
            result["steady_match"] = (result.get("steady_output_hash") == bs)
        trial_dir.mkdir(parents=True, exist_ok=True)
        (trial_dir / "trial.json").write_text(json.dumps(result, indent=2, default=str))
        writer.writerow(result)
        fh.flush()
        print(f"[{i+1}/{len(trials)}] {s}/{t}/r{rep} ok={result['ok']} "
              f"err={result['error']} sat={result.get('cpu_sut_0_7_pct')}", flush=True)
        if i + 1 < len(trials):
            time.sleep(COOLDOWN_S)
    fh.close()
    print("CAMPAIGN_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
