<script lang="ts">
  import { getDepartures, type Departure, type DeparturesResponse, type Station } from './api';
  import LineBadge from './LineBadge.svelte';
  import { MODE_ORDER } from './lines';

  let { station }: { station: Station } = $props();

  const REFRESH_MS = 30_000;

  let data = $state<DeparturesResponse | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let lineFilter = $state<string | null>(null);
  let now = $state(Date.now());

  async function load() {
    loading = true;
    try {
      data = await getDepartures(station.id);
      error = null;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  // Rechargement à chaque changement de gare, puis toutes les 30 s (en pause si l'onglet est caché)
  $effect(() => {
    station.id;
    data = null;
    error = null;
    lineFilter = null;
    load();
    const timer = setInterval(() => {
      if (!document.hidden) load();
    }, REFRESH_MS);
    const onVisible = () => !document.hidden && load();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  });

  // Horloge locale pour faire défiler les « dans X min » entre deux rafraîchissements
  $effect(() => {
    const timer = setInterval(() => (now = Date.now()), 10_000);
    return () => clearInterval(timer);
  });

  const lines = $derived(
    [...station.lines].sort(
      (a, b) => MODE_ORDER.indexOf(a.mode) - MODE_ORDER.indexOf(b.mode) || a.name.localeCompare(b.name),
    ),
  );

  const departures = $derived(
    (data?.departures ?? [])
      .filter((d) => !lineFilter || d.line.name === lineFilter)
      .filter((d) => new Date(d.expected_time).getTime() > now - 60_000),
  );

  const timeFmt = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });
  const fmt = (iso: string | null) => (iso ? timeFmt.format(new Date(iso)) : '');

  function minutes(d: Departure) {
    return Math.max(0, Math.floor((new Date(d.expected_time).getTime() - now) / 60_000));
  }

  function updatedLabel(iso: string) {
    const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
    if (s < 60) return "à l'instant";
    return `il y a ${Math.floor(s / 60)} min`;
  }

  const cancelled = (d: Departure) => d.status === 'cancelled';
</script>

