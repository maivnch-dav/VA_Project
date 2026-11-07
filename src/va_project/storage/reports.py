"""Run reports the collectors write next to the curated data (`curated/live_runs/run=….json`)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def load_live_runs(curated_dir: Path) -> list[dict[str, Any]]:
    """All live-collector run reports, oldest first; unreadable files are skipped (logged)."""
    runs = []
    for path in sorted((curated_dir / "live_runs").glob("run=*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("skipping unreadable live run report %s: %s", path.name, e)
            continue
        if not isinstance(report, dict) or not report.get("started_at"):
            log.warning("skipping live run report without start time: %s", path.name)
            continue
        runs.append(report)
    return sorted(runs, key=lambda r: str(r["started_at"]))
