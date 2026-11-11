import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { contrastRatio } from '../src/lib/contrast.ts';
import { UNW_HIGH_CONTRAST_COLORS, UNW_THEME_COLORS, applyReadingAttributes, applyTheme, resolveTheme } from '../src/lib/unw-theme.ts';

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

test('every text-capable token reaches WCAG 4.5:1 on the page and the surface in both themes (body text 7:1)', () => {
  for (const theme of ['night', 'day']) {
    const c = UNW_THEME_COLORS[theme];
    for (const name of ['text', 'textSoft', 'accentLight', 'patinaText', 'dangerText']) {
      assert.ok(contrastRatio(c[name], c.page) >= 4.5, `${theme} ${name}/page`);
      assert.ok(contrastRatio(c[name], c.surface) >= 4.5, `${theme} ${name}/surface`);
      assert.ok(contrastRatio(c[name], c.surfaceSunken) >= 4.5, `${theme} ${name}/surfaceSunken`);
    }
    assert.ok(contrastRatio(c.text, c.page) >= 7, `${theme} body text/page`);
    assert.ok(contrastRatio(c.text, c.surface) >= 7, `${theme} body text/surface`);
  }
});

test('high contrast: every text-capable token reaches 7:1, rules reach 3:1 against the page', () => {
  for (const theme of ['night', 'day']) {
    const c = UNW_HIGH_CONTRAST_COLORS[theme];
    for (const name of ['text', 'textSoft', 'accentLight', 'patinaText', 'dangerText']) {
      assert.ok(contrastRatio(c[name], c.page) >= 7, `${theme} ${name}/page`);
      assert.ok(contrastRatio(c[name], c.surface) >= 7, `${theme} ${name}/surface`);
    }
    assert.ok(contrastRatio(c.border, c.page) >= 3, `${theme} border/page`);
    assert.deepEqual(Object.keys(c), Object.keys(UNW_THEME_COLORS[theme]));
  }
});

test('applyReadingAttributes sets theme, contrast and font attributes in one call', () => {
  const attrs = {};
  const root = { setAttribute: (k, v) => { attrs[k] = v; } };
  assert.equal(applyReadingAttributes(root, { theme: 'day', highContrast: true, dyslexiaFont: true }, true), 'day');
  assert.deepEqual(attrs, { 'data-unw-theme': 'day', 'data-unw-contrast': 'high', 'data-unw-font': 'dyslexia' });
  assert.equal(applyReadingAttributes(root, { theme: 'system', highContrast: false, dyslexiaFont: false }, true), 'night');
  assert.deepEqual(attrs, { 'data-unw-theme': 'night', 'data-unw-contrast': 'normal', 'data-unw-font': 'normal' });
});

test('contrast helper matches known WCAG values', () => {
  assert.equal(Math.round(contrastRatio('#000000', '#FFFFFF')), 21);
  assert.equal(contrastRatio('#777777', '#777777'), 1);
});

test('CSS token hex values match the TypeScript source of truth (themes and high contrast)', () => {
  const blocks = {
    night: [/:root,\s*:root\[data-unw-theme="night"\]\s*\{([^}]*)\}/.exec(css)?.[1], UNW_THEME_COLORS.night],
    day: [/:root\[data-unw-theme="day"\]\s*\{([^}]*)\}/.exec(css)?.[1], UNW_THEME_COLORS.day],
    'night high contrast': [/:root\[data-unw-theme="night"\]\[data-unw-contrast="high"\]\s*\{([^}]*)\}/.exec(css)?.[1], UNW_HIGH_CONTRAST_COLORS.night],
    'day high contrast': [/:root\[data-unw-theme="day"\]\[data-unw-contrast="high"\]\s*\{([^}]*)\}/.exec(css)?.[1], UNW_HIGH_CONTRAST_COLORS.day],
  };
  for (const [name, [block, colours]] of Object.entries(blocks)) {
    assert.ok(block, `${name} block exists`);
    for (const [token, hex] of Object.entries(colours)) {
      assert.match(block, new RegExp(`--unw-${kebab(token)}:\\s*${hex};`, 'i'), `${name} ${token}`);
    }
  }
});

test('no night islands: no rule re-declares the --unw tokens for a surface, so every screen follows the theme and the contrast level', () => {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const redeclared = [...bare.matchAll(/([^{}]*)\{([^{}]*--unw-(?:page|surface|text)\s*:[^{}]*)\}/g)].map((m) => m[1].trim());
  const allowed = [':root,\n:root[data-unw-theme="night"]', ':root[data-unw-theme="day"]', ':root[data-unw-theme="night"][data-unw-contrast="high"]', ':root[data-unw-theme="day"][data-unw-contrast="high"]'];
  assert.deepEqual(redeclared.filter((selector) => !allowed.includes(selector)), []);
});

test('theme resolution lives in code: no prefers-color-scheme block sets tokens, font variables exist', () => {
  assert.ok(!/prefers-color-scheme[^{]*\{[^}]*--unw-/.test(css));
  assert.match(css, /--unw-font-read:/);
  assert.match(css, /--unw-font-display:/);
});

test('reading faces: Spectral for the story, Atkinson Hyperlegible for the dyslexia setting, both from the existing Google Fonts stylesheet', () => {
  assert.match(css, /--unw-font-read: 'Spectral'/);
  assert.match(css, /:root\[data-unw-font="dyslexia"\] \{[^}]*--unw-font-read: 'Atkinson Hyperlegible'/);
  const imports = /@import url\('(https:\/\/fonts\.googleapis\.com\/css2[^']*)'\)/.exec(css)?.[1] ?? '';
  assert.match(imports, /family=Spectral:/);
  assert.match(imports, /family=Atkinson\+Hyperlegible:/);
  assert.doesNotMatch(imports, /IM\+Fell/, 'IM Fell English ships no Turkish glyphs (latin subset only)');
  assert.doesNotMatch(css, /--unw-font-display:[^;]*IM Fell/);
});
