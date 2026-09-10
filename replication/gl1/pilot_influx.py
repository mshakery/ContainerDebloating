from __future__ import annotations

import argparse
import hashlib
import statistics
import time
import urllib.request
from pathlib import Path

from replication.runner import container as docker
from replication.runner import envelope, rapl
from replication.runner.energibridge import EnergiBridgeSession
from replication.runner.measurements import load_csv as eb_load_csv, _row_time_s, _row_float
from replication.workloads import loadgen

TOKEN = "greenlab-token"
ORG = "gl"
BUCKET = "gl"
INIT_ENV = [
    "DOCKER_INFLUXDB_INIT_MODE=setup",
    "DOCKER_INFLUXDB_INIT_USERNAME=greenlab",
    "DOCKER_INFLUXDB_INIT_PASSWORD=greenlab-password",
    f"DOCKER_INFLUXDB_INIT_ORG={ORG}",
    f"DOCKER_INFLUXDB_INIT_BUCKET={BUCKET}",
    f"DOCKER_INFLUXDB_INIT_ADMIN_TOKEN={TOKEN}",
]


def _req(url, data=None, headers=None, method="GET", timeout=10):
    r = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def _write(hp, line):
    return _req(f"http://127.0.0.1:{hp}/api/v2/write?org={ORG}&bucket={BUCKET}&precision=s",
                data=line.encode(),
                headers={"Authorization": f"Token {TOKEN}", "Content-Type": "text/plain"},
                method="POST")


def _query_last(hp, phase):
    flux = (f'from(bucket:"{BUCKET}") |> range(start:-1h) '
            f'|> filter(fn:(r) => r.phase == "{phase}") |> last()')
    _, body = _req(f"http://127.0.0.1:{hp}/api/v2/query?org={ORG}",
                   data=flux.encode(),
                   headers={"Authorization": f"Token {TOKEN}",
                            "Content-Type": "application/vnd.flux", "Accept": "application/csv"},
                   method="POST")

    vals = []
    for row in body.decode().splitlines():
        cells = row.split(",")
        if len(cells) > 6 and cells[6] not in ("_value", "", "result"):
            vals.append(cells[6])
    return "|".join(vals)


def _mean_core_usage(rows, cores, t0, t1):
    per = []
    for r in rows:
        ts = _row_time_s(r)
        if ts is None or not (t0 <= ts <= t1):
            continue
        vals = [v for c in cores if (v := _row_float(r, (f"CPU_USAGE_{c}",))) is not None]
        if vals:
            per.append(sum(vals) / len(vals))
    return statistics.mean(per) if per else None


