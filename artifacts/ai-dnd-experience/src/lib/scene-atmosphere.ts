import type { EffectsLevel } from './appearance-settings.ts';
import { MAX_ACTIVE_EFFECTS } from './effect-registry.ts';

/*
 * Scene atmosphere: pure data and resolution. The page layer in
 * src/components/scene-atmosphere-layer.tsx only paints what resolveAtmosphere returns.
 * Inputs are engine facts only (world.environment, world.time_of_day, world.weather and the
 * campaign clock, which only splits 'day' into morning and afternoon); nothing here reads or
 * writes story text. Period light is ported from the V4 prototype (UI_PROTOTIP_V4_20261111);
 * family hues and the weather overlays are ported from the old .environment-theme rules.
 */

export type DayPeriod = 'dawn' | 'morning' | 'afternoon' | 'evening' | 'night';
export type AtmosphereFamily =
  | 'tavern' | 'forest' | 'city' | 'village' | 'road' | 'wilderness'
  | 'dungeon' | 'cave' | 'castle' | 'temple' | 'ruins';
export type AtmosphereWeather = 'clear' | 'rain' | 'fog' | 'snow' | 'storm';
export type AtmosphereTheme = 'night' | 'day';
/** [red, green, blue, alpha] with channels 0..255 and alpha 0..1. */
export type Rgba = readonly [number, number, number, number];

export const DAY_PERIODS: readonly DayPeriod[] = ['dawn', 'morning', 'afternoon', 'evening', 'night'];
export const ATMOSPHERE_FAMILIES: readonly AtmosphereFamily[] = [
  'tavern', 'forest', 'city', 'village', 'road', 'wilderness', 'dungeon', 'cave', 'castle', 'temple', 'ruins',
];
export const ATMOSPHERE_WEATHERS: readonly AtmosphereWeather[] = ['clear', 'rain', 'fog', 'snow', 'storm'];

/**
 * Animated element budget (Ruling: subtract). The layer's motes + fog bands are always-on CSS
 * animations that the event-effect registry cannot evict, so the registry's cap for event effects
 * is the shared MAX_ACTIVE_EFFECTS (14) minus what the layer can use: createEffectRegistry should be
 * given { maxActive: EVENT_EFFECT_BUDGET }.
 */
export const MOTE_POOL = 8;
export const FOG_BANDS = 2;
export const ATMOSPHERE_ANIMATED_MAX = MOTE_POOL + FOG_BANDS;
export const EVENT_EFFECT_BUDGET = MAX_ACTIVE_EFFECTS - ATMOSPHERE_ANIMATED_MAX;
/** Crossfade between presets, mirrored by the transition duration in scene-atmosphere-layer.css. */
export const CROSSFADE_MS = 1500;

/**
 * The engine's time_of_day is authoritative. Only 'day' is split, by the campaign clock:
 * 12:00 and later is afternoon, anything earlier or a missing/invalid clock is morning.
 */
export function periodFromWorld(
  timeOfDay: string | null | undefined,
  clock?: { hour: number; minute: number } | null,
): DayPeriod | null {
  switch (timeOfDay) {
    case 'dawn':
    case 'evening':
    case 'night':
      return timeOfDay;
    case 'day': {
      const valid = clock
        && Number.isInteger(clock.hour) && Number.isInteger(clock.minute)
        && clock.hour >= 0 && clock.hour <= 23 && clock.minute >= 0 && clock.minute <= 59;
      return valid && clock.hour >= 12 ? 'afternoon' : 'morning';
    }
    default:
      return null;
  }
}

export type AtmospherePreset = {
  /** Family colour (the old per-family wash): the same in every period. */
  hue: Rgba;
  /** Period light: strong outdoors, a fixed base tint indoors. */
  tint: Rgba;
  bloom: { c: Rgba; x: number; y: number; r: number };
  win: Rgba;
  vig: Rgba;
  fog: Rgba;
  mote: { c: Rgba; n: number; glow: number };
};

type OutdoorLight = Omit<AtmospherePreset, 'hue' | 'win'>;

