const timeFmt = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });

export const fmtTime = (iso: string | null | undefined) => (iso ? timeFmt.format(new Date(iso)) : '');

export const minutesUntil = (iso: string, now: number) =>
  Math.max(0, Math.floor((new Date(iso).getTime() - now) / 60_000));

export function updatedLabel(iso: string, now: number) {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return s < 60 ? "à l'instant" : `il y a ${Math.floor(s / 60)} min`;
}

export const journeyTitle = (j: { name: string | null; origin: { name: string }; destination: { name: string } }) =>
  j.name ?? `${j.origin.name} → ${j.destination.name}`;
