import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { UNW_HIGH_CONTRAST_COLORS, UNW_THEME_COLORS } from '../src/lib/unw-theme.ts';
import { MAX_ACTIVE_EFFECTS, createEffectRegistry } from '../src/lib/effect-registry.ts';
import {
  ATMOSPHERE_ANIMATED_MAX,
  ATMOSPHERE_FAMILIES,
  ATMOSPHERE_FAMILY_DATA,
  ATMOSPHERE_TABLE,
  ATMOSPHERE_WEATHERS,
  DAY_PERIODS,
  EVENT_EFFECT_BUDGET,
  FOG_BANDS,
  MOTE_POOL,
  NEUTRAL_ATMOSPHERE,
  WEATHER_TABLE,
  periodFromWorld,
  resolveAtmosphere,
  themedAtmosphere,
} from '../src/lib/scene-atmosphere.ts';

const TIMES = ['dawn', 'day', 'evening', 'night'];
const WORLD_CLOCK = { hour: 13, minute: 0 };
const world = (environment, timeOfDay, weather, clock = WORLD_CLOCK) => ({ environment, timeOfDay, weather, clock });

/* ---------- period split ---------- */

test('engine time_of_day is authoritative; the clock only splits day', () => {
  for (const t of ['dawn', 'evening', 'night']) {
    for (const hour of [0, 6, 9, 13, 18, 23]) assert.equal(periodFromWorld(t, { hour, minute: 0 }), t, `${t} at ${hour}`);
    assert.equal(periodFromWorld(t, null), t);
  }
  const day = (hour, minute) => periodFromWorld('day', { hour, minute });
  assert.equal(day(7, 0), 'morning');
  assert.equal(day(11, 59), 'morning');
  assert.equal(day(12, 0), 'afternoon');
  assert.equal(day(16, 59), 'afternoon');
});

test('day without a usable clock is morning; unknown time is null', () => {
  for (const clock of [null, undefined, { hour: 99, minute: 0 }, { hour: 13, minute: 77 }, { hour: 13.5, minute: 0 }, { hour: '13', minute: 0 }, { hour: -1, minute: 0 }]) {
    assert.equal(periodFromWorld('day', clock), 'morning', JSON.stringify(clock));
  }
  for (const t of [null, undefined, '', 'neutral', 'noon', 'Day']) assert.equal(periodFromWorld(t, WORLD_CLOCK), null, String(t));
});

/* ---------- table shape ---------- */

const isRgba = (c) => Array.isArray(c) && c.length === 4 && c.every((v, i) => Number.isFinite(v) && v >= 0 && v <= (i < 3 ? 255 : 1));

test('table is 11 families x 5 periods with every required field', () => {
  assert.deepEqual([...ATMOSPHERE_FAMILIES].sort(), ['castle', 'cave', 'city', 'dungeon', 'forest', 'road', 'ruins', 'tavern', 'temple', 'village', 'wilderness']);
  assert.deepEqual(Object.keys(ATMOSPHERE_TABLE).sort(), [...ATMOSPHERE_FAMILIES].sort());
  assert.equal(ATMOSPHERE_FAMILIES.length * DAY_PERIODS.length, 55);
  for (const family of ATMOSPHERE_FAMILIES) {
    assert.deepEqual(Object.keys(ATMOSPHERE_TABLE[family]).sort(), [...DAY_PERIODS].sort(), family);
    for (const period of DAY_PERIODS) {
      const p = ATMOSPHERE_TABLE[family][period];
      const at = `${family}/${period}`;
      for (const f of ['hue', 'tint', 'win', 'vig', 'fog']) assert.ok(isRgba(p[f]), `${at} ${f}`);
      assert.ok(isRgba(p.bloom.c), `${at} bloom.c`);
      for (const f of ['x', 'y', 'r']) assert.ok(Number.isFinite(p.bloom[f]), `${at} bloom.${f}`);
      assert.ok(isRgba(p.mote.c), `${at} mote.c`);
      assert.ok(Number.isInteger(p.mote.n) && p.mote.n >= 0 && p.mote.n <= MOTE_POOL, `${at} mote.n`);
      assert.ok(Number.isFinite(p.mote.glow), `${at} mote.glow`);
    }
  }
});

