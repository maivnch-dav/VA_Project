"""GTFS-RT (opentransportdata.swiss): Trip Updates and Service Alerts, Protobuf format."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import requests
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as pb
from pydantic import SecretStr

from va_project.collectors.http import fetch

TRIP_COLUMNS = [
    "feed_ts", "trip_id", "route_id", "start_date", "start_time", "trip_status", "stop_sequence",
    "stop_id", "stop_status", "arr_delay_s", "dep_delay_s", "delay_s", "arr_time", "dep_time",
    "ingested_at",
]  # fmt: skip
ALERT_COLUMNS = [
    "feed_ts", "alert_id", "active_from", "active_to", "cause", "effect", "header",
    "stop_ids", "route_ids", "ingested_at",
]  # fmt: skip

_TRIP_REL = pb.TripDescriptor.ScheduleRelationship
_STOP_REL = pb.TripUpdate.StopTimeUpdate.ScheduleRelationship
_NOT_A_DELAY_TRIP = {"CANCELED", "DELETED"}
_NOT_A_DELAY_STOP = {"SKIPPED", "NO_DATA"}


def fetch_feed(
    session: requests.Session, url: str, api_key: SecretStr, source: str = "", retries: int = 3
) -> bytes:
    resp = fetch(
        session,
        url,
        source=source or url,
        headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
        retries=retries,
    )
    return resp.content


def parse_feed(raw: bytes) -> pb.FeedMessage:
    feed = pb.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except DecodeError as e:
        raise ValueError(f"Response is not a GTFS-RT Protobuf message: {e}") from e
    return feed


def _ts(seconds: int) -> pd.Timestamp:
    return pd.Timestamp(seconds, unit="s", tz="UTC")


def _nullable_ints(values: list[int | None]) -> pd.Series:
    return pd.Series(pd.array(values, dtype="Int32"))


def _event(u: pb.TripUpdate.StopTimeUpdate, kind: str) -> tuple[int | None, int | None]:
    """(delay, absolute time) of the arrival or departure; None where the feed leaves it out."""
    if not u.HasField(kind):
        return None, None
    ev = getattr(u, kind)
    return (ev.delay if ev.HasField("delay") else None), (ev.time if ev.HasField("time") else None)


def trip_updates_frame(
    feed: pb.FeedMessage, ingested_at: datetime, include_bare_trips: bool = False
) -> pd.DataFrame:
    """One row per stop_time_update. `delay_s` = arrival delay, else departure delay;
    NULL for skipped stops and cancelled trips (BR2: those are not delays).

    `include_bare_trips` adds one row (no stop) per trip without stop updates, so that a trip
    cancelled after its stops were seen still reaches compaction."""
    rows: list[dict[str, object]] = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip = {
            "trip_id": tu.trip.trip_id,
            "route_id": tu.trip.route_id or None,
            "start_date": tu.trip.start_date or None,
            "start_time": tu.trip.start_time or None,
            "trip_status": _TRIP_REL.Name(tu.trip.schedule_relationship),
        }
        if include_bare_trips and not tu.stop_time_update:
            rows.append({**trip, "stop_sequence": None, "stop_id": None, "stop_status": None})
        for u in tu.stop_time_update:
            stop_status = _STOP_REL.Name(u.schedule_relationship)
            arr, arr_time = _event(u, "arrival")
            dep, dep_time = _event(u, "departure")
            is_delay = (
                trip["trip_status"] not in _NOT_A_DELAY_TRIP
                and stop_status not in _NOT_A_DELAY_STOP
            )
            rows.append({
                **trip,
                "stop_sequence": u.stop_sequence if u.HasField("stop_sequence") else None,
                "stop_id": u.stop_id,
                "stop_status": stop_status,
                "arr_delay_s": arr,
                "dep_delay_s": dep,
                "delay_s": (arr if arr is not None else dep) if is_delay else None,
                "arr_time": arr_time,
                "dep_time": dep_time,
            })  # fmt: skip

    df = pd.DataFrame(rows, columns=TRIP_COLUMNS)
    for col in ("arr_delay_s", "dep_delay_s", "delay_s", "stop_sequence"):
        df[col] = _nullable_ints(df[col].tolist())
    for col in ("arr_time", "dep_time"):
        df[col] = pd.to_datetime(df[col].astype("Float64"), unit="s", utc=True)
    df["feed_ts"] = _ts(feed.header.timestamp)
    df["ingested_at"] = pd.Timestamp(ingested_at).tz_convert(UTC)
    return df[TRIP_COLUMNS]


def _translation(ts: pb.TranslatedString, prefer: str = "de") -> str | None:
    texts = {t.language: t.text for t in ts.translation}
    return texts.get(prefer) or next(iter(texts.values()), None)


def alerts_frame(feed: pb.FeedMessage, ingested_at: datetime) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ent in feed.entity:
        if not ent.HasField("alert"):
            continue
        a = ent.alert
        starts = [p.start for p in a.active_period if p.start]
        ends = [p.end for p in a.active_period if p.end]
        rows.append({
            "alert_id": ent.id,
            "active_from": _ts(min(starts)) if starts else pd.NaT,
            "active_to": _ts(max(ends)) if ends else pd.NaT,
            "cause": pb.Alert.Cause.Name(a.cause),
            "effect": pb.Alert.Effect.Name(a.effect),
            "header": _translation(a.header_text),
            "stop_ids": [e.stop_id for e in a.informed_entity if e.stop_id],
            "route_ids": [e.route_id for e in a.informed_entity if e.route_id],
        })  # fmt: skip
    df = pd.DataFrame(rows, columns=ALERT_COLUMNS)
    df["feed_ts"] = _ts(feed.header.timestamp)
    df["ingested_at"] = pd.Timestamp(ingested_at).tz_convert(UTC)
    return df[ALERT_COLUMNS]
