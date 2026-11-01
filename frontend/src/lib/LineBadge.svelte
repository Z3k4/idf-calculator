<script lang="ts">
  import type { Line } from './api';
  import { lineColor } from './lines';

  let { line, size = 'md' }: { line: Line; size?: 'sm' | 'md' } = $props();
  const color = $derived(lineColor(line.name));
</script>

<span
  class="badge {size}"
  class:rer={line.mode === 'RER'}
  style:background={color.bg}
  style:color={color.fg}
  title="{line.mode} {line.name}"
>
  {line.name}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    border-radius: 6px;
    line-height: 1;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }
  .badge.rer {
    border-radius: 50%;
  }
  .md {
    min-width: 2rem;
    height: 2rem;
    font-size: 1rem;
    padding: 0 0.35rem;
  }
  .sm {
    min-width: 1.4rem;
    height: 1.4rem;
    font-size: 0.75rem;
    padding: 0 0.25rem;
  }
</style>
