<script lang="ts">
  import { deleteSavedItinerary, getSavedItinerary, renameSavedItinerary, type SavedItinerary } from '../lib/api';
  import { journeyTitle } from '../lib/format';
  import ItineraryResults from '../lib/ItineraryResults.svelte';
  import TimeChooser, { nowLocal, type TimeMode } from '../lib/TimeChooser.svelte';

  let { id }: { id: number } = $props();

  let itinerary = $state<SavedItinerary | null>(null);
  let notFound = $state(false);
  let mode = $state<TimeMode>('now');
  let when = $state(nowLocal());
  let editing = $state(false);
  let draftName = $state('');

  $effect(() => {
    const iid = id;
    itinerary = null;
    notFound = false;
    getSavedItinerary(iid)
      .then((it) => (itinerary = it))
      .catch(() => (notFound = true));
  });

  $effect(() => {
    if (itinerary) document.title = `${journeyTitle(itinerary)} · Itinéraire`;
  });

  // Lien vers la page Itinéraire avec ce trajet pré-rempli (pour le modifier ou l'inverser)
  function plannerLink(it: SavedItinerary, reverse = false) {
    const [o, d] = reverse ? [it.destination, it.origin] : [it.origin, it.destination];
    const p = new URLSearchParams({ from: o.id, fromName: o.name, to: d.id, toName: d.name });
    return `#/itineraire?${p}`;
  }

  function startEdit() {
    draftName = itinerary?.name ?? '';
    editing = true;
  }

  async function saveName(e: SubmitEvent) {
    e.preventDefault();
    itinerary = await renameSavedItinerary(id, draftName.trim() || null);
    editing = false;
  }

  async function remove() {
    if (!itinerary || !confirm(`Supprimer l'itinéraire « ${journeyTitle(itinerary)} » ?`)) return;
    await deleteSavedItinerary(id);
    location.hash = '#/trajets';
  }
</script>

<a class="back" href="#/trajets">← Mes trajets</a>

{#if notFound}
  <p class="notice">Cet itinéraire n'existe pas ou a été supprimé.</p>
{:else if itinerary}
  <section class="card">
    {#if editing}
      <form class="rename" onsubmit={saveName}>
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={draftName} maxlength="80" placeholder="Nom de l'itinéraire" autofocus />
        <button type="submit">OK</button>
        <button type="button" class="ghost" onclick={() => (editing = false)}>Annuler</button>
      </form>
    {:else}
      <h1>{journeyTitle(itinerary)}</h1>
    {/if}
    <ol class="route">
      <li><span class="dot"></span><strong>{itinerary.origin.name}</strong></li>
      <li><span class="dot end"></span><strong>{itinerary.destination.name}</strong></li>
    </ol>
    <TimeChooser bind:mode bind:when />
  </section>

  <ItineraryResults from={itinerary.origin.id} to={itinerary.destination.id} {mode} {when} />

  <div class="actions">
    <a href={plannerLink(itinerary, true)}>⇄ Itinéraire retour</a>
    <a href={plannerLink(itinerary)}>Modifier</a>
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
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
    letter-spacing: -0.01em;
  }
  .route {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    position: relative;
  }
  .route li {
    display: flex;
    align-items: center;
    gap: 0.7rem;
  }
  .route strong {
    font-weight: 600;
  }
  .dot {
    width: 0.75rem;
    height: 0.75rem;
    flex-shrink: 0;
    border-radius: 50%;
    border: 3px solid var(--accent);
    background: var(--surface);
  }
  .dot.end {
    background: var(--accent);
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
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 1rem;
  }
  .actions a {
    color: var(--accent);
    font-weight: 600;
    text-decoration: none;
  }
  .actions a + a {
    margin-right: auto;
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
