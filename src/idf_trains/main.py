import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

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
    ApiUsageToday,
    HomeItem,
    HomeResponse,
    HomeUpdate,
    SavedItinerary,
    SavedItineraryCreate,
    UsageCall,
    UsageDay,
    UsageEndpoint,
    UsageHour,
    UsageResponse,
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
from .storage import (
    DuplicateItineraryError,
    DuplicateJourneyError,
    HomeStore,
    ItineraryRow,
    ItineraryStore,
    JourneyRow,
    JourneyStore,
    PlaceSearchStore,
    UsageStore,
)
from .usage import APIS, PARIS, UsageTracker, now_paris


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = create_cache(settings.redis_url, settings.cache_max_entries)
    try:
        async with httpx.AsyncClient(timeout=settings.prim_timeout) as http:
            app.state.repo = StationRepository.from_file(settings.stations_file)
            app.state.store = JourneyStore(settings.db_path)
            app.state.itinerary_store = ItineraryStore(settings.db_path)
            app.state.home_store = HomeStore(settings.db_path)
            place_store = PlaceSearchStore(settings.db_path, max_age=settings.places_db_ttl)
            place_store.purge()
            app.state.usage_store = UsageStore(settings.db_path)
            app.state.usage_store.purge(
                (now_paris() - timedelta(days=settings.usage_retention_days)).date().isoformat()
            )
            usage = UsageTracker(app.state.usage_store)
            app.state.prim = PrimClient(
                http,
                settings.prim_api_key,
                settings.prim_url,
                cache=cache,
                cache_ttl=settings.cache_ttl,
                stale_ttl=settings.cache_stale_ttl,
                usage=usage,
            )
            app.state.navitia = NavitiaClient(
                http,
                settings.prim_api_key,
                settings.navitia_url,
                cache=cache,
                places_ttl=settings.places_cache_ttl,
                journeys_ttl=settings.itineraries_cache_ttl,
                place_store=place_store,
                usage=usage,
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


def get_itinerary_store(request: Request) -> ItineraryStore:
    return request.app.state.itinerary_store


def get_usage_store(request: Request) -> UsageStore:
    return request.app.state.usage_store


def get_home_store(request: Request) -> HomeStore:
    return request.app.state.home_store


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
    journey: SavedJourney = Depends(get_saved_or_404),
    store: JourneyStore = Depends(get_store),
    home: HomeStore = Depends(get_home_store),
):
    store.delete(journey.id)
    home.remove("journey", journey.id)
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
    return await run_itineraries(navitia, origin, destination, when, represents, count)


async def run_itineraries(
    navitia: NavitiaClient,
    origin: str,
    destination: str,
    when: datetime | None,
    represents: str,
    count: int,
) -> ItinerariesResponse:
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


# --- Itinéraires sauvegardés ----------------------------------------------------------------


def to_saved_itinerary(row: ItineraryRow) -> SavedItinerary:
    return SavedItinerary(
        id=row.id,
        name=row.name,
        origin=Place(**row.origin),
        destination=Place(**row.destination),
        created_at=row.created_at,
    )


def get_saved_itinerary_or_404(
    itinerary_id: int, store: ItineraryStore = Depends(get_itinerary_store)
) -> SavedItinerary:
    row = store.get(itinerary_id)
    if row is None:
        raise HTTPException(404, f"Itinéraire inconnu : {itinerary_id}")
    return to_saved_itinerary(row)


@app.get(
    "/itineraries/saved",
    response_model=list[SavedItinerary],
    summary="Itinéraires sauvegardés",
    tags=["itinéraires"],
)
def list_saved_itineraries(store: ItineraryStore = Depends(get_itinerary_store)):
    return [to_saved_itinerary(r) for r in store.list()]


@app.post(
    "/itineraries/saved",
    response_model=SavedItinerary,
    status_code=201,
    summary="Sauvegarder un itinéraire",
    tags=["itinéraires"],
)
def create_saved_itinerary(
    body: SavedItineraryCreate, store: ItineraryStore = Depends(get_itinerary_store)
):
    if body.origin.id == body.destination.id:
        raise HTTPException(422, "Les lieux de départ et d'arrivée doivent être différents")
    try:
        row = store.create(
            body.origin.model_dump(), body.destination.model_dump(), _clean_name(body.name)
        )
    except DuplicateItineraryError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_saved_itinerary(row)


@app.get(
    "/itineraries/saved/{itinerary_id}",
    response_model=SavedItinerary,
    summary="Détail d'un itinéraire sauvegardé",
    tags=["itinéraires"],
)
def get_saved_itinerary(itinerary: SavedItinerary = Depends(get_saved_itinerary_or_404)):
    return itinerary


@app.patch(
    "/itineraries/saved/{itinerary_id}",
    response_model=SavedItinerary,
    summary="Renommer un itinéraire sauvegardé",
    tags=["itinéraires"],
)
def rename_saved_itinerary(
    body: SavedJourneyUpdate,
    itinerary: SavedItinerary = Depends(get_saved_itinerary_or_404),
    store: ItineraryStore = Depends(get_itinerary_store),
):
    return to_saved_itinerary(store.rename(itinerary.id, _clean_name(body.name)))


