<script lang="ts">
  import type { Station } from './api';
  import LineBadge from './LineBadge.svelte';
  import StationSearch from './StationSearch.svelte';

  let {
    label,
    station = $bindable(null),
    placeholder,
    autofocus = false,
  }: { label: string; station?: Station | null; placeholder?: string; autofocus?: boolean } = $props();
</script>

<div class="picker">
  <span class="label">{label}</span>
  {#if station}
    <div class="chosen">
      <span class="name">
        <strong>{station.name}</strong>
        <small>{station.city}</small>
      </span>
      <span class="lines">
        {#each station.lines as line (line.id)}<LineBadge {line} size="sm" />{/each}
      </span>
      <button type="button" class="clear" onclick={() => (station = null)} aria-label="Changer de gare ({label})">
        ×
      </button>
    </div>
  {:else}
    <StationSearch onselect={(s) => (station = s)} {placeholder} {autofocus} />
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
  .chosen {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 14px;
    padding: 0.6rem 0.6rem 0.6rem 1rem;
    min-height: 3.2rem;
    box-shadow: var(--shadow);
  }
  .name {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .name strong {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .name small {
    color: var(--muted);
  }
  .lines {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem;
    justify-content: flex-end;
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
</style>
