<script lang="ts">
  import { getUsage, type ApiUsageToday, type UsageResponse } from '../lib/api';
  import BarChart, { type Series } from '../lib/BarChart.svelte';
  import { autoRefresh } from '../lib/refresh.svelte';

  const COLORS: Record<string, string> = { realtime: 'var(--series-1)', navitia: 'var(--series-2)' };
  const SHORT: Record<string, string> = { realtime: 'Temps réel', navitia: 'Calculateur' };
  const ENDPOINTS: Record<string, string> = {
    'stop-monitoring': 'Prochains passages',
    places: 'Recherche de lieux',
    journeys: 'Calcul d’itinéraire',
  };

  let days = $state(30);
  let data = $state<UsageResponse | null>(null);
  let error = $state<string | null>(null);

  $effect(() => {
    const d = days;
    return autoRefresh(async () => {
      try {
        data = await getUsage(d);
        error = null;
      } catch (e) {
        error = (e as Error).message;
      }
    }, 30_000);
  });

  const fmt = new Intl.NumberFormat('fr-FR');
  const dayFmt = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' });
  const timeFmt = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const apiKeys = $derived(data?.apis.map((a) => a.api) ?? []);

  // Historique : une série par API
  const dailyDays = $derived([...new Set(data?.daily.map((d) => d.day) ?? [])]);
  const dailySeries = $derived<Series[]>(
    apiKeys.map((api) => ({
      key: api,
      label: SHORT[api] ?? api,
      color: COLORS[api],
      values: dailyDays.map((day) => data!.daily.find((d) => d.day === day && d.api === api)?.calls ?? 0),
    })),
  );
  const dailyLabels = $derived(dailyDays.map((d) => dayFmt.format(new Date(`${d}T12:00:00`))));

  // Aujourd'hui, heure par heure
  const hours = Array.from({ length: 24 }, (_, h) => String(h));
  const hourlySeries = $derived<Series[]>(
    apiKeys.map((api) => ({
      key: api,
      label: SHORT[api] ?? api,
      color: COLORS[api],
      values: hours.map((h) => data!.hourly.find((r) => r.hour === +h && r.api === api)?.calls ?? 0),
    })),
  );

  const totalPeriod = $derived(
    (data?.daily ?? []).reduce((acc, d) => ({ calls: acc.calls + d.calls, hits: acc.hits + d.cache_hits }), {
      calls: 0,
      hits: 0,
    }),
  );

  function ratio(a: ApiUsageToday) {
    return a.quota ? Math.min(1, a.calls / a.quota) : 0;
  }
  function level(a: ApiUsageToday) {
    const r = a.quota ? a.calls / a.quota : 0;
    return r >= 1 ? 'danger' : r >= 0.8 ? 'warn' : 'ok';
  }
  function savedShare(a: ApiUsageToday) {
    const total = a.calls + a.cache_hits;
    return total ? Math.round((a.cache_hits / total) * 100) : 0;
  }
</script>

<div class="head">
  <div>
    <h1>Consommation des API IDFM</h1>
    <p class="muted">
      Appels envoyés à Île-de-France Mobilités par ce serveur. Les quotas sont remis à zéro chaque jour à minuit (heure de
      Paris).
    </p>
  </div>
</div>

