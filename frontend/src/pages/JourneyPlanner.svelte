<script lang="ts">
  import { untrack } from 'svelte';
  import {
    ApiError,
    createJourney,
    getNextTrains,
    getStation,
    listJourneys,
    type JourneyNext,
    type Station,
  } from '../lib/api';
  import JourneyTrains from '../lib/JourneyTrains.svelte';
  import LineBadge from '../lib/LineBadge.svelte';
  import StationPicker from '../lib/StationPicker.svelte';
  import { autoRefresh } from '../lib/refresh.svelte';

  let { fromId = null, toId = null }: { fromId?: string | null; toId?: string | null } = $props();

  let origin = $state<Station | null>(null);
  let destination = $state<Station | null>(null);
  let data = $state<JourneyNext | null>(null);
  let error = $state<string | null>(null);

  let name = $state('');
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let existingId = $state<number | null>(null);

  // Gares passées dans l'URL (#/trajet?from=…&to=…)
  $effect(() => {
    const [f, t] = [fromId, toId];
    untrack(() => {
      if (f && f !== origin?.id) getStation(f).then((s) => (origin = s)).catch(() => {});
      if (t && t !== destination?.id) getStation(t).then((s) => (destination = s)).catch(() => {});
    });
  });

  const ready = $derived(!!origin && !!destination && origin.id !== destination.id);
  const sameStation = $derived(!!origin && !!destination && origin.id === destination.id);

  // Recherche des trains dès que les deux gares sont choisies, puis toutes les 30 s
  $effect(() => {
    const o = origin?.id;
    const d = destination?.id;
    syncUrl(o, d);
    data = null;
    error = null;
    saveError = null;
    existingId = null;
    if (!o || !d || o === d) return;

    let stale = false;
    const stop = autoRefresh(async () => {
      try {
        const res = await getNextTrains(o, d, 6);
        if (!stale) [data, error] = [res, null];
      } catch (e) {
        if (!stale) error = (e as Error).message;
      }
    });
    return () => {
      stale = true;
      stop();
    };
  });

  function syncUrl(o?: string, d?: string) {
    const params = new URLSearchParams();
    if (o) params.set('from', o);
    if (d) params.set('to', d);
    const hash = `#/trajet${params.size ? `?${params}` : ''}`;
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
      const journey = await createJourney(origin.id, destination.id, name.trim() || null);
      location.hash = `#/trajets/${journey.id}`;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const all = await listJourneys().catch(() => []);
        existingId = all.find((j) => j.origin.id === origin?.id && j.destination.id === destination?.id)?.id ?? null;
        saveError = 'Ce trajet est déjà sauvegardé.';
      } else {
        saveError = (err as Error).message;
      }
    } finally {
      saving = false;
    }
  }
</script>

<section class="card form">
  <h1>Trajet direct</h1>
  <div class="pickers">
    <StationPicker label="Départ" bind:station={origin} placeholder="Gare de départ…" autofocus={!origin} />
    <button
      type="button"
      class="swap"
      onclick={swap}
      disabled={!origin && !destination}
      aria-label="Inverser départ et arrivée"
      title="Inverser"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16M7 4 3 8M7 4l4 4M17 20V4M17 20l-4-4M17 20l4-4" /></svg>
    </button>
    <StationPicker
      label="Arrivée"
      bind:station={destination}
      placeholder="Gare d'arrivée…"
      autofocus={!!origin && !destination}
    />
  </div>
  {#if sameStation}
    <p class="hint error">Choisissez deux gares différentes.</p>
  {/if}
</section>

{#if ready && origin && destination}
  <section class="card">
    <header>
      <h2>Prochains trains</h2>
      {#if data?.common_lines.length}
        <span class="lines">
          {#each data.common_lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
        </span>
      {/if}
    </header>
    <JourneyTrains {data} {error} />
  </section>

  {#if !data || data.common_lines.length}
    <form class="card save" onsubmit={save}>
      <label>
        <span>Nom du trajet <small>(facultatif)</small></span>
        <input bind:value={name} maxlength="80" placeholder="ex. Maison → Travail" />
      </label>
      <button type="submit" disabled={saving}>{saving ? 'Sauvegarde…' : 'Sauvegarder ce trajet'}</button>
      {#if saveError}
        <p class="hint error">
          {saveError}
          {#if existingId}<a href="#/trajets/{existingId}">Voir le trajet</a>{/if}
        </p>
      {/if}
    </form>
  {/if}
{/if}

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow);
    overflow: visible;
  }
  .form {
    padding: 1.25rem;
  }
  h1 {
    margin: 0 0 1rem;
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
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem 0.75rem;
  }
  h2 {
    margin: 0;
    font-size: 1.1rem;
  }
  .lines {
    display: flex;
    gap: 0.25rem;
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
    margin: 0.5rem 0 0;
    font-size: 0.9rem;
    width: 100%;
  }
  .error {
    color: var(--danger);
  }
  .error a {
    color: var(--accent);
    margin-left: 0.4rem;
  }
</style>
