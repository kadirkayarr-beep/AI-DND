export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** The slice of MediaQueryList this module needs; lets tests pass a fake. */
export type ReducedMotionQuery = {
  matches: boolean;
  addEventListener(type: 'change', listener: () => void): void;
  removeEventListener(type: 'change', listener: () => void): void;
};

export type ReducedMotionWindow = { matchMedia?: (query: string) => ReducedMotionQuery };

function queryOf(win: ReducedMotionWindow | null | undefined): ReducedMotionQuery | null {
  try {
    return win?.matchMedia?.(REDUCED_MOTION_QUERY) ?? null;
  } catch {
    return null;
  }
}

/** Current system preference; false when the browser cannot tell. */
export function readPrefersReducedMotion(win: ReducedMotionWindow | null | undefined): boolean {
  return queryOf(win)?.matches === true;
}

/** Calls onChange when the system preference changes; returns the unsubscribe. */
export function subscribePrefersReducedMotion(win: ReducedMotionWindow | null | undefined, onChange: () => void): () => void {
  const query = queryOf(win);
  if (!query) return () => {};
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}
