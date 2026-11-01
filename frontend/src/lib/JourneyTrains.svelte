<script lang="ts">
  import type { JourneyNext, JourneyTrain } from './api';
  import { fmtTime, minutesUntil, updatedLabel } from './format';
  import LineBadge from './LineBadge.svelte';
  import { createClock } from './refresh.svelte';

  // `data` absent = chargement en cours
  let { data, error = null, onretry }: { data: JourneyNext | null; error?: string | null; onretry?: () => void } =
    $props();

  const clock = createClock();

  const trains = $derived(
    (data?.trains ?? []).filter((t) => new Date(t.expected_departure).getTime() > clock.now - 60_000),
  );
  const cancelled = (t: JourneyTrain) => t.status === 'cancelled';
  // Train mis en avant : le premier qui circule réellement
  const firstIndex = $derived(trains.findIndex((t) => !cancelled(t)));
</script>

{#if data?.stale}
  <p class="banner warn">Temps réel momentanément indisponible : affichage des dernières données connues.</p>
{/if}

{#if error && !data}
  <div class="state error">
    <p>Impossible de charger les trains.</p>
    <small>{error}</small>
    {#if onretry}<button onclick={onretry}>Réessayer</button>{/if}
  </div>
{:else if !data}
  <ul class="list" aria-busy="true">
    {#each Array(3) as _, i (i)}<li class="row skeleton"></li>{/each}
  </ul>
{:else if !trains.length}
  <div class="state">{data.message ?? 'Aucun train direct annoncé pour le moment.'}</div>
{:else}
  <ul class="list">
    {#each trains as t, i (t.expected_departure + t.line.id + (t.train_number ?? t.destination))}
      <li class="row" class:first={i === firstIndex} class:cancelled={cancelled(t)}>
        <LineBadge line={t.line} />
        <div class="info">
          <strong class="times">
            {#if t.delay_minutes > 0 && !cancelled(t)}
              <s>{fmtTime(t.aimed_departure)}</s> <span class="late">{fmtTime(t.expected_departure)}</span>
            {:else}
              {fmtTime(t.expected_departure)}
            {/if}
            <span class="arrow">→</span>
            {fmtTime(t.expected_arrival)}
          </strong>
          <small>
            <span>Direction {t.destination}</span>
            {#if t.mission}<span class="mission">{t.mission}</span>{/if}
            {#if t.platform}<span>Voie {t.platform}</span>{/if}
          </small>
        </div>
        <div class="when">
          {#if cancelled(t)}
            <span class="tag danger">Supprimé</span>
          {:else if t.at_platform}
            <span class="tag ok">À quai</span>
          {:else if minutesUntil(t.expected_departure, clock.now) === 0}
            <span class="soon">Imminent</span>
          {:else}
            <span class="mins">{minutesUntil(t.expected_departure, clock.now)}<small> min</small></span>
          {/if}
          <small>trajet {t.duration_minutes} min{t.delay_minutes > 0 ? ` · +${t.delay_minutes}` : ''}</small>
        </div>
      </li>
    {/each}
  </ul>
{/if}

{#if data}
  <footer>
    Mis à jour {updatedLabel(data.updated_at, clock.now)}
    {#if error}· <span class="late">dernier rafraîchissement en échec</span>{/if}
  </footer>
{/if}

<style>
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
  .row.first {
    background: var(--accent-soft);
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
  .info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .times {
    font-size: 1.1rem;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .arrow {
    color: var(--muted);
    margin: 0 0.15rem;
  }
  .info small {
    display: flex;
    flex-wrap: wrap;
    gap: 0.1rem 0.6rem;
    color: var(--muted);
  }
  .mission {
    font-family: ui-monospace, monospace;
    font-weight: 600;
  }
  .when {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .when small {
    color: var(--muted);
    white-space: nowrap;
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
  .cancelled .times {
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
  .state p {
    margin: 0;
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
    .row,
    footer {
      padding-left: 1rem;
      padding-right: 1rem;
    }
    .row {
      gap: 0.7rem;
    }
    .times {
      font-size: 1rem;
    }
  }
</style>
