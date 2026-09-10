from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from replication.runner import container as docker
from replication.runner.base import (
    Phase, PhaseWindow, TrialContext, Workload, WorkloadOutcome,
)


@dataclass
class DatastoreConfig:
    subject_id: str
    container_port: int
    host_port: int
    extra_run_args: tuple[str, ...] = ()
    extra_env: tuple[tuple[str, str], ...] = ()


class _DatastoreBase(Workload):


    config: DatastoreConfig

    def __init__(self, config: DatastoreConfig):
        self.config = config
        self.subject_id = config.subject_id

    def _run_args(self, assets_dir: Path) -> list[str]:
        args: list[str] = [
            "-p", f"127.0.0.1:{self.config.host_port}:{self.config.container_port}",
            "-v", f"{assets_dir}:/work:ro",
        ]
        for k, v in self.config.extra_env:
            args += ["-e", f"{k}={v}"]
        args += list(self.config.extra_run_args)
        return args


    def wait_ready(self, ctx: TrialContext) -> None:

        docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                            timeout_s=ctx.provisioning_timeout_s)

    def cold_start(self) -> str:
        raise NotImplementedError

    def steady_state(self, duration_s: float) -> str:
        raise NotImplementedError

    def execute(self, ctx: TrialContext) -> WorkloadOutcome:
        out = WorkloadOutcome()
        cid: Optional[str] = None
        try:
            t0_mono, t0_wall = time.monotonic(), time.time()
            cid = docker.run_detached(
                image_ref=ctx.image_ref,
                cpus=ctx.cpus, memory_mb=ctx.memory_mb, cpuset_cpu=ctx.cpuset_cpu,
                extra_args=self._run_args(ctx.assets_dir),
                seccomp_profile=ctx.seccomp_profile,
            )
            self.wait_ready(ctx)
            t1_mono, t1_wall = time.monotonic(), time.time()
            out.windows[Phase.PROVISIONING] = PhaseWindow(
                Phase.PROVISIONING, t0_mono, t1_mono, t0_wall, t1_wall)

            out.cold_output_hash = self.cold_start()
            t2_mono, t2_wall = time.monotonic(), time.time()
            out.windows[Phase.COLD_START] = PhaseWindow(
                Phase.COLD_START, t1_mono, t2_mono, t1_wall, t2_wall)

            out.steady_output_hash = self.steady_state(ctx.steady_duration_s)
            t3_mono, t3_wall = time.monotonic(), time.time()
            out.windows[Phase.STEADY_STATE] = PhaseWindow(
                Phase.STEADY_STATE, t2_mono, t3_mono, t2_wall, t3_wall)

            out.peak_memory_bytes = docker.read_memory_peak_bytes(cid)
        except Exception as e:
            out.error = f"{type(e).__name__}: {e}"
        finally:
            if cid is not None:
                docker.stop(cid, timeout_s=15)
        return out