test('family hues keep the old per-family wash colours', () => {
  const old = {
    tavern: [153, 99, 45, 0.12], forest: [52, 99, 62, 0.2], city: [75, 90, 115, 0.19], village: [139, 103, 51, 0.17],
    road: [147, 97, 44, 0.17], wilderness: [47, 88, 61, 0.23], dungeon: [76, 62, 91, 0.23], cave: [60, 80, 98, 0.23],
    castle: [98, 79, 51, 0.19], temple: [138, 106, 59, 0.17], ruins: [91, 82, 63, 0.21],
  };
  for (const [family, hue] of Object.entries(old)) {
    for (const period of DAY_PERIODS) assert.deepEqual([...ATMOSPHERE_TABLE[family][period].hue], hue, `${family}/${period}`);
  }
});

test('outdoor families vary strongly with period; indoor families keep a fixed base tint', () => {
  for (const family of ATMOSPHERE_FAMILIES) {
    const tints = DAY_PERIODS.map((p) => JSON.stringify(ATMOSPHERE_TABLE[family][p].tint));
    if (ATMOSPHERE_FAMILY_DATA[family].place === 'outdoor') {
      assert.equal(new Set(tints).size, 5, `${family} outdoor tint differs per period`);
    } else {
      assert.equal(new Set(tints).size, 1, `${family} indoor tint is fixed`);
      assert.ok(ATMOSPHERE_TABLE[family].night.tint[3] > 0);
    }
  }
});

test('only tavern, castle and temple get window light; outdoors and other interiors get none', () => {
  for (const family of ATMOSPHERE_FAMILIES) {
    for (const period of DAY_PERIODS) {
      const alpha = ATMOSPHERE_TABLE[family][period].win[3];
      if (['tavern', 'castle', 'temple'].includes(family)) assert.ok(alpha > 0, `${family}/${period}`);
      else assert.equal(alpha, 0, `${family}/${period}`);
    }
  }
});

/* ---------- weather overlays as table data ---------- */

test('weather table keeps the old washes and overlays at the old strength (fog: the one Ruling exception)', () => {
  assert.deepEqual(Object.keys(WEATHER_TABLE).sort(), [...ATMOSPHERE_WEATHERS].sort());
  const washes = { clear: [235, 198, 116, 0.07], rain: [91, 128, 158, 0.1], fog: [176, 190, 184, 0.055], snow: [170, 199, 218, 0.09], storm: [52, 69, 100, 0.15] };
  for (const [name, wash] of Object.entries(washes)) assert.deepEqual([...WEATHER_TABLE[name].wash], wash, name);
  assert.equal(WEATHER_TABLE.clear.veil, null);
  for (const name of ['rain', 'storm']) {
    const v = WEATHER_TABLE[name].veil;
    assert.equal(v.opacity, 0.13, name);
    assert.match(v.background, /^repeating-linear-gradient\(108deg, transparent 0 27px, rgba\(183,199,211,0\.2500\) 28px, transparent 30px\)$/);
  }
  assert.equal(WEATHER_TABLE.storm.veil, WEATHER_TABLE.rain.veil, 'storm shows the rain veil, as before');
  const fog = WEATHER_TABLE.fog.veil;
  assert.equal(fog.opacity, 1);
  assert.match(fog.background, /radial-gradient\(ellipse at 50% 40%, rgba\(196,205,194,0.1600\), transparent 68%\), linear-gradient\(180deg, rgba\(170,184,180,0\.0350\), transparent 75%\)/);
  const snow = WEATHER_TABLE.snow.veil;
  assert.equal(snow.opacity, 0.15);
  assert.equal(snow.backgroundSize, '97px 113px, 141px 157px, 177px 191px');
  assert.equal(snow.speck, true);
  for (const [at, a] of [['18% 23%', 0.85], ['74% 38%', 0.72], ['44% 78%', 0.6]]) {
    assert.ok(snow.background.includes(`radial-gradient(circle at ${at}, rgba(226,232,238,${a.toFixed(4)}) 0 1px, transparent 2px)`), at);
  }
});

test('Ruling: dense weather lets only part of the place light through; the vignette is never dimmed', () => {
  assert.deepEqual(ATMOSPHERE_WEATHERS.map((w) => WEATHER_TABLE[w].calm), [1, 1, 0.2, 1, 0.5]);
  const clear = resolveAtmosphere(world('village', 'night', 'clear'), 'full');
  const fog = resolveAtmosphere(world('village', 'night', 'fog'), 'full');
  assert.ok(Math.abs(fog.tint[3] - clear.tint[3] * 0.2) < 1e-9);
  assert.ok(Math.abs(fog.hue[3] - clear.hue[3] * 0.2) < 1e-9);
  assert.ok(Math.abs(fog.bloom.c[3] - clear.bloom.c[3] * 0.2) < 1e-9);
  assert.ok(Math.abs(fog.motion.fog[3] - clear.motion.fog[3] * 0.2) < 1e-9);
  assert.deepEqual(fog.vig, clear.vig);
  assert.deepEqual(fog.motion.mote, clear.motion.mote);
});

