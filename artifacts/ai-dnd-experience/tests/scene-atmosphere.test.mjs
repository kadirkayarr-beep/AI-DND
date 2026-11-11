import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { contrastRatio } from '../src/lib/contrast.ts';
import { UNW_THEME_COLORS } from '../src/lib/unw-theme.ts';
import { MAX_ACTIVE_EFFECTS } from '../src/lib/effect-registry.ts';
import {
  ATMOSPHERE_PLACE_KINDS,
  ATMOSPHERE_TABLE,
  DAY_PERIODS,
  FOG_BANDS,
  MOTE_POOL,
  NEUTRAL_ATMOSPHERE,
  periodFromClock,
  placeKindFromSceneKind,
  resolveAtmosphere,
  themedAtmosphere,
} from '../src/lib/scene-atmosphere.ts';

const CLOCKS = [[5, 0], [8, 0], [13, 0], [18, 0], [22, 0]];
const SCENE_KINDS = ['wilderness', 'city', 'tavern', 'building', 'quiet'];

test('periodFromClock honours the five boundaries and wraps night', () => {
  const cases = [
    [0, 0, 'night'], [4, 59, 'night'], [5, 0, 'dawn'], [6, 59, 'dawn'], [7, 0, 'morning'],
    [11, 59, 'morning'], [12, 0, 'afternoon'], [16, 59, 'afternoon'], [17, 0, 'evening'],
    [19, 59, 'evening'], [20, 0, 'night'], [23, 59, 'night'],
  ];
  for (const [h, m, expected] of cases) assert.equal(periodFromClock(h, m), expected, `${h}:${m}`);
});

test('periodFromClock rejects non-integer and out-of-range input', () => {
  for (const [h, m] of [[1.5, 0], [0, 0.5], [-1, 0], [24, 0], [0, 60], [0, -1], [NaN, 0], [0, Infinity]]) {
    assert.equal(periodFromClock(h, m), null, `${h}:${m}`);
  }
  assert.equal(periodFromClock(undefined, 0), null);
  assert.equal(periodFromClock('7', 0), null);
});

test('scene.kind maps the five engine values and rejects the rest', () => {
  for (const k of ['wilderness', 'city']) assert.equal(placeKindFromSceneKind(k), 'outdoor');
  for (const k of ['tavern', 'building', 'quiet']) assert.equal(placeKindFromSceneKind(k), 'indoor');
  for (const k of [null, undefined, '', 'harbor', 'Tavern']) assert.equal(placeKindFromSceneKind(k), null);
});

test('every kind x period table cell exists with all required fields', () => {
  const isRgba = (c) => Array.isArray(c) && c.length === 4 && c.every((v, i) => Number.isFinite(v) && v >= 0 && v <= (i < 3 ? 255 : 1));
  for (const kind of ATMOSPHERE_PLACE_KINDS) {
    assert.deepEqual(Object.keys(ATMOSPHERE_TABLE[kind]).sort(), [...DAY_PERIODS].sort(), kind);
    for (const period of DAY_PERIODS) {
      const p = ATMOSPHERE_TABLE[kind][period];
      const at = `${kind}/${period}`;
      for (const f of ['tint', 'win', 'vig', 'fog']) assert.ok(isRgba(p[f]), `${at} ${f}`);
      assert.ok(isRgba(p.bloom.c), `${at} bloom.c`);
      for (const f of ['x', 'y', 'r']) assert.ok(Number.isFinite(p.bloom[f]), `${at} bloom.${f}`);
      assert.ok(isRgba(p.mote.c), `${at} mote.c`);
      assert.ok(Number.isInteger(p.mote.n) && p.mote.n >= 0 && p.mote.n <= MOTE_POOL, `${at} mote.n`);
      assert.ok(Number.isFinite(p.mote.glow), `${at} mote.glow`);
    }
  }
});

test('missing or unknown inputs resolve to the neutral preset', () => {
  const neutralInputs = [
    {}, { clock: null, sceneKind: 'tavern' }, { clock: { hour: 9, minute: 0 } },
    { clock: { hour: 9, minute: 0 }, sceneKind: 'harbor' }, { clock: { hour: 99, minute: 0 }, sceneKind: 'city' },
    { clock: { hour: 9, minute: 0 }, sceneKind: null },
  ];
  for (const input of neutralInputs) {
    for (const level of ['off', 'low', 'full']) {
      const r = resolveAtmosphere(input, level);
      assert.equal(r, NEUTRAL_ATMOSPHERE);
      assert.equal(r.kind, 'neutral');
      assert.equal(r.motion, null);
      assert.equal(r.tint[3], 0);
      assert.equal(r.vig[3], 0);
    }
  }
});

test('crowd and fire sockets are ignored', () => {
  const base = { clock: { hour: 21, minute: 0 }, sceneKind: 'tavern' };
  assert.deepEqual(resolveAtmosphere({ ...base, crowd: 3, fire: true }, 'full'), resolveAtmosphere(base, 'full'));
});