@app.delete(
    "/itineraries/saved/{itinerary_id}",
    status_code=204,
    summary="Supprimer un itinéraire sauvegardé",
    tags=["itinéraires"],
)
def delete_saved_itinerary(
    itinerary: SavedItinerary = Depends(get_saved_itinerary_or_404),
    store: ItineraryStore = Depends(get_itinerary_store),
    home: HomeStore = Depends(get_home_store),
):
    store.delete(itinerary.id)
    home.remove("itinerary", itinerary.id)
    return Response(status_code=204)


@app.get(
    "/itineraries/saved/{itinerary_id}/next",
    response_model=ItinerariesResponse,
    summary="Calculer un itinéraire sauvegardé",
    tags=["itinéraires"],
)
async def saved_itinerary_next(
    itinerary: SavedItinerary = Depends(get_saved_itinerary_or_404),
    when: datetime | None = Query(None, alias="datetime", description="Par défaut : maintenant"),
    represents: str = Query("departure", pattern="^(departure|arrival)$"),
    count: int = Query(3, ge=1, le=6),
    navitia: NavitiaClient = Depends(get_navitia),
):
    return await run_itineraries(
        navitia, itinerary.origin.id, itinerary.destination.id, when, represents, count
    )


# --- Page d'accueil ------------------------------------------------------------------------


def _home_items(
    refs: list[tuple[str, int]],
    journeys: JourneyStore,
    itineraries: ItineraryStore,
    repo: StationRepository,
) -> list[HomeItem]:
    """Résout les références ; celles qui n'existent plus sont ignorées."""
    items = []
    for kind, ref_id in refs:
        if kind == "journey":
            row = journeys.get(ref_id)
            journey = to_saved_journey(row, repo) if row else None
            if journey:
                items.append(HomeItem(kind=kind, id=ref_id, journey=journey))
        else:
            row = itineraries.get(ref_id)
            if row:
                items.append(HomeItem(kind=kind, id=ref_id, itinerary=to_saved_itinerary(row)))
    return items


@app.get("/home", response_model=HomeResponse, summary="Éléments de la page d'accueil", tags=["accueil"])
def get_home(
    home: HomeStore = Depends(get_home_store),
    journeys: JourneyStore = Depends(get_store),
    itineraries: ItineraryStore = Depends(get_itinerary_store),
    repo: StationRepository = Depends(get_repo),
):
    return HomeResponse(items=_home_items(home.list(), journeys, itineraries, repo))


@app.put(
    "/home",
    response_model=HomeResponse,
    summary="Choisir les trajets et itinéraires de la page d'accueil (dans l'ordre)",
    tags=["accueil"],
)
def update_home(
    body: HomeUpdate,
    home: HomeStore = Depends(get_home_store),
    journeys: JourneyStore = Depends(get_store),
    itineraries: ItineraryStore = Depends(get_itinerary_store),
    repo: StationRepository = Depends(get_repo),
):
    refs: list[tuple[str, int]] = []
    for item in body.items:
        ref = (item.kind, item.id)
        if ref in refs:
            continue  # doublon ignoré
        exists = journeys.get(item.id) if item.kind == "journey" else itineraries.get(item.id)
        if exists is None:
            label = "Trajet" if item.kind == "journey" else "Itinéraire"
            raise HTTPException(422, f"{label} inconnu : {item.id}")
        refs.append(ref)
    home.replace(refs)
    return HomeResponse(items=_home_items(refs, journeys, itineraries, repo))


# --- Suivi de la consommation des API IDFM ------------------------------------------------


@app.get(
    "/usage",
    response_model=UsageResponse,
    summary="Consommation des API IDFM (appels, quotas, cache)",
    tags=["consommation"],
)
def get_usage(
    days: int = Query(30, ge=1, le=90, description="Nombre de jours d'historique"),
    store: UsageStore = Depends(get_usage_store),
):
    today = now_paris().date()
    since = today - timedelta(days=days - 1)
    rows = {(r["day"], r["api"]): r for r in store.daily(since.isoformat())}

    # Une ligne par jour et par API, y compris les jours sans appel
    daily = [
        UsageDay(**rows.get((d, api), {"day": d, "api": api, "calls": 0, "errors": 0, "cache_hits": 0}))
        for d in ((since + timedelta(days=i)).isoformat() for i in range(days))
        for api in APIS
    ]
    quotas = {"realtime": settings.quota_realtime, "navitia": settings.quota_navitia}
    apis = []
    for api, label in APIS.items():
        r = rows.get((today.isoformat(), api), {})
        calls, quota = r.get("calls", 0), quotas[api]
        apis.append(
            ApiUsageToday(
                api=api,
                label=label,
                calls=calls,
                errors=r.get("errors", 0),
                cache_hits=r.get("cache_hits", 0),
                quota=quota,
                remaining=max(0, quota - calls) if quota else None,
            )
        )
    return UsageResponse(
        day=today.isoformat(),
        apis=apis,
        daily=daily,
        hourly=[UsageHour(**r) for r in store.hourly(today.isoformat())],
        endpoints=[UsageEndpoint(**r) for r in store.by_endpoint(today.isoformat())],
        recent=[
            UsageCall(
                at=datetime.fromtimestamp(r["ts"], PARIS),
                api=r["api"],
                endpoint=r["endpoint"],
                status=r["status"],
                duration_ms=r["duration_ms"],
            )
            for r in store.recent()
        ],
    )


# Frontend Svelte compilé (cd frontend && npm run build), servi sur « / » s'il existe.
# Monté en dernier : les routes de l'API ci-dessus restent prioritaires.
if settings.frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
