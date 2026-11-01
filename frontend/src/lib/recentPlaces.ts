// Adresses déjà choisies, mémorisées dans le navigateur : proposées sans appel à l'API
import type { Place } from './api';

const KEY = 'idf-trains:recent-places';
const MAX = 10;

export function loadRecentPlaces(): Place[] {
  try {
    const data = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function rememberPlace(place: Place): Place[] {
  // « Ma position » change à chaque fois : inutile de la mémoriser
  if (place.type === 'position') return loadRecentPlaces();
  const list = [place, ...loadRecentPlaces().filter((p) => p.id !== place.id)].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* stockage indisponible */
  }
  return list;
}

export function forgetPlace(id: string): Place[] {
  const list = loadRecentPlaces().filter((p) => p.id !== id);
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* stockage indisponible */
  }
  return list;
}

const norm = (s: string) =>
  s
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

export function matchRecent(places: Place[], query: string): Place[] {
  const tokens = norm(query).split(/\s+/).filter(Boolean);
  return places.filter((p) => {
    const hay = norm(`${p.name} ${p.city ?? ''}`);
    return tokens.every((t) => hay.includes(t));
  });
}
