from __future__ import annotations

from pathlib import Path
from typing import Optional

from replication.debloat.base import DebloaterError, ImageCache
from replication.runner.base import SubjectSpec


_CACHE = ImageCache(Path(__file__).resolve().parents[1] / "debloat" / "cache.json")


_FAIL_PREFIX = "__BUILD_FAILED__:"


def resolve_image(spec: SubjectSpec, debloater: str) -> str:
    if debloater == "baseline":
        return spec.image_ref

    cached = _CACHE.get(spec.id, debloater)
    if cached is not None:
        if cached.startswith(_FAIL_PREFIX):
            raise DebloaterError(
                f"{spec.id}/{debloater}: build previously failed (cached): "
                f"{cached[len(_FAIL_PREFIX):]}"
            )
        return cached

    try:
        if debloater == "slim":
            from replication.debloat.slim import build_slim_image
            result = build_slim_image(spec)
        elif debloater == "blafs":
            from replication.debloat.blafs import build_blafs_image
            result = build_blafs_image(spec)
        elif debloater == "confine":
            from replication.debloat.confine import build_confine_image
            result = build_confine_image(spec)
        else:
            raise DebloaterError(f"unknown debloater: {debloater}")
    except DebloaterError as e:
        _CACHE.put(spec.id, debloater, _FAIL_PREFIX + str(e).replace("\n", " ")[:300])
        raise

    _CACHE.put(spec.id, debloater, result)
    return result


def resolve_seccomp(spec: SubjectSpec, debloater: str) -> Optional[Path]:

    if debloater != "confine":
        return None
    from replication.debloat.confine import confine_profile_path
    return confine_profile_path(spec)
