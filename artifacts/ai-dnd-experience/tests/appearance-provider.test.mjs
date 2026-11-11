import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import {
  readPrefersReducedMotion,
  subscribePrefersReducedMotion,
} from '../src/lib/reduced-motion.ts';
import { resolveEffectsLevel, DEFAULT_APPEARANCE_SETTINGS } from '../src/lib/appearance-settings.ts';

process.env.PORT ||= '4190';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let React;
let renderToStaticMarkup;
let AppearanceProvider;
let AppearanceSettingsPanel;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  ({ AppearanceProvider } = await vite.ssrLoadModule('/src/components/appearance-provider.tsx'));
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

test('with storage unavailable the panel shows the default level and the provider does not throw', () => {
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

test('SessionHeader offers the Görünüm trigger and the settings drawer, leaving character and world intact', () => {
  const source = readGameBrowserSource();
  assert.match(source, /data-testid="button-open-settings"[^>]*onClick=\{\(event\) => onDrawer\('settings', event\.currentTarget\)\}/);
  assert.match(source, /Görünüm<\/button>/);
  assert.match(source, /export type Drawer = 'character' \| 'world' \| 'settings' \| null;/);
  assert.match(source, /drawer === 'settings' \? <AppearanceSettingsPanel \/>/);
  assert.match(source, /data-testid="button-open-character"/);
  assert.match(source, /data-testid="button-open-world"/);
});
