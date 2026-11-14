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

// Fonts are served from the repository (src/fonts), not from Google. The faces are listed here exactly as the
// previous Google Fonts stylesheet requested them, Turkish needs both the latin and the latin-ext subset.
const fontsDir = new URL('../src/fonts/', import.meta.url);
const WANTED_FACES = {
  'Cinzel': [['normal', '500'], ['normal', '600'], ['normal', '700']],
  'Cormorant Garamond': [['normal', '400'], ['normal', '500'], ['normal', '600'], ['italic', '400'], ['italic', '500']],
  'Spectral': [['normal', '400'], ['normal', '600'], ['italic', '400']],
  'Atkinson Hyperlegible': [['normal', '400'], ['normal', '700'], ['italic', '400']],
  'DM Sans': [['normal', '400'], ['normal', '500'], ['normal', '600'], ['normal', '700']],
  // A1 (book UI): Literata is one variable file per style (weight 400-700, optical size 7-72); the hand faces are static.
  'Literata': [['normal', '400 700'], ['italic', '400 700']],
  'Kalam': [['normal', '400']],
  'Charm': [['normal', '400'], ['normal', '700']],
  'Bad Script': [['normal', '400']],
};
const WANTED_FILES = {
  'Cinzel': 2, 'Cormorant Garamond': 4, 'Spectral': 6, 'Atkinson Hyperlegible': 6, 'DM Sans': 2,
  'Literata': 4, 'Kalam': 2, 'Charm': 4, 'Bad Script': 2,
};
const readFonts = () => {
  try { return readFileSync(new URL('fonts.css', fontsDir), 'utf8'); } catch { return ''; }
};
const fontFaces = (text) => [...text.matchAll(/\/\*\s*([\w-]+)\s*\*\/\s*@font-face\s*\{([^}]*)\}/g)].map(([, subset, body]) => ({
  subset,
  family: /font-family:\s*'([^']+)'/.exec(body)?.[1],
  style: /font-style:\s*(\w+)/.exec(body)?.[1],
  weight: /font-weight:\s*([\d ]+);/.exec(body)?.[1],
  url: /url\(([^)]+)\)/.exec(body)?.[1]?.replace(/^['"]|['"]$/g, ''),
  range: /unicode-range:\s*([^;]+);/.exec(body)?.[1] ?? '',
}));

test('reading faces: Spectral for the story, Atkinson Hyperlegible for the dyslexia setting, both defined from the repository (TIGHTENED REWRITE, may loosen: the stylesheet check moved from the Google URL to local @font-face rules)', () => {
  assert.match(css, /--unw-font-read: 'Spectral'/);
  assert.match(css, /:root\[data-unw-font="dyslexia"\] \{[^}]*--unw-font-read: 'Atkinson Hyperlegible'/);
  const faces = fontFaces(readFonts());
  for (const family of ['Spectral', 'Atkinson Hyperlegible']) {
    for (const [style, weight] of WANTED_FACES[family]) {
      for (const subset of ['latin', 'latin-ext']) {
        assert.ok(faces.some((f) => f.family === family && f.style === style && f.weight === weight && f.subset === subset),
          `${family} ${style} ${weight} ${subset} is not defined locally`);
      }
    }
  }
  assert.doesNotMatch(readFonts() + css, /IM\+?\s?Fell/, 'IM Fell English ships no Turkish glyphs (latin subset only)');
  assert.doesNotMatch(css, /--unw-font-display:[^;]*IM Fell/);
});

test('fonts come from the repository: no outside font address, nine families with latin and latin-ext, files in place', () => {
  const fontCss = readFonts();
  assert.notEqual(fontCss, '', 'src/fonts/fonts.css is missing');
  assert.match(css, /@import\s+['"]\.\/fonts\/fonts\.css['"]/, 'index.css does not load the local font stylesheet');
  for (const text of [css, fontCss]) {
    assert.doesNotMatch(text, /fonts\.(googleapis|gstatic)\.com/, 'a stylesheet still names Google Fonts');
    assert.doesNotMatch(text, /@import\s+url\(\s*['"]?https?:/, 'a stylesheet imports an outside address');
  }
  const faces = fontFaces(fontCss);
  assert.equal(faces.length, 48, 'the 36 latin and latin-ext rules of the previous Google stylesheet and the 12 of the A1 book faces');
  for (const [family, wanted] of Object.entries(WANTED_FACES)) {
    for (const [style, weight] of wanted) {
      for (const subset of ['latin', 'latin-ext']) {
        assert.equal(faces.filter((f) => f.family === family && f.style === style && f.weight === weight && f.subset === subset).length, 1,
          `${family} ${style} ${weight} ${subset}: expected exactly one local @font-face`);
      }
    }
  }
  assert.ok(faces.every((f) => /U\+0100-02BA/.test(f.range) === (f.subset === 'latin-ext')), 'latin-ext carries U+0100-02BA, latin does not');
  assert.ok(faces.filter((f) => f.subset === 'latin').every((f) => /U\+0000-00FF/.test(f.range)), 'latin carries U+0000-00FF (ö, ü, ç)');
  for (const f of faces) {
    assert.match(f.url ?? '', /^\.\/[^/]+\/[^/:]+\.woff2$/, `${f.family} ${f.subset}: url must be a relative local .woff2`);
    const bytes = readFileSync(new URL(f.url.replace(/^\.\//, ''), fontsDir));
    assert.equal(bytes.subarray(0, 4).toString('latin1'), 'wOF2', `${f.url} is not a woff2 file`);
  }
  const files = new Set(faces.map((f) => f.url));
  assert.equal(files.size, 32, '32 distinct font files');
  for (const [family, count] of Object.entries(WANTED_FILES)) {
    assert.equal(new Set(faces.filter((f) => f.family === family).map((f) => f.url)).size, count, `${family}: file count`);
  }
  for (const folder of ['cinzel', 'cormorant-garamond', 'spectral', 'atkinson-hyperlegible', 'dm-sans', 'literata', 'kalam', 'charm', 'bad-script']) {
    const licence = readFileSync(new URL(`${folder}/OFL.txt`, fontsDir), 'utf8');
    assert.match(licence, /SIL OPEN FONT LICENSE Version 1\.1/, `${folder}/OFL.txt is not the OFL 1.1 text`);
  }
});
