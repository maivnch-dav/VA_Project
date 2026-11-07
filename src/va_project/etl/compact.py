"""Live compaction (US-02b): raw GTFS-RT snapshots → `fact_stop_delay` → live aggregates.

Every snapshot repeats the same trips, so only the **last observation** per
`(start_date, trip_id, stop_sequence)` is kept (D4). A trip's status comes from its own latest
snapshot: a trip cancelled after its stops were seen turns those stops into cancellations,
never delays (BR2). Compaction is incremental and merging: new raw files (tracked in
`_loaded.json` under `live`) are combined with the existing fact partitions of the service dates
they touch, so re-running is idempotent and raw files can be deleted afterwards.

Station keys follow the history (7-digit BPUIC, `etl.link.live_station_keys`). `hour_local` is
the scheduled hour where the feed gives an absolute time (`time − delay`), otherwise the hour of
the trip's `start_time` — an approximation (97 % of stop updates carry only a delay). Stops the
feed leaves out (sparse updates) are not reconstructed without GTFS static.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import groupby
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from va_project.config import LOCAL_TZ, Settings
from va_project.etl.aggregate import aggregate_month
from va_project.etl.link import live_station_keys
from va_project.storage.ledger import Ledger

log = logging.getLogger(__name__)

LEDGER_SOURCE = "live"
TRIP_UPDATES = "gtfs_rt/trip_updates"
WEATHER = "meteo/smn"
MEMORY_LIMIT = "1GB"  # DuckDB spills to data/tmp/duckdb beyond this (runs next to the collector)

# Raw columns and their type, for snapshots written before a column existed (US-01).
_RAW_COLUMNS = {
    "feed_ts": "TIMESTAMPTZ", "trip_id": "VARCHAR", "route_id": "VARCHAR",
    "start_date": "VARCHAR", "start_time": "VARCHAR", "trip_status": "VARCHAR",
    "stop_sequence": "INTEGER", "stop_id": "VARCHAR", "stop_status": "VARCHAR",
    "arr_delay_s": "INTEGER", "dep_delay_s": "INTEGER", "arr_time": "TIMESTAMPTZ",
    "dep_time": "TIMESTAMPTZ", "ingested_at": "TIMESTAMPTZ",
}  # fmt: skip

# One observation per row: raw snapshots, and existing fact rows so that merges are idempotent.
_RAW_OBS_SQL = """
SELECT
    coalesce(try_strptime(start_date, '%Y%m%d')::DATE, timezone($tz, feed_ts)::DATE)
        AS service_date,
    trip_id, route_id, start_time, stop_id, stop_sequence, trip_status, stop_status,
    arr_delay_s, dep_delay_s, arr_time, dep_time,
    feed_ts AS observed_at, feed_ts AS trip_observed_at, ingested_at
FROM raw_typed
"""
_FACT_OBS_SQL = """
SELECT service_date, trip_id, route_id, start_time, stop_id, stop_sequence, trip_status,
       stop_status, arr_delay_s, dep_delay_s, arr_time, dep_time, observed_at,
       trip_observed_at, ingested_at
FROM existing
"""

_COMPACT_SQL = """
WITH trips AS (
    SELECT service_date, trip_id,
           arg_max(trip_status, trip_observed_at) AS trip_status,
           max(trip_observed_at) AS trip_observed_at
    FROM obs
    GROUP BY service_date, trip_id
), last AS (
    SELECT * EXCLUDE (trip_status, trip_observed_at)
    FROM obs
    WHERE stop_id IS NOT NULL
    QUALIFY row_number() OVER (
        PARTITION BY service_date, trip_id, stop_sequence,
                     CASE WHEN stop_sequence IS NULL THEN stop_id END
        ORDER BY observed_at DESC, ingested_at DESC
    ) = 1
), ev AS (
    SELECT l.*, t.trip_status, t.trip_observed_at,
           CASE WHEN t.trip_status IN ('CANCELED', 'DELETED') THEN 'CANCELED'
                WHEN l.stop_status = 'SKIPPED' THEN 'SKIPPED'
                ELSE 'SCHEDULED' END AS status,
           l.arr_time - to_seconds(l.arr_delay_s) AS sched_arr,
           l.dep_time - to_seconds(l.dep_delay_s) AS sched_dep
    FROM last AS l JOIN trips AS t USING (service_date, trip_id)
)
SELECT
    ev.service_date, ev.trip_id, ev.route_id, ev.start_time, ev.stop_id, ev.stop_sequence,
    s.station_key, s.station_name, coalesce(s.foreign_stop, false) AS foreign_stop,
    ev.trip_status, ev.stop_status, ev.status,
    ev.arr_delay_s, ev.dep_delay_s,
    CASE WHEN ev.status = 'SCHEDULED' AND ev.stop_status IS DISTINCT FROM 'NO_DATA'
         THEN coalesce(ev.arr_delay_s, ev.dep_delay_s) END AS delay_s,
    ev.arr_time, ev.dep_time, ev.sched_arr,
    coalesce(hour(timezone($tz, coalesce(ev.sched_arr, ev.sched_dep))),
             try_cast(split_part(ev.start_time, ':', 1) AS INTEGER) % 24)::TINYINT AS hour_local,
    ev.observed_at, ev.trip_observed_at, ev.ingested_at
