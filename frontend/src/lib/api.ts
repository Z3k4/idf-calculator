// Client de l'API FastAPI (mêmes routes en dev via le proxy Vite et en production)

export interface Line {
  id: string;
  name: string;
  mode: string;
}

export interface Station {
  id: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  lines: Line[];
}

export interface StationMatch {
  score: number;
  station: Station;
}

export interface Departure {
  line: Line;
  destination: string;
  direction: string | null;
  mission: string | null;
  train_number: string | null;
  platform: string | null;
  aimed_time: string | null;
  expected_time: string;
  in_minutes: number;
  delay_minutes: number;
  status: string;
  at_platform: boolean;
}

export interface DeparturesResponse {
  station: Station;
  updated_at: string;
  stale: boolean;
  departures: Departure[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
  });
  if (!resp.ok) {
    let detail = `Erreur ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* corps non JSON */
    }
    throw new ApiError(detail, resp.status);
  }
  return resp.status === 204 ? (undefined as T) : resp.json();
}

function get<T>(path: string, params: Record<string, string | number> = {}, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  return request<T>(query.size ? `${path}?${query}` : path, { signal });
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const searchStations = (name: string, signal?: AbortSignal) =>
  get<StationMatch[]>('/stations/search', { name, limit: 8 }, signal);

export const getStation = (id: string) => get<Station>(`/stations/${encodeURIComponent(id)}`);

export const getDepartures = (id: string, limit = 30) =>
  get<DeparturesResponse>(`/stations/${encodeURIComponent(id)}/departures`, { limit });

// --- Trajets -------------------------------------------------------------------------------

export interface JourneyTrain {
  line: Line;
  destination: string;
  mission: string | null;
  train_number: string | null;
  platform: string | null;
  aimed_departure: string | null;
  expected_departure: string;
  aimed_arrival: string | null;
  expected_arrival: string;
  in_minutes: number;
  duration_minutes: number;
  delay_minutes: number;
  status: string;
  at_platform: boolean;
}

export interface JourneyNext {
  origin: Station;
  destination: Station;
  common_lines: Line[];
  updated_at: string;
  stale: boolean;
  trains: JourneyTrain[];
  message: string | null;
}

export interface SavedJourney {
  id: number;
  name: string | null;
  origin: Station;
  destination: Station;
  common_lines: Line[];
  created_at: string;
}

export const getNextTrains = (from: string, to: string, limit = 5) =>
  get<JourneyNext>('/journeys/next', { from, to, limit });

export const listJourneys = () => get<SavedJourney[]>('/journeys');

export const getJourney = (id: number) => get<SavedJourney>(`/journeys/${id}`);

export const getJourneyNext = (id: number, limit = 5) => get<JourneyNext>(`/journeys/${id}/next`, { limit });

export const createJourney = (origin_id: string, destination_id: string, name: string | null) =>
  send<SavedJourney>('POST', '/journeys', { origin_id, destination_id, name });

export const renameJourney = (id: number, name: string | null) =>
  send<SavedJourney>('PATCH', `/journeys/${id}`, { name });

export const deleteJourney = (id: number) => send<void>('DELETE', `/journeys/${id}`);

// --- Itinéraires (calculateur IDFM) ------------------------------------------------------

export interface Place {
  id: string; // identifiant Navitia ou « lon;lat »
  name: string;
  type: 'address' | 'stop_area' | 'poi' | 'administrative_region' | 'position';
  city?: string | null;
  lat?: number | null;
  lon?: number | null;
}

export interface TransitLine {
  code: string;
  name: string | null;
  mode: string;
  network: string | null;
  color: string | null;
  text_color: string | null;
}

export interface ItinerarySection {
  type: 'walk' | 'transit' | 'transfer' | 'wait';
  departure: string | null;
  arrival: string | null;
  duration_minutes: number;
  from_name: string | null;
  to_name: string | null;
  line: TransitLine | null;
  direction: string | null;
  headsign: string | null;
  stops: string[];
  delay_minutes: number;
  distance_m: number | null;
  geometry: number[][];
}

export interface Itinerary {
  departure: string;
  arrival: string;
  duration_minutes: number;
  transfers: number;
  walking_minutes: number;
  walking_distance_m: number | null;
  co2_grams: number | null;
  tags: string[];
  status: string | null;
  sections: ItinerarySection[];
}

export interface ItinerariesResponse {
  origin: string;
  destination: string;
  itineraries: Itinerary[];
  message: string | null;
}

export const searchPlaces = (q: string, signal?: AbortSignal) => get<Place[]>('/places', { q, limit: 8 }, signal);

export function getItineraries(
  from: string,
  to: string,
  options: { datetime?: string; represents?: 'departure' | 'arrival'; count?: number } = {},
) {
  const params: Record<string, string | number> = { from, to, count: options.count ?? 4 };
  if (options.datetime) {
    params.datetime = options.datetime;
    params.represents = options.represents ?? 'departure';
  }
  return get<ItinerariesResponse>('/itineraries', params);
}

export interface SavedItinerary {
  id: number;
  name: string | null;
  origin: Place;
  destination: Place;
  created_at: string;
}

export const listSavedItineraries = () => get<SavedItinerary[]>('/itineraries/saved');

export const getSavedItinerary = (id: number) => get<SavedItinerary>(`/itineraries/saved/${id}`);

export const createSavedItinerary = (origin: Place, destination: Place, name: string | null) =>
  send<SavedItinerary>('POST', '/itineraries/saved', { origin, destination, name });

export const renameSavedItinerary = (id: number, name: string | null) =>
  send<SavedItinerary>('PATCH', `/itineraries/saved/${id}`, { name });

export const deleteSavedItinerary = (id: number) => send<void>('DELETE', `/itineraries/saved/${id}`);

// --- Consommation des API IDFM -----------------------------------------------------------

export interface ApiUsageToday {
  api: 'realtime' | 'navitia';
  label: string;
  calls: number;
  errors: number;
  cache_hits: number;
  quota: number | null;
  remaining: number | null;
}

export interface UsageResponse {
  day: string;
  timezone: string;
  apis: ApiUsageToday[];
  daily: { day: string; api: string; calls: number; errors: number; cache_hits: number }[];
  hourly: { hour: number; api: string; calls: number }[];
  endpoints: { api: string; endpoint: string; calls: number; errors: number; avg_ms: number }[];
  recent: { at: string; api: string; endpoint: string; status: number; duration_ms: number }[];
}

export const getUsage = (days = 30) => get<UsageResponse>('/usage', { days });

// --- Page d'accueil ------------------------------------------------------------------------

export interface HomeItem {
  kind: 'journey' | 'itinerary';
  id: number;
  journey: SavedJourney | null;
  itinerary: SavedItinerary | null;
}

export const getHome = () => get<{ items: HomeItem[] }>('/home');

export const updateHome = (items: { kind: HomeItem['kind']; id: number }[]) =>
  send<{ items: HomeItem[] }>('PUT', '/home', { items });
