import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import {
  readPrefersReducedMotion,
  subscribePrefersReducedMotion,
} from '../src/lib/reduced-motion.ts';
import { tabStops, trapWrapTarget } from '../src/lib/focus-trap.ts';
import { createAppearanceStore } from '../src/lib/appearance-store.ts';
import { resolveEffectsLevel, DEFAULT_APPEARANCE_SETTINGS } from '../src/lib/appearance-settings.ts';

process.env.PORT ||= '4190';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let React;
let renderToStaticMarkup;
let AppearanceProvider;
let AppearanceSettingsPanel;
let useAppearance;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  ({ AppearanceProvider, useAppearance } = await vite.ssrLoadModule('/src/components/appearance-provider.tsx'));
  ({ AppearanceSettingsPanel } = await vite.ssrLoadModule('/src/components/appearance-settings-panel.tsx'));
  React = await import('react');
  ({ renderToStaticMarkup } = await import('react-dom/server'));
});
after(async () => { await vite?.close(); });

function withWindow(fakeWindow, run) {
  const had = 'window' in globalThis;
  const previous = globalThis.window;
  globalThis.window = fakeWindow;
  try { return run(); } finally { if (had) globalThis.window = previous; else delete globalThis.window; }
}

const renderPanel = () => renderToStaticMarkup(
  React.createElement(AppearanceProvider, null, React.createElement(AppearanceSettingsPanel)),
);
const inputTags = (html) => [...html.matchAll(/<input[^>]*>/g)].map((m) => m[0]);
const checkedIn = (html, name) => inputTags(html)
  .filter((tag) => tag.includes(`name="${name}"`) && /checked=""/.test(tag))
  .map((tag) => /value="(\w+)"/.exec(tag)?.[1]);
const checkedValue = (html) => { const found = checkedIn(html, 'appearance-effects-level'); assert.equal(found.length, 1, 'exactly one effects level is checked'); return found[0]; };

test('panel renders theme, effects level, ink speed and readability controls in Turkish, as accessible groups, and no control for a setting without a consumer', () => {
  const html = renderPanel();
  assert.match(html, /data-testid="appearance-settings-panel"/);
  assert.equal((html.match(/role="radiogroup"/g) ?? []).length, 3);
  for (const legend of ['Okuma teması', 'Efekt seviyesi', 'Mürekkep belirme hızı', 'Ses', 'Okunabilirlik']) assert.match(html, new RegExp(`<legend>${legend}</legend>`));
  for (const label of ['Gece', 'Gündüz', 'Sistem', 'Kapalı', 'Az', 'Tam', 'Yavaş', 'Normal', 'Hızlı', 'Anında', 'Ana menü müziği', 'Yüksek kontrast', 'Disleksi dostu yazı tipi']) {
    assert.match(html, new RegExp(`<span>${label}</span>`), label);
  }
  assert.equal(inputTags(html).filter((tag) => tag.includes('type="radio"')).length, 3 + 3 + 4);
  assert.equal(inputTags(html).filter((tag) => tag.includes('type="checkbox"')).length, 3);
  assert.match(html, /Hareketi azalt ayarı sistemden okunur/);
  // Dice set, health gauge, spell-slot style and font scale are stored but nothing reads them yet: no control.
  assert.doesNotMatch(html, /zar|can göstergesi|büyü yuvası|yazı boyutu/i);
});

test('defaults are checked per group: night, full effects, normal ink speed, both readability boxes off, menu music on', () => {
  const html = renderPanel();
  assert.deepEqual(checkedIn(html, 'appearance-theme'), ['night']);
  assert.deepEqual(checkedIn(html, 'appearance-effects-level'), ['full']);
  assert.deepEqual(checkedIn(html, 'appearance-ink-speed'), ['normal']);
  assert.equal(inputTags(html).filter((tag) => tag.includes('type="checkbox"') && /checked=""/.test(tag)).length, 1);
  assert.ok(inputTags(html).some((tag) => tag.includes('checkbox-menu-music') && /checked=""/.test(tag)));
});

test('stored theme, ink speed and readability flags come back through the provider', () => {
  const store = { localStorage: { getItem: () => JSON.stringify({ theme: 'day', inkRevealSpeed: 'fast', highContrast: true, dyslexiaFont: true }), setItem() {} } };
  const html = withWindow(store, renderPanel);
  assert.deepEqual(checkedIn(html, 'appearance-theme'), ['day']);
  assert.deepEqual(checkedIn(html, 'appearance-ink-speed'), ['fast']);
  const boxes = inputTags(html).filter((tag) => tag.includes('type="checkbox"'));
  assert.equal(boxes.length, 3);
  assert.ok(boxes.every((tag) => /checked=""/.test(tag)));
});