FROM ev LEFT JOIN stations AS s ON s.stop_id = ev.stop_id
ORDER BY ev.service_date, s.station_key, ev.trip_id, ev.stop_sequence
"""


@dataclass
class CompactResult:
    files: int = 0  # raw trip-update snapshots read
    observations: int = 0  # raw rows read
    stop_events: int = 0  # fact rows in the service dates written
    dates: list[str] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    weather_rows: int = 0
    raw_deleted: list[str] = field(default_factory=list)


def fact_path(curated_dir: Path, day: str) -> Path:
    return curated_dir / "fact_stop_delay" / f"date={day}" / "part.parquet"


def _stamp(path: Path) -> str:
    """`HHMMSS` of a snapshot file (`101500.parquet`, `smn_101500.parquet`, `chu_101500…`)."""
    return path.stem.rsplit("_", 1)[-1]


def _day(path: Path) -> str:
    return path.parent.name.removeprefix("date=")


def _pending(root: Path, ledger: Ledger, feed: str) -> list[Path]:
    """Raw files newer than what the ledger says is compacted, oldest first."""
    files: list[Path] = []
    for folder in sorted(root.glob("date=*")):
        day = folder.name.removeprefix("date=")
        last = (ledger.get(LEDGER_SOURCE, f"{feed}:{day}") or {}).get("last", "")
        files += [p for p in sorted(folder.glob("*.parquet"), key=_stamp) if _stamp(p) > last]
    return files


def _mark(ledger: Ledger, feed: str, files: list[Path]) -> None:
    for day, group in groupby(files, key=_day):
        ledger.put(LEDGER_SOURCE, f"{feed}:{day}",
                   {"complete": False, "last": max(_stamp(p) for p in group)})  # fmt: skip


def _write(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(path)


def _compact_batch(
    con: duckdb.DuckDBPyConnection,
    files: list[Path],
    curated_dir: Path,
    service_points: pd.DataFrame | None,
) -> tuple[int, dict[str, int]]:
    """Merge one batch of snapshots into the fact; returns (raw rows, {date: fact rows})."""
    raw = con.read_parquet([str(p) for p in files], union_by_name=True, hive_partitioning=False)
    raw.create_view("raw_in", replace=True)
    have = set(raw.columns)
    cols = ", ".join(
        f"{c}::{t} AS {c}" if c in have else f"NULL::{t} AS {c}" for c, t in _RAW_COLUMNS.items()
    )  # names and types come from the constant above
    con.execute(f"CREATE OR REPLACE TEMP VIEW raw_typed AS SELECT {cols} FROM raw_in")  # noqa: S608
    # Observations stay inside DuckDB (can spill to disk); only the compacted result leaves it.
    con.execute("CREATE OR REPLACE TEMP TABLE new_obs AS " + _RAW_OBS_SQL, {"tz": LOCAL_TZ})
    n_raw = con.execute("SELECT count(*) FROM new_obs").fetchone()
    found = con.execute("SELECT DISTINCT service_date FROM new_obs WHERE service_date IS NOT NULL")
    days = sorted(d.isoformat() for (d,) in found.fetchall())

    existing = [p for p in (fact_path(curated_dir, d) for d in days) if p.exists()]
    union = ""
    if existing:
        con.read_parquet([str(p) for p in existing], hive_partitioning=False).create_view(
            "existing", replace=True
        )
        union = " UNION ALL BY NAME " + _FACT_OBS_SQL
    # only constant SQL fragments are joined here
    con.execute("CREATE OR REPLACE TEMP VIEW obs AS SELECT * FROM new_obs" + union)  # noqa: S608

    stop_ids = [s for (s,) in con.execute("SELECT DISTINCT stop_id FROM obs").fetchall() if s]
    con.register("stations", live_station_keys(stop_ids, service_points))
    result = con.execute(_COMPACT_SQL, {"tz": LOCAL_TZ}).to_arrow_table()
    con.unregister("stations")
    con.execute("DROP TABLE new_obs")

    written = {}
    for day in days:
        part = result.filter(pc.equal(result["service_date"], pa.scalar(date.fromisoformat(day))))
        if part.num_rows:
            _write(part, fact_path(curated_dir, day))
            written[day] = part.num_rows
    return int(n_raw[0]) if n_raw else 0, written


def _merge_weather(settings: Settings, ledger: Ledger) -> int:
    """Live 10-minute weather → `fact_weather_10min` (newest observation per station and ts)."""
    files = _pending(settings.raw_dir / WEATHER, ledger, "meteo")
    if not files:
        return 0
    new = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    if "ingested_at" not in new.columns:  # US-01 snapshots
        new["ingested_at"] = pd.NaT
    new["ingested_at"] = pd.to_datetime(new["ingested_at"], utc=True)
    for (station, year), grp in new.groupby([new["station"], new["ts"].dt.year]):
        path = (settings.curated_dir / "fact_weather_10min" / f"station={station}"
                / f"year={year}" / "part.parquet")  # fmt: skip
        rows = grp.drop(columns="station")
        if path.exists():
            rows = pd.concat([pd.read_parquet(path), rows], ignore_index=True)
        rows = (
            rows.sort_values(["ts", "ingested_at"], na_position="first")
            .drop_duplicates("ts", keep="last")
            .reset_index(drop=True)
        )
        _write(pa.Table.from_pandas(rows, preserve_index=False), path)
    _mark(ledger, "meteo", files)
    return len(new)


def cleanup_raw(settings: Settings, ledger: Ledger, today: date | None = None) -> list[str]:
    """Delete raw date folders older than LIVE_RAW_KEEP_DAYS whose files are all compacted.

    Alerts are kept: they are small and not compacted yet (fact_alert, US-05)."""
    today = today or datetime.now(UTC).date()
    cutoff = today - timedelta(days=settings.live_raw_keep_days)
    deleted = []
    for feed, sub in (("trip_updates", TRIP_UPDATES), ("meteo", WEATHER)):
        for folder in sorted((settings.raw_dir / sub).glob("date=*")):
            try:
                day = date.fromisoformat(folder.name.removeprefix("date="))
            except ValueError:
                continue
            if day >= cutoff:
                continue
            last = (ledger.get(LEDGER_SOURCE, f"{feed}:{day}") or {}).get("last", "")
            if all(_stamp(p) <= last for p in folder.glob("*.parquet")):
                shutil.rmtree(folder)
                deleted.append(f"{feed}/{folder.name}")
    if deleted:
        log.info("deleted raw folders: %s", ", ".join(deleted))
    return deleted


def compact_live(
    settings: Settings,
    ledger: Ledger,
    service_points: pd.DataFrame | None,
    *,
    today: date | None = None,
    batch_files: int = 30,
    cleanup: bool = True,
) -> CompactResult:
    """Compact new raw snapshots, rebuild `source=live` aggregates of the months touched,
    merge live weather, then delete old raw folders (only what has been compacted)."""
    res = CompactResult()
    files = _pending(settings.raw_dir / TRIP_UPDATES, ledger, "trip_updates")
    events: dict[str, int] = {}
    if files:
        spill = settings.tmp_dir / "duckdb"
        spill.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        try:
            con.execute("SET TimeZone = 'UTC'")
            con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
            con.execute(f"SET temp_directory = '{str(spill).replace("'", "''")}'")
            for i in range(0, len(files), batch_files):
                batch = files[i : i + batch_files]
                n_raw, written = _compact_batch(con, batch, settings.curated_dir, service_points)
                _mark(ledger, "trip_updates", batch)  # only after the fact files are written
                res.files += len(batch)
                res.observations += n_raw
                events.update(written)
        finally:
            con.close()

    res.dates = sorted(events)
    res.stop_events = sum(events.values())
    res.months = sorted({d[:7] for d in res.dates})
    for month in res.months:
        month_files = sorted(
            (settings.curated_dir / "fact_stop_delay").glob(f"date={month}-*/*.parquet")
        )
        aggregate_month(month_files, settings.curated_dir, source="live", month=month)

    res.weather_rows = _merge_weather(settings, ledger)
    if cleanup:
        res.raw_deleted = cleanup_raw(settings, ledger, today)
    return res
