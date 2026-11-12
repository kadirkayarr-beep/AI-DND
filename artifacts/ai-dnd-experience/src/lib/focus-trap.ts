/** The fields of an element that decide whether the browser gives it its own Tab stop. */
export type TabCandidate = { type?: string; name?: string; checked?: boolean };

/**
 * Browsers visit a radio group once: the checked radio, or the first when none is checked.
 * Keep only that one per named group, in document order, so a trap compares against real Tab stops.
 */
export function tabStops<T extends object>(elements: readonly T[]): T[] {
  const chosen = new Map<string, T & TabCandidate>();
  for (const element of elements as readonly (T & TabCandidate)[]) {
    if (element.type !== 'radio' || !element.name) continue;
    const current = chosen.get(element.name);
    if (!current || (element.checked && !current.checked)) chosen.set(element.name, element);
  }
  return (elements as readonly (T & TabCandidate)[]).filter((element) => element.type !== 'radio' || !element.name || chosen.get(element.name) === element);
}

/** Where Tab should wrap to, or null when the browser may move focus on its own. */
export function trapWrapTarget<T>(stops: readonly T[], active: unknown, shift: boolean): T | null {
  if (!stops.length) return null;
  const first = stops[0];
  const last = stops[stops.length - 1];
  if (shift && active === first) return last;
  if (!shift && active === last) return first;
  return null;
}
