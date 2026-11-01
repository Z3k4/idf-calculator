<script lang="ts">
  import {
    getHome,
    listJourneys,
    listSavedItineraries,
    updateHome,
    type HomeItem,
    type SavedItinerary,
    type SavedJourney,
  } from '../lib/api';
  import { journeyTitle } from '../lib/format';
  import ItineraryWidget from '../lib/ItineraryWidget.svelte';
  import JourneyWidget from '../lib/JourneyWidget.svelte';

  type Ref = { kind: HomeItem['kind']; id: number };
  type Choice = Ref & { title: string; subtitle: string | null };

  let items = $state<HomeItem[] | null>(null);
  let error = $state<string | null>(null);

  // Mode personnalisation
  let editing = $state(false);
  let choices = $state<Choice[]>([]); // tous les trajets et itinéraires sauvegardés
  let selected = $state<Ref[]>([]); // sélection en cours, dans l'ordre
  let saving = $state(false);
  let saveError = $state<string | null>(null);

  $effect(() => {
    getHome()
      .then((r) => (items = r.items))
      .catch((e) => (error = (e as Error).message));
  });

  const key = (r: Ref) => `${r.kind}:${r.id}`;
  const isSelected = (c: Ref) => selected.some((s) => key(s) === key(c));
  const choiceOf = (r: Ref) => choices.find((c) => key(c) === key(r));

  function toChoice(kind: Ref['kind'], j: SavedJourney | SavedItinerary): Choice {
    return {
      kind,
      id: j.id,
      title: journeyTitle(j),
      subtitle: j.name ? `${j.origin.name} → ${j.destination.name}` : null,
    };
  }

  async function startEdit() {
    saveError = null;
    const [journeys, itineraries] = await Promise.all([listJourneys(), listSavedItineraries()]);
    choices = [
      ...itineraries.map((it) => toChoice('itinerary', it)),
      ...journeys.map((j) => toChoice('journey', j)),
    ];
    selected = (items ?? []).map(({ kind, id }) => ({ kind, id }));
    editing = true;
  }

  function toggle(c: Choice) {
    selected = isSelected(c) ? selected.filter((s) => key(s) !== key(c)) : [...selected, { kind: c.kind, id: c.id }];
  }

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= selected.length) return;
    const next = [...selected];
    [next[index], next[target]] = [next[target], next[index]];
    selected = next;
  }

  async function save() {
    saving = true;
    saveError = null;
    try {
      items = (await updateHome(selected)).items;
      editing = false;
    } catch (e) {
      saveError = (e as Error).message;
    } finally {
      saving = false;
    }
  }
</script>

<div class="head">
  <h1>Accueil</h1>
  {#if !editing && items}
    <button class="ghost" onclick={startEdit}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4" /></svg>
      Personnaliser
    </button>
  {/if}
</div>

{#if error}
  <p class="notice">Impossible de charger l'accueil : {error}</p>
{:else if !items}
  <p class="muted">Chargement…</p>
{:else if editing}
  <section class="card editor">
    <h2>Affichés sur l'accueil</h2>
    {#if !selected.length}
      <p class="muted">Rien pour l'instant : cochez des trajets ou itinéraires ci-dessous.</p>
    {:else}
      <ol class="order">
        {#each selected as ref, i (key(ref))}
          {@const c = choiceOf(ref)}
          <li>
            <span class="pos">{i + 1}</span>
            <span class="name">
              <span class="kind">{ref.kind === 'journey' ? 'Train direct' : 'Itinéraire'}</span>
              <strong>{c?.title ?? '?'}</strong>
            </span>
            <button class="icon" onclick={() => move(i, -1)} disabled={i === 0} aria-label="Monter">↑</button>
            <button class="icon" onclick={() => move(i, 1)} disabled={i === selected.length - 1} aria-label="Descendre">↓</button>
            <button class="icon" onclick={() => c && toggle(c)} aria-label="Retirer">×</button>
          </li>
        {/each}
      </ol>
    {/if}

    <h2>Trajets et itinéraires sauvegardés</h2>
    {#if !choices.length}
      <p class="muted">
        Aucun élément sauvegardé. Créez un <a href="#/itineraire">itinéraire</a> ou un <a href="#/trajet">trajet direct</a>
        puis sauvegardez-le.
      </p>
    {:else}
      <ul class="choices">
        {#each choices as c (key(c))}
          <li>
            <label>
              <input type="checkbox" checked={isSelected(c)} onchange={() => toggle(c)} />
              <span class="name">
                <span class="kind">{c.kind === 'journey' ? 'Train direct' : 'Itinéraire'}</span>
                <strong>{c.title}</strong>
                {#if c.subtitle}<small>{c.subtitle}</small>{/if}
              </span>
            </label>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="actions">
      {#if saveError}<p class="err">{saveError}</p>{/if}
      <button class="ghost" onclick={() => (editing = false)}>Annuler</button>
      <button class="primary" onclick={save} disabled={saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
    </div>
  </section>
{:else if !items.length}
  <div class="empty">
    <p><strong>Votre accueil est vide.</strong></p>
    <p class="muted">Choisissez les trajets et itinéraires sauvegardés à afficher ici pour voir d'un coup d'œil vos prochains départs.</p>
    <button class="primary" onclick={startEdit}>Choisir quoi afficher</button>
  </div>
{:else}
  <div class="grid">
    {#each items as item (key(item))}
      {#if item.kind === 'journey' && item.journey}
        <JourneyWidget journey={item.journey} />
      {:else if item.itinerary}
        <ItineraryWidget itinerary={item.itinerary} />
      {/if}
    {/each}
  </div>
{/if}

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
    letter-spacing: -0.01em;
  }
  h2 {
    margin: 0;
    font-size: 1rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 0.75rem;
    align-items: start;
  }
  button {
    font: inherit;
    font-weight: 600;
    border-radius: 10px;
    padding: 0.5rem 0.9rem;
    cursor: pointer;
  }
  .ghost {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .ghost svg {
    width: 1rem;
    height: 1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .primary {
    background: var(--accent);
    color: var(--on-accent);
    border: 0;
  }
  .primary:disabled {
    opacity: 0.6;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
    padding: 1.1rem;
  }
  .editor {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .order,
  .choices {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .order li {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--accent);
    border-radius: 10px;
    background: var(--accent-soft);
  }
  .pos {
    width: 1.5rem;
    text-align: center;
    font-weight: 700;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .name {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .name strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name small {
    color: var(--muted);
  }
  .kind {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
  }
  .icon {
    width: 2rem;
    height: 2rem;
    padding: 0;
    flex-shrink: 0;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 8px;
  }
  .icon:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .choices label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.55rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
  }
  .choices label:hover {
    background: var(--hover);
  }
  input[type='checkbox'] {
    width: 1.1rem;
    height: 1.1rem;
    accent-color: var(--accent);
    flex-shrink: 0;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
  }
  .err {
    margin: 0 auto 0 0;
    color: var(--danger);
  }
  .empty {
    text-align: center;
    padding: 2.5rem 1rem;
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 18px;
  }
  .empty p {
    margin: 0 0 0.5rem;
  }
  .empty .primary {
    margin-top: 0.75rem;
  }
  .muted {
    margin: 0;
    color: var(--muted);
  }
  .muted a {
    color: var(--accent);
  }
  .notice {
    padding: 0.7rem 0.9rem;
    border-radius: 10px;
    background: var(--danger-soft);
    color: var(--danger);
  }
</style>
