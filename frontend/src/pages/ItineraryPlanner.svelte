<script lang="ts">
  import { ApiError, createSavedItinerary, listSavedItineraries, type Place } from '../lib/api';
  import ItineraryResults from '../lib/ItineraryResults.svelte';
  import PlacePicker from '../lib/PlacePicker.svelte';
  import TimeChooser, { nowLocal, type TimeMode } from '../lib/TimeChooser.svelte';

  let {
    initial,
  }: {
    initial: { from: Place | null; to: Place | null; mode: TimeMode; when: string | null };
  } = $props();

  // svelte-ignore state_referenced_locally
  let origin = $state<Place | null>(initial.from);
  // svelte-ignore state_referenced_locally
  let destination = $state<Place | null>(initial.to);
  // svelte-ignore state_referenced_locally
  let mode = $state<TimeMode>(initial.mode);
  // svelte-ignore state_referenced_locally
  let when = $state(initial.when ?? nowLocal());

  let name = $state('');
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let existingId = $state<number | null>(null);

  const ready = $derived(!!origin && !!destination && origin.id !== destination.id);
  // « Ma position » change à chaque fois : on ne peut pas la sauvegarder telle quelle
  const usesPosition = $derived(origin?.type === 'position' || destination?.type === 'position');

  $effect(() => {
    syncUrl(origin, destination, mode, when);
    saveError = null;
    existingId = null;
  });

  function syncUrl(o: Place | null, d: Place | null, m: TimeMode, w: string) {
    const p = new URLSearchParams();
    if (o) p.set('from', o.id), p.set('fromName', o.name);
    if (d) p.set('to', d.id), p.set('toName', d.name);
    if (m !== 'now') p.set('mode', m), p.set('when', w);
    const hash = `#/itineraire${p.size ? `?${p}` : ''}`;
    if (location.hash !== hash) history.replaceState(null, '', hash);
  }

  function swap() {
    [origin, destination] = [destination, origin];
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    if (!origin || !destination) return;
    saving = true;
    saveError = null;
    try {
      const saved = await createSavedItinerary(origin, destination, name.trim() || null);
      location.hash = `#/itineraires/${saved.id}`;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const all = await listSavedItineraries().catch(() => []);
        existingId = all.find((s) => s.origin.id === origin?.id && s.destination.id === destination?.id)?.id ?? null;
        saveError = 'Cet itinéraire est déjà sauvegardé.';
      } else {
        saveError = (err as Error).message;
      }
    } finally {
      saving = false;
    }
  }
</script>

<section class="card form">
  <h1>Itinéraire</h1>
  <div class="pickers">
    <PlacePicker label="Départ" bind:place={origin} allowPosition autofocus={!origin} />
    <button type="button" class="swap" onclick={swap} disabled={!origin && !destination} aria-label="Inverser départ et arrivée" title="Inverser">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16M7 4 3 8M7 4l4 4M17 20V4M17 20l-4-4M17 20l4-4" /></svg>
    </button>
    <PlacePicker label="Arrivée" bind:place={destination} autofocus={!!origin && !destination} />
  </div>
  <TimeChooser bind:mode bind:when />
  {#if origin && destination && origin.id === destination.id}
    <p class="hint error">Choisissez deux lieux différents.</p>
  {/if}
</section>

{#if ready && origin && destination}
  <ItineraryResults from={origin.id} to={destination.id} {mode} {when} />

  <form class="card save" onsubmit={save}>
    {#if usesPosition}
      <p class="hint">Pour sauvegarder cet itinéraire, remplacez « Ma position » par une adresse.</p>
    {:else}
      <label>
        <span>Sauvegarder cet itinéraire <small>(nom facultatif)</small></span>
        <input bind:value={name} maxlength="80" placeholder="ex. Maison → Bureau" />
      </label>
      <button type="submit" disabled={saving}>{saving ? 'Sauvegarde…' : 'Sauvegarder'}</button>
    {/if}
    {#if saveError}
      <p class="hint error">
        {saveError}
        {#if existingId}<a href="#/itineraires/{existingId}">Voir l'itinéraire</a>{/if}
      </p>
    {/if}
  </form>
{/if}

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow);
  }
  .form {
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
    letter-spacing: -0.01em;
  }
  .pickers {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .swap {
    align-self: center;
    width: 2.4rem;
    height: 2.4rem;
    display: grid;
    place-items: center;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
  }
  .swap:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .swap svg {
    width: 1.1rem;
    height: 1.1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .save {
    padding: 1rem 1.25rem;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 0.75rem;
  }
  .save label {
    flex: 1 1 240px;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .save small {
    font-weight: 400;
    color: var(--muted);
  }
  .save input {
    font: inherit;
    font-weight: 400;
    padding: 0.65rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text);
  }
  .save input:focus {
    outline: 0;
    border-color: var(--accent);
  }
  .save button {
    font: inherit;
    font-weight: 700;
    padding: 0.7rem 1.1rem;
    border: 0;
    border-radius: 10px;
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
  }
  .save button:disabled {
    opacity: 0.6;
  }
  .hint {
    margin: 0;
    width: 100%;
    font-size: 0.9rem;
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
  .error a {
    color: var(--accent);
    margin-left: 0.4rem;
  }
</style>
