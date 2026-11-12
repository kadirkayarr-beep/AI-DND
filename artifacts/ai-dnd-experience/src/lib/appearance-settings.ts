import type { UnwThemeChoice } from './unw-theme.ts';

export type DiceSet = 'bone' | 'obsidian' | 'gilded';
export type HpGauge = 'seal' | 'ink';
export type SpellSlotStyle = 'candles' | 'inkwells';
export type EffectsLevel = 'off' | 'low' | 'full';
export type InkRevealSpeed = 'slow' | 'normal' | 'fast' | 'instant';

export type AppearanceSettings = {
  diceSet: DiceSet;
  hpGauge: HpGauge;
  spellSlots: SpellSlotStyle;
  theme: UnwThemeChoice;
  effectsLevel: EffectsLevel;
  fontScale: number;
  dyslexiaFont: boolean;
  highContrast: boolean;
  inkRevealSpeed: InkRevealSpeed;
};

export type AppearanceStorage = Pick<Storage, 'getItem' | 'setItem'>;

export const DEFAULT_APPEARANCE_SETTINGS: AppearanceSettings = {
  diceSet: 'bone',
  hpGauge: 'seal',
  spellSlots: 'candles',
  theme: 'night',
  effectsLevel: 'full',
  fontScale: 1,
  dyslexiaFont: false,
  highContrast: false,
  inkRevealSpeed: 'normal',
};

export const FONT_SCALE_MIN = 0.85;
export const FONT_SCALE_MAX = 1.5;

const STORAGE_KEY = 'ai-dnd-appearance-settings-v1';

function availableStorage(storage?: AppearanceStorage | null): AppearanceStorage | null {
  if (storage !== undefined) return storage;
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

function boundedScale(value: unknown, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < FONT_SCALE_MIN || value > FONT_SCALE_MAX) {
    return fallback;
  }
  return Math.round(value * 100) / 100;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function sanitize(values: Record<string, unknown>): AppearanceSettings {
  const d = DEFAULT_APPEARANCE_SETTINGS;
  return {
    diceSet: oneOf(values.diceSet, ['bone', 'obsidian', 'gilded'], d.diceSet),
    hpGauge: oneOf(values.hpGauge, ['seal', 'ink'], d.hpGauge),
    spellSlots: oneOf(values.spellSlots, ['candles', 'inkwells'], d.spellSlots),
    theme: oneOf(values.theme, ['night', 'day', 'system'], d.theme),
    effectsLevel: oneOf(values.effectsLevel, ['off', 'low', 'full'], d.effectsLevel),
    fontScale: boundedScale(values.fontScale, d.fontScale),
    dyslexiaFont: flag(values.dyslexiaFont, d.dyslexiaFont),
    highContrast: flag(values.highContrast, d.highContrast),
    inkRevealSpeed: oneOf(values.inkRevealSpeed, ['slow', 'normal', 'fast', 'instant'], d.inkRevealSpeed),
  };
}

export function readAppearanceSettings(storage?: AppearanceStorage | null): AppearanceSettings {
  try {
    const serialized = availableStorage(storage)?.getItem(STORAGE_KEY);
    if (!serialized) return { ...DEFAULT_APPEARANCE_SETTINGS };
    const parsed: unknown = JSON.parse(serialized);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { ...DEFAULT_APPEARANCE_SETTINGS };
    return sanitize(parsed as Record<string, unknown>);
  } catch {
    return { ...DEFAULT_APPEARANCE_SETTINGS };
  }
}

export function writeAppearanceSettings(
  settings: AppearanceSettings,
  storage?: AppearanceStorage | null,
): void {
  try {
    availableStorage(storage)?.setItem(STORAGE_KEY, JSON.stringify(sanitize({ ...settings })));
  } catch {
    // A blocked or full browser store must not interrupt play or the controls.
  }
}

/** Reduced motion forces effects off; otherwise the chosen level applies. */
export function resolveEffectsLevel(settings: AppearanceSettings, prefersReducedMotion: boolean): EffectsLevel {
  return prefersReducedMotion ? 'off' : settings.effectsLevel;
}

/** Separate from the level: whether any motion (not just colour tone) may play. */
export function motionAllowed(settings: AppearanceSettings, prefersReducedMotion: boolean): boolean {
  return !prefersReducedMotion && settings.effectsLevel !== 'off';
}
