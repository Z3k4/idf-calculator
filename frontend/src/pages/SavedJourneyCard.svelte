<script lang="ts">
  import { getJourneyNext, type JourneyNext, type SavedJourney } from '../lib/api';
  import { fmtTime, journeyTitle, minutesUntil } from '../lib/format';
  import LineBadge from '../lib/LineBadge.svelte';
  import { autoRefresh, createClock } from '../lib/refresh.svelte';

  let { journey }: { journey: SavedJourney } = $props();

  let next = $state<JourneyNext | null>(null);
  let error = $state(false);
  const clock = createClock();

  $effect(() => {
    const id = journey.id;
    return autoRefresh(async () => {
      try {
        next = await getJourneyNext(id, 4);
        error = false;
      } catch {
        error = true;
      }
    });
  });

  // Prochain train non supprimé et pas encore parti
  const train = $derived(
    next?.trains.find(
      (t) => t.status !== 'cancelled' && new Date(t.expected_departure).getTime() > clock.now - 60_000,
    ),
  );
</script>

<a class="card" href="#/trajets/{journey.id}">
  <div class="head">
    <div class="title">
      <strong>{journeyTitle(journey)}</strong>
      {#if journey.name}<small>{journey.origin.name} → {journey.destination.name}</small>{/if}
    </div>
    <span class="lines">
      {#each journey.common_lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
    </span>
  </div>

  <div class="next">
    {#if train}
      <LineBadge line={train.line} size="sm" />
      <span class="when">
        {#if train.at_platform}À quai{:else if minutesUntil(train.expected_departure, clock.now) === 0}Imminent{:else}dans
          <b>{minutesUntil(train.expected_departure, clock.now)} min</b>{/if}
      </span>
      <span class="detail">
        {fmtTime(train.expected_departure)} → {fmtTime(train.expected_arrival)}
        {#if train.delay_minutes > 0}<span class="late">+{train.delay_minutes}</span>{/if}
      </span>
    {:else if error}
      <span class="muted">Temps réel indisponible</span>
    {:else if next}
      <span class="muted">{next.message ?? 'Aucun train direct annoncé'}</span>
    {:else}
      <span class="muted">Chargement…</span>
    {/if}
  </div>
</a>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem 1.1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
    color: var(--text);
    text-decoration: none;
    transition: border-color 0.15s;
  }
  .card:hover {
    border-color: var(--accent);
  }
  .head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }
  .title {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .title small {
    color: var(--muted);
  }
  .lines {
    display: flex;
    gap: 0.2rem;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .next {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border);
    font-variant-numeric: tabular-nums;
  }
  .when b {
    font-size: 1.1rem;
  }
  .detail {
    margin-left: auto;
    color: var(--muted);
  }
  .late {
    color: var(--warn);
    font-weight: 600;
  }
  .muted {
    color: var(--muted);
  }
</style>