class InfluxDBWorkload(_DatastoreBase):
    def __init__(self):
        super().__init__(DatastoreConfig(
            subject_id="influxdb",
            container_port=8086, host_port=18086,
            extra_env=(
                ("DOCKER_INFLUXDB_INIT_MODE", "setup"),
                ("DOCKER_INFLUXDB_INIT_USERNAME", "greenlab"),
                ("DOCKER_INFLUXDB_INIT_PASSWORD", "greenlab-password"),
                ("DOCKER_INFLUXDB_INIT_ORG", "gl"),
                ("DOCKER_INFLUXDB_INIT_BUCKET", "gl"),
                ("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN", "greenlab-token"),
            ),
        ))

    def _client(self):
        from influxdb_client import InfluxDBClient, Point, WriteOptions
        return InfluxDBClient(
            url=f"http://127.0.0.1:{self.config.host_port}",
            token="greenlab-token", org="gl",
        )

    def wait_ready(self, ctx: TrialContext) -> None:


        import urllib.error, urllib.request
        docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                            timeout_s=ctx.provisioning_timeout_s)
        deadline = time.monotonic() + ctx.provisioning_timeout_s
        last_err: Optional[BaseException] = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.config.host_port}/ping", timeout=2,
                ) as r:
                    if 200 <= r.status < 400:
                        return
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
            time.sleep(0.5)
        raise TimeoutError(f"influxdb HTTP not ready: {last_err}")

    def cold_start(self) -> str:


        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        with self._client() as c:
            w = c.write_api(write_options=SYNCHRONOUS)
            w.write(bucket="gl",
                    record=Point("greenlab").tag("phase", "cold").field("v", 42))
            q = c.query_api().query(
                'from(bucket:"gl") |> range(start:-1h) '
                '|> filter(fn:(r) => r.phase == "cold") |> limit(n:1)')
            payload = "|".join(str(r.get_value()) for tbl in q for r in tbl.records)
            return hashlib.sha256(payload.encode()).hexdigest()

    def steady_state(self, duration_s: float) -> str:


        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        deadline = time.monotonic() + duration_s
        i = 0
        with self._client() as c:
            w = c.write_api(write_options=SYNCHRONOUS)
            while time.monotonic() < deadline:
                w.write(bucket="gl",
                        record=Point("greenlab").tag("phase", "steady").field("v", i))
                i += 1
            w.write(bucket="gl",
                    record=Point("greenlab").tag("phase", "probe").field("v", 99))
            q = c.query_api().query(
                'from(bucket:"gl") |> range(start:-1h) '
                '|> filter(fn:(r) => r.phase == "probe") |> limit(n:1)')
            payload = "|".join(str(r.get_value()) for tbl in q for r in tbl.records)
        return hashlib.sha256(payload.encode()).hexdigest()


class MemcachedWorkload(_DatastoreBase):
    def __init__(self):
        super().__init__(DatastoreConfig(
            subject_id="memcached",
            container_port=11211, host_port=21211,
        ))

    def _client(self):
        from pymemcache.client.base import Client
        return Client(("127.0.0.1", self.config.host_port), connect_timeout=5, timeout=5)

    def wait_ready(self, ctx: TrialContext) -> None:


        from pymemcache.exceptions import MemcacheError
        docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                            timeout_s=ctx.provisioning_timeout_s)
        deadline = time.monotonic() + ctx.provisioning_timeout_s
        last_err: Optional[BaseException] = None
        while time.monotonic() < deadline:
            try:
                self._client().version()
                return
            except (ConnectionError, OSError, MemcacheError) as e:
                last_err = e
                time.sleep(0.5)
        raise TimeoutError(f"memcached not ready: {last_err}")

    def cold_start(self) -> str:
        c = self._client()
        c.set(b"greenlab-cold", b"hello", expire=0)
        v = c.get(b"greenlab-cold")
        return hashlib.sha256(v or b"").hexdigest()

    def steady_state(self, duration_s: float) -> str:


        c = self._client()
        deadline = time.monotonic() + duration_s
        i = 0
        while time.monotonic() < deadline:
            key = f"gl-{i % 1024}".encode()
            c.set(key, str(i).encode(), expire=0)
            c.get(key)
            i += 1
        c.set(b"greenlab-probe", b"probe-value", expire=0)
        v = c.get(b"greenlab-probe")
        return hashlib.sha256(v or b"").hexdigest()


