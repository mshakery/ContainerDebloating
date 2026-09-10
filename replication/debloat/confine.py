from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from replication.debloat.base import DebloaterError
from replication.runner.base import SubjectSpec
from replication.workloads import datastore, http_service, oneshot

CONFINE_DIR = Path(os.environ.get("CONFINE_DIR", str(Path.home() / "confine"))).expanduser().resolve()
CONFINE_PROFILE_DIR = Path(__file__).resolve().parent / "confine_profiles"
ASSETS_DIR = (Path(__file__).resolve().parents[1] / "workloads" / "assets").resolve()


_TIMEOUT_S = int(os.environ.get("CONFINE_TIMEOUT_S", "1800"))


def _sanitized_name(subject_id: str) -> str:

    return re.sub(r"\W+", "-", subject_id)


def _confine_run_options(spec: SubjectSpec) -> str:

    w = spec.workload_factory()
    args = w._run_args(ASSETS_DIR)
    return " ".join(args)


def _is_oneshot(spec: SubjectSpec) -> bool:
    return isinstance(spec.workload_factory(), oneshot.OneShotScriptWorkload)


def _write_images_json(spec: SubjectSpec, path: Path, options: str, args: str) -> None:
    entry = {
        spec.id: {
            "enable": "true",
            "image-name": spec.id,
            "image-url": spec.image_ref,
            "category": [spec.category],
            "official": True,
            "options": options,
            "args": args,
            "dependencies": {},
            "id": "1",
        }
    }
    path.write_text(json.dumps(entry, indent=2))


def _invoke_confine(spec: SubjectSpec, work: Path, *, allbinaries: bool,
                    options: str, args: str) -> Path | None:

    out_dir = work / "out"
    res_dir = work / "res"
    out_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)
    images_json = work / "images.json"
    _write_images_json(spec, images_json, options, args)

    cmd = [
        "python3", "confine.py",
        "-i", str(images_json),
        "-o", str(out_dir),
        "-r", str(res_dir),
        "-p", "default.seccomp.json",
        "-l", "libc-callgraphs/glibc.callgraph",
        "-m", "libc-callgraphs/musllibc.callgraph",
        "-g", "go.syscalls",
        "--monitoringtool", "execsnoop",
    ]
    if allbinaries:
        cmd.append("--allbinaries")

    log = work / "confine.log"
    with log.open("w") as fh:
        try:
            subprocess.run(cmd, cwd=CONFINE_DIR, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=_TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            pass

    produced = res_dir / f"{_sanitized_name(spec.id)}.seccomp.json"
    return produced if produced.exists() else None


def build_confine_image(spec: SubjectSpec) -> str:

    CONFINE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    work = CONFINE_PROFILE_DIR / f".build-{spec.id}"
    if work.exists():
        shutil.rmtree(work)

    oneshot_subject = _is_oneshot(spec)
    options = _confine_run_options(spec)


    profile = None
    mode = None
    if not oneshot_subject:
        profile = _invoke_confine(spec, work / "dynamic", allbinaries=False,
                                  options=options, args="")
        if profile is not None:
            mode = "dynamic"


    if profile is None:
        keepalive = "sleep 600" if oneshot_subject else ""
        profile = _invoke_confine(spec, work / "static", allbinaries=True,
                                  options=options, args=keepalive)
        if profile is not None:
            mode = "static"

    if profile is None:
        raise DebloaterError(
            f"Confine produced no seccomp profile for {spec.id} "
            f"(dynamic and static --allbinaries both failed; see "
            f"{work}/*/confine.log)."
        )

    dest = CONFINE_PROFILE_DIR / f"{spec.id}.seccomp.json"
    shutil.copyfile(profile, dest)

    (CONFINE_PROFILE_DIR / f"{spec.id}.mode").write_text(mode + "\n")


    shutil.rmtree(work, ignore_errors=True)
    return spec.image_ref


def confine_profile_path(spec: SubjectSpec) -> Path:

    dest = CONFINE_PROFILE_DIR / f"{spec.id}.seccomp.json"
    if not dest.exists():
        build_confine_image(spec)
    if not dest.exists():
        raise DebloaterError(f"Confine profile missing for {spec.id} after build.")
    return dest
