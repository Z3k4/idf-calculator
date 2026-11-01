<script lang="ts" module>
  export type TimeMode = 'now' | 'departure' | 'arrival';

  /** Date (AAAA-MM-JJ) et heure (HH:MM) facultatives : vides = aujourd'hui / heure actuelle. */
  export interface TimeValue {
    date: string;
    time: string;
  }

  export const emptyTime = (): TimeValue => ({ date: '', time: '' });

  type Schedule = { mode: TimeMode; date: string | null; time: string | null };

  /** Horaire enregistré -> état du sélecteur. */
  export const fromSchedule = (s: Schedule): { mode: TimeMode; value: TimeValue } => ({
    mode: s.mode,
    value: { date: s.date ?? '', time: s.time ?? '' },
  });

  /** État du sélecteur -> horaire à enregistrer. */
  export const toSchedule = (mode: TimeMode, value: TimeValue): Schedule =>
    mode === 'now' ? { mode, date: null, time: null } : { mode, date: value.date || null, time: value.time || null };

  export const sameSchedule = (a: Schedule, b: Schedule) => a.mode === b.mode && a.date === b.date && a.time === b.time;

  /** Lit les paramètres d'URL (`date`, `time`, ou l'ancien `when` = AAAA-MM-JJTHH:MM). */
  export function timeFromParams(params: URLSearchParams): TimeValue {
    const legacy = params.get('when');
    if (legacy) {
      const [date = '', time = ''] = legacy.split('T');
      return { date, time: time.slice(0, 5) };
    }
    return { date: params.get('date') ?? '', time: params.get('time') ?? '' };
  }
</script>

<script lang="ts">
  let {
    mode = $bindable('now'),
    value = $bindable(emptyTime()),
  }: { mode?: TimeMode; value?: TimeValue } = $props();

  // Brouillons : la valeur n'est transmise qu'à la validation d'un champ (événement change),
  // pour ne pas lancer un calcul (et consommer le quota) à chaque chiffre tapé
  // svelte-ignore state_referenced_locally
  let draftDate = $state(value.date);
  // svelte-ignore state_referenced_locally
  let draftTime = $state(value.time);

  const MODES: [TimeMode, string][] = [
    ['now', 'Maintenant'],
    ['departure', 'Partir à'],
    ['arrival', 'Arriver à'],
  ];

  function commit() {
    value = { date: draftDate, time: draftTime };
  }

  function clear(field: 'date' | 'time') {
    if (field === 'date') draftDate = '';
    else draftTime = '';
    commit();
  }

  const todayIso = () => {
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  };
  const dayFmt = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

  // Résumé lisible de l'horaire qui sera utilisé
  const summary = $derived.by(() => {
    if (mode === 'now') return null;
    const verb = mode === 'departure' ? 'Départ' : 'Arrivée';
    if (!value.date && !value.time) return `${verb} maintenant`;
    // Même règle que l'API : une heure seule déjà passée désigne le lendemain
    const now = new Date();
    const currentHHMM = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const day = !value.date
      ? value.time && value.time < currentHHMM
        ? 'demain'
        : "aujourd'hui"
      : value.date === todayIso()
        ? "aujourd'hui"
        : `le ${dayFmt.format(new Date(`${value.date}T12:00:00`))}`;
    const hour = value.time ? `à ${value.time.replace(':', 'h')}` : "à l'heure actuelle";
    return `${verb} ${day} ${hour}`;
  });
</script>

<div class="chooser">
  <div class="segmented" role="radiogroup" aria-label="Horaire">
    {#each MODES as [m, label] (m)}
      <button type="button" role="radio" aria-checked={mode === m} class:on={mode === m} onclick={() => (mode = m)}>
        {label}
      </button>
    {/each}
  </div>

  {#if mode !== 'now'}
    <div class="fields">
      <label class="field">
        <span>Date</span>
        <span class="input">
          <input type="date" bind:value={draftDate} onchange={commit} aria-label="Date (facultative)" />
          {#if draftDate}<button type="button" class="clear" onclick={() => clear('date')} aria-label="Effacer la date">×</button>{/if}
        </span>
        <small>Vide : aujourd'hui (demain si l'heure est passée)</small>
      </label>
      <label class="field">
        <span>Heure</span>
        <span class="input">
          <input type="time" bind:value={draftTime} onchange={commit} aria-label="Heure (facultative)" />
          {#if draftTime}<button type="button" class="clear" onclick={() => clear('time')} aria-label="Effacer l'heure">×</button>{/if}
        </span>
        <small>Vide : heure actuelle</small>
      </label>
    </div>
    <p class="summary">{summary}</p>
  {/if}
</div>

<style>
  .chooser {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .segmented {
    align-self: flex-start;
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
  .fields {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .field small {
    font-weight: 400;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .input {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  input {
    font: inherit;
    font-weight: 400;
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
    color: var(--text);
    min-width: 0;
  }
  input:focus {
    outline: 0;
    border-color: var(--accent);
  }
  .clear {
    width: 1.8rem;
    height: 1.8rem;
    flex-shrink: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--muted);
    font-size: 1rem;
    line-height: 1;
    cursor: pointer;
  }
  .summary {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--accent);
  }
</style>
