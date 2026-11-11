import { readMediaMatch, subscribeMediaMatch, type ReducedMotionWindow } from './reduced-motion.ts';

export const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)';

/** True when the system asks for a dark scheme; false (so 'system' falls to day) when the browser cannot tell. */
export function readPrefersDark(win: ReducedMotionWindow | null | undefined): boolean {
  return readMediaMatch(win, DARK_SCHEME_QUERY);
}

export function subscribePrefersDark(win: ReducedMotionWindow | null | undefined, onChange: () => void): () => void {
  return subscribeMediaMatch(win, DARK_SCHEME_QUERY, onChange);
}
