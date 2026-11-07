"""REST API /api/v1 — see docs/api-spec.yaml."""

from __future__ import annotations

from flask import Blueprint, Response, request
from pydantic import TypeAdapter, ValidationError

from va_project import __version__
from va_project.api.errors import problem_response
from va_project.api.schemas import (
    CompletenessCellOut,
    DataQualityOut,
    DataQualityQuery,
    GapOut,
    HealthOut,
    QualitySourceOut,
    SourceHealthOut,
    StopOut,
    StopsPage,
    StopsQuery,
    UnlinkedStationOut,
    WeatherStationOut,
)
from va_project.config import Settings
from va_project.services.health import get_health
from va_project.services.quality import RangeError, get_data_quality
from va_project.services.stops import DataNotReadyError, list_stops, list_weather_stations

_WEATHER_STATIONS = TypeAdapter(list[WeatherStationOut])


def _json(body: str) -> Response:
    return Response(body, mimetype="application/json")


def _bad_request(e: ValidationError) -> Response:
    detail = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
    return problem_response(400, "Bad Request", detail)


def create_api(settings: Settings) -> Blueprint:
    api = Blueprint("api_v1", __name__, url_prefix="/api/v1")

    @api.get("/health")
    def health() -> Response:
        h = get_health(settings)
        out = HealthOut(
            status=h.status,
            version=__version__,
            sources=[SourceHealthOut.model_validate(s, from_attributes=True) for s in h.sources],
        )
        return _json(out.model_dump_json())

    @api.get("/stops")
    def stops() -> Response:
        try:
            q = StopsQuery.model_validate(request.args.to_dict())
        except ValidationError as e:
            return _bad_request(e)
        try:
            total, items = list_stops(
                settings.curated_dir,
                kanton=q.kanton,
                region=q.region,
                bbox=q.bbox_tuple(),
                linked_only=q.linked_only,
                limit=q.limit,
                offset=q.offset,
            )
        except DataNotReadyError as e:
            return problem_response(503, "Service Unavailable", str(e))
        page = StopsPage(
            total=total,
            limit=q.limit,
            offset=q.offset,
            items=[StopOut.model_validate(i) for i in items],
        )
        return _json(page.model_dump_json())

    @api.get("/weather/stations")
    def weather_stations() -> Response:
        try:
            items = list_weather_stations(settings.curated_dir)
        except DataNotReadyError as e:
            return problem_response(503, "Service Unavailable", str(e))
        return _json(_WEATHER_STATIONS.dump_json(_WEATHER_STATIONS.validate_python(items)).decode())

    @api.get("/data-quality")
    def data_quality() -> Response:
        try:
            q = DataQualityQuery.model_validate(request.args.to_dict())
        except ValidationError as e:
            return _bad_request(e)
        try:
            dq = get_data_quality(settings.curated_dir, q.date_from, q.date_to)
        except RangeError as e:
            return problem_response(400, "Bad Request", str(e))
        except DataNotReadyError as e:
            return problem_response(503, "Service Unavailable", str(e))
        out = DataQualityOut(
            date_from=dq.date_from,
            date_to=dq.date_to,
            sources=[QualitySourceOut(id=k, label=v) for k, v in dq.sources.items()],
            completeness=[
                CompletenessCellOut(
                    source=c.source,
                    day=c.day,
                    expected=c.expected,
                    received=c.received,
                    ratio=c.ratio,
                    note=c.note,
                )
                for c in dq.completeness
            ],
            gaps=[GapOut.model_validate(g, from_attributes=True) for g in dq.gaps],
            kpis=dq.kpis,
            link_rate=dq.kpis.get("link_rate"),
            unlinked_stops=[UnlinkedStationOut.model_validate(u) for u in dq.unlinked],
        )
        return _json(out.model_dump_json(by_alias=True))

    return api
