from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional


class DebloaterError(RuntimeError):
    pass


class ImageCache:


    def __init__(self, store_path: Path):
        self.store_path = store_path
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        if store_path.exists():
            self._data = json.loads(store_path.read_text() or "{}")

    @staticmethod
    def _key(subject_id: str, debloater: str) -> str:
        return f"{subject_id}::{debloater}"

    def get(self, subject_id: str, debloater: str) -> Optional[str]:
        return self._data.get(self._key(subject_id, debloater))

    def put(self, subject_id: str, debloater: str, image_ref: str) -> None:
        with self._lock:
            self._data[self._key(subject_id, debloater)] = image_ref
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
            tmp.replace(self.store_path)
