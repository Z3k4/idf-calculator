<script lang="ts">
  import { searchStations, type Station, type StationMatch } from './api';
  import LineBadge from './LineBadge.svelte';

  let {
    onselect,
    autofocus = false,
    placeholder = 'Rechercher une gare…',
  }: { onselect: (station: Station) => void; autofocus?: boolean; placeholder?: string } = $props();

  let query = $state('');
  let results = $state<StationMatch[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let active = $state(0);
  let open = $state(false);
  let input: HTMLInputElement;

  // Recherche avec anti-rebond (250 ms) et annulation de la requête précédente
  $effect(() => {
    const q = query.trim();
    if (q.length < 2) {
      results = [];
      error = null;
      loading = false;
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      loading = true;
      try {
        results = await searchStations(q, controller.signal);
        error = null;
        active = 0;
      } catch (e) {
        if ((e as Error).name !== 'AbortError') error = (e as Error).message;
      } finally {
        if (!controller.signal.aborted) loading = false;
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  });

  $effect(() => {
    if (autofocus) input?.focus();
  });

  function choose(station: Station) {
    onselect(station);
    query = '';
    results = [];
    open = false;
    input.blur();
  }

  function onkeydown(e: KeyboardEvent) {
    if (!results.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = (active + 1) % results.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active - 1 + results.length) % results.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(results[active].station);
    } else if (e.key === 'Escape') {
      open = false;
    }
  }

  const showList = $derived(open && query.trim().length >= 2);
</script>

<div class="search">
  <label class="field">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
    <input
      bind:this={input}
      bind:value={query}
      onfocus={() => (open = true)}
      onblur={() => setTimeout(() => (open = false), 150)}
      {onkeydown}
      type="search"
      {placeholder}
      aria-label={placeholder}
      role="combobox"
      aria-expanded={showList}
      aria-controls="station-results"
      autocomplete="off"
      spellcheck="false"
    />
    {#if loading}<span class="spinner" aria-hidden="true"></span>{/if}
  </label>

  {#if showList}
    <ul id="station-results" class="results" role="listbox">
      {#if error}
        <li class="empty error">{error}</li>
      {:else if !results.length && !loading}
        <li class="empty">Aucune gare trouvée pour « {query.trim()} »</li>
      {/if}
      {#each results as { station }, i (station.id)}
        <li role="option" aria-selected={i === active}>
          <button
            type="button"
            class:active={i === active}
            onmouseenter={() => (active = i)}
            onclick={() => choose(station)}
          >
            <span class="name">
              <strong>{station.name}</strong>
              <small>{station.city}</small>
            </span>
            <span class="lines">
              {#each station.lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .search {
    position: relative;
  }
  .field {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0 1rem;
    box-shadow: var(--shadow);
    transition: border-color 0.15s;
  }
  .field:focus-within {
    border-color: var(--accent);
  }
  svg {
    width: 1.2rem;
    height: 1.2rem;
    fill: none;
    stroke: var(--muted);
    stroke-width: 2;
    stroke-linecap: round;
    flex-shrink: 0;
  }
  input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: 1.05rem;
    padding: 0.95rem 0;
  }
  .spinner {
    width: 1rem;
    height: 1rem;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .results {
    position: absolute;
    z-index: 10;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    margin: 0;
    padding: 0.35rem;
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    box-shadow: var(--shadow-lg);
    max-height: 60vh;
    overflow-y: auto;
  }
  .results button {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.6rem 0.75rem;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .results button.active {
    background: var(--hover);
  }
  .name {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .name small {
    color: var(--muted);
  }
  .lines {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.25rem;
  }
  .empty {
    padding: 0.75rem;
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
</style>
