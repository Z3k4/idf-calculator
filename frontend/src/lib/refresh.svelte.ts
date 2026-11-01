import { untrack } from 'svelte';

/**
 * À appeler dans un $effect : charge tout de suite, puis toutes les `ms` millisecondes
 * (en pause quand l'onglet est caché, rechargé à son retour). Renvoie la fonction de nettoyage.
 */
export function autoRefresh(load: () => unknown, ms = 30_000) {
  untrack(load);
  const tick = () => !document.hidden && untrack(load);
  const timer = setInterval(tick, ms);
  document.addEventListener('visibilitychange', tick);
  return () => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', tick);
  };
}

/** Horloge réactive (rafraîchie toutes les 10 s) pour faire défiler les « dans X min ». */
export function createClock(ms = 10_000) {
  const clock = $state({ now: Date.now() });
  $effect(() => {
    const t = setInterval(() => (clock.now = Date.now()), ms);
    return () => clearInterval(t);
  });
  return clock;
}
