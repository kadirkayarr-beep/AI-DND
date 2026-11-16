// Plan part C: a small die on the Tür / Sınıf / Geçmiş steps. Client-side
// randomness only; the engine is not involved. Picks a different option than
// the current one when there is more than one, so re-rolling visibly changes it.
export function pickRandomKey(keys: string[], current: string, random: () => number = Math.random): string | null {
  if (keys.length === 0) return null;
  const pool = keys.length > 1 ? keys.filter(key => key !== current) : keys;
  const index = Math.min(pool.length - 1, Math.floor(random() * pool.length));
  return pool[index];
}
