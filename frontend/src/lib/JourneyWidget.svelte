<script lang="ts">
  import { getJourneyNext, type JourneyNext, type SavedJourney } from './api';
  import { fmtTime, journeyTitle, minutesUntil } from './format';
  import LineBadge from './LineBadge.svelte';
  import { autoRefresh, createClock } from './refresh.svelte';

  /** Bloc d'accueil : les 3 prochains trains directs d'un trajet sauvegardé (rafraîchi toutes les 30 s). */
  let { journey }: { journey: SavedJourney } = $props();

  let next = $state<JourneyNext | null>(null);
  let error = $state(false);
  const clock = createClock();

  $effect(() => {
    const id = journey.id;
    return autoRefresh(async () => {
      try {
        next = await getJourneyNext(id, 6);
        error = false;
      } catch {
        error = true;
      }
    });
  });

  const trains = $derived(
    (next?.trains ?? []).filter((t) => new Date(t.expected_departure).getTime() > clock.now - 60_000).slice(0, 3),
  );
</script>

<article class="widget">
  <a class="head" href="#/trajets/{journey.id}">
    <span class="kind">Train direct</span>
    <strong>{journeyTitle(journey)}</strong>
    {#if journey.name}<small>{journey.origin.name} → {journey.destination.name}</small>{/if}
  </a>

  {#if trains.length}
    <ul>
      {#each trains as t (t.expected_departure + t.line.id + (t.train_number ?? t.destination))}
        <li class:cancelled={t.status === 'cancelled'}>
          <LineBadge line={t.line} size="sm" />
          <span class="times">
            {fmtTime(t.expected_departure)} → {fmtTime(t.expected_arrival)}
            {#if t.delay_minutes > 0 && t.status !== 'cancelled'}<span class="late">+{t.delay_minutes}</span>{/if}
          </span>
          <span class="when">
            {#if t.status === 'cancelled'}
              <span class="tag danger">Supprimé</span>
            {:else if t.at_platform}
              <span class="tag ok">À quai</span>
            {:else if minutesUntil(t.expected_departure, clock.now) === 0}
              <b class="soon">Imminent</b>
            {:else}
              <b>{minutesUntil(t.expected_departure, clock.now)}</b> min
            {/if}
          </span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="muted">
      {#if error}Temps réel indisponible{:else if next}{next.message ?? 'Aucun train direct annoncé'}{:else}Chargement…{/if}
    </p>
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
  .head {
    display: flex;
    flex-direction: column;
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
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
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
    white-space: nowrap;
  }
  .when {
    white-space: nowrap;
    color: var(--muted);
  }
  .when b {
    font-size: 1.1rem;
    color: var(--text);
  }
  .soon {
    color: var(--accent) !important;
    font-size: 0.95rem !important;
  }
  .late {
    color: var(--warn);
    font-weight: 600;
    margin-left: 0.2rem;
  }
  .cancelled .times {
    text-decoration: line-through;
    color: var(--muted);
  }
  .tag {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.1rem 0.45rem;
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
  .muted {
    margin: 0;
    color: var(--muted);
  }
</style>
