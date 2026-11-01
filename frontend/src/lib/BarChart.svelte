<script lang="ts" module>
  export interface Series {
    key: string;
    label: string;
    color: string; // variable CSS, ex. var(--series-1)
    values: number[];
  }
</script>

<script lang="ts">
  /**
   * Histogramme en colonnes (empilées si plusieurs séries), en SVG.
   * Barres fines (≤ 24 px, extrémité arrondie de 4 px, carrées à la base), 2 px d'écart entre
   * segments, grille discrète, info-bulle au survol de chaque colonne, légende si ≥ 2 séries.
   */
  let {
    categories,
    labels = categories,
    series,
    height = 180,
    ariaLabel,
    unit = 'appel',
  }: {
    categories: string[];
    labels?: string[];
    series: Series[];
    height?: number;
    ariaLabel: string;
    unit?: string;
  } = $props();

  let width = $state(600);
  let hover = $state<number | null>(null);

  const M = { top: 8, right: 8, bottom: 22, left: 36 };
  const plotW = $derived(Math.max(10, width - M.left - M.right));
  const plotH = $derived(height - M.top - M.bottom);

  const totals = $derived(categories.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0)));

  // Graduations « rondes » : 1, 2, 5 × 10^n
  const ticks = $derived.by(() => {
    const max = Math.max(...totals, 0);
    if (max === 0) return [0, 1];
    const raw = max / 4;
    const pow = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? pow * 10;
    const top = Math.ceil(max / step) * step;
    return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  });
  const yMax = $derived(ticks[ticks.length - 1] || 1);
  const y = (v: number) => M.top + plotH - (v / yMax) * plotH;

  const band = $derived(plotW / Math.max(1, categories.length));
  const barW = $derived(Math.max(2, Math.min(24, band * 0.7)));
  const x = (i: number) => M.left + i * band + (band - barW) / 2;

  // N'afficher qu'une étiquette d'abscisse sur k pour éviter les chevauchements
  const labelEvery = $derived(Math.max(1, Math.ceil(categories.length / Math.max(1, Math.floor(plotW / 44)))));
  // La dernière catégorie (ex. aujourd'hui) est toujours étiquetée ; l'étiquette régulière
  // qui la précède est retirée si elle la toucherait
  const showLabel = (i: number) => {
    const last = categories.length - 1;
    if (i === last) return true;
    return i % labelEvery === 0 && last - i >= labelEvery * 0.75;
  };

  const GAP = 2;
  const R = 4;

  /** Segments empilés d'une colonne ; seul le segment du haut a l'extrémité arrondie. */
  function segments(i: number) {
    const out: { key: string; color: string; d: string }[] = [];
    let base = 0;
    const visible = series.filter((s) => (s.values[i] ?? 0) > 0);
    visible.forEach((s, k) => {
      const v = s.values[i];
      const y0 = y(base) - (k > 0 ? GAP : 0);
      const y1 = y(base + v);
      base += v;
      const h = y0 - y1;
      if (h <= 0.5) return;
      const isTop = k === visible.length - 1;
      out.push({ key: s.key, color: s.color, d: barPath(x(i), y1, barW, h, isTop ? Math.min(R, h, barW / 2) : 0) });
    });
    return out;
  }

  function barPath(x0: number, y0: number, w: number, h: number, r: number) {
    return r > 0
      ? `M${x0},${y0 + h}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + w - r}Q${x0 + w},${y0} ${x0 + w},${y0 + r}V${y0 + h}Z`
      : `M${x0},${y0 + h}V${y0}H${x0 + w}V${y0 + h}Z`;
  }

  const fmt = new Intl.NumberFormat('fr-FR');
  const plural = (n: number) => `${fmt.format(n)} ${unit}${n > 1 ? 's' : ''}`;

  const tipLeft = $derived(hover === null ? 0 : Math.min(Math.max(x(hover) + barW / 2, 70), width - 70));
  // Juste au-dessus de la colonne survolée
  const tipTop = $derived(hover === null ? 0 : y(totals[hover]) - 8);
</script>

<div class="chart">
  {#if series.length > 1}
    <ul class="legend">
      {#each series as s (s.key)}
        <li><span class="swatch" style:background={s.color}></span>{s.label}</li>
      {/each}
    </ul>
  {/if}

  <div class="plot" bind:clientWidth={width} role="img" aria-label={ariaLabel}>
    <svg {width} {height} viewBox="0 0 {width} {height}">
      {#each ticks as t (t)}
        <line class="grid" x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} />
        <text class="tick" x={M.left - 6} y={y(t)} dy="0.32em" text-anchor="end">{fmt.format(t)}</text>
      {/each}

      {#each categories as c, i (c)}
        {#if hover === i}<rect class="hover-band" x={M.left + i * band} y={M.top} width={band} height={plotH} />{/if}
        {#each segments(i) as seg (seg.key)}
          <path d={seg.d} fill={seg.color} />
        {/each}
        {#if showLabel(i)}
          <text class="tick" x={x(i) + barW / 2} y={height - 6} text-anchor="middle">{labels[i]}</text>
        {/if}
        <!-- Zone de survol plus large que la barre -->
        <rect
          class="hit"
          x={M.left + i * band}
          y={M.top}
          width={band}
          height={plotH}
          role="presentation"
          onmouseenter={() => (hover = i)}
          onmouseleave={() => (hover = null)}
        />
      {/each}
    </svg>

    {#if hover !== null}
      <div class="tooltip" style:left="{tipLeft}px" style:top="{tipTop}px">
        <strong>{labels[hover]}</strong>
        {#each series as s (s.key)}
          <span class="row"><span class="swatch" style:background={s.color}></span>{s.label} <b>{plural(s.values[hover] ?? 0)}</b></span>
        {/each}
        {#if series.length > 1}<span class="row total">Total <b>{plural(totals[hover])}</b></span>{/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .chart {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 1rem;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .legend li,
  .row {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }
  .swatch {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .plot {
    position: relative;
    width: 100%;
  }
  svg {
    display: block;
    overflow: visible;
  }
  .grid {
    stroke: var(--grid);
    stroke-width: 1;
    shape-rendering: crispEdges;
  }
  .tick {
    font-size: 11px;
    fill: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .hover-band {
    fill: var(--hover);
  }
  .hit {
    fill: transparent;
  }
  .tooltip {
    position: absolute;
    transform: translate(-50%, -100%);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.5rem 0.65rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: var(--shadow-lg);
    font-size: 0.8rem;
    white-space: nowrap;
    pointer-events: none;
    z-index: 5;
  }
  .tooltip b {
    margin-left: auto;
    padding-left: 0.75rem;
    font-variant-numeric: tabular-nums;
  }
  .total {
    border-top: 1px solid var(--border);
    padding-top: 0.2rem;
    margin-top: 0.1rem;
  }
</style>
