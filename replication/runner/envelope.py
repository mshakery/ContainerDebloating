from __future__ import annotations

import os

SUT_CPUSET: str = os.environ.get("MB_ENV_SUT_CPUSET", "0-7")     
SUT_MEMS: str = os.environ.get("MB_ENV_SUT_MEMS", "0")           
SUT_CPUS: float = float(os.environ.get("MB_ENV_SUT_CPUS", "8"))  
SUT_MEMORY_MB: int = int(os.environ.get("MB_ENV_SUT_MEMORY_MB", str(32 * 1024)))  

LOADGEN_CPUSET: str = os.environ.get("MB_ENV_LOADGEN_CPUSET", "8-15")  


RAPL_SUT_PKG: int = int(os.environ.get("MB_ENV_RAPL_SUT_PKG", "0"))
RAPL_PKGS: tuple[int, ...] = (0, 1)


def summary() -> str:
    return (f"envelope: SUT cpuset={SUT_CPUSET} mems={SUT_MEMS} cpus={SUT_CPUS} "
            f"mem={SUT_MEMORY_MB}MB | loadgen cpuset={LOADGEN_CPUSET} | "
            f"RAPL SUT pkg={RAPL_SUT_PKG}")
