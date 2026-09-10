from __future__ import annotations

import os
import socket
import sys
import time
from multiprocessing import Process, Value


def _worker(port: int, deadline: float, cpuset: list[int], counter):
    try:
        os.sched_setaffinity(0, cpuset)
    except Exception:
        pass
    n = 0
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        f = s.makefile("rwb")
        i = 0
        while time.monotonic() < deadline:
            key = b"gl-%d" % (i % 4096)
            val = b"%d" % i
            f.write(b"set %s 0 0 %d\r\n%s\r\n" % (key, len(val), val))
            f.flush()
            f.readline()
            f.write(b"get %s\r\n" % key)
            f.flush()
            line = f.readline()
            if line.startswith(b"VALUE"):
                f.readline()
                f.readline()
            n += 1
            i += 1
    except Exception:
        pass
    with counter.get_lock():
        counter.value += n


def memcached_load(port: int, duration_s: float, procs: int = 16,
                   cpuset: list[int] | None = None) -> int:
    if cpuset is None:
        cpuset = list(range(8, 16))
    deadline = time.monotonic() + duration_s
    counter = Value("q", 0)
    workers = [Process(target=_worker, args=(port, deadline, cpuset, counter))
               for _ in range(procs)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return counter.value


if __name__ == "__main__":
    port = int(sys.argv[1])
    dur = float(sys.argv[2])
    procs = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    print(memcached_load(port, dur, procs))
