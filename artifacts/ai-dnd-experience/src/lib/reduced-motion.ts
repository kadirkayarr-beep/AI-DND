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

function queryOf(win: ReducedMotionWindow | null | undefined, query = REDUCED_MOTION_QUERY): ReducedMotionQuery | null {
  try {
    return win?.matchMedia?.(query) ?? null;
  } catch {
    return null;
  }
}

/** Current system preference; false when the browser cannot tell. */
export function readPrefersReducedMotion(win: ReducedMotionWindow | null | undefined): boolean {
  return readMediaMatch(win, REDUCED_MOTION_QUERY);
}

/** Same reading for any media query (the dark colour scheme uses it); false when the browser cannot tell. */
export function readMediaMatch(win: ReducedMotionWindow | null | undefined, query: string): boolean {
  return queryOf(win, query)?.matches === true;
}

/** Calls onChange when the system preference changes; returns the unsubscribe. Never throws. */
export function subscribePrefersReducedMotion(win: ReducedMotionWindow | null | undefined, onChange: () => void): () => void {
  return subscribeMediaMatch(win, REDUCED_MOTION_QUERY, onChange);
}

export function subscribeMediaMatch(win: ReducedMotionWindow | null | undefined, mediaQuery: string, onChange: () => void): () => void {
  const query = queryOf(win, mediaQuery);
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
