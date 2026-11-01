<script lang="ts">
  import { searchPlaces, type Place } from './api';
  import { forgetPlace, loadRecentPlaces, matchRecent, rememberPlace } from './recentPlaces';

  let {
    label,
    place = $bindable(null),
    placeholder = 'Adresse, gare, lieu…',
    allowPosition = false,
    autofocus = false,
  }: {
    label: string;
    place?: Place | null;
    placeholder?: string;
    allowPosition?: boolean;
    autofocus?: boolean;
  } = $props();

  const ICONS: Record<string, string> = {
    address: 'M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21Zm0-9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
    stop_area: 'M7 4h10a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Zm-3 7h16M8 21l2-3m6 3-2-3',
    poi: 'm12 3 2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3.1-5.4 3.1 1.2-6L3.3 9.3l6.1-.7Z',
    administrative_region: 'M4 21V8l8-5 8 5v13M9 21v-6h6v6',
    position: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v3m0 14v3M2 12h3m14 0h3',
  };

  const uid = $props.id();
  let query = $state('');
  let results = $state<Place[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let active = $state(0);
  let open = $state(false);
  let locating = $state(false);
  let input = $state<HTMLInputElement>();
  let recent = $state<Place[]>(loadRecentPlaces());

  // Suggestions : adresses déjà utilisées (locales, sans appel API) puis résultats de l'API
  const options = $derived.by(() => {
    const q = query.trim();
    if (q.length < 3) return recent.map((p) => ({ place: p, recent: true }));
    const local = matchRecent(recent, q);
    const ids = new Set(local.map((p) => p.id));
    return [
      ...local.map((p) => ({ place: p, recent: true })),
      ...results.filter((p) => !ids.has(p.id)).map((p) => ({ place: p, recent: false })),
    ];
  });

  // Anti-rebond plus long que pour les gares : chaque appel consomme le quota de l'API IDFM
  $effect(() => {
    const q = query.trim();
    if (q.length < 3) {
      results = [];
      error = null;
      loading = false;
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      loading = true;
      try {
        results = await searchPlaces(q, controller.signal);
        error = null;
        active = 0;
      } catch (e) {
        if ((e as Error).name !== 'AbortError') error = (e as Error).message;
      } finally {
        if (!controller.signal.aborted) loading = false;
      }
    }, 400);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  });

  $effect(() => {
    if (autofocus && !place) input?.focus();
  });

  function choose(p: Place) {
    recent = rememberPlace(p);
    place = p;
    query = '';
    results = [];
    open = false;
  }

  function locate() {
    if (!navigator.geolocation) {
      error = 'Géolocalisation non disponible sur cet appareil';
      return;
    }
    locating = true;
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        locating = false;
        const [lon, lat] = [coords.longitude.toFixed(5), coords.latitude.toFixed(5)];
        choose({ id: `${lon};${lat}`, name: 'Ma position', type: 'position', lat: +lat, lon: +lon });
      },
      () => {
        locating = false;
        error = 'Position introuvable (autorisation refusée ?)';
        open = true;
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  function forget(e: MouseEvent, id: string) {
    e.stopPropagation();
    recent = forgetPlace(id);
    input?.focus();
  }

  function onkeydown(e: KeyboardEvent) {
    if (!options.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      active = (active + 1) % options.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      active = (active - 1 + options.length) % options.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(options[active].place);
    } else if (e.key === 'Escape') {
      open = false;
    }
  }

  const showList = $derived(open && (query.trim().length >= 3 || !!error || options.length > 0));
  const showingRecentOnly = $derived(query.trim().length < 3);
</script>

<div class="picker">
  <span class="label">{label}</span>
  {#if place}
    <div class="chosen">
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[place.type] ?? ICONS.address} /></svg>
      <span class="name">
        <strong>{place.name}</strong>
        {#if place.city && !place.name.includes(place.city)}<small>{place.city}</small>{/if}
      </span>
      <button type="button" class="clear" onclick={() => (place = null)} aria-label="Changer ({label})">×</button>
    </div>
  {:else}
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
          aria-label="{label} : {placeholder}"
          role="combobox"
          aria-expanded={showList}
          aria-controls="{uid}-results"
          autocomplete="off"
          spellcheck="false"
        />
        {#if loading}<span class="spinner" aria-hidden="true"></span>{/if}
        {#if allowPosition}
          <button type="button" class="locate" onclick={locate} disabled={locating} title="Utiliser ma position">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.position} /></svg>
            <span>{locating ? '…' : 'Ma position'}</span>
          </button>
        {/if}
      </label>

      {#if showList}
        <ul id="{uid}-results" class="results" role="listbox">
          {#if error}
            <li class="empty error">{error}</li>
          {:else if !options.length && !loading}
            <li class="empty">Aucun résultat pour « {query.trim()} »</li>
          {/if}
          {#if showingRecentOnly && options.length}
            <li class="heading" role="presentation">Adresses récentes</li>
          {/if}
          {#each options as { place: p, recent: isRecent }, i (p.id)}
            <li role="option" aria-selected={i === active} class="option">
              <button
                type="button"
                class:active={i === active}
                onmouseenter={() => (active = i)}
                onclick={() => choose(p)}
              >
                {#if isRecent}
                  <svg class="icon recent" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
                {:else}
                  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[p.type] ?? ICONS.address} /></svg>
                {/if}
                <span class="name">
                  <strong>{p.name}</strong>
                  {#if p.city && !p.name.includes(p.city)}<small>{p.city}</small>{/if}
                </span>
              </button>
              {#if isRecent}
                <button type="button" class="forget" onclick={(e) => forget(e, p.id)} aria-label="Oublier {p.name}" title="Oublier">×</button>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .search {
    position: relative;
  }
  .field,
  .chosen {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0 0.6rem 0 1rem;
    min-height: 3.2rem;
    box-shadow: var(--shadow);
  }
  .field:focus-within {
    border-color: var(--accent);
  }
  .chosen {
    border-color: var(--accent);
  }
  svg {
    width: 1.2rem;
    height: 1.2rem;
    flex-shrink: 0;
    fill: none;
    stroke: var(--muted);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .chosen .icon {
    stroke: var(--accent);
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
    padding: 0.85rem 0;
  }
  .name {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    text-align: left;
  }
  .name strong {
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name small {
    color: var(--muted);
  }
  .clear {
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
    border: 0;
    border-radius: 8px;
    background: var(--hover);
    color: var(--text);
    font-size: 1.3rem;
    line-height: 1;
    cursor: pointer;
  }
  .locate {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface);
    color: var(--text);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.3rem 0.6rem;
    cursor: pointer;
  }
  .locate svg {
    width: 1rem;
    height: 1rem;
    stroke: var(--accent);
  }
  .spinner {
    width: 1rem;
    height: 1rem;
    flex-shrink: 0;
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
    gap: 0.7rem;
    padding: 0.6rem 0.75rem;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .results button.active {
    background: var(--hover);
  }
  .option {
    display: flex;
    align-items: center;
  }
  .heading {
    padding: 0.4rem 0.75rem 0.2rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .results .forget {
    width: 2rem;
    height: 2rem;
    flex-shrink: 0;
    justify-content: center;
    padding: 0;
    color: var(--muted);
    font-size: 1.1rem;
  }
  .results .forget:hover {
    color: var(--danger);
  }
  .icon.recent {
    stroke: var(--muted);
  }
  .empty {
    padding: 0.75rem;
    color: var(--muted);
  }
  .error {
    color: var(--danger);
  }
  @media (max-width: 420px) {
    .locate span {
      display: none;
    }
  }
</style>