test('with storage unavailable the panel shows the default level, where a readable store would show the stored one', () => {
  const readable = { localStorage: { getItem: () => JSON.stringify({ effectsLevel: 'low' }), setItem() {} } };
  assert.equal(checkedValue(withWindow(readable, renderPanel)), 'low');
  assert.equal(checkedValue(renderPanel()), DEFAULT_APPEARANCE_SETTINGS.effectsLevel);
  const throwing = { get localStorage() { throw new Error('blocked'); } };
  assert.equal(checkedValue(withWindow(throwing, renderPanel)), 'full');
  const failingStore = { localStorage: { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } } };
  assert.equal(checkedValue(withWindow(failingStore, renderPanel)), 'full');
});

test('the stored level is restored through the provider and marked as current', () => {
  for (const level of ['off', 'low', 'full']) {
    const store = { localStorage: { getItem: () => JSON.stringify({ effectsLevel: level }), setItem() {} } };
    const html = withWindow(store, renderPanel);
    assert.equal(checkedValue(html), level);
    assert.deepEqual(checkedIn(html, 'appearance-effects-level'), [level]);
    assert.equal((html.match(/checked=""/g) ?? []).length, 4, 'one checked radio in each of the three groups, plus the menu-music box (on by default)');
  }
});

test('reduced motion caps the resolved level regardless of the chosen one', () => {
  for (const effectsLevel of ['off', 'low', 'full']) {
    const settings = { ...DEFAULT_APPEARANCE_SETTINGS, effectsLevel };
    assert.equal(resolveEffectsLevel(settings, true), 'off');
    assert.equal(resolveEffectsLevel(settings, false), effectsLevel);
  }
});

function fakeMedia(initial) {
  const listeners = new Set();
  const query = {
    matches: initial,
    addEventListener(_t, l) { listeners.add(l); },
    removeEventListener(_t, l) { listeners.delete(l); },
  };
  return { query, listeners, flip(next) { query.matches = next; for (const l of [...listeners]) l(); } };
}

test('reduced-motion preference is read live and the subscription is removable', () => {
  const media = fakeMedia(false);
  const win = { matchMedia: () => media.query };
  assert.equal(readPrefersReducedMotion(win), false);
  let calls = 0;
  const off = subscribePrefersReducedMotion(win, () => { calls += 1; });
  media.flip(true);
  assert.equal(readPrefersReducedMotion(win), true);
  assert.equal(calls, 1);
  off();
  media.flip(false);
  assert.equal(calls, 1);
  assert.equal(media.listeners.size, 0);
});

test('reduced-motion helpers tolerate a missing or throwing matchMedia', () => {
  for (const win of [null, undefined, {}, { matchMedia() { throw new Error('nope'); } }]) {
    assert.equal(readPrefersReducedMotion(win), false);
    assert.doesNotThrow(() => subscribePrefersReducedMotion(win, () => {})());
  }
});

test('reduced-motion subscription falls back to addListener, and never throws into the caller', () => {
  const listeners = new Set();
  const legacy = { matches: true, addListener: (l) => listeners.add(l), removeListener: (l) => listeners.delete(l) };
  let calls = 0;
  const off = subscribePrefersReducedMotion({ matchMedia: () => legacy }, () => { calls += 1; });
  assert.equal(listeners.size, 1);
  for (const l of listeners) l();
  assert.equal(calls, 1);
  off();
  assert.equal(listeners.size, 0);
  const throwingQuery = { matches: false, addEventListener() { throw new Error('no'); }, removeEventListener() { throw new Error('no'); } };
  assert.doesNotThrow(() => subscribePrefersReducedMotion({ matchMedia: () => throwingQuery }, () => {})());
  assert.doesNotThrow(() => subscribePrefersReducedMotion({ matchMedia: () => ({ matches: false }) }, () => {})());
  const throwingOff = { matches: false, addEventListener() {}, removeEventListener() { throw new Error('no'); } };
  assert.doesNotThrow(() => subscribePrefersReducedMotion({ matchMedia: () => throwingOff }, () => {})());
});

function radioStops(checked) {
  const radios = ['off', 'low', 'full'].map((value) => ({ type: 'radio', name: 'appearance-effects-level', value, checked: value === checked }));
  return { close: { type: 'submit' }, radios };
}