/* ---------- resolution ---------- */

test('missing or unknown world fields resolve to the neutral atmosphere (no tint)', () => {
  const neutralInputs = [
    {}, { environment: 'forest' }, { timeOfDay: 'night' }, world('unknown', 'night', null), world('harbor', 'day', undefined),
    world(null, 'night', null), world('forest', 'noon', null), world('constructor', 'day', null), world('', 'dawn', null),
    { environment: 'neutral', timeOfDay: 'neutral', weather: 'neutral', clock: null },
  ];
  for (const input of neutralInputs) {
    for (const level of ['off', 'low', 'full']) {
      const r = resolveAtmosphere(input, level);
      assert.equal(r, NEUTRAL_ATMOSPHERE, JSON.stringify(input));
      assert.equal(r.family, 'neutral');
      assert.equal(r.motion, null);
      for (const f of ['hue', 'tint', 'win', 'vig']) assert.equal(r[f][3], 0, f);
      assert.equal(r.bloom.c[3], 0);
      assert.equal(r.weather, null);
    }
  }
});

test('weather draws on its own: unknown place, known weather keeps no place tint', () => {
  const r = resolveAtmosphere(world('unknown', 'night', 'rain'), 'full');
  assert.equal(r.family, 'neutral');
  assert.equal(r.tint[3], 0);
  assert.equal(r.hue[3], 0);
  assert.equal(r.weather.name, 'rain');
  assert.equal(resolveAtmosphere(world('forest', 'night', 'unknown'), 'full').weather, null);
  assert.equal(resolveAtmosphere(world('forest', 'night', 'neutral'), 'full').weather, null);
  assert.equal(resolveAtmosphere(world('forest', 'night', 'hail'), 'full').weather, null);
});

test('crowd and fire sockets are ignored', () => {
  const base = world('tavern', 'night', 'clear');
  assert.deepEqual(resolveAtmosphere({ ...base, crowd: 3, fire: true }, 'full'), resolveAtmosphere(base, 'full'));
});

test('every family x time x weather cell resolves, with day split by the clock', () => {
  let cells = 0;
  for (const family of ATMOSPHERE_FAMILIES) {
    for (const time of TIMES) {
      for (const weather of [null, ...ATMOSPHERE_WEATHERS]) {
        const r = resolveAtmosphere(world(family, time, weather), 'full');
        const period = periodFromWorld(time, WORLD_CLOCK);
        assert.equal(r.family, family);
        assert.equal(r.period, period);
        const expected = ATMOSPHERE_TABLE[family][period].tint;
        const calm = weather ? WEATHER_TABLE[weather].calm : 1;
        assert.deepEqual(r.tint.slice(0, 3), expected.slice(0, 3));
        assert.ok(Math.abs(r.tint[3] - expected[3] * calm) < 1e-9);
        assert.equal(r.weather?.name ?? null, weather);
        cells += 1;
      }
    }
  }
  assert.equal(cells, 11 * 4 * 6);
  assert.equal(resolveAtmosphere(world('forest', 'day', null, { hour: 9, minute: 0 }), 'full').period, 'morning');
  assert.equal(resolveAtmosphere(world('forest', 'day', null, { hour: 14, minute: 0 }), 'full').period, 'afternoon');
  assert.equal(resolveAtmosphere(world('forest', 'day', null, null), 'full').period, 'morning');
});

test('effects off keeps the static tint and weather and drops every motion field', () => {
  for (const family of ATMOSPHERE_FAMILIES) {
    for (const time of TIMES) {
      const r = resolveAtmosphere(world(family, time, 'rain'), 'off');
      assert.equal(r.motion, null, `${family} ${time}`);
      assert.ok(r.tint[3] > 0 && r.hue[3] > 0, `${family} ${time} keeps its tint`);
      assert.notEqual(r.family, 'neutral');
      assert.equal(r.weather.name, 'rain');
    }
  }
});

test('low halves the motes and fog bands; the layer stays inside its animated budget', () => {
  assert.equal(ATMOSPHERE_ANIMATED_MAX, MOTE_POOL + FOG_BANDS);
  for (const family of ATMOSPHERE_FAMILIES) {
    for (const time of TIMES) {
      const input = world(family, time, null);
      const full = resolveAtmosphere(input, 'full').motion;
      const low = resolveAtmosphere(input, 'low').motion;
      assert.equal(low.mote.n, Math.ceil(full.mote.n / 2));
      assert.equal(full.fogBands, FOG_BANDS);
      assert.equal(low.fogBands, 1);
      assert.ok(full.mote.n + full.fogBands <= ATMOSPHERE_ANIMATED_MAX, `${family} ${time}`);
    }
  }
});

