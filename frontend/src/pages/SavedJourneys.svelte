<script lang="ts">
  import { listJourneys, listSavedItineraries, type SavedItinerary, type SavedJourney } from '../lib/api';
  import { journeyTitle } from '../lib/format';
  import SavedJourneyCard from './SavedJourneyCard.svelte';

  let journeys = $state<SavedJourney[] | null>(null);
  let itineraries = $state<SavedItinerary[] | null>(null);
  let error = $state<string | null>(null);

  $effect(() => {
    Promise.all([listJourneys(), listSavedItineraries()])
      .then(([j, it]) => ([journeys, itineraries] = [j, it]))
      .catch((e) => (error = (e as Error).message));
  });
</script>

<h1>Mes trajets</h1>

{#if error}
  <p class="state error">Impossible de charger les trajets : {error}</p>
{:else if !journeys || !itineraries}
  <p class="state">Chargement…</p>
{:else}
  <section>
    <div class="head">
      <h2>Itinéraires</h2>
      <a class="add" href="#/itineraire">+ Nouvel itinéraire</a>
    </div>
    {#if !itineraries.length}
      <div class="empty">
        <p>Aucun itinéraire sauvegardé.</p>
        <p class="muted">Calculez un itinéraire entre deux adresses puis sauvegardez-le pour le retrouver ici.</p>
      </div>
    {:else}
      <ul>
        {#each itineraries as it (it.id)}
          <li>
            <a class="it-card" href="#/itineraires/{it.id}">
              <strong>{journeyTitle(it)}</strong>
              <span class="route">
                <span class="dot"></span>{it.origin.name}
              </span>
              <span class="route">
                <span class="dot end"></span>{it.destination.name}
              </span>
              <span class="go">Voir les itinéraires →</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section>
    <div class="head">
      <h2>Trajets directs en train</h2>
      <a class="add" href="#/trajet">+ Nouveau trajet</a>
    </div>
    {#if !journeys.length}
      <div class="empty">
        <p>Aucun trajet sauvegardé.</p>
        <p class="muted">Enregistrez vos trajets habituels pour voir d'un coup d'œil le prochain train direct.</p>
      </div>
    {:else}
      <ul>
        {#each journeys as journey (journey.id)}
          <li><SavedJourneyCard {journey} /></li>
        {/each}
      </ul>
    {/if}
  </section>
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
  section {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  h2 {
    margin: 0;
    font-size: 1.05rem;
  }
  .it-card {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 1rem 1.1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
    color: var(--text);
    text-decoration: none;
  }
  .it-card:hover {
    border-color: var(--accent);
  }
  .route {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .dot {
    width: 0.6rem;
    height: 0.6rem;
    flex-shrink: 0;
    border-radius: 50%;
    border: 2px solid var(--accent);
  }
  .dot.end {
    background: var(--accent);
  }
  .go {
    margin-top: 0.3rem;
    color: var(--accent);
    font-weight: 600;
    font-size: 0.9rem;
  }
  .add {
    display: inline-block;
    padding: 0.45rem 0.8rem;
    font-size: 0.9rem;
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
  .muted {
    color: var(--muted);
  }
</style>
