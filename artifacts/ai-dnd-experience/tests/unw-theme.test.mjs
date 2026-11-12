import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { contrastRatio } from '../src/lib/contrast.ts';
import { UNW_THEME_COLORS, applyTheme, resolveTheme } from '../src/lib/unw-theme.ts';

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');
const kebab = (name) => name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

test('resolveTheme honours explicit choices and resolves system from the flag', () => {
  assert.equal(resolveTheme('night', false), 'night');
  assert.equal(resolveTheme('day', true), 'day');
  assert.equal(resolveTheme('system', true), 'night');
  assert.equal(resolveTheme('system', false), 'day');
});

test('applyTheme sets data-unw-theme on the root and returns the resolved theme', () => {
  const attrs = {};
  const root = { setAttribute: (k, v) => { attrs[k] = v; } };
  assert.equal(applyTheme(root, 'system', false), 'day');
  assert.deepEqual(attrs, { 'data-unw-theme': 'day' });
  assert.equal(applyTheme(root, 'night', false), 'night');
  assert.equal(attrs['data-unw-theme'], 'night');
});

test('text and soft text reach WCAG 4.5:1 on the page in both themes', () => {
  for (const theme of ['night', 'day']) {
    const c = UNW_THEME_COLORS[theme];
    assert.ok(contrastRatio(c.text, c.page) >= 4.5, `${theme} text/page`);
    assert.ok(contrastRatio(c.textSoft, c.page) >= 4.5, `${theme} text-soft/page`);
    assert.ok(contrastRatio(c.text, c.surface) >= 4.5, `${theme} text/surface`);
    assert.ok(contrastRatio(c.textSoft, c.surface) >= 4.5, `${theme} text-soft/surface`);
  }
});

test('contrast helper matches known WCAG values', () => {
  assert.equal(Math.round(contrastRatio('#000000', '#FFFFFF')), 21);
  assert.equal(contrastRatio('#777777', '#777777'), 1);
});

test('CSS token hex values match the TypeScript source of truth', () => {
  const blocks = {
    night: /:root,\s*:root\[data-unw-theme="night"\]\s*\{([^}]*)\}/.exec(css)?.[1],
    day: /:root\[data-unw-theme="day"\]\s*\{([^}]*)\}/.exec(css)?.[1],
  };
  for (const theme of ['night', 'day']) {
    assert.ok(blocks[theme], `${theme} block exists`);
    for (const [name, hex] of Object.entries(UNW_THEME_COLORS[theme])) {
      assert.match(blocks[theme], new RegExp(`--unw-${kebab(name)}:\\s*${hex};`, 'i'), `${theme} ${name}`);
    }
  }
});

test('theme resolution lives in code: no prefers-color-scheme block sets tokens, font variables exist', () => {
  assert.ok(!/prefers-color-scheme[^{]*\{[^}]*--unw-/.test(css));
  assert.match(css, /--unw-font-read:/);
  assert.match(css, /--unw-font-display:/);
});