/** Outdoor period light, from V4 'outdoor'. */
const OUTDOOR_LIGHT: Record<DayPeriod, OutdoorLight> = {
  dawn: { tint: [150, 115, 160, 0.13], bloom: { c: [255, 170, 140, 0.16], x: 6, y: 94, r: 80 }, vig: [40, 30, 60, 0.14], fog: [210, 175, 195, 0.1], mote: { c: [255, 210, 190, 0.5], n: 5, glow: 4 } },
  morning: { tint: [255, 240, 200, 0.05], bloom: { c: [255, 242, 205, 0.15], x: 88, y: 4, r: 78 }, vig: [60, 50, 20, 0.07], fog: [225, 235, 225, 0.06], mote: { c: [255, 240, 190, 0.55], n: 6, glow: 3 } },
  afternoon: { tint: [255, 165, 60, 0.1], bloom: { c: [255, 170, 70, 0.18], x: 94, y: 24, r: 85 }, vig: [70, 35, 10, 0.12], fog: [255, 210, 150, 0.04], mote: { c: [255, 205, 120, 0.6], n: 8, glow: 4 } },
  evening: { tint: [140, 60, 90, 0.13], bloom: { c: [235, 105, 65, 0.15], x: 100, y: 55, r: 80 }, vig: [30, 10, 35, 0.18], fog: [130, 90, 130, 0.08], mote: { c: [255, 165, 145, 0.5], n: 6, glow: 3 } },
  night: { tint: [25, 45, 100, 0.15], bloom: { c: [165, 190, 255, 0.1], x: 18, y: 5, r: 70 }, vig: [0, 5, 25, 0.24], fog: [90, 110, 150, 0.09], mote: { c: [175, 255, 200, 0.6], n: 8, glow: 8 } },
};

/** Indoor light that does not follow the sky: a base tint, a dark vignette, a little dust. */
const INDOOR_LIGHT = {
  bloom: { c: [255, 195, 120, 0], x: 22, y: 88, r: 70 },
  vig: [8, 4, 0, 0.22],
  fog: [165, 150, 135, 0.05],
  mote: { c: [255, 225, 170, 0.5], n: 3, glow: 2 },
} as const;

/** Window light colour by period, from V4 'indoor'; scaled per family by windowLight. */
const WINDOW_LIGHT_BY_PERIOD: Record<DayPeriod, Rgba> = {
  dawn: [255, 175, 170, 0.11],
  morning: [255, 252, 235, 0.15],
  afternoon: [255, 200, 110, 0.17],
  evening: [255, 115, 65, 0.14],
  night: [150, 180, 255, 0.09],
};

export type AtmosphereFamilyData = {
  place: 'outdoor' | 'indoor';
  /** Old --theme-wash value. */
  hue: Rgba;
  /** Old --theme-line value: the location ribbon edge. */
  line: Rgba;
  /** Indoor fixed base tint (ignored outdoors). */
  base: Rgba;
  /** 0..1 share of window light; only places known to have windows get any. */
  windowLight: number;
  /** Multiplies the period's mote count (rounded). */
  moteScale: number;
};

