<script lang="ts">
  import type { TransitLine } from './api';

  let { line, compact = false }: { line: TransitLine; compact?: boolean } = $props();

  // Forme selon le mode, comme la signalétique IDFM : rond (métro, RER), rectangle (bus), etc.
  const shape = $derived.by(() => {
    const m = line.mode.toLowerCase();
    if (m.includes('métro') || m.includes('metro') || m.includes('rer')) return 'round';
    if (m.includes('tram')) return 'tram';
    return 'rect';
  });
</script>

<span class="badge {shape}" style:--line-bg={line.color ?? '#6b7280'} style:--line-fg={line.text_color ?? '#fff'} title={line.name ?? `${line.mode} ${line.code}`}>
  {#if !compact}<span class="mode">{line.mode}</span>{/if}
  <span class="code">{line.code}</span>
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .mode {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }
  .code {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.6rem;
    height: 1.6rem;
    padding: 0 0.35rem;
    background: var(--line-bg);
    color: var(--line-fg);
    font-weight: 800;
    font-size: 0.85rem;
    line-height: 1;
    border-radius: 5px;
  }
  .round .code {
    border-radius: 999px;
  }
  .tram .code {
    background: transparent;
    color: var(--text);
    border-top: 3px solid var(--line-bg);
    border-bottom: 3px solid var(--line-bg);
    border-radius: 0;
  }
</style>
