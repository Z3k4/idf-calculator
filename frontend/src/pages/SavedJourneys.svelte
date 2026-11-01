<script lang="ts">
  import { listJourneys, type SavedJourney } from '../lib/api';
  import SavedJourneyCard from './SavedJourneyCard.svelte';

  let journeys = $state<SavedJourney[] | null>(null);
  let error = $state<string | null>(null);

  $effect(() => {
    listJourneys()
      .then((j) => (journeys = j))
      .catch((e) => (error = (e as Error).message));
  });
</script>

<div class="head">
  <h1>Mes trajets</h1>
  <a class="add" href="#/trajet">+ Nouveau trajet</a>
</div>

{#if error}
  <p class="state error">Impossible de charger les trajets : {error}</p>
{:else if !journeys}
  <p class="state">Chargement…</p>
{:else if !journeys.length}
  <div class="empty">
    <p>Aucun trajet sauvegardé.</p>
    <p class="muted">Enregistrez vos trajets habituels pour voir d'un coup d'œil le prochain train direct.</p>
    <a class="add" href="#/trajet">Créer mon premier trajet</a>
  </div>
{:else}
  <ul>
    {#each journeys as journey (journey.id)}
      <li><SavedJourneyCard {journey} /></li>
    {/each}
  </ul>
{/if}

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
    letter-spacing: -0.01em;
  }
  .add {
    display: inline-block;
    padding: 0.55rem 0.9rem;
    border-radius: 10px;
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 700;
    text-decoration: none;
    white-space: nowrap;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.75rem;
  }
  .state {
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
  .empty {
    text-align: center;
    padding: 2.5rem 1rem;
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 18px;
  }
  .empty p {
    margin: 0 0 0.5rem;
  }
  .empty .add {
    margin-top: 0.75rem;
  }
  .muted {
    color: var(--muted);
  }
</style>