test('Ruling: the layer budget is subtracted from the event-effect cap', () => {
  assert.equal(ATMOSPHERE_ANIMATED_MAX + EVENT_EFFECT_BUDGET, MAX_ACTIVE_EFFECTS);
  assert.ok(EVENT_EFFECT_BUDGET >= 4);
  const registry = createEffectRegistry({ maxActive: EVENT_EFFECT_BUDGET });
  for (let i = 0; i < EVENT_EFFECT_BUDGET + 3; i += 1) registry.start({ durationMs: 1000, dispose: () => {} });
  assert.equal(registry.leftovers(), EVENT_EFFECT_BUDGET);
  registry.flushAll();
  const wide = createEffectRegistry({ maxActive: 999 });
  for (let i = 0; i < MAX_ACTIVE_EFFECTS + 3; i += 1) wide.start({ durationMs: 1000, dispose: () => {} });
  assert.equal(wide.leftovers(), MAX_ACTIVE_EFFECTS, 'out-of-range maxActive falls back to the full cap');
  wide.flushAll();
});

/*
 * Contrast safety. Model: for every family x period x weather and both themes, take the full-effects
 * preset (fog counted as two bands), scale layers per theme, and alpha-composite every subset of the
 * page layers (hue, tint, bloom, window, fog x2, vignette, weather wash) over the page colour at peak
 * alpha. The weather veil is position:fixed at z-index 10, ABOVE the story text, so its layers are
 * composited over the background AND over the text colour (page first, then the veil on both) before
 * the ratio is taken. Motes and snow flakes are 1-3 px dots: left out of the full-layer rule and
 * checked separately for body text only (>= 4.5).
 * Stacks: the two theme token pairs, and the REAL play screen: the --unw-page token plus the top gradient of .design-preview (text colour at 6%, src/components/unwritten-play.css), for night,
 * day and both high-contrast sets, with every hex text colour that file still sets (parsed from the CSS, so a new colour cannot slip in unchecked).
 */
const rgbOf = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lin = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = (rgb) => 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
const over = (under, l) => [0, 1, 2].map((i) => under[i] * (1 - l[3]) + l[i] * l[3]);

/** Worst ratio of text over page: every subset of `layers` under the text, then every subset of `veils` over text and page. */
function worst(layers, veils, pageRgb, textHex) {
  const text = rgbOf(textHex);
  let worstRatio = Infinity;
  for (let mask = 0; mask < 1 << layers.length; mask += 1) {
    let bg = pageRgb;
    for (let i = 0; i < layers.length; i += 1) if (mask & (1 << i)) bg = over(bg, layers[i]);
    for (let vm = 0; vm < 1 << veils.length; vm += 1) {
      let b = bg;
      let t = text;
      for (let i = 0; i < veils.length; i += 1) if (vm & (1 << i)) { b = over(b, veils[i]); t = over(t, veils[i]); }
      worstRatio = Math.min(worstRatio, ratio(lum(t), lum(b)));
    }
  }
  return worstRatio;
}

// The play screen is painted from the --unw-* tokens: page colour plus a top gradient of the text colour at 6%.
const playPage = (colours) => over(rgbOf(colours.page), [...rgbOf(colours.text), 0.06]);
const PLAY_STACKS = {
  night: [UNW_THEME_COLORS.night, 'night'],
  day: [UNW_THEME_COLORS.day, 'day'],
  'night high contrast': [UNW_HIGH_CONTRAST_COLORS.night, 'night'],
  'day high contrast': [UNW_HIGH_CONTRAST_COLORS.day, 'day'],
};
const PLAY_BODY_TOKENS = ['text'];
const PLAY_SOFT_TOKENS = ['textSoft', 'accentLight', 'patinaText', 'dangerText'];
const PLAY_NOT_ON_PAGE = ['#201d19']; // dark label on the light primary-button fill (.unwritten-entry), never on the page.
// Hex text colours left in unwritten-play.css all sit inside the night islands (opening, creation, drawers); they are tested on the night play page anyway.
const NIGHT_PLAY_PAGE = playPage(UNW_THEME_COLORS.night);

