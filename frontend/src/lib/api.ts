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