class Neo4jWorkload(_DatastoreBase):
    def __init__(self):
        super().__init__(DatastoreConfig(
            subject_id="neo4j",
            container_port=7687, host_port=27687,
            extra_env=(("NEO4J_AUTH", "neo4j/greenlab-password"),),
        ))

    def _driver(self):
        from neo4j import GraphDatabase
        return GraphDatabase.driver(
            f"bolt://127.0.0.1:{self.config.host_port}",
            auth=("neo4j", "greenlab-password"),
        )

    def wait_ready(self, ctx: TrialContext) -> None:


        from neo4j.exceptions import (
            AuthError, ServiceUnavailable, ClientError,
        )
        docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                            timeout_s=ctx.provisioning_timeout_s)
        deadline = time.monotonic() + ctx.provisioning_timeout_s
        last_err: Optional[BaseException] = None
        while time.monotonic() < deadline:
            try:
                d = self._driver()
                try:
                    d.verify_connectivity()
                    return
                finally:
                    d.close()
            except (ServiceUnavailable, AuthError, ClientError, OSError) as e:
                last_err = e
            time.sleep(1.0)
        raise TimeoutError(f"neo4j bolt not ready: {last_err}")

    def cold_start(self) -> str:
        with self._driver() as d, d.session() as s:
            s.run("CREATE (:N {name:'cold', v:1})").consume()
            rec = s.run("MATCH (n:N {name:'cold'}) RETURN n.v AS v").single()
            return hashlib.sha256(str(rec["v"]).encode()).hexdigest()

    def steady_state(self, duration_s: float) -> str:


        deadline = time.monotonic() + duration_s
        i = 0
        with self._driver() as d, d.session() as s:
            while time.monotonic() < deadline:
                s.run("CREATE (:N {name:$n, v:$v})", n=f"steady-{i}", v=i).consume()
                s.run("MATCH (n:N {name:$n}) RETURN n.v", n=f"steady-{i}").single()
                i += 1
            s.run("CREATE (:N {name:'probe', v:42})").consume()
            rec = s.run("MATCH (n:N {name:'probe'}) RETURN n.v AS v").single()
        return hashlib.sha256(str(rec["v"]).encode()).hexdigest()


class CassandraWorkload(_DatastoreBase):
    def __init__(self):
        super().__init__(DatastoreConfig(
            subject_id="cassandra",
            container_port=9042, host_port=29042,
            extra_env=(("CASSANDRA_CLUSTER_NAME", "greenlab"),),
        ))

    def wait_ready(self, ctx: TrialContext) -> None:
        from cassandra.cluster import Cluster, NoHostAvailable
        docker.wait_for_tcp("127.0.0.1", self.config.host_port,
                            timeout_s=ctx.provisioning_timeout_s)
        deadline = time.monotonic() + ctx.provisioning_timeout_s
        while time.monotonic() < deadline:
            try:
                with Cluster(["127.0.0.1"], port=self.config.host_port).connect() as s:
                    s.execute("SELECT release_version FROM system.local").one()
                    return
            except NoHostAvailable:
                time.sleep(2.0)
        raise TimeoutError("cassandra cluster did not accept client connections")

    def _session(self):
        from cassandra.cluster import Cluster
        cluster = Cluster(["127.0.0.1"], port=self.config.host_port)
        s = cluster.connect()
        s.execute("CREATE KEYSPACE IF NOT EXISTS gl WITH replication = "
                  "{'class':'SimpleStrategy','replication_factor':1}")
        s.set_keyspace("gl")
        s.execute("CREATE TABLE IF NOT EXISTS kv (k text PRIMARY KEY, v int)")
        return s

    def cold_start(self) -> str:
        s = self._session()
        s.execute("INSERT INTO kv (k, v) VALUES (%s, %s)", ("cold", 1))
        row = s.execute("SELECT v FROM kv WHERE k=%s", ("cold",)).one()
        return hashlib.sha256(str(row.v).encode()).hexdigest()

    def steady_state(self, duration_s: float) -> str:


        s = self._session()
        deadline = time.monotonic() + duration_s
        i = 0
        while time.monotonic() < deadline:
            s.execute("INSERT INTO kv (k, v) VALUES (%s, %s)", (f"steady-{i}", i))
            s.execute("SELECT v FROM kv WHERE k=%s", (f"steady-{i}",)).one()
            i += 1
        s.execute("INSERT INTO kv (k, v) VALUES (%s, %s)", ("probe", 42))
        row = s.execute("SELECT v FROM kv WHERE k=%s", ("probe",)).one()
        return hashlib.sha256(str(row.v).encode()).hexdigest()


def make_influxdb() -> InfluxDBWorkload:   return InfluxDBWorkload()
def make_memcached() -> MemcachedWorkload: return MemcachedWorkload()
def make_neo4j() -> Neo4jWorkload:         return Neo4jWorkload()
def make_cassandra() -> CassandraWorkload: return CassandraWorkload()
