// Couleurs officielles approximatives des lignes RER / Transilien
const COLORS: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#E3051C', fg: '#fff' },
  B: { bg: '#5291CE', fg: '#fff' },
  C: { bg: '#FFCD00', fg: '#000' },
  D: { bg: '#00814F', fg: '#fff' },
  E: { bg: '#C04191', fg: '#fff' },
  H: { bg: '#8D5E2A', fg: '#fff' },
  J: { bg: '#D5C900', fg: '#000' },
  K: { bg: '#9F9825', fg: '#fff' },
  L: { bg: '#CEADD2', fg: '#000' },
  N: { bg: '#00A092', fg: '#fff' },
  P: { bg: '#F0B600', fg: '#000' },
  R: { bg: '#E4B4D1', fg: '#000' },
  U: { bg: '#B6134C', fg: '#fff' },
  V: { bg: '#9F9825', fg: '#fff' },
  TER: { bg: '#4b5563', fg: '#fff' },
};

export function lineColor(name: string) {
  return COLORS[name] ?? { bg: '#6b7280', fg: '#fff' };
}

export const MODE_ORDER = ['RER', 'Transilien', 'TER'];
