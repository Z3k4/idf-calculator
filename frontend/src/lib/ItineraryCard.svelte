<script lang="ts">
  import type { Itinerary, ItinerarySection } from './api';
  import { fmtTime } from './format';
  import TransitBadge from './TransitBadge.svelte';

  let { itinerary, open = $bindable(false) }: { itinerary: Itinerary; open?: boolean } = $props();

  const STATUS: Record<string, string> = {
    SIGNIFICANT_DELAYS: 'Retards',
    REDUCED_SERVICE: 'Service réduit',
    NO_SERVICE: 'Interruption',
    DETOUR: 'Déviation',
    MODIFIED_SERVICE: 'Service modifié',
  };
  const statusLabel = $derived(itinerary.status ? (STATUS[itinerary.status] ?? 'Perturbations') : null);

  // Résumé : on masque les attentes et les marches très courtes
  const ribbon = $derived(
    itinerary.sections.filter((s) => s.type === 'transit' || (s.type !== 'wait' && s.duration_minutes >= 1)),
  );

  const fmtDuration = (min: number) => (min < 60 ? `${min} min` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}`);
  const fmtDistance = (m: number | null) => (m == null ? '' : m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`);
  const intermediate = (s: ItinerarySection) => Math.max(0, s.stops.length - 2);
</script>

<article class="card" class:open>
  <button class="summary" onclick={() => (open = !open)} aria-expanded={open}>
    <div class="top">
      <span class="times">{fmtTime(itinerary.departure)} <span class="arrow">→</span> {fmtTime(itinerary.arrival)}</span>
      <span class="duration">{fmtDuration(itinerary.duration_minutes)}</span>
    </div>
    <div class="ribbon">
      {#each ribbon as s, i (i)}
        {#if i > 0}<span class="sep" aria-hidden="true">›</span>{/if}
        {#if s.type === 'transit' && s.line}
          <TransitBadge line={s.line} compact />
        {:else}
          <span class="walk" title="Marche {s.duration_minutes} min">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="13" cy="4" r="2" /><path d="m9 20 3-6 3 3v4M6 12l3-4 4 1 3 3M10 8l-1 6" /></svg>
            {s.duration_minutes}
          </span>
        {/if}
      {/each}
    </div>
    <div class="meta">
      <span>{itinerary.transfers === 0 ? 'Sans correspondance' : `${itinerary.transfers} correspondance${itinerary.transfers > 1 ? 's' : ''}`}</span>
      <span>{itinerary.walking_minutes} min à pied{itinerary.walking_distance_m ? ` (${fmtDistance(itinerary.walking_distance_m)})` : ''}</span>
      {#if statusLabel}<span class="warn">⚠ {statusLabel}</span>{/if}
    </div>
  </button>

  {#if open}
    <ol class="steps">
      {#each itinerary.sections as s, i (i)}
        {#if s.type === 'transit' && s.line}
          <li class="step transit" style:--line={s.line.color ?? 'var(--muted)'}>
            <div class="row">
              <time>{fmtTime(s.departure)}</time>
              <strong>{s.from_name}</strong>
            </div>
            <div class="ride">
              <div class="ride-head">
                <TransitBadge line={s.line} />
                <span>Direction <b>{s.direction ?? '?'}</b></span>
              </div>
              <small>
                {#if s.headsign}<span class="mission">{s.headsign}</span> ·{/if}
                {intermediate(s)} arrêt{intermediate(s) > 1 ? 's' : ''} · {fmtDuration(s.duration_minutes)}
                {#if s.delay_minutes > 0}<span class="late">· +{s.delay_minutes} min</span>{/if}
              </small>
              {#if intermediate(s) > 0}
                <details>
                  <summary>Voir les arrêts</summary>
                  <ul>
                    {#each s.stops.slice(1, -1) as stop, j (j)}<li>{stop}</li>{/each}
                  </ul>
                </details>
              {/if}
            </div>
            <div class="row">
              <time>{fmtTime(s.arrival)}</time>
              <strong>{s.to_name}</strong>
            </div>
          </li>
        {:else if s.type === 'wait'}
          <li class="step minor">Attente {fmtDuration(s.duration_minutes)}</li>
        {:else}
          <li class="step walk-step">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="13" cy="4" r="2" /><path d="m9 20 3-6 3 3v4M6 12l3-4 4 1 3 3M10 8l-1 6" /></svg>
            <span>
              {s.type === 'transfer' ? 'Correspondance à pied' : 'Marche'}
              {fmtDuration(s.duration_minutes)}{s.distance_m ? ` (${fmtDistance(s.distance_m)})` : ''}
              {#if s.to_name}jusqu'à <b>{s.to_name}</b>{/if}
            </span>
          </li>
        {/if}
      {/each}
      <li class="step end">
        <time>{fmtTime(itinerary.arrival)}</time>
        <strong>Arrivée</strong>
        {#if itinerary.co2_grams != null}<small>{Math.round(itinerary.co2_grams)} g CO₂</small>{/if}
      </li>
    </ol>
  {/if}
</article>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  .card.open {
    border-color: var(--accent);
  }
  .summary {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    padding: 0.9rem 1.1rem;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .summary:hover {
    background: var(--hover);
  }
  .top {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1rem;
  }
  .times {
    font-size: 1.2rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
  }
  .arrow {
    color: var(--muted);
    font-weight: 400;
  }
  .duration {
    font-weight: 700;
    white-space: nowrap;
  }
  .ribbon {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .sep {
    color: var(--muted);
  }
  .walk {
    display: inline-flex;
    align-items: center;
    gap: 0.1rem;
    font-size: 0.85rem;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  svg {
    width: 1.1rem;
    height: 1.1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    flex-shrink: 0;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem 0.9rem;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .warn {
    color: var(--warn);
    font-weight: 600;
  }
  .steps {
    list-style: none;
    margin: 0;
    padding: 0.5rem 1.1rem 1rem;
    border-top: 1px solid var(--border);
  }
  .step {
    position: relative;
    padding: 0.45rem 0 0.45rem 0;
  }
  .row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }
  time {
    width: 3rem;
    flex-shrink: 0;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .transit .ride {
    margin: 0.35rem 0 0.35rem 1.35rem;
    padding: 0.2rem 0 0.2rem 1.4rem;
    border-left: 4px solid var(--line);
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .ride-head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .ride small {
    color: var(--muted);
  }
  .mission {
    font-family: ui-monospace, monospace;
    font-weight: 600;
  }
  .late {
    color: var(--warn);
    font-weight: 600;
  }
  details {
    font-size: 0.85rem;
    color: var(--muted);
  }
  summary {
    cursor: pointer;
    color: var(--accent);
  }
  details ul {
    margin: 0.3rem 0 0;
    padding-left: 1.1rem;
  }
  .walk-step,
  .minor {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: 3.75rem;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .walk-step b {
    color: var(--text);
    font-weight: 600;
  }
  .minor {
    padding-left: 1.6rem;
    font-style: italic;
  }
  .end {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }
  .end small {
    margin-left: auto;
    color: var(--muted);
  }
</style>