test('focus trap: only the checked radio is a Tab stop, so Tab wraps from it for every checked value', () => {
  for (const [index, checked] of ['off', 'low', 'full'].entries()) {
    const { close, radios } = radioStops(checked);
    const stops = tabStops([close, ...radios]);
    assert.deepEqual(stops, [close, radios[index]]);
    assert.equal(trapWrapTarget(stops, radios[index], false), close, 'forward from checked radio wraps to first');
    assert.equal(trapWrapTarget(stops, close, true), radios[index], 'backward from first wraps to checked radio');
    assert.equal(trapWrapTarget(stops, close, false), null, 'forward from first is left to the browser');
    assert.equal(trapWrapTarget(stops, radios[index], true), null);
  }
});

test('focus trap: no checked radio keeps the first of the group; other groups and non-radios are untouched', () => {
  const { close, radios } = radioStops(null);
  const other = { type: 'radio', name: 'other', checked: true };
  const unnamed = { type: 'radio', checked: false };
  assert.deepEqual(tabStops([close, ...radios, other, unnamed]), [close, radios[0], other, unnamed]);
  assert.equal(trapWrapTarget([], close, false), null);
});

function memoryStorage(initial = null) {
  let value = initial;
  return { getItem: () => value, setItem: (_k, next) => { value = next; }, read: () => value };
}

test('setSetting persists and a fresh store restores it; unchanged value does not notify; unsubscribe stops calls', () => {
  const storage = memoryStorage();
  const store = createAppearanceStore(storage);
  let notified = 0;
  const off = store.subscribe(() => { notified += 1; });
  store.set('effectsLevel', 'low');
  assert.equal(store.get().effectsLevel, 'low');
  assert.equal(JSON.parse(storage.read()).effectsLevel, 'low');
  assert.equal(createAppearanceStore(storage).get().effectsLevel, 'low');
  store.set('effectsLevel', 'low');
  assert.equal(notified, 1);
  off();
  store.set('effectsLevel', 'off');
  assert.equal(notified, 1);
});

test('a throwing setItem or getItem does not crash and the in-memory choice is kept', () => {
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  const store = createAppearanceStore(blocked);
  assert.equal(store.get().effectsLevel, 'full');
  assert.doesNotThrow(() => store.set('effectsLevel', 'off'));
  assert.equal(store.get().effectsLevel, 'off');
  assert.equal(createAppearanceStore(null).get().effectsLevel, 'full');
});

test('provider exposes the reduced-motion-capped level and the raw choice; no-provider defaults', () => {
  function Probe() {
    const a = useAppearance();
    return React.createElement('i', { 'data-level': a.effectsLevel, 'data-choice': a.settings.effectsLevel, 'data-rm': String(a.prefersReducedMotion) });
  }
  const html = (win, provided) => withWindow(win, () => renderToStaticMarkup(
    provided ? React.createElement(AppearanceProvider, null, React.createElement(Probe)) : React.createElement(Probe)));
  const stored = { getItem: () => JSON.stringify({ effectsLevel: 'low' }), setItem() {} };
  const reduced = { localStorage: stored, matchMedia: () => ({ matches: true }) };
  const normal = { localStorage: stored, matchMedia: () => ({ matches: false }) };
  assert.match(html(reduced, true), /data-level="off" data-choice="low" data-rm="true"/);
  assert.match(html(normal, true), /data-level="low" data-choice="low" data-rm="false"/);
  assert.match(html(reduced, false), /data-level="full" data-choice="full" data-rm="false"/);
});

test('SessionHeader offers the Görünüm trigger and the settings drawer, leaving character and world intact', () => {
  const source = readGameBrowserSource();
  assert.match(source, /data-testid="button-open-settings"[^>]*onClick=\{\(event\) => onDrawer\('settings', event\.currentTarget\)\}/);
  assert.match(source, /Görünüm<\/button>/);
  assert.match(source, /export type Drawer = 'character' \| 'world' \| 'settings' \| null;/);
  assert.match(source, /data-testid="button-open-character"/);
  assert.match(source, /data-testid="button-open-world"/);
});

test('settings drawer shares the DrawerSheet trap, Escape and focus return, and shows the panel instead of world or character content', () => {
  const source = readGameBrowserSource();
  assert.match(source, /tabStops\(Array\.from\(dialog\?\.querySelectorAll/);
  assert.match(source, /trapWrapTarget\(elements, document\.activeElement, event\.shiftKey\)/);
  assert.match(source, /event\.key === 'Escape'[\s\S]{0,80}closeRef\.current\(\)/);
  assert.match(source, /focusReturnTarget\(Boolean\(opener\?\.isConnected\)\)/);
  assert.match(source, /drawer === 'character' \? <LeftColumn[^\n]*\/> : drawer === 'settings' \? <AppearanceSettingsPanel \/> : <WorldTabs/);
});
