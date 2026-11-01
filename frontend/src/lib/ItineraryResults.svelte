<script lang="ts">
  import { getItineraries, type ItinerariesResponse } from './api';
  import ItineraryCard from './ItineraryCard.svelte';
  import type { TimeMode } from './TimeChooser.svelte';

  // Pas de rafraîchissement périodique : le quota de l'API itinéraire IDFM est limité
  let { from, to, mode, when }: { from: string; to: string; mode: TimeMode; when: string } = $props();

  let data = $state<ItinerariesResponse | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);
  let openIndex = $state(0);
  let refreshKey = $state(0);

  $effect(() => {
    const [f, t, m, w] = [from, to, mode, when];
    refreshKey;
    let stale = false;
    loading = true;
    error = null;
    getItineraries(f, t, m === 'now' ? {} : { datetime: w, represents: m })
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

  const count = $derived(data?.itineraries.length ?? 0);
</script>

<section class="results" aria-busy={loading}>
  <div class="head">
    <h2>{data ? `${count} itinéraire${count > 1 ? 's' : ''}` : 'Recherche…'}</h2>
    <button class="refresh" onclick={() => refreshKey++} disabled={loading}>{loading ? 'Recherche…' : 'Actualiser'}</button>
  </div>

  {#if error}
    <div class="state error">
      <p>Impossible de calculer l'itinéraire.</p>
      <small>{error}</small>
    </div>
  {:else if !data}
    {#each Array(3) as _, i (i)}<div class="skeleton"></div>{/each}
  {:else if !count}
    <div class="state">{data.message ?? 'Aucun itinéraire trouvé.'}</div>
  {:else}
    <div class="list" class:dim={loading}>
      {#each data.itineraries as itinerary, i (i + itinerary.departure)}
        <ItineraryCard {itinerary} bind:open={() => openIndex === i, (v) => (openIndex = v ? i : -1)} />
      {/each}
    </div>
  {/if}
</section>

<style>
  .results {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .head {
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
