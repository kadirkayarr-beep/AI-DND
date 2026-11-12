import type { EffectsLevel } from './appearance-settings.ts';

/*
 * Scene atmosphere: pure data and resolution. The page layer in
 * src/components/scene-atmosphere-layer.tsx only paints what resolveAtmosphere returns.
 * Inputs are engine facts only (campaign clock, scene.kind); nothing here reads or writes story text.
 * Table values are ported from the V4 prototype (UI_PROTOTIP_V4_20261111) for the place kinds
 * the engine can report today.
 */

export type DayPeriod = 'dawn' | 'morning' | 'afternoon' | 'evening' | 'night';
export type AtmospherePlaceKind = 'outdoor' | 'indoor';
export type AtmosphereTheme = 'night' | 'day';
/** [red, green, blue, alpha] with channels 0..255 and alpha 0..1. */
export type Rgba = readonly [number, number, number, number];

export const DAY_PERIODS: readonly DayPeriod[] = ['dawn', 'morning', 'afternoon', 'evening', 'night'];
export const ATMOSPHERE_PLACE_KINDS: readonly AtmospherePlaceKind[] = ['outdoor', 'indoor'];

/** Animated element budget: motes + fog bands stay under MAX_ACTIVE_EFFECTS (14) in effect-registry. */
export const MOTE_POOL = 10;
export const FOG_BANDS = 2;
/** Crossfade between presets, mirrored by the transition duration in scene-atmosphere-layer.css. */
export const CROSSFADE_MS = 1500;

/** Period starts in minutes after midnight; night wraps from 20:00 to 05:00. */
const PERIOD_STARTS: ReadonlyArray<readonly [DayPeriod, number]> = [
  ['dawn', 5 * 60],
  ['morning', 7 * 60],
  ['afternoon', 12 * 60],
  ['evening', 17 * 60],
  ['night', 20 * 60],
];

/** Returns null for anything that is not an integer hour 0-23 and integer minute 0-59. */
export function periodFromClock(hour: number, minute: number): DayPeriod | null {
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return null;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  const minutes = hour * 60 + minute;
  let period: DayPeriod = 'night';
  for (const [name, start] of PERIOD_STARTS) {
    if (minutes >= start) period = name;
  }
  return period;
}

/**
 * scene.kind as the engine serialises it (ai-dnd/living_world.py scene_kind: tavern, city,
 * wilderness, building, quiet; the API type is string | null). Anything else is unknown.
 */
export function placeKindFromSceneKind(sceneKind: string | null | undefined): AtmospherePlaceKind | null {
  switch (sceneKind) {
    case 'wilderness':
    case 'city':
      return 'outdoor';
    case 'tavern':
    case 'building':
    case 'quiet':
      return 'indoor';
    default:
      return null;
  }
}

export type AtmospherePreset = {
  tint: Rgba;
  bloom: { c: Rgba; x: number; y: number; r: number };
  win: Rgba;
  vig: Rgba;
  fog: Rgba;
  mote: { c: Rgba; n: number; glow: number };
};

const INDOOR_BASE = {
  tint: [110, 70, 35, 0.1],
  bloom: { c: [255, 195, 120, 0], x: 22, y: 88, r: 70 },
  vig: [8, 4, 0, 0.22],
  fog: [165, 150, 135, 0.05],
  mote: { c: [255, 225, 170, 0.5], n: 3, glow: 2 },
} as const;

/** place kind x period -> preset. JSON-shaped: no code branches on a particular cell. */
export const ATMOSPHERE_TABLE: Record<AtmospherePlaceKind, Record<DayPeriod, AtmospherePreset>> = {
  outdoor: {
    dawn: { tint: [150, 115, 160, 0.13], bloom: { c: [255, 170, 140, 0.16], x: 6, y: 94, r: 80 }, win: [0, 0, 0, 0], vig: [40, 30, 60, 0.14], fog: [210, 175, 195, 0.1], mote: { c: [255, 210, 190, 0.5], n: 5, glow: 4 } },
    morning: { tint: [255, 240, 200, 0.05], bloom: { c: [255, 242, 205, 0.15], x: 88, y: 4, r: 78 }, win: [0, 0, 0, 0], vig: [60, 50, 20, 0.07], fog: [225, 235, 225, 0.06], mote: { c: [255, 240, 190, 0.55], n: 6, glow: 3 } },
    afternoon: { tint: [255, 165, 60, 0.1], bloom: { c: [255, 170, 70, 0.18], x: 94, y: 24, r: 85 }, win: [0, 0, 0, 0], vig: [70, 35, 10, 0.12], fog: [255, 210, 150, 0.04], mote: { c: [255, 205, 120, 0.6], n: 8, glow: 4 } },
    evening: { tint: [140, 60, 90, 0.13], bloom: { c: [235, 105, 65, 0.15], x: 100, y: 55, r: 80 }, win: [0, 0, 0, 0], vig: [30, 10, 35, 0.18], fog: [130, 90, 130, 0.08], mote: { c: [255, 165, 145, 0.5], n: 6, glow: 3 } },
    night: { tint: [25, 45, 100, 0.15], bloom: { c: [165, 190, 255, 0.1], x: 18, y: 5, r: 70 }, win: [0, 0, 0, 0], vig: [0, 5, 25, 0.24], fog: [90, 110, 150, 0.09], mote: { c: [175, 255, 200, 0.6], n: 8, glow: 8 } },
  },
  indoor: {
    dawn: { ...INDOOR_BASE, win: [255, 175, 170, 0.11] },
    morning: { ...INDOOR_BASE, win: [255, 252, 235, 0.15] },
    afternoon: { ...INDOOR_BASE, win: [255, 200, 110, 0.17] },
    evening: { ...INDOOR_BASE, win: [255, 115, 65, 0.14] },
    night: { ...INDOOR_BASE, win: [150, 180, 255, 0.09] },
  },
};