{#if error && !data}
  <p class="notice">Impossible de charger la consommation : {error}</p>
{:else if !data}
  <p class="muted">Chargement…</p>
{:else}
  <section class="tiles" aria-label="Aujourd'hui">
    {#each data.apis as a (a.api)}
      <article class="tile">
        <header>
          <span class="swatch" style:background={COLORS[a.api]}></span>
          <span class="label">{a.label}</span>
        </header>
        <p class="value">
          {fmt.format(a.calls)}
          <small>
            {#if a.quota}/ {fmt.format(a.quota)} aujourd'hui{:else}appel{a.calls > 1 ? 's' : ''} aujourd'hui{/if}
          </small>
        </p>
        {#if a.quota}
          <div
            class="meter {level(a)}"
            role="meter"
            aria-valuemin="0"
            aria-valuemax={a.quota}
            aria-valuenow={a.calls}
            aria-label="Quota utilisé"
          >
            <span style:width="{ratio(a) * 100}%"></span>
          </div>
          <p class="sub">
            {#if level(a) === 'danger'}
              <span class="status danger">⛔ Quota atteint</span>
            {:else if level(a) === 'warn'}
              <span class="status warn">⚠ Plus que {fmt.format(a.remaining ?? 0)} appels</span>
            {:else}
              Reste <b>{fmt.format(a.remaining ?? 0)}</b> appels ({Math.round((1 - ratio(a)) * 100)} %)
            {/if}
          </p>
        {:else}
          <p class="sub muted">Pas de quota configuré (<code>IDF_QUOTA_REALTIME</code>)</p>
        {/if}
        <dl>
          <div>
            <dt>Évités par le cache</dt>
            <dd>{fmt.format(a.cache_hits)} <small>({savedShare(a)} %)</small></dd>
          </div>
          <div>
            <dt>Erreurs</dt>
            <dd class:bad={a.errors > 0}>{a.errors > 0 ? '⚠ ' : ''}{fmt.format(a.errors)}</dd>
          </div>
        </dl>
      </article>
    {/each}
  </section>

  <section class="card">
    <div class="card-head">
      <h2>Appels par jour</h2>
      <div class="segmented" role="radiogroup" aria-label="Période">
        {#each [7, 30, 90] as d (d)}
          <button role="radio" aria-checked={days === d} class:on={days === d} onclick={() => (days = d)}>{d} j</button>
        {/each}
      </div>
    </div>
    <p class="muted small">
      {fmt.format(totalPeriod.calls)} appels sur la période · {fmt.format(totalPeriod.hits)} requêtes servies par le cache
    </p>
    <BarChart
      categories={dailyDays}
      labels={dailyLabels}
      series={dailySeries}
      ariaLabel="Appels par jour et par API sur {days} jours"
    />
    <details>
      <summary>Voir le tableau</summary>
      <table>
        <thead>
          <tr><th>Jour</th>{#each apiKeys as api (api)}<th>{SHORT[api]}</th>{/each}</tr>
        </thead>
        <tbody>
          {#each [...dailyDays].reverse() as day (day)}
            <tr>
              <td>{dayFmt.format(new Date(`${day}T12:00:00`))}</td>
              {#each apiKeys as api (api)}
                <td class="num">{fmt.format(data.daily.find((d) => d.day === day && d.api === api)?.calls ?? 0)}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </details>
  </section>

  <section class="card">
    <h2>Aujourd'hui, heure par heure</h2>
    <BarChart categories={hours} labels={hours.map((h) => `${h}h`)} series={hourlySeries} height={150} ariaLabel="Appels par heure aujourd'hui" />
  </section>

  <section class="card">
    <h2>Détail par service (aujourd'hui)</h2>
    {#if !data.endpoints.length}
      <p class="muted">Aucun appel aujourd'hui.</p>
    {:else}
      <table>
        <thead><tr><th>Service</th><th class="num">Appels</th><th class="num">Erreurs</th><th class="num">Temps moyen</th></tr></thead>
        <tbody>
          {#each data.endpoints as e (e.api + e.endpoint)}
            <tr>
              <td><span class="swatch" style:background={COLORS[e.api]}></span> {ENDPOINTS[e.endpoint] ?? e.endpoint}</td>
              <td class="num">{fmt.format(e.calls)}</td>
              <td class="num" class:bad={e.errors > 0}>{fmt.format(e.errors)}</td>
              <td class="num">{fmt.format(e.avg_ms)} ms</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <section class="card">
    <h2>Derniers appels</h2>
    {#if !data.recent.length}
      <p class="muted">Aucun appel enregistré.</p>
    {:else}
      <table>
        <thead><tr><th>Heure</th><th>Service</th><th>Statut</th><th class="num">Durée</th></tr></thead>
        <tbody>
          {#each data.recent as c, i (i)}
            <tr>
              <td class="num">{timeFmt.format(new Date(c.at))}</td>
              <td><span class="swatch" style:background={COLORS[c.api]}></span> {ENDPOINTS[c.endpoint] ?? c.endpoint}</td>
              <td>
                {#if c.status === 200}
                  <span class="pill ok">✓ 200</span>
                {:else}
                  <span class="pill err">⚠ {c.status === 0 ? 'réseau' : c.status}</span>
                {/if}
              </td>
              <td class="num">{fmt.format(c.duration_ms)} ms</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
{/if}

<style>
  h1 {
    margin: 0 0 0.3rem;
    font-size: 1.4rem;
    letter-spacing: -0.01em;
  }
  h2 {
    margin: 0;
    font-size: 1.05rem;
  }
  .muted {
    color: var(--muted);
    margin: 0;
  }
  .small {
    font-size: 0.85rem;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 0.75rem;
  }
  .tile,
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow);
    padding: 1rem 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .tile header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .label {
    font-weight: 600;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .swatch {
    display: inline-block;
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 3px;
    flex-shrink: 0;
    vertical-align: baseline;
  }
  .value {
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.1;
  }
  .value small {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--muted);
  }
  .meter {
    height: 8px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    overflow: hidden;
  }
  .meter span {
    display: block;
    height: 100%;
    min-width: 2px;
    border-radius: 999px;
    background: var(--accent);
  }
  .meter.warn {
    background: color-mix(in srgb, var(--warn) 18%, transparent);
  }
  .meter.warn span {
    background: var(--warn);
  }
  .meter.danger {
    background: color-mix(in srgb, var(--danger) 18%, transparent);
  }
  .meter.danger span {
    background: var(--danger);
  }
  .sub {
    margin: 0;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .sub b {
    color: var(--text);
  }
  .status {
    font-weight: 600;
  }
  .status.warn {
    color: var(--warn);
  }
  .status.danger {
    color: var(--danger);
  }
  code {
    font-size: 0.8em;
  }
  dl {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
    margin: 0.2rem 0 0;
    padding-top: 0.6rem;
    border-top: 1px solid var(--border);
  }
  dt {
    font-size: 0.8rem;
    color: var(--muted);
  }
  dd {
    margin: 0;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  dd small {
    color: var(--muted);
    font-weight: 400;
  }
  .bad {
    color: var(--danger);
  }
  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
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
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.3rem 0.6rem;
    border-radius: 8px;
    cursor: pointer;
  }
  .segmented button.on {
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow);
  }
  details {
    font-size: 0.9rem;
  }
  summary {
    cursor: pointer;
    color: var(--accent);
    margin-bottom: 0.4rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  th {
    text-align: left;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--muted);
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 0.45rem 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  tbody tr:last-child td {
    border-bottom: 0;
  }
  .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .pill {
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 6px;
  }
  .pill.ok {
    background: var(--ok-soft);
    color: var(--ok);
  }
  .pill.err {
    background: var(--danger-soft);
    color: var(--danger);
  }
  .notice {
    padding: 0.7rem 0.9rem;
    border-radius: 10px;
    background: var(--danger-soft);
    color: var(--danger);
  }
</style>