export const ATMOSPHERE_FAMILY_DATA: Record<AtmosphereFamily, AtmosphereFamilyData> = {
  tavern: { place: 'indoor', hue: [153, 99, 45, 0.12], line: [117, 86, 50, 0.82], base: [110, 70, 35, 0.1], windowLight: 1, moteScale: 1 },
  forest: { place: 'outdoor', hue: [52, 99, 62, 0.2], line: [104, 132, 94, 0.7], base: [0, 0, 0, 0], windowLight: 0, moteScale: 1 },
  city: { place: 'outdoor', hue: [75, 90, 115, 0.19], line: [139, 130, 103, 0.72], base: [0, 0, 0, 0], windowLight: 0, moteScale: 0.5 },
  village: { place: 'outdoor', hue: [139, 103, 51, 0.17], line: [153, 122, 77, 0.72], base: [0, 0, 0, 0], windowLight: 0, moteScale: 0.75 },
  road: { place: 'outdoor', hue: [147, 97, 44, 0.17], line: [164, 125, 73, 0.72], base: [0, 0, 0, 0], windowLight: 0, moteScale: 1 },
  wilderness: { place: 'outdoor', hue: [47, 88, 61, 0.23], line: [106, 127, 93, 0.72], base: [0, 0, 0, 0], windowLight: 0, moteScale: 1 },
  dungeon: { place: 'indoor', hue: [76, 62, 91, 0.23], line: [122, 111, 127, 0.68], base: [60, 50, 80, 0.1], windowLight: 0, moteScale: 0.67 },
  cave: { place: 'indoor', hue: [60, 80, 98, 0.23], line: [111, 123, 132, 0.68], base: [45, 60, 80, 0.1], windowLight: 0, moteScale: 0.67 },
  castle: { place: 'indoor', hue: [98, 79, 51, 0.19], line: [154, 132, 94, 0.72], base: [100, 80, 50, 0.1], windowLight: 0.8, moteScale: 1 },
  temple: { place: 'indoor', hue: [138, 106, 59, 0.17], line: [162, 137, 93, 0.72], base: [120, 95, 50, 0.1], windowLight: 1, moteScale: 1 },
  ruins: { place: 'indoor', hue: [91, 82, 63, 0.21], line: [132, 119, 94, 0.68], base: [85, 75, 55, 0.1], windowLight: 0, moteScale: 1 },
};

/** Old default --theme-line, used when no family is known. */
export const NEUTRAL_LINE: Rgba = [117, 108, 91, 0.62];

function buildPreset(data: AtmosphereFamilyData, period: DayPeriod): AtmospherePreset {
  const scaleMotes = (n: number) => Math.min(MOTE_POOL, Math.round(n * data.moteScale));
  if (data.place === 'outdoor') {
    const light = OUTDOOR_LIGHT[period];
    return { hue: data.hue, ...light, win: [0, 0, 0, 0], mote: { ...light.mote, n: scaleMotes(light.mote.n) } };
  }
  const w = WINDOW_LIGHT_BY_PERIOD[period];
  return {
    hue: data.hue,
    tint: data.base,
    bloom: INDOOR_LIGHT.bloom,
    win: [w[0], w[1], w[2], w[3] * data.windowLight],
    vig: INDOOR_LIGHT.vig,
    fog: INDOOR_LIGHT.fog,
    mote: { ...INDOOR_LIGHT.mote, n: scaleMotes(INDOOR_LIGHT.mote.n) },
  };
}

/** family x period -> preset, materialised once from the data above (no branch on a particular cell). */
export const ATMOSPHERE_TABLE: Record<AtmosphereFamily, Record<DayPeriod, AtmospherePreset>> = Object.fromEntries(
  ATMOSPHERE_FAMILIES.map((family) => [
    family,
    Object.fromEntries(DAY_PERIODS.map((period) => [period, buildPreset(ATMOSPHERE_FAMILY_DATA[family], period)])),
  ]),
) as Record<AtmosphereFamily, Record<DayPeriod, AtmospherePreset>>;

