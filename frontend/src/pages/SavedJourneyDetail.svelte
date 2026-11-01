<script lang="ts">
  import {
    deleteJourney,
    getJourney,
    getJourneyNext,
    renameJourney,
    type JourneyNext,
    type SavedJourney,
  } from '../lib/api';
  import { journeyTitle } from '../lib/format';
  import JourneyTrains from '../lib/JourneyTrains.svelte';
  import LineBadge from '../lib/LineBadge.svelte';
  import { autoRefresh } from '../lib/refresh.svelte';

  let { id }: { id: number } = $props();

  let journey = $state<SavedJourney | null>(null);
  let notFound = $state(false);
  let data = $state<JourneyNext | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);

  let editing = $state(false);
  let draftName = $state('');

  $effect(() => {
    const jid = id;
    journey = null;
    notFound = false;
    data = null;
    getJourney(jid)
      .then((j) => (journey = j))
      .catch(() => (notFound = true));
  });

  async function load() {
    loading = true;
    try {
      data = await getJourneyNext(id, 8);
      error = null;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    id;
    return autoRefresh(load);
  });

  $effect(() => {
    if (journey) document.title = `${journeyTitle(journey)} · Prochains trains`;
  });

  function startEdit() {
    draftName = journey?.name ?? '';
    editing = true;
  }

  async function saveName(e: SubmitEvent) {
    e.preventDefault();
    journey = await renameJourney(id, draftName.trim() || null);
    editing = false;
  }

  async function remove() {
    if (!journey || !confirm(`Supprimer le trajet « ${journeyTitle(journey)} » ?`)) return;
    await deleteJourney(id);
    location.hash = '#/trajets';
  }
</script>

<a class="back" href="#/trajets">← Mes trajets</a>

{#if notFound}
  <p class="notice">Ce trajet n'existe pas ou a été supprimé.</p>
{:else if journey}
  <section class="card">
    <header>
      <div class="title">
        {#if editing}
          <form class="rename" onsubmit={saveName}>
            <!-- svelte-ignore a11y_autofocus -->
            <input bind:value={draftName} maxlength="80" placeholder="Nom du trajet" autofocus />
            <button type="submit">OK</button>
            <button type="button" class="ghost" onclick={() => (editing = false)}>Annuler</button>
          </form>
        {:else}
          <h1>{journeyTitle(journey)}</h1>
        {/if}
        {#if journey.name}
          <p class="route">
            <strong>{journey.origin.name}</strong> <span>→</span> <strong>{journey.destination.name}</strong>
          </p>
        {/if}
        <span class="lines">
          {#each journey.common_lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
        </span>
      </div>
      <button class="icon" onclick={load} disabled={loading} aria-label="Rafraîchir" title="Rafraîchir">
        <svg class:spinning={loading} viewBox="0 0 24 24" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
        </svg>
      </button>
    </header>
    <JourneyTrains {data} {error} onretry={load} />
  </section>

  <div class="actions">
    <a href="#/trajet?from={journey.destination.id}&to={journey.origin.id}">⇄ Trajet retour</a>
    {#if !editing}<button class="ghost" onclick={startEdit}>Renommer</button>{/if}
    <button class="ghost danger" onclick={remove}>Supprimer</button>
  </div>
{:else}
  <p class="muted">Chargement…</p>
{/if}

<style>
  .back {
    color: var(--muted);
    text-decoration: none;
    font-size: 0.9rem;
  }
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
    padding: 1.25rem 1.25rem 0.9rem;
  }
  .title {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-width: 0;
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
    letter-spacing: -0.01em;
  }
  .route {
    margin: 0;
    color: var(--muted);
  }
  .route strong {
    color: var(--text);
    font-weight: 600;
  }
  .lines {
    display: flex;
    gap: 0.25rem;
  }
  .rename {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .rename input {
    flex: 1 1 180px;
    font: inherit;
    font-size: 1.1rem;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--accent);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
  }
  button {
    font: inherit;
    border-radius: 8px;
    padding: 0.4rem 0.8rem;
    cursor: pointer;
    border: 0;
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 600;
  }
  .ghost {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .danger {
    color: var(--danger);
  }
  .icon {
    width: 2.4rem;
    height: 2.4rem;
    padding: 0;
    flex-shrink: 0;
    display: grid;
    place-items: center;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text);
  }
  .icon svg {
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
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }
  .actions a {
    margin-right: auto;
    color: var(--accent);
    font-weight: 600;
    text-decoration: none;
  }
  .notice {
    padding: 0.7rem 0.9rem;
    border-radius: 10px;
    background: var(--danger-soft);
    color: var(--danger);
  }
  .muted {
    color: var(--muted);
  }
</style>
