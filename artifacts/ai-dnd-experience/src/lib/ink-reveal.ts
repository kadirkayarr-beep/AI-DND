import type { EffectsLevel, InkRevealSpeed } from './appearance-settings.ts';
import { effectIntensity } from './effect-registry.ts';

/** Delay between two words and the most a whole paragraph may take, per speed. 'instant' never animates. */
export const INK_STEP_MS: Record<InkRevealSpeed, number> = { slow: 90, normal: 45, fast: 20, instant: 0 };
export const INK_MAX_TOTAL_MS: Record<InkRevealSpeed, number> = { slow: 5000, normal: 3000, fast: 1500, instant: 0 };

/**
 * Per-word delay for a paragraph of `wordCount` words: the speed's step, shortened so a long paragraph stays inside its cap.
 * Effects level 'low' (Az) plays a reduced reveal: step and cap both scale by the level's intensity (0.4), so the whole
 * paragraph finishes in under half the time. 'off' never animates.
 */
export function inkStepMs(speed: InkRevealSpeed, wordCount: number, level: EffectsLevel = 'full'): number {
  const scale = effectIntensity(level);
  if (speed === 'instant' || wordCount <= 0 || scale === 0) return 0;
  return Math.min(INK_STEP_MS[speed] * scale, (INK_MAX_TOTAL_MS[speed] * scale) / wordCount);
}

export type InkPiece = { text: string; word: boolean };

/** Splits into words and the whitespace between them; joining the pieces gives back the exact input. */
export function splitInkPieces(text: string): InkPiece[] {
  return text.split(/(\s+)/).filter((piece) => piece !== '').map((piece) => ({ text: piece, word: !/^\s+$/.test(piece) }));
}

type EntryLike = { kind: string; text: string; live?: boolean };

/**
 * Index of the entry that just arrived and should be written out, or null. Only a short append to an
 * unchanged transcript counts (one turn adds the player line and the narration); a reload, an undo or any
 * rewrite is not an arrival and shows at once. An empty transcript is an arrival only when the last entry is
 * marked `live` (the opening of a new adventure, the first turn): loading a saved history into an empty
 * transcript looks the same in the data and must stay instant.
 */
export function freshInkIndex(previous: readonly EntryLike[], next: readonly EntryLike[]): number | null {
  if (previous.length === 0 && next[next.length - 1]?.live !== true) return null;
  if (next.length <= previous.length || next.length - previous.length > 2) return null;
  for (let i = 0; i < previous.length; i += 1) {
    if (previous[i].kind !== next[i].kind || previous[i].text !== next[i].text) return null;
  }
  const last = next.length - 1;
  return next[last].kind === 'narration' ? last : null;
}
