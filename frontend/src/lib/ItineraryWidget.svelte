<script lang="ts">
  import { getItineraries, type Itinerary, type SavedItinerary } from './api';
  import { fmtTime, journeyTitle, scheduleLabel } from './format';
  import TransitBadge from './TransitBadge.svelte';

  /**
   * Bloc d'accueil : les 2 prochains itinéraires d'un itinéraire sauvegardé.
   * Calculé à l'ouverture et sur demande seulement (quota du calculateur IDFM limité).
   */
  let { itinerary }: { itinerary: SavedItinerary } = $props();

  let results = $state<Itinerary[] | null>(null);
  let message = $state<string | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let computedAt = $state<Date | null>(null);

  async function load() {
    loading = true;
    try {
      const { mode, date, time } = itinerary.schedule;
      const res = await getItineraries(
        itinerary.origin.id,
        itinerary.destination.id,
        mode === 'now' ? { count: 2 } : { count: 2, date: date ?? '', time: time ?? '', represents: mode },
      );
      results = res.itineraries.slice(0, 2);
      message = res.message;
      error = null;
      computedAt = new Date();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    itinerary.id;
    load();
  });

  const fmtDuration = (min: number) => (min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}`);
</script>

<article class="widget">
  <div class="top">
    <a class="head" href="#/itineraires/{itinerary.id}">
      <span class="kind">Itinéraire</span>
      <strong>{journeyTitle(itinerary)}</strong>
      {#if itinerary.name}<small>{itinerary.origin.name} → {itinerary.destination.name}</small>{/if}
      {#if scheduleLabel(itinerary.schedule)}
        <small class="sched">{scheduleLabel(itinerary.schedule)}</small>
      {/if}
    </a>
    <button class="refresh" onclick={load} disabled={loading} aria-label="Recalculer" title="Recalculer">
      <svg class:spinning={loading} viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></svg>
    </button>
  </div>

  {#if error}
    <p class="muted err">Calcul impossible : {error}</p>
  {:else if !results}
    <p class="muted">Calcul…</p>
  {:else if !results.length}
    <p class="muted">{message ?? 'Aucun itinéraire trouvé.'}</p>
  {:else}
    <ul class:dim={loading}>
      {#each results as it, i (i)}
        <li>
          <span class="times">{fmtTime(it.departure)} → {fmtTime(it.arrival)}</span>
          <span class="ribbon">
            {#each it.sections.filter((s) => s.type === 'transit' && s.line) as s, j (j)}
              <TransitBadge line={s.line!} compact />
            {/each}
            {#if !it.sections.some((s) => s.type === 'transit')}<span class="muted">À pied</span>{/if}
          </span>
          <span class="dur">{fmtDuration(it.duration_minutes)}</span>
        </li>
      {/each}
    </ul>
    {#if computedAt}<small class="muted stamp">Calculé à {fmtTime(computedAt.toISOString())}</small>{/if}
  {/if}
</article>

<style>
  .widget {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 1rem 1.1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
  }
  .top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.75rem;
  }
  .head {
    display: flex;
    flex-direction: column;
    min-width: 0;
    color: var(--text);
    text-decoration: none;
  }
  .head:hover strong {
    color: var(--accent);
  }
  .kind {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .head small {
    color: var(--muted);
  }
  .head .sched {
    color: var(--accent);
    font-weight: 600;
  }
  .refresh {
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }
  .refresh svg {
    width: 1rem;
    height: 1rem;
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
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    transition: opacity 0.2s;
  }
  .dim {
    opacity: 0.55;
  }
  li {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 0.6rem;
    padding: 0.45rem 0;
    border-top: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }
  .times {
    font-weight: 600;
    white-space: nowrap;
  }
  .ribbon {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    min-width: 0;
  }
  .dur {
    font-weight: 700;
    white-space: nowrap;
  }
  .muted {
    margin: 0;
    color: var(--muted);
  }
  .err {
    color: var(--danger);
  }
  .stamp {
    font-size: 0.75rem;
  }
</style>
