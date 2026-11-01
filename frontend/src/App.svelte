<script lang="ts">
  import { untrack } from 'svelte';
  import { getStation, type Place, type Station } from './lib/api';
  import Departures from './lib/Departures.svelte';
  import LineBadge from './lib/LineBadge.svelte';
  import StationSearch from './lib/StationSearch.svelte';
  import ItineraryPlanner from './pages/ItineraryPlanner.svelte';
  import JourneyPlanner from './pages/JourneyPlanner.svelte';
  import SavedJourneyDetail from './pages/SavedJourneyDetail.svelte';
  import SavedJourneys from './pages/SavedJourneys.svelte';

  const RECENT_KEY = 'idf-trains:recent';
  const MAX_RECENT = 6;

  let station = $state<Station | null>(null);
  let notFound = $state<string | null>(null);
  let recent = $state<Station[]>(loadRecent());

  function loadRecent(): Station[] {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
    } catch {
      return [];
    }
  }

  function remember(s: Station) {
    recent = [s, ...recent.filter((r) => r.id !== s.id)].slice(0, MAX_RECENT);
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
    } catch {
      /* stockage indisponible : pas grave */
    }
  }

  // Routage par hash (liens partageables, bouton retour du navigateur) :
  //   #/  ·  #/gare/45102  ·  #/trajet?from=…&to=…  ·  #/trajets  ·  #/trajets/3
  type Page =
    | { name: 'home' }
    | { name: 'planner'; from: string | null; to: string | null }
    | { name: 'itinerary'; from: Place | null; to: Place | null; mode: 'now' | 'departure' | 'arrival'; when: string | null }
    | { name: 'journeys' }
    | { name: 'journey'; id: number };

  let page = $state<Page>({ name: 'home' });

  function parseHash(): Page {
    const [path, query = ''] = location.hash.replace(/^#/, '').split('?');
    const params = new URLSearchParams(query);
    if (path === '/trajet') return { name: 'planner', from: params.get('from'), to: params.get('to') };
    if (path === '/itineraire') {
      const mode = params.get('mode');
      return {
        name: 'itinerary',
        from: placeFromUrl(params.get('from'), params.get('fromName')),
        to: placeFromUrl(params.get('to'), params.get('toName')),
        mode: mode === 'departure' || mode === 'arrival' ? mode : 'now',
        when: params.get('when'),
      };
    }
    if (path === '/trajets') return { name: 'journeys' };
    const m = path.match(/^\/trajets\/(\d+)$/);
    if (m) return { name: 'journey', id: Number(m[1]) };
    return { name: 'home' };
  }

  function placeFromUrl(id: string | null, name: string | null): Place | null {
    if (!id) return null;
    const type = id.startsWith('stop_area') ? 'stop_area' : id.startsWith('poi') ? 'poi' : name === 'Ma position' ? 'position' : 'address';
    return { id, name: name || id, type };
  }

  async function route() {
    page = parseHash();
    const id = location.hash.match(/^#\/gare\/([^/]+)$/)?.[1];
    notFound = null;
    if (!id) {
      station = null;
      return;
    }
    if (station?.id === id) return;
    const known = recent.find((r) => r.id === id);
    if (known) {
      station = known;
      return;
    }
    try {
      station = await getStation(id);
      remember(station);
    } catch {
      station = null;
      notFound = id;
    }
  }

  function select(s: Station) {
    station = s;
    remember(s);
    location.hash = `#/gare/${s.id}`;
  }

  $effect(() => {
    untrack(route);
    window.addEventListener('hashchange', route);
    return () => window.removeEventListener('hashchange', route);
  });

  $effect(() => {
    const titles: Record<string, string> = { planner: 'Trajet direct', journeys: 'Mes trajets', itinerary: 'Itinéraire' };
    if (page.name === 'journey') return; // titre fixé par la page du trajet
    const title = page.name === 'home' ? station?.name : titles[page.name];
    document.title = title ? `${title} · Prochains trains` : 'Prochains trains IDF';
  });
</script>

<div class="app">
  <header class="top">
    <div class="bar">
      <a href="#/" class="brand" aria-label="Accueil">
        <img src="/favicon.svg" alt="" width="32" height="32" />
        <span>Prochains trains <em>IDF</em></span>
      </a>
      <nav aria-label="Navigation principale">
        <a href="#/" class:active={page.name === 'home'}>Départs</a>
        <a href="#/itineraire" class:active={page.name === 'itinerary'}>Itinéraire</a>
        <a href="#/trajet" class:active={page.name === 'planner'}>Trajet</a>
        <a href="#/trajets" class:active={page.name === 'journeys' || page.name === 'journey'}>Mes trajets</a>
      </nav>
    </div>
  </header>

  <main>
  {#if page.name === 'itinerary'}
    <ItineraryPlanner initial={page} />
  {:else if page.name === 'planner'}
    <JourneyPlanner fromId={page.from} toId={page.to} />
  {:else if page.name === 'journeys'}
    <SavedJourneys />
  {:else if page.name === 'journey'}
    <SavedJourneyDetail id={page.id} />
  {:else}
    <StationSearch onselect={select} autofocus={!station} />

    {#if notFound}
      <p class="notice">Gare introuvable : « {notFound} ».</p>
    {/if}

    {#if station}
      <Departures {station} />
      <a class="trip-link" href="#/trajet?from={station.id}">Aller de {station.name} vers… →</a>
    {:else}
      <section class="intro">
        <h1>Où prenez-vous le train ?</h1>
        <p>RER, Transilien et TER en temps réel, pour les gares d'Île-de-France.</p>
      </section>
    {/if}

    {#if recent.length}
      <section class="recent">
        <h3>Gares récentes</h3>
        <ul>
          {#each recent as r (r.id)}
            <li>
              <a href="#/gare/{r.id}" class:current={station?.id === r.id}>
                <span>{r.name}</span>
                <span class="badges">
                  {#each r.lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
                </span>
              </a>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
  </main>

  <footer class="bottom">
    Données temps réel : <a href="https://prim.iledefrance-mobilites.fr" target="_blank" rel="noreferrer">PRIM – Île-de-France Mobilités</a>
  </footer>
</div>

<style>
  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .top {
    background: var(--brand);
    color: #fff;
    padding: 0.9rem 1rem;
  }
  .bar {
    max-width: 720px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
  }
  nav {
    display: flex;
    gap: 0.25rem;
    max-width: 100%;
    overflow-x: auto;
  }
  nav a {
    white-space: nowrap;
    color: rgb(255 255 255 / 0.75);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
    padding: 0.4rem 0.7rem;
    border-radius: 8px;
  }
  nav a:hover {
    color: #fff;
  }
  nav a.active {
    color: #fff;
    background: rgb(255 255 255 / 0.14);
  }
  .trip-link {
    align-self: flex-end;
    color: var(--accent);
    font-weight: 600;
    text-decoration: none;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    color: inherit;
    text-decoration: none;
    font-weight: 700;
    font-size: 1.1rem;
  }
  .brand em {
    font-style: normal;
    opacity: 0.7;
  }
  main {
    flex: 1;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
    padding: 1.25rem 1rem 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .intro {
    text-align: center;
    padding: 2.5rem 1rem 1rem;
  }
  .intro h1 {
    margin: 0 0 0.5rem;
    font-size: 1.8rem;
    letter-spacing: -0.02em;
  }
  .intro p {
    margin: 0;
    color: var(--muted);
  }
  .notice {
    margin: 0;
    padding: 0.7rem 0.9rem;
    border-radius: 10px;
    background: var(--danger-soft);
    color: var(--danger);
  }
  .recent h3 {
    margin: 0 0 0.6rem;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .recent ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.5rem;
  }
  .recent a {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    padding: 0.65rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
  }
  .recent a:hover {
    background: var(--hover);
  }
  .recent a.current {
    border-color: var(--accent);
  }
  .badges {
    display: flex;
    gap: 0.2rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .bottom {
    text-align: center;
    font-size: 0.8rem;
    color: var(--muted);
    padding: 1rem;
  }
  .bottom a {
    color: inherit;
  }
</style>