export function rgbaCss(c: Rgba): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${c[3].toFixed(4)})`;
}

export type WeatherVeil = {
  /** CSS background of the fixed, pointer-events-none veil above the page (same look as the old ::before). */
  background: string;
  backgroundSize?: string;
  opacity: number;
  /** Strongest effective colours the veil lays over text (alpha already times opacity), for contrast checks. */
  peaks: readonly Rgba[];
  /** True when the veil is specks a couple of pixels wide (checked like motes, not as a full layer). */
  speck: boolean;
};

export type WeatherPreset = {
  /** Old --weather-wash value (fog: halved, see Ruling below). */
  wash: Rgba;
  veil: WeatherVeil | null;
  /**
   * 0..1 share of the place's light (hue, tint, bloom, window, fog bands) that gets through this
   * weather; the vignette is never dimmed. Dense weather diffuses direct light; it also keeps text
   * contrast with the veil on top.
   */
  calm: number;
};

const effective = (c: Rgba, opacity: number): Rgba => [c[0], c[1], c[2], c[3] * opacity];

const RAIN_STREAK: Rgba = [183, 199, 211, 0.25];
const RAIN_VEIL: WeatherVeil = {
  background: `repeating-linear-gradient(108deg, transparent 0 27px, ${rgbaCss(RAIN_STREAK)} 28px, transparent 30px)`,
  opacity: 0.13,
  peaks: [effective(RAIN_STREAK, 0.13)],
  speck: false,
};
/*
 * Ruling: fog keeps its old veil strength (core alpha .16). The wash is halved (.055) and fog lets 20%
 * of the place's light through (calm .2): the only weakening of an old overlay, a margin kept for the
 * contrast rule. The veil sits above both the text and the page (position fixed, z-index 10), so the
 * contrast test composites it over the text colour as well as the background.
 */
const FOG_CORE: Rgba = [196, 205, 194, 0.16];
const FOG_HAZE: Rgba = [170, 184, 180, 0.035];
const SNOW_FLAKES: readonly Rgba[] = [[226, 232, 238, 0.85], [226, 232, 238, 0.72], [226, 232, 238, 0.6]];

/** Weather overlays ported from the old index.css, kept at the same strength. */
export const WEATHER_TABLE: Record<AtmosphereWeather, WeatherPreset> = {
  clear: { wash: [235, 198, 116, 0.07], veil: null, calm: 1 },
  rain: { wash: [91, 128, 158, 0.1], veil: RAIN_VEIL, calm: 1 },
  fog: {
    wash: [176, 190, 184, 0.055],
    calm: 0.2,
    veil: {
      background: `radial-gradient(ellipse at 50% 40%, ${rgbaCss(FOG_CORE)}, transparent 68%), linear-gradient(180deg, ${rgbaCss(FOG_HAZE)}, transparent 75%)`,
      opacity: 1,
      peaks: [FOG_CORE, FOG_HAZE],
      speck: false,
    },
  },
  snow: {
    wash: [170, 199, 218, 0.09],
    calm: 1,
    veil: {
      background: [
        `radial-gradient(circle at 18% 23%, ${rgbaCss(SNOW_FLAKES[0])} 0 1px, transparent 2px)`,
        `radial-gradient(circle at 74% 38%, ${rgbaCss(SNOW_FLAKES[1])} 0 1px, transparent 2px)`,
        `radial-gradient(circle at 44% 78%, ${rgbaCss(SNOW_FLAKES[2])} 0 1px, transparent 2px)`,
      ].join(', '),
      backgroundSize: '97px 113px, 141px 157px, 177px 191px',
      opacity: 0.15,
      peaks: [effective(SNOW_FLAKES[0], 0.15)],
      speck: true,
    },
  },
  storm: { wash: [52, 69, 100, 0.15], veil: RAIN_VEIL, calm: 0.5 },
};

/** Per-theme layer multipliers, from V4. cs darkens body colours in the night theme. */
export const ATMOSPHERE_THEME_SCALE: Record<AtmosphereTheme, {
  cs: number; tint: number; hue: number; bloom: number; win: number; vig: number; fog: number; mote: number; mc: number;
}> = {
  night: { cs: 0.3, tint: 2.5, hue: 1.5, bloom: 0.22, win: 0.22, vig: 1, fog: 1.6, mote: 0.3, mc: 1 },
  day: { cs: 1, tint: 0.35, hue: 0.35, bloom: 1, win: 1, vig: 0.2, fog: 0.3, mote: 0.6, mc: 0.6 },
};

export type AtmosphereInput = {
  /** world.environment; anything outside the eleven families (including 'unknown') is neutral. */
  environment?: string | null;
  /** world.time_of_day. */
  timeOfDay?: string | null;
  /** world.weather; 'unknown' and anything else draws no weather. */
  weather?: string | null;
  /** In-game clock, used only to split 'day' into morning and afternoon. */
  clock?: { hour: number; minute: number } | null;
  /** Socket: engine does not supply crowd size yet (motor gerektirir). Ignored. */
  crowd?: number;
  /** Socket: engine does not supply fire/light state yet (motor gerektirir). Ignored. */
  fire?: boolean;
};

export type ResolvedAtmosphere = {
  /** 'neutral' when the family or period is missing/unknown: every place layer is transparent. */
  family: AtmosphereFamily | 'neutral';
  period: DayPeriod | null;
  hue: Rgba;
  tint: Rgba;
  bloom: { c: Rgba; x: number; y: number; r: number };
  win: Rgba;
  vig: Rgba;
  /** Null when no known weather is reported. Independent of the place layers. */
  weather: { name: AtmosphereWeather; preset: WeatherPreset } | null;
  /** Null when effectsLevel is 'off' (static tint only) and for the neutral place. */
  motion: null | { fog: Rgba; fogBands: number; mote: { c: Rgba; n: number; glow: number } };
};

const CLEAR: Rgba = [0, 0, 0, 0];
export const NEUTRAL_ATMOSPHERE: ResolvedAtmosphere = {
  family: 'neutral',
  period: null,
  hue: CLEAR,
  tint: CLEAR,
  bloom: { c: CLEAR, x: 50, y: 50, r: 60 },
  win: CLEAR,
  vig: CLEAR,
  weather: null,
  motion: null,
};

function isFamily(value: string | null | undefined): value is AtmosphereFamily {
  return typeof value === 'string' && Object.hasOwn(ATMOSPHERE_FAMILY_DATA, value);
}

function isWeather(value: string | null | undefined): value is AtmosphereWeather {
  return typeof value === 'string' && Object.hasOwn(WEATHER_TABLE, value);
}

export function resolveAtmosphere(input: AtmosphereInput, effectsLevel: EffectsLevel): ResolvedAtmosphere {
  const period = periodFromWorld(input.timeOfDay, input.clock);
  const weather = isWeather(input.weather) ? { name: input.weather, preset: WEATHER_TABLE[input.weather] } : null;
  if (!isFamily(input.environment) || !period) return weather ? { ...NEUTRAL_ATMOSPHERE, weather } : NEUTRAL_ATMOSPHERE;
  const preset = ATMOSPHERE_TABLE[input.environment][period];
  const calm = weather?.preset.calm ?? 1;
  const dim = (c: Rgba): Rgba => [c[0], c[1], c[2], c[3] * calm];
  const base = {
    family: input.environment, period, hue: dim(preset.hue), tint: dim(preset.tint),
    bloom: { ...preset.bloom, c: dim(preset.bloom.c) }, win: dim(preset.win), vig: preset.vig, weather,
  };
  if (effectsLevel === 'off') return { ...base, motion: null };
  const low = effectsLevel === 'low';
  const n = preset.mote.n;
  return {
    ...base,
    motion: {
      fog: dim(preset.fog),
      fogBands: low ? 1 : FOG_BANDS,
      mote: { ...preset.mote, n: low ? Math.ceil(n / 2) : n },
    },
  };
}

export type ThemedAtmosphere = {
  hue: Rgba; tint: Rgba; bloom: Rgba; win: Rgba; vig: Rgba; fog: Rgba; mote: Rgba; wash: Rgba;
};

/** Layer colours after the per-theme scale; what the layer paints and what the contrast test checks. */
export function themedAtmosphere(a: ResolvedAtmosphere, theme: AtmosphereTheme): ThemedAtmosphere {
  const k = ATMOSPHERE_THEME_SCALE[theme];
  const body = (c: Rgba, m: number): Rgba => [Math.round(c[0] * k.cs), Math.round(c[1] * k.cs), Math.round(c[2] * k.cs), c[3] * m];
  const light = (c: Rgba, m: number): Rgba => [c[0], c[1], c[2], c[3] * m];
  const fog = a.motion?.fog ?? CLEAR;
  const mote = a.motion?.mote.c ?? CLEAR;
  return {
    hue: body(a.hue, k.hue),
    tint: body(a.tint, k.tint),
    bloom: light(a.bloom.c, k.bloom),
    win: light(a.win, k.win),
    vig: body(a.vig, k.vig),
    fog: body(fog, k.fog),
    mote: [Math.round(mote[0] * k.mc), Math.round(mote[1] * k.mc), Math.round(mote[2] * k.mc), mote[3] * k.mote],
    wash: body(a.weather?.preset.wash ?? CLEAR, k.tint),
  };
}