<section class="card">
  <header>
    <div>
      <h2>{station.name}</h2>
      <p class="city">{station.city}</p>
    </div>
    <button class="refresh" onclick={load} disabled={loading} aria-label="Rafraîchir" title="Rafraîchir">
      <svg class:spinning={loading} viewBox="0 0 24 24" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
      </svg>
    </button>
  </header>

  {#if lines.length > 1}
    <div class="filters" role="group" aria-label="Filtrer par ligne">
      <button class="chip" class:on={!lineFilter} onclick={() => (lineFilter = null)}>Toutes</button>
      {#each lines as line (line.id)}
        <button
          class="chip"
          class:on={lineFilter === line.name}
          onclick={() => (lineFilter = lineFilter === line.name ? null : line.name)}
          aria-pressed={lineFilter === line.name}
        >
          <LineBadge {line} size="sm" />
        </button>
      {/each}
    </div>
  {/if}

  {#if data?.stale}
    <p class="banner warn">Temps réel momentanément indisponible : affichage des dernières données connues.</p>
  {/if}

  {#if error && !data}
    <div class="state error">
      <p>Impossible de charger les départs.</p>
      <small>{error}</small>
      <button onclick={load}>Réessayer</button>
    </div>
  {:else if !data}
    <ul class="list" aria-busy="true">
      {#each Array(5) as _, i (i)}<li class="row skeleton"></li>{/each}
    </ul>
  {:else if !departures.length}
    <div class="state">Aucun départ prévu pour le moment{lineFilter ? ` sur la ligne ${lineFilter}` : ''}.</div>
  {:else}
    <ul class="list">
      {#each departures as d (d.expected_time + d.line.id + (d.train_number ?? d.destination))}
        <li class="row" class:cancelled={cancelled(d)}>
          <LineBadge line={d.line} />
          <div class="dest">
            <strong>{d.destination}</strong>
            <small>
              {#if d.mission}<span class="mission">{d.mission}</span>{/if}
              {#if d.train_number}<span>n° {d.train_number}</span>{/if}
              {#if d.platform}<span>Voie {d.platform}</span>{/if}
            </small>
          </div>
          <div class="time">
            {#if cancelled(d)}
              <span class="tag danger">Supprimé</span>
              <small><s>{fmt(d.aimed_time ?? d.expected_time)}</s></small>
            {:else}
              {#if d.at_platform}
                <span class="tag ok">À quai</span>
              {:else if minutes(d) === 0}
                <span class="soon">Imminent</span>
              {:else}
                <span class="mins">{minutes(d)}<small> min</small></span>
              {/if}
              <small>
                {#if d.delay_minutes > 0}
                  <s>{fmt(d.aimed_time)}</s> <span class="late">{fmt(d.expected_time)} (+{d.delay_minutes})</span>
                {:else}
                  {fmt(d.expected_time)}
                {/if}
              </small>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  {#if data}
    <footer>
      Mis à jour {updatedLabel(data.updated_at)}
      {#if error}· <span class="late">dernier rafraîchissement en échec</span>{/if}
    </footer>
  {/if}
</section>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    padding: 1.25rem 1.25rem 0.75rem;
  }
  h2 {
    margin: 0;
    font-size: 1.5rem;
    letter-spacing: -0.01em;
  }
  .city {
    margin: 0.15rem 0 0;
    color: var(--muted);
  }
  .refresh {
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: 10px;
    width: 2.4rem;
    height: 2.4rem;
    display: grid;
    place-items: center;
    cursor: pointer;
    color: var(--text);
  }
  .refresh svg {
    width: 1.1rem;
    height: 1.1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .spinning {
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0 1.25rem 0.9rem;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 999px;
    padding: 0.25rem 0.6rem;
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
    min-height: 2rem;
  }
  .chip.on {
    border-color: var(--accent);
    background: var(--accent-soft);
    font-weight: 600;
  }
  .banner {
    margin: 0 1.25rem 0.75rem;
    padding: 0.6rem 0.8rem;
    border-radius: 10px;
    font-size: 0.9rem;
  }
  .warn {
    background: var(--warn-soft);
    color: var(--warn);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    border-top: 1px solid var(--border);
  }
  .row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 0.9rem;
    padding: 0.8rem 1.25rem;
    border-bottom: 1px solid var(--border);
  }
  .row:last-child {
    border-bottom: 0;
  }
  .skeleton {
    height: 3.6rem;
    background: linear-gradient(90deg, var(--hover), var(--surface), var(--hover));
    background-size: 200% 100%;
    animation: shimmer 1.2s infinite;
  }
  @keyframes shimmer {
    to {
      background-position: -200% 0;
    }
  }
  .dest {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .dest strong {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dest small {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    color: var(--muted);
  }
  .mission {
    font-family: ui-monospace, monospace;
    font-weight: 600;
  }
  .time {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .time small {
    color: var(--muted);
  }
  .mins {
    font-size: 1.35rem;
    font-weight: 800;
    line-height: 1.1;
  }
  .mins small {
    font-size: 0.8rem;
    font-weight: 600;
  }
  .soon {
    font-weight: 800;
    color: var(--accent);
  }
  .tag {
    font-size: 0.8rem;
    font-weight: 700;
    padding: 0.15rem 0.5rem;
    border-radius: 6px;
  }
  .tag.ok {
    background: var(--ok-soft);
    color: var(--ok);
  }
  .tag.danger {
    background: var(--danger-soft);
    color: var(--danger);
  }
  .late {
    color: var(--warn);
    font-weight: 600;
  }
  .cancelled .dest strong {
    text-decoration: line-through;
    color: var(--muted);
  }
  .state {
    padding: 2rem 1.25rem;
    text-align: center;
    color: var(--muted);
    border-top: 1px solid var(--border);
  }
  .state.error {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
    color: var(--danger);
  }
  .state button {
    margin-top: 0.5rem;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 8px;
    padding: 0.4rem 0.9rem;
    font: inherit;
    cursor: pointer;
  }
  footer {
    padding: 0.7rem 1.25rem;
    font-size: 0.8rem;
    color: var(--muted);
    border-top: 1px solid var(--border);
  }
  @media (max-width: 480px) {
    header,
    .row,
    footer {
      padding-left: 1rem;
      padding-right: 1rem;
    }
    .filters {
      padding: 0 1rem 0.9rem;
    }
  }
</style>
