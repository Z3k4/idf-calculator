import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from .cache import create_cache
from .config import settings
from .journeys import common_lines, find_direct_trains
from .models import (
    DeparturesResponse,
    ItinerariesResponse,
    JourneyNextResponse,
    Place,
    SavedJourney,
    SavedJourneyCreate,
    SavedJourneyUpdate,
    Station,
    StationMatch,
)
from .prim import (
    PrimClient,
    PrimConfigError,
    PrimError,
    StopMonitoring,
    parse_departures,
    parse_visits,
)
from .navitia import PLACE_ID, NavitiaClient, NavitiaError, NoSolution
from .stations import StationRepository
from .storage import DuplicateJourneyError, JourneyRow, JourneyStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = create_cache(settings.redis_url, settings.cache_max_entries)
    try:
        async with httpx.AsyncClient(timeout=settings.prim_timeout) as http:
            app.state.repo = StationRepository.from_file(settings.stations_file)
            app.state.store = JourneyStore(settings.db_path)
            app.state.prim = PrimClient(
                http,
                settings.prim_api_key,
                settings.prim_url,
                cache=cache,
                cache_ttl=settings.cache_ttl,
                stale_ttl=settings.cache_stale_ttl,
            )
            app.state.navitia = NavitiaClient(
                http,
                settings.prim_api_key,
                settings.navitia_url,
                cache=cache,
                places_ttl=settings.places_cache_ttl,
                journeys_ttl=settings.itineraries_cache_ttl,
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


def get_store(request: Request) -> JourneyStore:
    return request.app.state.store


def get_navitia(request: Request) -> NavitiaClient:
    return request.app.state.navitia


async def fetch_stop(prim: PrimClient, station_id: str) -> StopMonitoring:
    """Appel PRIM avec conversion des erreurs en réponses HTTP."""
    try:
        return await prim.stop_monitoring(station_id)
    except PrimConfigError as exc:
        raise HTTPException(503, str(exc)) from exc
    except PrimError as exc:
        raise HTTPException(502, str(exc)) from exc


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
    result = await fetch_stop(prim, station.id)

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


# --- Trajets : prochain train direct d'une gare à une autre --------------------------------

SAME_STATION = "Les gares de départ et d'arrivée doivent être différentes"


def _station(repo: StationRepository, station_id: str, role: str) -> Station:
    station = repo.get(station_id)
    if station is None:
        raise HTTPException(404, f"Gare {role} inconnue : {station_id}")
    return station


async def compute_next_trains(
    origin: Station,
    destination: Station,
    repo: StationRepository,
    prim: PrimClient,
    limit: int,
    line: str | None = None,
) -> JourneyNextResponse:
    now = datetime.now(timezone.utc)
    lines = common_lines(origin, destination)
    if not lines:
        # Inutile d'appeler PRIM : aucun train ne peut relier les deux gares sans changement
        return JourneyNextResponse(
            origin=origin,
            destination=destination,
            common_lines=[],
            updated_at=now,
            trains=[],
            message="Aucune ligne directe entre ces deux gares.",
        )

    dep, arr = await asyncio.gather(fetch_stop(prim, origin.id), fetch_stop(prim, destination.id))
    trains = find_direct_trains(parse_visits(dep.data), parse_visits(arr.data), repo, now=now)
    if line:
        trains = [t for t in trains if t.line.name.upper() == line.upper()]

    return JourneyNextResponse(
        origin=origin,
        destination=destination,
        common_lines=lines,
        updated_at=min(dep.fetched_at, arr.fetched_at),
        stale="STALE" in (dep.cache, arr.cache),
        trains=trains[:limit],
        message=None if trains else "Aucun train direct annoncé pour le moment.",
    )


def to_saved_journey(row: JourneyRow, repo: StationRepository) -> SavedJourney | None:
    origin, destination = repo.get(row.origin_id), repo.get(row.destination_id)
    if origin is None or destination is None:
        return None  # gare disparue du référentiel après régénération
    return SavedJourney(
        id=row.id,
        name=row.name,
        origin=origin,
        destination=destination,
        common_lines=common_lines(origin, destination),
        created_at=row.created_at,
    )


def get_saved_or_404(
    journey_id: int,
    store: JourneyStore = Depends(get_store),
    repo: StationRepository = Depends(get_repo),
) -> SavedJourney:
    row = store.get(journey_id)
    journey = to_saved_journey(row, repo) if row else None
    if journey is None:
        raise HTTPException(404, f"Trajet inconnu : {journey_id}")
    return journey


def _clean_name(name: str | None) -> str | None:
    return (name or "").strip() or None


# Déclaré avant /journeys/{journey_id}
@app.get(
    "/journeys/next",
    response_model=JourneyNextResponse,
    summary="Prochains trains directs entre deux gares",
    tags=["trajets"],
)
async def next_trains(
    origin_id: str = Query(..., alias="from", description="Identifiant de la gare de départ"),
    destination_id: str = Query(..., alias="to", description="Identifiant de la gare d'arrivée"),
    line: str | None = Query(None, description="Filtrer par ligne, ex. A"),
    limit: int = Query(5, ge=1, le=20),
    repo: StationRepository = Depends(get_repo),
    prim: PrimClient = Depends(get_prim),
):
    if origin_id == destination_id:
        raise HTTPException(422, SAME_STATION)
    origin = _station(repo, origin_id, "de départ")
    destination = _station(repo, destination_id, "d'arrivée")
    return await compute_next_trains(origin, destination, repo, prim, limit, line)


@app.get(
    "/journeys", response_model=list[SavedJourney], summary="Trajets sauvegardés", tags=["trajets"]
)
def list_journeys(
    store: JourneyStore = Depends(get_store), repo: StationRepository = Depends(get_repo)
):
    return [j for row in store.list() if (j := to_saved_journey(row, repo))]


@app.post(
    "/journeys",
    response_model=SavedJourney,
    status_code=201,
    summary="Sauvegarder un trajet",
    tags=["trajets"],
)
def create_journey(
    body: SavedJourneyCreate,
    store: JourneyStore = Depends(get_store),
    repo: StationRepository = Depends(get_repo),
):
    if body.origin_id == body.destination_id:
        raise HTTPException(422, SAME_STATION)
    origin = _station(repo, body.origin_id, "de départ")
    destination = _station(repo, body.destination_id, "d'arrivée")
    if not common_lines(origin, destination):
        raise HTTPException(422, "Aucune ligne directe entre ces deux gares")
    try:
        row = store.create(origin.id, destination.id, _clean_name(body.name))
    except DuplicateJourneyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_saved_journey(row, repo)


@app.get(
    "/journeys/{journey_id}",
    response_model=SavedJourney,
    summary="Détail d'un trajet sauvegardé",
    tags=["trajets"],
)
def get_journey(journey: SavedJourney = Depends(get_saved_or_404)):
    return journey


@app.patch(
    "/journeys/{journey_id}",
    response_model=SavedJourney,
    summary="Renommer un trajet",
    tags=["trajets"],
)
def rename_journey(
    body: SavedJourneyUpdate,
    journey: SavedJourney = Depends(get_saved_or_404),
    store: JourneyStore = Depends(get_store),
    repo: StationRepository = Depends(get_repo),
):
    row = store.rename(journey.id, _clean_name(body.name))
    return to_saved_journey(row, repo)


@app.delete(
    "/journeys/{journey_id}", status_code=204, summary="Supprimer un trajet", tags=["trajets"]
)
def delete_journey(
    journey: SavedJourney = Depends(get_saved_or_404), store: JourneyStore = Depends(get_store)
):
    store.delete(journey.id)
    return Response(status_code=204)


@app.get(
    "/journeys/{journey_id}/next",
    response_model=JourneyNextResponse,
    summary="Prochains trains d'un trajet sauvegardé",
    tags=["trajets"],
)
async def saved_journey_next(
    journey: SavedJourney = Depends(get_saved_or_404),
    line: str | None = Query(None, description="Filtrer par ligne, ex. A"),
    limit: int = Query(5, ge=1, le=20),
    repo: StationRepository = Depends(get_repo),
    prim: PrimClient = Depends(get_prim),
):
    return await compute_next_trains(journey.origin, journey.destination, repo, prim, limit, line)


# --- Itinéraires entre deux adresses (calculateur Navitia IDFM) ---------------------------


def _navitia_http_error(exc: PrimError) -> HTTPException:
    if isinstance(exc, PrimConfigError):
        return HTTPException(503, str(exc))
    status = exc.status if isinstance(exc, NavitiaError) else 502
    return HTTPException(status, str(exc))


def _place_id(value: str, role: str) -> str:
    value = value.strip()
    if not PLACE_ID.fullmatch(value):
        raise HTTPException(422, f"Lieu {role} invalide : utilisez un identifiant de /places ou « lon;lat »")
    return value


@app.get(
    "/places",
    response_model=list[Place],
    summary="Rechercher une adresse, un arrêt ou un lieu",
    tags=["itinéraires"],
)
async def search_places(
    q: str = Query(..., min_length=3, max_length=200, description="Adresse, arrêt, lieu ou commune"),
    limit: int = Query(8, ge=1, le=20),
    navitia: NavitiaClient = Depends(get_navitia),
):
    try:
        return await navitia.places(q, count=limit)
    except NoSolution:
        return []
    except PrimError as exc:
        raise _navitia_http_error(exc) from exc


@app.get(
    "/itineraries",
    response_model=ItinerariesResponse,
    summary="Calculer un itinéraire entre deux lieux",
    tags=["itinéraires"],
)
async def compute_itineraries(
    origin: str = Query(..., alias="from", description="Identifiant de lieu (/places) ou « lon;lat »"),
    destination: str = Query(..., alias="to", description="Identifiant de lieu (/places) ou « lon;lat »"),
    when: datetime | None = Query(
        None,
        alias="datetime",
        description="Date et heure (ISO 8601, heure de Paris si sans fuseau). Par défaut : maintenant",
    ),
    represents: str = Query(
        "departure", pattern="^(departure|arrival)$", description="Partir à (departure) ou arriver avant (arrival)"
    ),
    count: int = Query(3, ge=1, le=6, description="Nombre d'itinéraires"),
    navitia: NavitiaClient = Depends(get_navitia),
):
    origin = _place_id(origin, "de départ")
    destination = _place_id(destination, "d'arrivée")
    if origin == destination:
        raise HTTPException(422, "Les lieux de départ et d'arrivée doivent être différents")
    try:
        itineraries = await navitia.journeys(origin, destination, when, represents, count)
    except NoSolution as exc:
        return ItinerariesResponse(origin=origin, destination=destination, itineraries=[], message=str(exc))
    except PrimError as exc:
        raise _navitia_http_error(exc) from exc
    return ItinerariesResponse(
        origin=origin,
        destination=destination,
        itineraries=itineraries,
        message=None if itineraries else "Aucun itinéraire trouvé.",
    )


# Frontend Svelte compilé (cd frontend && npm run build), servi sur « / » s'il existe.
# Monté en dernier : les routes de l'API ci-dessus restent prioritaires.
if settings.frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