async function playScreenColours() {
  const css = await readFile(new URL('../src/components/unwritten-play.css', import.meta.url), 'utf8');
  const found = [...css.matchAll(/(?:[^-a-z]color|--preview-(?:text|muted)): *(#[0-9a-fA-F]{6})/g)].map((m) => m[1].toLowerCase());
  return [...new Set(found)].filter((c) => !PLAY_NOT_ON_PAGE.includes(c)).sort();
}

/*
 * S3 closed the old allowlist: the 23 soft colours and the narration colour now come from tokens that hold the
 * thresholds in both themes. Nothing is parked any more: every colour is strict, so any new weak colour fails.
 */
function worstOverWorld(theme, page, textHex, { includeSpecks = false } = {}) {
  let low = Infinity;
  for (const family of ATMOSPHERE_FAMILIES) {
    for (const time of TIMES) {
      for (const weather of [null, ...ATMOSPHERE_WEATHERS]) {
        const resolved = resolveAtmosphere(world(family, time, weather), 'full');
        const t = themedAtmosphere(resolved, theme);
        const veil = resolved.weather?.preset.veil;
        const veilLayers = veil && !veil.speck ? veil.peaks : [];
        const layers = [t.hue, t.tint, t.bloom, t.win, t.fog, t.fog, t.vig, t.wash];
        low = Math.min(low, worst(layers, veilLayers, page, textHex));
        if (includeSpecks) {
          low = Math.min(low, worst([...layers, t.mote], veilLayers, page, textHex));
          if (veil?.speck) low = Math.min(low, worst(layers, veil.peaks, page, textHex));
        }
      }
    }
  }
  return low;
}

test('token themes: body >= 7 and soft >= 4.5 under every layer and the veil over the text, night, day and high contrast', () => {
  for (const [name, [colours, atmosphereTheme]] of Object.entries(PLAY_STACKS)) {
    for (const page of [rgbOf(colours.page), playPage(colours)]) {
      for (const token of PLAY_BODY_TOKENS) {
        const text = colours[token].toLowerCase();
        const low = worstOverWorld(atmosphereTheme, page, text, { includeSpecks: true });
        assert.ok(low >= 4.5, `${name} ${token} under a mote or flake ${low}`);
        const veiled = worstOverWorld(atmosphereTheme, page, text);
        assert.ok(veiled >= 7, `${name} ${token} ${veiled}`);
      }
      for (const token of PLAY_SOFT_TOKENS) {
        const low = worstOverWorld(atmosphereTheme, page, colours[token].toLowerCase());
        assert.ok(low >= 4.5, `${name} ${token} ${low}`);
      }
    }
  }
});

test('play screen: every hex text colour left in unwritten-play.css holds its threshold on the night page under every layer', async () => {
  const colours = await playScreenColours();
  assert.ok(colours.length >= 10, `parsed ${colours.length} colours`);
  for (const colour of colours) {
    assert.ok(worstOverWorld('night', NIGHT_PLAY_PAGE, colour) >= 4.5, `${colour}`);
  }
  assert.equal(colours.includes('#deddd4'), false, 'the narration colour is a token now');
});

test('the fog veil keeps its old core strength .16 and is modelled above the text, not only the page', () => {
  const core = WEATHER_TABLE.fog.veil.peaks[0];
  assert.equal(core[3], 0.16);
  const pageOnly = ratio(lum(rgbOf('#e5e4dc')), lum(over(NIGHT_PLAY_PAGE, core)));
  assert.ok(worst([], [core], NIGHT_PLAY_PAGE, '#e5e4dc') < pageOnly, 'compositing over the text as well lowers the ratio');
});

test('neutral atmosphere leaves the page colour untouched', () => {
  const t = themedAtmosphere(NEUTRAL_ATMOSPHERE, 'night');
  for (const [name, c] of Object.entries(t)) assert.equal(c[3], 0, name);
});

/* ---------- layer markup and CSS contract ---------- */

let vite;
let React;
let renderToStaticMarkup;
let mods;
before(async () => {
  process.env.PORT ||= '4179';
  process.env.BASE_PATH ||= '/';
  delete process.env.REPL_ID;
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  mods = {
    layer: await vite.ssrLoadModule('/src/components/scene-atmosphere-layer.tsx'),
    theme: await vite.ssrLoadModule('/src/components/environment-theme.tsx'),
    atmosphere: await vite.ssrLoadModule('/src/components/environment-atmosphere.tsx'),
    appearance: await vite.ssrLoadModule('/src/components/appearance-provider.tsx'),
  };
  React = await import('react');
  ({ renderToStaticMarkup } = await import('react-dom/server'));
});
after(async () => { await vite?.close(); });

const renderLayer = (atmosphere, { theme = 'night', fade = true } = {}) =>
  renderToStaticMarkup(React.createElement(mods.layer.SceneAtmosphereLayer, { atmosphere, theme, fade }));
const count = (html, cls) => (html.match(new RegExp(`class="${cls}"`, 'g')) ?? []).length;

test('layer is aria-hidden, paints no text, and counts motes and fog by level', () => {
  const input = world('forest', 'evening', null);
  const full = renderLayer(resolveAtmosphere(input, 'full'));
  const low = renderLayer(resolveAtmosphere(input, 'low'));
  const off = renderLayer(resolveAtmosphere(input, 'off'), { fade: false });
  for (const html of [full, low, off, renderLayer(NEUTRAL_ATMOSPHERE, { theme: 'day' })]) {
    assert.match(html, /aria-hidden="true"/);
    assert.doesNotMatch(html, />[^<\s]/, 'no text nodes');
  }
  assert.equal(count(full, 'unw-atmo-mote'), 6);
  assert.equal(count(low, 'unw-atmo-mote'), 3);
  assert.equal(count(off, 'unw-atmo-mote'), 0);
  assert.equal(count(full, 'unw-atmo-fog'), 2);
  assert.equal(count(off, 'unw-atmo-fog'), 0);
  assert.match(off, /data-motion="0"/);
  assert.match(off, /data-fade="0"/);
  assert.match(full, /data-fade="1"/);
});

test('crossfade contract: neutral <-> preset animates through registered colour variables, only when effects are not off', async () => {
  const css = await readFile(new URL('../src/components/scene-atmosphere-layer.css', import.meta.url), 'utf8');
  const vars = ['--sc-hue', '--sc-wx', '--sc-tint', '--sc-bloom', '--sc-win', '--sc-vig', '--sc-fog', '--sc-mote', '--sc-bx', '--sc-by', '--sc-br'];
  const at = css.indexOf('.unw-atmo {');
  const baseRule = css.slice(at, css.indexOf('}', at));
  const transition = baseRule.slice(baseRule.indexOf('transition:'));
  // Every variable has an endpoint on both the neutral and the preset layer, a registered type and a 1.5 s transition.
  const neutral = renderLayer(NEUTRAL_ATMOSPHERE, { fade: true });
  const preset = renderLayer(resolveAtmosphere(world('tavern', 'night', null), 'full'), { fade: true });
  for (const name of vars) {
    assert.ok(neutral.includes(`${name}:`), `neutral sets ${name}`);
    assert.ok(preset.includes(`${name}:`), `preset sets ${name}`);
    assert.match(transition, new RegExp(`${name} 1\\.5s ease-in-out`), `${name} transitions in 1.5 s`);
    assert.match(css, new RegExp(`@property ${name} \\{`), `${name} registered`);
  }
  for (const name of vars.filter((v) => !['--sc-bx', '--sc-by', '--sc-br'].includes(v))) {
    assert.match(css, new RegExp(`var\\(${name}\\)`), `${name} is consumed by a layer element`);
  }
  // The preset really differs from neutral, so there is something to fade between.
  assert.notEqual(neutral.match(/--sc-tint:[^;"]*/)[0], preset.match(/--sc-tint:[^;"]*/)[0]);
  // Fade follows the effects level, not the preset's motion: on for neutral and preset, off when effects are off.
  assert.match(neutral, /data-motion="0"/);
  assert.match(neutral, /data-fade="1"/);
  assert.match(preset, /data-fade="1"/);
  assert.match(renderLayer(resolveAtmosphere(world('tavern', 'night', null), 'off'), { fade: false }), /data-fade="0"/);
  assert.match(css, /\.unw-atmo\[data-fade="0"\] \{ transition: none; \}/);
  // Nothing else restricts when the base transition applies (the only overrides are fade 0 and reduced motion).
  const selectors = [...css.matchAll(/([^{}]*)\{[^{}]*\btransition\b/g)].map((m) => m[1].trim().split('\n').pop().trim());
  assert.deepEqual(selectors, [".unw-atmo", ".unw-atmo[data-fade=\"0\"]", ".unw-atmo"]);
  // Park (not asserted): veil, fog bands and motes appear abruptly; only the colour layers crossfade.
});

test('weather veil renders above the page as its own aria-hidden element, also with effects off', () => {
  for (const level of ['off', 'low', 'full']) {
    for (const weather of ['rain', 'fog', 'snow', 'storm']) {
      const html = renderLayer(resolveAtmosphere(world('forest', 'night', weather), level), { fade: level !== 'off' });
      assert.equal(count(html, 'unw-atmo-veil'), 1, `${level} ${weather}`);
      assert.match(html, /<div class="unw-atmo-veil" aria-hidden="true"/, `${level} ${weather}`);
      assert.ok(html.includes(`opacity:${WEATHER_TABLE[weather].veil.opacity}`), `${level} ${weather} opacity`);
    }
  }
  const clear = renderLayer(resolveAtmosphere(world('forest', 'night', 'clear'), 'full'));
  assert.doesNotMatch(clear, /unw-atmo-veil/);
  assert.doesNotMatch(renderLayer(NEUTRAL_ATMOSPHERE), /unw-atmo-veil/);
});

test('layer CSS contract: never catches input, stays under the text, crossfades, honours reduced motion', async () => {
  const css = await readFile(new URL('../src/components/scene-atmosphere-layer.css', import.meta.url), 'utf8');
  const rule = (selector) => {
    const at = css.indexOf(`${selector} {`);
    assert.ok(at >= 0, `rule ${selector}`);
    return css.slice(at, css.indexOf('}', at) + 1);
  };
  const layer = rule('.unw-atmo');
  assert.match(layer, /pointer-events: none/);
  assert.match(layer, /z-index: -1/);
  assert.match(layer, /position: absolute/);
  for (const prop of ['--sc-hue', '--sc-wx', '--sc-tint', '--sc-bloom', '--sc-win', '--sc-vig', '--sc-fog', '--sc-mote', '--sc-bx', '--sc-by', '--sc-br']) {
    assert.match(layer, new RegExp(`${prop} 1\\.5s ease-in-out`), `${prop} transitions in 1.5 s`);
    assert.match(css, new RegExp(`@property ${prop} \\{`), `${prop} registered so it can animate`);
  }
  assert.match(rule('.unw-atmo[data-fade="0"]'), /transition: none/);
  assert.doesNotMatch(css, /data-motion="0"\] \{ transition/, 'fade must not depend on motion elements');
  const veil = rule('.unw-atmo-veil');
  assert.match(veil, /pointer-events: none/);
  assert.match(veil, /position: fixed/);
  const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'));
  assert.match(reduced, /\.unw-atmo \{ transition: none; \}/);
  assert.match(reduced, /\.unw-atmo-fog, \.unw-atmo-mote \{ display: none; \}/);
  assert.match(css, /\.unw-atmo\[data-hidden="1"\] \.unw-atmo-fog/);
});

/* ---------- provider and mounted wiring ---------- */

function withWindow(storedSettings, run) {
  const had = 'window' in globalThis;
  const previous = globalThis.window;
  globalThis.window = {
    localStorage: { getItem: () => (storedSettings ? JSON.stringify(storedSettings) : null), setItem() {} },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
  };
  try { return run(); } finally { if (had) globalThis.window = previous; else delete globalThis.window; }
}

const stateOf = (w, time = { hour: 13, minute: 5 }) => ({ world: w, campaign_time: time });
function renderWired(state, stored = null) {
  return withWindow(stored, () => renderToStaticMarkup(
    React.createElement(mods.appearance.AppearanceProvider, null,
      React.createElement(mods.theme.EnvironmentThemeProvider, { state }, React.createElement(mods.atmosphere.EnvironmentAtmosphere))),
  ));
}
const attr = (html, name) => new RegExp(`${name}="([^"]*)"`).exec(html)?.[1];

test('provider maps world fields to the wrapper and the layer', () => {
  const html = renderWired(stateOf({ environment: 'forest', time_of_day: 'night', weather: 'rain' }));
  assert.equal(attr(html, 'data-environment'), 'forest');
  assert.equal(attr(html, 'data-time'), 'night');
  assert.equal(attr(html, 'data-weather'), 'rain');
  assert.equal(attr(html, 'data-theme-source'), 'canonical-world');
  assert.match(html, /--theme-line:rgba\(104,132,94,0\.7000\)/, 'location ribbon edge follows the family table');
  assert.match(html, /class="unw-atmo"[^>]*data-atmosphere="forest" data-period="night" data-weather="rain"/);
  assert.match(html, /class="unw-atmo-veil"/);
});

test('mounted layer splits day by the clock and treats a missing clock as morning', () => {
  const periodOf = (state) => attr(renderWired(state), 'data-period');
  assert.equal(periodOf(stateOf({ environment: 'road', time_of_day: 'day', weather: 'clear' }, { hour: 9, minute: 0 })), 'morning');
  assert.equal(periodOf(stateOf({ environment: 'road', time_of_day: 'day', weather: 'clear' }, { hour: 14, minute: 30 })), 'afternoon');
  assert.equal(periodOf(stateOf({ environment: 'road', time_of_day: 'day', weather: 'clear' }, null)), 'morning');
  assert.equal(periodOf(stateOf({ environment: 'tavern', time_of_day: 'dawn', weather: 'clear' }, { hour: 6, minute: 0 })), 'dawn');
});

test('no world, unknown environment or unknown weather draw no place tint and no unknown weather', () => {
  for (const state of [undefined, {}, stateOf({ environment: 'unknown', time_of_day: 'day', weather: 'unknown' })]) {
    const html = renderWired(state);
    assert.match(html, /data-atmosphere="neutral"/);
    assert.doesNotMatch(html, /data-period=/);
    assert.doesNotMatch(html, /data-weather="unknown"/);
    assert.doesNotMatch(html, /unw-atmo-veil/);
    assert.match(html, /--theme-line:rgba\(117,108,91,0\.6200\)/);
  }
  assert.equal(attr(renderWired(undefined), 'data-theme-source'), 'neutral-default');
});

test('the effects setting reaches the mounted layer: off is static, low is half, full is full', () => {
  const state = stateOf({ environment: 'forest', time_of_day: 'evening', weather: 'fog' });
  const full = renderWired(state, { effectsLevel: 'full' });
  const low = renderWired(state, { effectsLevel: 'low' });
  const off = renderWired(state, { effectsLevel: 'off' });
  assert.equal(count(full, 'unw-atmo-mote'), 6);
  assert.equal(count(low, 'unw-atmo-mote'), 3);
  assert.equal(count(off, 'unw-atmo-mote'), 0);
  assert.equal(count(off, 'unw-atmo-fog'), 0);
  assert.match(off, /data-fade="0"/);
  assert.match(off, /data-atmosphere="forest"/, 'off keeps the static tint');
  assert.match(off, /class="unw-atmo-veil"/, 'the static veil stays');
});

/* ---------- old CSS gone, consumers intact ---------- */

async function sourceFiles(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await sourceFiles(full));
    else if (/\.(tsx?|css)$/.test(entry.name)) out.push(full);
  }
  return out;
}

test('old wash variables and weather ::before overlays are gone from the CSS', async () => {
  const css = await readFile(new URL('../src/index.css', import.meta.url), 'utf8');
  for (const gone of ['--theme-wash', '--time-wash', '--weather-wash']) assert.ok(!css.includes(gone), gone);
  assert.doesNotMatch(css, /\.environment-theme\[data-(environment|time|weather)/);
  assert.doesNotMatch(css, /\.environment-theme[^{]*::before/);
  assert.doesNotMatch(css, /repeating-linear-gradient\(108deg/, 'rain veil lives in the table now');
  // The page background for a neutral atmosphere is the single static wash that was the old default.
  assert.match(css, /\.dnd-app \{[^}]*radial-gradient\(ellipse at 12% 8%, rgba\(86, 78, 64, \.11\), transparent 42rem\),\s*transparent;/);
  assert.match(css, /\.environment-theme \{[^}]*--theme-line: rgba\(117, 108, 91, \.62\);/);
});

test('every consumer of the environment theme still resolves, and the layer is mounted once', async () => {
  const root = new URL('../src/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
  const files = await sourceFiles(decodeURIComponent(root));
  const users = [];
  for (const file of files) {
    const text = await readFile(file, 'utf8');
    if (/useEnvironmentTheme|EnvironmentThemeProvider|--theme-line|SceneAtmosphereLayer|EnvironmentAtmosphere/.test(text)) {
      users.push(path.relative(decodeURIComponent(root), file).replaceAll('\\', '/'));
    }
  }
  assert.deepEqual(users.sort(), [
    'components/environment-atmosphere.tsx',
    'components/environment-theme.tsx',
    'components/scene-atmosphere-layer.tsx',
    'index.css',
    'lib/scene-atmosphere.ts',
    'pages/game-browser.tsx',
  ]);
  assert.equal(typeof mods.theme.useEnvironmentTheme, 'function');
  const game = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
  assert.equal(game.split('<EnvironmentAtmosphere />').length - 1, 1);
  const open = game.indexOf('className="design-preview dnd-app play-shell"');
  const mount = game.indexOf('<EnvironmentAtmosphere />');
  const body = game.indexOf('<div className="preview-background">');
  assert.ok(open > 0 && mount > open && mount < body, 'layer is the first child inside .dnd-app, behind the content');
});
