export type ReadingPreferences = {
  fontSizePx: number | null;
  lineHeight: number | null;
};

export type ReadingPreferenceStorage = Pick<Storage, 'getItem' | 'setItem'>;

export const DEFAULT_READING_PREFERENCES: ReadingPreferences = {
  fontSizePx: null,
  lineHeight: null,
};

const STORAGE_KEY = 'ai-dnd-reading-preferences-v1';

function availableStorage(storage?: ReadingPreferenceStorage | null): ReadingPreferenceStorage | null {
  if (storage !== undefined) return storage;
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function boundedNumber(value: unknown, min: number, max: number, integer = false): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) return null;
  return integer ? Math.round(value) : Math.round(value * 100) / 100;
}

export function readReadingPreferences(storage?: ReadingPreferenceStorage | null): ReadingPreferences {
  try {
    const serialized = availableStorage(storage)?.getItem(STORAGE_KEY);
    if (!serialized) return { ...DEFAULT_READING_PREFERENCES };
    const parsed: unknown = JSON.parse(serialized);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ...DEFAULT_READING_PREFERENCES };
    const values = parsed as Record<string, unknown>;
    return {
      fontSizePx: boundedNumber(values.fontSizePx, 18, 32, true),
      lineHeight: boundedNumber(values.lineHeight, 1.3, 2),
    };
  } catch {
    return { ...DEFAULT_READING_PREFERENCES };
  }
}

export function writeReadingPreferences(
  preferences: ReadingPreferences,
  storage?: ReadingPreferenceStorage | null,
): void {
  try {
    availableStorage(storage)?.setItem(STORAGE_KEY, JSON.stringify({
      fontSizePx: boundedNumber(preferences.fontSizePx, 18, 32, true),
      lineHeight: boundedNumber(preferences.lineHeight, 1.3, 2),
    }));
  } catch {
    // A blocked or full browser store must not interrupt play or the controls.
  }
}
