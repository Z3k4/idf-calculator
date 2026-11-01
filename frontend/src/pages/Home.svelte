<script lang="ts">
  import {
    createHomeGroup,
    deleteHomeGroup,
    getHome,
    listJourneys,
    listSavedItineraries,
    updateHomeGroup,
    type HomeGroup,
    type HomeItemRef,
    type SavedItinerary,
    type SavedJourney,
  } from '../lib/api';
  import { journeyTitle, scheduleLabel } from '../lib/format';
  import ItineraryWidget from '../lib/ItineraryWidget.svelte';
  import JourneyWidget from '../lib/JourneyWidget.svelte';

  type Choice = HomeItemRef & { title: string; subtitle: string | null };

  const STORAGE_KEY = 'home.group';

  let groups = $state<HomeGroup[] | null>(null);
  let currentId = $state<number | null>(readStoredGroup());
  let error = $state<string | null>(null);

  // Groupe affiché : celui choisi s'il existe encore, sinon le premier
  const current = $derived(groups?.find((g) => g.id === currentId) ?? groups?.[0] ?? null);

  // Mode personnalisation (du groupe affiché)
  let editing = $state(false);
  let draftName = $state('');
  let choices = $state<Choice[]>([]); // tous les trajets et itinéraires sauvegardés
  let selected = $state<HomeItemRef[]>([]); // sélection en cours, dans l'ordre
  let saving = $state(false);
  let saveError = $state<string | null>(null);

  // Création d'un groupe
  let creating = $state(false);
  let newName = $state('');

  $effect(() => {
    getHome()
      .then((r) => (groups = r.groups))
      .catch((e) => (error = (e as Error).message));
  });

  function readStoredGroup(): number | null {
    try {
      const v = Number(localStorage.getItem(STORAGE_KEY));
      return Number.isInteger(v) && v > 0 ? v : null;
    } catch {
      return null;
    }
  }

  function selectGroup(id: number) {
    if (editing) return;
    currentId = id;
    try {
      localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      /* stockage indisponible : le choix vaut pour cette visite seulement */
    }
  }

  function replaceGroup(group: HomeGroup) {
    groups = (groups ?? []).map((g) => (g.id === group.id ? group : g));
  }

  const key = (r: HomeItemRef) => `${r.kind}:${r.id}`;
  const isSelected = (c: HomeItemRef) => selected.some((s) => key(s) === key(c));
  const choiceOf = (r: HomeItemRef) => choices.find((c) => key(c) === key(r));

  function toChoice(kind: HomeItemRef['kind'], j: SavedJourney | SavedItinerary): Choice {
    const route = j.name ? `${j.origin.name} → ${j.destination.name}` : null;
    const sched = 'schedule' in j ? scheduleLabel(j.schedule) : null;
    return { kind, id: j.id, title: journeyTitle(j), subtitle: [route, sched].filter(Boolean).join(' · ') || null };
  }

  async function startEdit() {
    if (!current) return;
    saveError = null;
    creating = false;
    const [journeys, itineraries] = await Promise.all([listJourneys(), listSavedItineraries()]);
    choices = [
      ...itineraries.map((it) => toChoice('itinerary', it)),
      ...journeys.map((j) => toChoice('journey', j)),
    ];
    selected = current.items.map(({ kind, id }) => ({ kind, id }));
    draftName = current.name;
    editing = true;
  }

  function toggle(c: HomeItemRef) {
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
    if (!current) return;
    saving = true;
    saveError = null;
    try {
      const name = draftName.trim();
      replaceGroup(await updateHomeGroup(current.id, { items: selected, ...(name ? { name } : {}) }));
      editing = false;
    } catch (e) {
      saveError = (e as Error).message;
    } finally {
      saving = false;
    }
  }

  async function removeGroup() {
    if (!current || !groups || groups.length < 2) return;
    if (!confirm(`Supprimer le groupe « ${current.name} » ? Les trajets et itinéraires restent sauvegardés.`)) return;
    const id = current.id;
    saving = true;
    try {
      await deleteHomeGroup(id);
      groups = groups.filter((g) => g.id !== id);
      editing = false;
      selectGroup(groups[0].id);
    } catch (e) {
      saveError = (e as Error).message;
    } finally {
      saving = false;
    }
  }

  async function createGroup(e: SubmitEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    saving = true;
    try {
      const group = await createHomeGroup(name);
      groups = [...(groups ?? []), group];
      creating = false;
      newName = '';
      selectGroup(group.id);
      await startEdit(); // on enchaîne sur le choix des éléments du nouveau groupe
    } catch (err) {
      error = (err as Error).message;
    } finally {
      saving = false;
    }
  }
