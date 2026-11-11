export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** The slice of MediaQueryList this module needs; lets tests pass a fake. Old Safari only has the legacy pair. */
export type ReducedMotionQuery = {
  matches: boolean;
  addEventListener?: (type: 'change', listener: () => void) => void;
  removeEventListener?: (type: 'change', listener: () => void) => void;
  addListener?: (listener: () => void) => void;
  removeListener?: (listener: () => void) => void;
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

/** Calls onChange when the system preference changes; returns the unsubscribe. Never throws. */
export function subscribePrefersReducedMotion(win: ReducedMotionWindow | null | undefined, onChange: () => void): () => void {
  const query = queryOf(win);
  if (!query) return () => {};
  try {
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', onChange);
      return () => { try { query.removeEventListener?.('change', onChange); } catch { /* nothing to undo */ } };
    }
    if (typeof query.addListener === 'function') {
      query.addListener(onChange);
      return () => { try { query.removeListener?.(onChange); } catch { /* nothing to undo */ } };
    }
  } catch {
    // A browser that rejects the subscription simply never reports changes.
  }
  return () => {};
}
