<script lang="ts">
  import {
    deleteSavedItinerary,
    getSavedItinerary,
    renameSavedItinerary,
    updateSavedItinerary,
    type SavedItinerary,
  } from '../lib/api';
  import { journeyTitle } from '../lib/format';
  import ItineraryResults from '../lib/ItineraryResults.svelte';
  import TimeChooser, {
    emptyTime,
    fromSchedule,
    sameSchedule,
    toSchedule,
    type TimeMode,
    type TimeValue,
  } from '../lib/TimeChooser.svelte';

  let { id }: { id: number } = $props();

  let itinerary = $state<SavedItinerary | null>(null);
  let notFound = $state(false);
  let mode = $state<TimeMode>('now');
  let time = $state<TimeValue>(emptyTime());
  let editing = $state(false);
  let draftName = $state('');
  let savingSchedule = $state(false);
  let scheduleSaved = $state(false);

  $effect(() => {
    const iid = id;
    itinerary = null;
    notFound = false;
    getSavedItinerary(iid)
      .then((it) => {
        // Horaire enregistré appliqué avant l'affichage du sélecteur
        ({ mode, value: time } = fromSchedule(it.schedule));
        itinerary = it;
      })
      .catch(() => (notFound = true));
  });

  $effect(() => {
    if (itinerary) document.title = `${journeyTitle(itinerary)} · Itinéraire`;
  });

  // L'horaire affiché diffère-t-il de celui enregistré ?
  const scheduleChanged = $derived(!!itinerary && !sameSchedule(toSchedule(mode, time), itinerary.schedule));

  $effect(() => {
    // Masquer la confirmation dès qu'on retouche l'horaire
    mode;
    time;
    scheduleSaved = false;
  });

  async function saveSchedule() {
    savingSchedule = true;
    try {
      itinerary = await updateSavedItinerary(id, { schedule: toSchedule(mode, time) });
      scheduleSaved = true;
    } finally {
      savingSchedule = false;
    }
  }

  /**
   * Lien vers la page Itinéraire pré-remplie : en modification (edit=…, « Mettre à jour »)
   * ou pour créer l'itinéraire retour.
   */
  function plannerLink(it: SavedItinerary, reverse = false) {
    const [o, d] = reverse ? [it.destination, it.origin] : [it.origin, it.destination];
    const p = new URLSearchParams({ from: o.id, fromName: o.name, to: d.id, toName: d.name });
    if (!reverse) {
      p.set('edit', String(it.id));
      const schedule = toSchedule(mode, time);
      if (schedule.mode !== 'now') {
        p.set('mode', schedule.mode);
        if (schedule.date) p.set('date', schedule.date);
        if (schedule.time) p.set('time', schedule.time);
      }
    }
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
    <TimeChooser bind:mode bind:value={time} />
    {#if scheduleChanged}
      <div class="schedule-bar">
        <span>Horaire modifié</span>
        <button onclick={saveSchedule} disabled={savingSchedule}>
          {savingSchedule ? 'Enregistrement…' : 'Enregistrer cet horaire'}
        </button>
      </div>
    {:else if scheduleSaved}
      <p class="saved">✓ Horaire enregistré</p>
    {/if}
  </section>

  <ItineraryResults from={itinerary.origin.id} to={itinerary.destination.id} {mode} {time} />

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
  .schedule-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding: 0.6rem 0.75rem;
    border-radius: 10px;
    background: var(--accent-soft);
    font-size: 0.9rem;
    font-weight: 600;
  }
  .saved {
    margin: 0;
    color: var(--ok);
    font-weight: 600;
    font-size: 0.9rem;
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
