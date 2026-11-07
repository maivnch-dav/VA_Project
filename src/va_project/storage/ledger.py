"""`curated/_loaded.json`: what the history loader has already loaded (idempotent re-runs).

Layout: {source: {key: entry}}, e.g. {"istdaten": {"2025-01": {"complete": true, ...}}}.
Every `put` re-reads the file and rewrites it atomically, so an interrupted run never leaves it
half-written and two loaders (different sources) do not drop each other's entries.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data = self._read()

    def _read(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def get(self, source: str, key: str) -> dict[str, Any] | None:
        return self._data.get(source, {}).get(key)

    def is_complete(self, source: str, key: str) -> bool:
        entry = self.get(source, key)
        return bool(entry and entry.get("complete"))

    def keys(self, source: str) -> list[str]:
        return sorted(self._data.get(source, {}))

    def put(self, source: str, key: str, entry: dict[str, Any]) -> None:
        stamped = {**entry, "loaded_at": datetime.now(UTC).isoformat(timespec="seconds")}
        self._data = self._read()  # merge with entries another loader wrote meanwhile
        self._data.setdefault(source, {})[key] = stamped
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
