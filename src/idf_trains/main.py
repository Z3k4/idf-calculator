from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response

from .cache import create_cache
from .config import settings
from .models import DeparturesResponse, Station, StationMatch
from .prim import PrimClient, PrimConfigError, PrimError, parse_departures
from .stations import StationRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = create_cache(settings.redis_url, settings.cache_max_entries)
    try:
        async with httpx.AsyncClient(timeout=settings.prim_timeout) as http:
            app.state.repo = StationRepository.from_file(settings.stations_file)
            app.state.prim = PrimClient(
                http,
                settings.prim_api_key,
                settings.prim_url,
                cache=cache,
                cache_ttl=settings.cache_ttl,
                stale_ttl=settings.cache_stale_ttl,
            )
            yield
    finally:
        await cache.close()


app = FastAPI(
    title="IDF Trains",
    description="Prochains trains (RER, Transilien, TER) des gares d'Île-de-France, "
    "à partir de l'API temps réel PRIM d'Île-de-France Mobilités.",
    version="0.1.0",
    lifespan=lifespan,
)


def get_repo(request: Request) -> StationRepository:
    return request.app.state.repo


def get_prim(request: Request) -> PrimClient:
    return request.app.state.prim


def get_station_or_404(station_id: str, repo: StationRepository = Depends(get_repo)) -> Station:
    station = repo.get(station_id)
    if station is None:
        raise HTTPException(404, f"Gare inconnue : {station_id}")
    return station


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/stations", response_model=list[Station], summary="Rechercher une gare")
async def search_stations(
    q: str = Query("", description="Nom de la gare ou de la commune (accents facultatifs)"),
    line: str | None = Query(None, description="Filtrer par ligne, ex. A, B, H, TER"),
    limit: int = Query(20, ge=1, le=500),
    repo: StationRepository = Depends(get_repo),
):
    return repo.search(q, line=line, limit=limit)


# Déclaré avant /stations/{station_id} pour que « search » ne soit pas pris pour un identifiant
@app.get(
    "/stations/search",
    response_model=list[StationMatch],
    summary="Chercher une gare par nom (recherche approximative)",
)
async def search_stations_by_name(
    name: str = Query(..., min_length=1, description="Nom de la gare, fautes de frappe tolérées"),
    limit: int = Query(10, ge=1, le=50),
    min_score: float = Query(0.65, ge=0, le=1, description="Score minimum de pertinence (0 à 1)"),
    repo: StationRepository = Depends(get_repo),
):
    return [
        StationMatch(score=score, station=station)
        for station, score in repo.search_by_name(name, limit=limit, min_score=min_score)
    ]


@app.get("/stations/{station_id}", response_model=Station, summary="Détail d'une gare")
async def get_station(station: Station = Depends(get_station_or_404)):
    return station


@app.get(
    "/stations/{station_id}/departures",
    response_model=DeparturesResponse,
    summary="Prochains départs d'une gare",
)
async def get_departures(
    response: Response,
    station: Station = Depends(get_station_or_404),
    line: str | None = Query(None, description="Filtrer par ligne, ex. A"),
    limit: int = Query(10, ge=1, le=50),
    repo: StationRepository = Depends(get_repo),
    prim: PrimClient = Depends(get_prim),
):
    try:
        result = await prim.stop_monitoring(station.id)
    except PrimConfigError as exc:
        raise HTTPException(503, str(exc)) from exc
    except PrimError as exc:
        raise HTTPException(502, str(exc)) from exc

    # Les minutes restantes sont recalculées à chaque requête, même depuis le cache
    departures = parse_departures(result.data, repo, now=datetime.now(timezone.utc))
    if line:
        departures = [d for d in departures if d.line.name.upper() == line.upper()]

    age = result.age_seconds
    response.headers["X-Cache"] = result.cache
    response.headers["Age"] = str(age)
    max_age = 0 if result.cache == "STALE" else max(0, int(prim.cache_ttl) - age)
    response.headers["Cache-Control"] = f"public, max-age={max_age}"

    return DeparturesResponse(
        station=station,
        updated_at=result.fetched_at,
        stale=result.cache == "STALE",
        departures=departures[:limit],
    )