</script>

<div class="head">
  <h1>Accueil</h1>
  {#if !editing && current}
    <button class="ghost" onclick={startEdit}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4" /></svg>
      Personnaliser
    </button>
  {/if}
</div>

{#if groups && !editing}
  <div class="tabs" role="tablist" aria-label="Groupes">
    {#each groups as g (g.id)}
      <button
        role="tab"
        class="tab"
        class:active={g.id === current?.id}
        aria-selected={g.id === current?.id}
        onclick={() => selectGroup(g.id)}
      >
        {g.name}
        <span class="count">{g.items.length}</span>
      </button>
    {/each}
    {#if creating}
      <form class="new-group" onsubmit={createGroup}>
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={newName} maxlength="40" placeholder="Nom du groupe" autofocus />
        <button class="primary small" type="submit" disabled={saving || !newName.trim()}>Créer</button>
        <button class="icon" type="button" onclick={() => (creating = false)} aria-label="Annuler">×</button>
      </form>
    {:else}
      <button class="tab add" onclick={() => (creating = true)} title="Nouveau groupe">+ Groupe</button>
    {/if}
  </div>
{/if}

{#if error}
  <p class="notice">Impossible de charger l'accueil : {error}</p>
{:else if !groups || !current}
  <p class="muted">Chargement…</p>
{:else if editing}
  <section class="card editor">
    <label class="group-name">
      <span>Nom du groupe</span>
      <input bind:value={draftName} maxlength="40" placeholder="ex. Semaine, Week-end…" />
    </label>

    <h2>Affichés dans ce groupe</h2>
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
              {#if c?.subtitle}<small>{c.subtitle}</small>{/if}
            </span>
            <button class="icon" onclick={() => move(i, -1)} disabled={i === 0} aria-label="Monter">↑</button>
            <button class="icon" onclick={() => move(i, 1)} disabled={i === selected.length - 1} aria-label="Descendre">↓</button>
            <button class="icon" onclick={() => toggle(ref)} aria-label="Retirer">×</button>
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
      {#if groups.length > 1}
        <button class="ghost danger" onclick={removeGroup} disabled={saving}>Supprimer le groupe</button>
      {/if}
      {#if saveError}<p class="err">{saveError}</p>{/if}
      <span class="spacer"></span>
      <button class="ghost" onclick={() => (editing = false)}>Annuler</button>
      <button class="primary" onclick={save} disabled={saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
    </div>
  </section>
{:else if !current.items.length}
  <div class="empty">
    <p><strong>{groups.length > 1 ? `Le groupe « ${current.name} » est vide.` : 'Votre accueil est vide.'}</strong></p>
    <p class="muted">Choisissez les trajets et itinéraires sauvegardés à afficher ici pour voir d'un coup d'œil vos prochains départs.</p>
    <button class="primary" onclick={startEdit}>Choisir quoi afficher</button>
  </div>
{:else}
  <div class="grid">
    {#each current.items as item (`${current.id}:${key(item)}`)}
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
  .tabs {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    overflow-x: auto;
    padding-bottom: 0.15rem;
    scrollbar-width: thin;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
    padding: 0.4rem 0.8rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    font-size: 0.9rem;
    white-space: nowrap;
  }
  .tab:hover {
    background: var(--hover);
  }
  .tab.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .tab.add {
    border-style: dashed;
    color: var(--muted);
  }
  .count {
    font-size: 0.75rem;
    font-weight: 700;
    opacity: 0.7;
    font-variant-numeric: tabular-nums;
  }
  .new-group {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .new-group input,
  .group-name input {
    font: inherit;
    padding: 0.35rem 0.6rem;
    border: 1px solid var(--accent);
    border-radius: 8px;
    background: var(--bg);
    color: var(--text);
  }
  .new-group input {
    width: 10rem;
  }
  .group-name {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .group-name input {
    font-size: 1rem;
    font-weight: 400;
    max-width: 22rem;
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
  .danger {
    color: var(--danger);
  }
  .primary {
    background: var(--accent);
    color: var(--on-accent);
    border: 0;
  }
  .primary.small {
    padding: 0.35rem 0.7rem;
  }
  .primary:disabled,
  .ghost:disabled {
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
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
  }
  .spacer {
    flex: 1;
  }
  .err {
    margin: 0;
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
