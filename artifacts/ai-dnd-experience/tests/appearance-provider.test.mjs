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
const checkedValue = (html) => /value="(\w+)"[^>]*checked/.exec(html)?.[1] ?? /checked=""[^>]*value="(\w+)"/.exec(html)?.[1];

test('panel renders the three levels in Turkish, an accessible radio group, and the reduced-motion note', () => {
  const html = renderPanel();
  assert.match(html, /data-testid="appearance-settings-panel"/);
  assert.match(html, /role="radiogroup"/);
  assert.match(html, /<legend>Efekt seviyesi<\/legend>/);
  for (const label of ['Kapalı', 'Az', 'Tam']) assert.match(html, new RegExp(`<span>${label}</span>`));
  assert.equal((html.match(/type="radio"/g) ?? []).length, 3);
  assert.match(html, /Hareketi azalt ayarı sistemden okunur/);
  assert.doesNotMatch(html, /zar|can göstergesi|tema|yazı tipi/i);
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
    assert.equal((html.match(/checked=""/g) ?? []).length, 1);
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
