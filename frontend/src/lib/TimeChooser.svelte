<script lang="ts" module>
  export type TimeMode = 'now' | 'departure' | 'arrival';

  /** Valeur pour <input type="datetime-local"> : heure locale, arrondie aux 5 minutes. */
  export function nowLocal() {
    const d = new Date();
    d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
</script>

<script lang="ts">
  // `when` n'est mis à jour qu'à la validation du champ (pas à chaque frappe) pour ne pas
  // déclencher une recherche (et consommer le quota) à chaque modification
  let { mode = $bindable('now'), when = $bindable(nowLocal()) }: { mode?: TimeMode; when?: string } = $props();

  // svelte-ignore state_referenced_locally
  let draft = $state(when);

  const MODES: [TimeMode, string][] = [
    ['now', 'Maintenant'],
    ['departure', 'Partir à'],
    ['arrival', 'Arriver à'],
  ];
</script>

<div class="when">
  <div class="segmented" role="radiogroup" aria-label="Horaire">
    {#each MODES as [value, label] (value)}
      <button type="button" role="radio" aria-checked={mode === value} class:on={mode === value} onclick={() => (mode = value)}>
        {label}
      </button>
    {/each}
  </div>
  {#if mode !== 'now'}
    <input type="datetime-local" bind:value={draft} onchange={() => (when = draft)} aria-label="Date et heure" />
  {/if}
</div>

<style>
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
  input {
    font: inherit;
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text);
  }
</style>
