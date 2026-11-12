// Mirror of LEVEL_THRESHOLDS in ai-dnd/xp.py (a test fails if they drift). The server owns the XP total.
export const XP_THRESHOLDS: ReadonlyArray<readonly [number, number]> = [
  [1, 0], [2, 300], [3, 900], [4, 2700], [5, 6500],
];

export type XpProgress = { atTop: true; xp: number } | { atTop: false; xp: number; next: number; nextLevel: number; percent: number };

/** Progress toward the next level from the character's level and server XP total. */
export function xpProgress(xp: number, level: number): XpProgress {
  const current = XP_THRESHOLDS.find(([lvl]) => lvl === level);
  const next = XP_THRESHOLDS.find(([lvl]) => lvl === level + 1);
  if (!current || !next) return { atTop: true, xp };
  const span = next[1] - current[1];
  const percent = Math.max(0, Math.min(100, ((xp - current[1]) / span) * 100));
  return { atTop: false, xp, next: next[1], nextLevel: next[0], percent };
}

export const TOP_LEVEL_LABEL = 'En yüksek seviye';