test('effects off keeps the static tint and drops every motion field', () => {
  for (const sceneKind of SCENE_KINDS) {
    for (const [hour, minute] of CLOCKS) {
      const r = resolveAtmosphere({ clock: { hour, minute }, sceneKind }, 'off');
      assert.equal(r.motion, null, `${sceneKind} ${hour}`);
      assert.ok(r.tint[3] > 0, `${sceneKind} ${hour} keeps a tint`);
      assert.notEqual(r.kind, 'neutral');
    }
  }
});

test('low halves the motes and fog bands; full stays under the animated budget', () => {
  for (const sceneKind of ['wilderness', 'tavern']) {
    for (const [hour, minute] of CLOCKS) {
      const input = { clock: { hour, minute }, sceneKind };
      const full = resolveAtmosphere(input, 'full').motion;
      const low = resolveAtmosphere(input, 'low').motion;
      assert.equal(low.mote.n, Math.ceil(full.mote.n / 2));
      assert.equal(full.fogBands, FOG_BANDS);
      assert.equal(low.fogBands, 1);
      assert.ok(full.mote.n + full.fogBands <= MAX_ACTIVE_EFFECTS);
    }
  }
});

test('only a tavern gets window light', () => {
  const at = (sceneKind) => resolveAtmosphere({ clock: { hour: 8, minute: 0 }, sceneKind }, 'full').win[3];
  assert.ok(at('tavern') > 0);
  for (const k of ['building', 'quiet', 'city', 'wilderness']) assert.equal(at(k), 0, k);
});

/*
 * Contrast safety. Model (V4 NOTLAR): for every scene kind x period and both themes, take the
 * full-effects preset (fog counted as two bands), scale layers per theme, and alpha-composite every
 * subset of layers over the theme page colour at peak alpha; the worst resulting background is
 * checked against --unw-text (needs 7) and --unw-text-soft (needs 4.5). Motes are 2-3 px dots: they
 * are left out of the body/soft rule (as in V4) and checked separately for body text only (>= 4.5).
 */
const hex = (c) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
const over = (bg, l) => bg.map((v, i) => v * (1 - l[3]) + l[i] * l[3]);

function worstContrast(layers, theme, text) {
  const page = UNW_THEME_COLORS[theme].page;
  const base = [1, 3, 5].map((i) => parseInt(page.slice(i, i + 2), 16));
  let worst = Infinity;
  for (let mask = 0; mask < 1 << layers.length; mask++) {
    let bg = base;
    layers.forEach((l, i) => { if (mask & (1 << i)) bg = over(bg, l); });
    worst = Math.min(worst, contrastRatio(text, hex(bg)));
  }
  return worst;
}

test('text over the atmosphere keeps body >= 7 and soft >= 4.5 in both themes', () => {
  let checked = 0;
  for (const theme of ['night', 'day']) {
    const colours = UNW_THEME_COLORS[theme];
    for (const sceneKind of SCENE_KINDS) {
      for (const [hour, minute] of CLOCKS) {
        const t = themedAtmosphere(resolveAtmosphere({ clock: { hour, minute }, sceneKind }, 'full'), theme);
        const layers = [t.tint, t.bloom, t.win, t.fog, t.fog, t.vig];
        const at = `${theme} ${sceneKind} ${hour}:${minute}`;
        assert.ok(worstContrast(layers, theme, colours.text) >= 7, `${at} body`);
        assert.ok(worstContrast(layers, theme, colours.textSoft) >= 4.5, `${at} soft`);
        assert.ok(worstContrast([...layers, t.mote], theme, colours.text) >= 4.5, `${at} body under a mote`);
        checked += 1;
      }
    }
  }
  assert.equal(checked, 50);
});

let vite;
let renderLayer;
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
  const mod = await vite.ssrLoadModule('/src/components/scene-atmosphere-layer.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  renderLayer = (atmosphere, theme = 'night') => renderToStaticMarkup(React.createElement(mod.SceneAtmosphereLayer, { atmosphere, theme }));
});
after(async () => { await vite?.close(); });

test('layer is aria-hidden, paints no text, and counts motes by level', () => {
  const input = { clock: { hour: 18, minute: 0 }, sceneKind: 'wilderness' };
  const full = renderLayer(resolveAtmosphere(input, 'full'));
  const low = renderLayer(resolveAtmosphere(input, 'low'));
  const off = renderLayer(resolveAtmosphere(input, 'off'));
  for (const html of [full, low, off, renderLayer(NEUTRAL_ATMOSPHERE, 'day')]) {
    assert.match(html, /aria-hidden="true"/);
    assert.doesNotMatch(html, />[^<\s]/, 'no text nodes');
  }
  const count = (html, cls) => (html.match(new RegExp(`class="${cls}"`, 'g')) ?? []).length;
  assert.equal(count(full, 'unw-atmo-mote'), 6);
  assert.equal(count(low, 'unw-atmo-mote'), 3);
  assert.equal(count(off, 'unw-atmo-mote'), 0);
  assert.equal(count(off, 'unw-atmo-fog'), 0);
  assert.match(off, /data-motion="0"/);
});
