from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

REG = os.environ.get("REGISTRY", "127.0.0.1:5000")
ROOT = Path(__file__).resolve().parents[3]
OV = Path(os.environ.get("OV_DIR", str(ROOT / "replication" / "stacks" / "overrides")))


PREFIXES = {
    "codewisdom-ts-": "train-ticket",
    "weaveworksdemos-": "sock-shop",
    "shopizerecomm-": "shopizer",
    "deathstarbench-": "hotel-reservation",
    "hotel_reserv": "hotel-reservation",
}

SUFFIX = {"slim": ".slim", "blafs": "-baffs"}
TREATMENTS = ["baseline", "slim", "blafs"]


def catalog() -> list[str]:
    with urllib.request.urlopen(f"http://{REG}/v2/_catalog?n=1000", timeout=30) as r:
        return json.load(r)["repositories"]


def stack_of(repo: str) -> str | None:
    if not repo.startswith("mbpull/"):
        return None
    name = repo[len("mbpull/"):]
    for pre, stack in PREFIXES.items():
        if name.startswith(pre):
            return stack
    return None


def is_baseline(repo: str) -> bool:
    return not repo.endswith((".slim", "-baffs"))


def variant(base: str, treatment: str, repos: set[str]) -> str | None:

    if treatment == "baseline":
        return base if base in repos else None
    suf = SUFFIX[treatment]
    for cand in (base + suf, base + "-latest" + suf):
        if cand in repos:
            return cand
    return None


def main() -> int:
    repos = set(catalog())
    services: dict[str, set[str]] = {}
    for r in repos:
        s = stack_of(r)
        if s and is_baseline(r):
            services.setdefault(s, set()).add(r)

    OV.mkdir(parents=True, exist_ok=True)
    rc = 0
    for stack in sorted(services):
        bases = sorted(services[stack])
        for treatment in TREATMENTS:
            lines, fallbacks = ["services:"], 0
            for i, b in enumerate(bases):
                want = variant(b, treatment, repos)
                if want is None:
                    want, fallbacks = b, fallbacks + 1
                lines.append(f"  svc{i:03d}:")
                lines.append(f"    image: {REG}/{want}:latest")
            out = OV / f"{stack}.{treatment}.pull.yml"
            out.write_text("\n".join(lines) + "\n")
            note = f" ({fallbacks} fell back to baseline)" if fallbacks else ""
            print(f"{out.name:42s} {len(bases):3d} images{note}")


    for f in sorted(OV.glob("*.pull.yml")):
        for line in f.read_text().splitlines():
            if "image:" in line:
                repo = line.split("image:")[1].strip().split(":latest")[0]
                repo = repo[len(REG) + 1:]
                if repo not in repos:
                    print(f"  !! {f.name}: {repo} not in registry")
                    rc = 1
    print("manifest verification:", "FAILED" if rc else "all references resolve")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