/**
 * Window light multiplier by engine scene.kind. Only a tavern is known to have windows (V4 han 1,
 * zindan 0); the engine does not say whether other interiors have one, so they get none.
 */
const WINDOW_LIGHT: Record<string, number> = { tavern: 1 };

/** Per-theme layer multipliers, from V4. cs darkens body colours in the night theme. */
export const ATMOSPHERE_THEME_SCALE: Record<AtmosphereTheme, {
  cs: number; tint: number; bloom: number; win: number; vig: number; fog: number; mote: number; mc: number;
}> = {
  night: { cs: 0.3, tint: 2.5, bloom: 0.22, win: 0.22, vig: 1, fog: 1.6, mote: 0.3, mc: 1 },
  day: { cs: 1, tint: 0.35, bloom: 1, win: 1, vig: 0.2, fog: 0.3, mote: 0.6, mc: 0.6 },
};

export type AtmosphereInput = {
  clock?: { hour: number; minute: number } | null;
  sceneKind?: string | null;
  /** Socket: engine does not supply crowd size yet (motor gerektirir). Ignored. */
  crowd?: number;
  /** Socket: engine does not supply fire/light state yet (motor gerektirir). Ignored. */
  fire?: boolean;
};

export type ResolvedAtmosphere = {
  /** 'neutral' when the clock or scene kind is missing/unknown: all layers transparent. */
  kind: AtmospherePlaceKind | 'neutral';
  period: DayPeriod | null;
  tint: Rgba;
  bloom: { c: Rgba; x: number; y: number; r: number };
  win: Rgba;
  vig: Rgba;
  /** Null when effectsLevel is 'off' (static tint only) and for the neutral preset. */
  motion: null | { fog: Rgba; fogBands: number; mote: { c: Rgba; n: number; glow: number } };
};

const CLEAR: Rgba = [0, 0, 0, 0];
export const NEUTRAL_ATMOSPHERE: ResolvedAtmosphere = {
  kind: 'neutral',
  period: null,
  tint: CLEAR,
  bloom: { c: CLEAR, x: 50, y: 50, r: 60 },
  win: CLEAR,
  vig: CLEAR,
  motion: null,
};

export function resolveAtmosphere(input: AtmosphereInput, effectsLevel: EffectsLevel): ResolvedAtmosphere {
  const period = input.clock ? periodFromClock(input.clock.hour, input.clock.minute) : null;
  const kind = placeKindFromSceneKind(input.sceneKind);
  if (!period || !kind) return NEUTRAL_ATMOSPHERE;
  const preset = ATMOSPHERE_TABLE[kind][period];
  const windowLight = WINDOW_LIGHT[input.sceneKind ?? ''] ?? 0;
  const win: Rgba = [preset.win[0], preset.win[1], preset.win[2], preset.win[3] * windowLight];
  const base = { kind, period, tint: preset.tint, bloom: preset.bloom, win, vig: preset.vig };
  if (effectsLevel === 'off') return { ...base, motion: null };
  const low = effectsLevel === 'low';
  const n = Math.min(MOTE_POOL, preset.mote.n);
  return {
    ...base,
    motion: {
      fog: preset.fog,
      fogBands: low ? 1 : FOG_BANDS,
      mote: { ...preset.mote, n: low ? Math.ceil(n / 2) : n },
    },
  };
}

export type ThemedAtmosphere = {
  tint: Rgba; bloom: Rgba; win: Rgba; vig: Rgba; fog: Rgba; mote: Rgba;
};

/** Layer colours after the per-theme scale; what the layer paints and what the contrast test checks. */
export function themedAtmosphere(a: ResolvedAtmosphere, theme: AtmosphereTheme): ThemedAtmosphere {
  const k = ATMOSPHERE_THEME_SCALE[theme];
  const body = (c: Rgba, m: number): Rgba => [Math.round(c[0] * k.cs), Math.round(c[1] * k.cs), Math.round(c[2] * k.cs), c[3] * m];
  const light = (c: Rgba, m: number): Rgba => [c[0], c[1], c[2], c[3] * m];
  const fog = a.motion?.fog ?? CLEAR;
  const mote = a.motion?.mote.c ?? CLEAR;
  return {
    tint: body(a.tint, k.tint),
    bloom: light(a.bloom.c, k.bloom),
    win: light(a.win, k.win),
    vig: body(a.vig, k.vig),
    fog: body(fog, k.fog),
    mote: [Math.round(mote[0] * k.mc), Math.round(mote[1] * k.mc), Math.round(mote[2] * k.mc), mote[3] * k.mote],
  };
}

export function rgbaCss(c: Rgba): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${c[3].toFixed(4)})`;
}