def _eb_pkg(rows, t0w, t1w):
    first = last = None
    for r in rows:
        ts = _row_time_s(r)
        if ts is None or not (t0w <= ts <= t1w):
            continue
        v = _row_float(r, ("PACKAGE_ENERGY (J)",))
        if v is None:
            continue
        first = v if first is None else first
        last = v
    return (last - first) if (first is not None and last is not None) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default="library/influxdb:latest")
    ap.add_argument("--subject", default="influx")
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--host-port", type=int, default=18086)
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=128)
    ap.add_argument("--provision-timeout", type=float, default=180.0)
    ap.add_argument("--seccomp", default=None)
    ap.add_argument("--outdir", default="/tmp/gl1_pilot")
    args = ap.parse_args()

    out = Path(args.outdir) / args.subject
    out.mkdir(parents=True, exist_ok=True)
    eb_csv = out / "energibridge.csv"
    rapl_csv = out / "rapl_socket.csv"
    hp = args.host_port
    base = f"http://127.0.0.1:{hp}"
    write_url = f"{base}/api/v2/write?org={ORG}&bucket={BUCKET}&precision=s"

    print(f"[influx] {args.subject} image={args.image}  {envelope.summary()}")
    if not docker.image_exists(args.image):
        docker.pull(args.image)

    cid = None
    rs = rapl.RaplSampler(rapl_csv, pkgs=envelope.RAPL_PKGS, interval_s=0.1)
    windows = {}
    cold_hash = steady_hash = None
    load = None
    try:
        with EnergiBridgeSession(eb_csv, sample_interval_ms=100):
            rs.start()
            t0m, t0w = time.monotonic(), time.time()
            cid = docker.run_detached(
                image_ref=args.image, cpus=envelope.SUT_CPUS,
                memory_mb=envelope.SUT_MEMORY_MB, cpuset_cpu=envelope.SUT_CPUSET,
                extra_args=["-p", f"127.0.0.1:{hp}:{args.port}", "--cpuset-mems", envelope.SUT_MEMS]
                           + [a for e in INIT_ENV for a in ("-e", e)],
                seccomp_profile=Path(args.seccomp) if args.seccomp else None,
            )

            deadline = t0m + args.provision_timeout
            ready = False
            while time.monotonic() < deadline:
                try:
                    st, _ = _req(f"{base}/health", timeout=3)
                    if st == 200:
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not ready:
                raise TimeoutError("influx /health never 200")
            t1m, t1w = time.monotonic(), time.time()
            windows["provisioning"] = (t0w, t1w, t1m - t0m)


            _write(hp, "greenlab,phase=cold v=42")
            time.sleep(0.3)
            cold_hash = hashlib.sha256(_query_last(hp, "cold").encode()).hexdigest()
            t2m, t2w = time.monotonic(), time.time()
            windows["cold_start"] = (t1w, t2w, t2m - t1m)


            load = loadgen.hey_load(
                write_url, args.duration, concurrency=args.concurrency,
                method="POST", body="greenlab,phase=steady v=1", content_type="text/plain",
                headers=[f"Authorization: Token {TOKEN}"])
            _write(hp, "greenlab,phase=probe v=99")
            time.sleep(0.3)
            steady_hash = hashlib.sha256(_query_last(hp, "probe").encode()).hexdigest()
            t3m, t3w = time.monotonic(), time.time()
            windows["steady_state"] = (t2w, t3w, t3m - t2m)

            peak = docker.read_memory_peak_bytes(cid)
            rs.stop()
    finally:
        rs.stop()
        if cid:
            docker.stop(cid, timeout_s=15)

    eb_rows = eb_load_csv(eb_csv)
    rp_rows = rapl.load_csv(rapl_csv)
    print("\n============ INFLUX PILOT RESULT ============")
    print(f"cold_hash={cold_hash}  steady_hash={steady_hash}  peak_mem_MB="
          f"{(peak/1048576):.0f}" if peak else "peak=?")
    if load:
        print(f"write load: {load.requests} writes, {load.rps:.0f} wps, status={load.status_dist}, ok={load.ok}")
    for ph in ("provisioning", "cold_start", "steady_state"):
        t0w, t1w, dur = windows[ph]
        eb = _eb_pkg(eb_rows, t0w, t1w)
        p0 = rapl.energy_over_window(rp_rows, t0w, t1w, "pkg0_j")
        p1 = rapl.energy_over_window(rp_rows, t0w, t1w, "pkg1_j")
        def w(x): return f"{x/dur:5.1f}W" if x is not None and dur > 0 else "  ?  "
        def j(x): return f"{x:6.1f}J" if x is not None else "   ?  "
        print(f"  {ph:13} dur={dur:6.2f}s | EB_pkg0={j(eb)} ({w(eb)}) "
              f"sysfs_pkg0={j(p0)} pkg1={j(p1)}")
    s = windows["steady_state"]
    c07 = _mean_core_usage(eb_rows, range(0, 8), s[0], s[1])
    c815 = _mean_core_usage(eb_rows, range(8, 16), s[0], s[1])
    if c07 is not None:
        print(f"  steady CPU: cores0-7(SUT)={c07:.1f}%  cores8-15(loadgen)={c815:.1f}%")
    print("=============================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
