<script lang="ts">
  import { getItineraries, type ItinerariesResponse, type Place } from '../lib/api';
  import ItineraryCard from '../lib/ItineraryCard.svelte';
  import PlacePicker from '../lib/PlacePicker.svelte';

  type Mode = 'now' | 'departure' | 'arrival';

  let {
    initial,
  }: {
    initial: { from: Place | null; to: Place | null; mode: Mode; when: string | null };
  } = $props();

  // Valeur pour <input type="datetime-local"> : heure locale, arrondie aux 5 minutes
  function nowLocal() {
    const d = new Date();
    d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // svelte-ignore state_referenced_locally
  let origin = $state<Place | null>(initial.from);
  // svelte-ignore state_referenced_locally
  let destination = $state<Place | null>(initial.to);
  // svelte-ignore state_referenced_locally
  let mode = $state<Mode>(initial.mode);
  // svelte-ignore state_referenced_locally
  let when = $state(initial.when ?? nowLocal());
  // Heure prise en compte (mise à jour à la validation du champ, pas à chaque frappe)
  // svelte-ignore state_referenced_locally
  let committedWhen = $state(when);

  let data = $state<ItinerariesResponse | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let openIndex = $state(0);
  let refreshKey = $state(0);

  const ready = $derived(!!origin && !!destination && origin.id !== destination.id);

  // Recherche automatique quand les lieux ou l'horaire changent (pas de rafraîchissement
  // périodique : le quota de l'API itinéraire IDFM est limité)
  $effect(() => {
    const [o, d, m, w] = [origin, destination, mode, committedWhen];
    refreshKey;
    syncUrl(o, d, m, w);
    if (!o || !d || o.id === d.id) {
      data = null;
      error = null;
      return;
    }
    let stale = false;
    loading = true;
    error = null;
    getItineraries(o.id, d.id, m === 'now' ? {} : { datetime: w, represents: m })
      .then((res) => {
        if (stale) return;
        data = res;
        openIndex = 0;
      })
      .catch((e) => {
        if (!stale) error = (e as Error).message;
      })
      .finally(() => {
        if (!stale) loading = false;
      });
    return () => {
      stale = true;
    };
  });

  function syncUrl(o: Place | null, d: Place | null, m: Mode, w: string) {
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

  function setMode(m: Mode) {
    mode = m;
    if (m !== 'now' && !when) when = committedWhen = nowLocal();
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

  <div class="when">
    <div class="segmented" role="radiogroup" aria-label="Horaire">
      {#each [['now', 'Maintenant'], ['departure', 'Partir à'], ['arrival', 'Arriver à']] as [value, label] (value)}
        <button
          type="button"
          role="radio"
          aria-checked={mode === value}
          class:on={mode === value}
          onclick={() => setMode(value as Mode)}
        >
          {label}
        </button>
      {/each}
    </div>
    {#if mode !== 'now'}
      <input
        type="datetime-local"
        bind:value={when}
        onchange={() => (committedWhen = when)}
        aria-label="Date et heure"
      />
    {/if}
  </div>

  {#if origin && destination && origin.id === destination.id}
    <p class="hint error">Choisissez deux lieux différents.</p>
  {/if}
</section>

{#if ready}
  <section class="results" aria-busy={loading}>
    <div class="results-head">
      <h2>{data?.itineraries.length ?? ''} itinéraire{(data?.itineraries.length ?? 0) > 1 ? 's' : ''}</h2>
      <button class="refresh" onclick={() => refreshKey++} disabled={loading}>
        {loading ? 'Recherche…' : 'Actualiser'}
      </button>
    </div>

    {#if error}
      <div class="state error">
        <p>Impossible de calculer l'itinéraire.</p>
        <small>{error}</small>
      </div>
    {:else if !data}
      {#each Array(3) as _, i (i)}<div class="skeleton"></div>{/each}
    {:else if !data.itineraries.length}
      <div class="state">{data.message ?? 'Aucun itinéraire trouvé.'}</div>
    {:else}
      <div class="list" class:dim={loading}>
        {#each data.itineraries as itinerary, i (i + itinerary.departure)}
          <ItineraryCard {itinerary} bind:open={() => openIndex === i, (v) => (openIndex = v ? i : -1)} />
        {/each}
      </div>
    {/if}
  </section>
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
  .when {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
  }
  .segmented {
    display: inline-flex;
    padding: 0.2rem;
    background: var(--hover);
    border-radius: 10px;
  }
  .segmented button {
    border: 0;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 0.9rem;
    font-weight: 600;
    padding: 0.4rem 0.75rem;
    border-radius: 8px;
    cursor: pointer;
  }
  .segmented button.on {
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow);
  }
  input[type='datetime-local'] {
    font: inherit;
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text);
    color-scheme: inherit;
  }
  .hint {
    margin: 0;
  }
  .error {
    color: var(--danger);
  }
  .results {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .results-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  h2 {
    margin: 0;
    font-size: 1rem;
    color: var(--muted);
    font-weight: 600;
  }
  .refresh {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 8px;
    padding: 0.35rem 0.8rem;
    font: inherit;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    transition: opacity 0.2s;
  }
  .dim {
    opacity: 0.55;
  }
  .skeleton {
    height: 6.5rem;
    border-radius: 16px;
    background: linear-gradient(90deg, var(--hover), var(--surface), var(--hover));
    background-size: 200% 100%;
    animation: shimmer 1.2s infinite;
  }
  @keyframes shimmer {
    to {
      background-position: -200% 0;
    }
  }
  .state {
    padding: 2rem 1rem;
    text-align: center;
    color: var(--muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
  }
  .state.error {
    color: var(--danger);
  }
  .state p {
    margin: 0 0 0.3rem;
  }
</style>
