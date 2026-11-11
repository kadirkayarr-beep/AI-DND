import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { after, before, test } from 'node:test';
import {
  INK_MAX_TOTAL_MS,
  INK_STEP_MS,
  freshInkIndex,
  inkStepMs,
  splitInkPieces,
} from '../src/lib/ink-reveal.ts';
import { readPrefersDark, subscribePrefersDark } from '../src/lib/system-theme.ts';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';

const read = (relative) => readFileSync(new URL(relative, import.meta.url), 'utf8');
const readingCss = read('../src/components/unwritten-reading.css');

process.env.PORT ||= '4192';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let React;
let renderToStaticMarkup;
let InkText;
let Transcript;
let AppearanceProvider;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  ({ InkText } = await vite.ssrLoadModule('/src/components/ink-text.tsx'));
  ({ Transcript } = await vite.ssrLoadModule('/src/components/campaign-transcript.tsx'));
  ({ AppearanceProvider } = await vite.ssrLoadModule('/src/components/appearance-provider.tsx'));
  React = await import('react');
  ({ renderToStaticMarkup } = await import('react-dom/server'));
});
after(async () => { await vite?.close(); });

const textOf = (html) => html.replace(/<[^>]*>/g, '');

/* ---------- pure ink helpers ---------- */

test('speeds: instant never animates, a long paragraph stays inside its cap, a short one keeps the step', () => {
  assert.equal(inkStepMs('instant', 50), 0);
  assert.equal(inkStepMs('normal', 0), 0);
  for (const speed of ['slow', 'normal', 'fast']) {
    assert.equal(inkStepMs(speed, 3), INK_STEP_MS[speed]);
    for (const words of [10, 100, 400, 2000]) {
      const total = inkStepMs(speed, words) * words;
      assert.ok(total <= INK_MAX_TOTAL_MS[speed] + 1e-6, `${speed} ${words} words took ${total} ms`);
    }
  }
  assert.ok(INK_STEP_MS.slow > INK_STEP_MS.normal && INK_STEP_MS.normal > INK_STEP_MS.fast && INK_STEP_MS.fast > 0);
});

test('splitInkPieces round-trips any text exactly, Turkish letters and line breaks included', () => {
  for (const text of ['', 'Kapı kilitli.', '  başında  boşluk', 'İlk satır\nİkinci  satır\tüğşıÖç', 'tek']) {
    assert.equal(splitInkPieces(text).map((piece) => piece.text).join(''), text);
  }
  assert.deepEqual(splitInkPieces('a  b').map((p) => p.word), [true, false, true]);
});

test('freshInkIndex: only a short append to a non-empty, unchanged transcript is an arrival', () => {
  const p = (text) => ({ kind: 'player', text });
  const n = (text) => ({ kind: 'narration', text });
  const base = [n('a'), p('b'), n('c')];
  assert.equal(freshInkIndex(base, [...base, p('d'), n('e')]), 4);
  assert.equal(freshInkIndex(base, [...base, n('e')]), 3);
  assert.equal(freshInkIndex([], base), null, 'a first load (history) is not an arrival');
  assert.equal(freshInkIndex(base, base), null, 'same list');
  assert.equal(freshInkIndex(base, [...base, p('d')]), null, 'a player line alone');
  assert.equal(freshInkIndex(base, [...base, p('d'), n('e'), p('f'), n('g')]), null, 'a big jump is a reload');
  assert.equal(freshInkIndex(base, [n('a'), p('B'), n('c'), n('e')]), null, 'a rewritten earlier entry is not a continuation');
  assert.equal(freshInkIndex(base, base.slice(0, 2)), null, 'a shorter list (undo)');
});

/* ---------- InkText markup ---------- */

test('InkText: the text content is exactly the story with and without animation, every word present', () => {
  const story = 'Tavan kirişlerinden toz süzülüyor.\nİçeride ğ, ş, ı, İ, ö, ç, ü kalır.';
  for (const animate of [true, false]) {
    for (const quill of [true, false]) {
      const html = renderToStaticMarkup(React.createElement(InkText, { text: story, speed: 'normal', animate, quill, still: false }));
      assert.equal(textOf(html), story, `animate=${animate} quill=${quill}`);
    }
  }
  const fresh = renderToStaticMarkup(React.createElement(InkText, { text: story, speed: 'normal', animate: true, quill: false, still: false }));
  const wordCount = splitInkPieces(story).filter((piece) => piece.word).length;
  assert.equal((fresh.match(/class="ink-word"/g) ?? []).length, wordCount);
  assert.match(fresh, /class="story-text ink-fresh"/);
  assert.match(fresh, /--ink-step:\d/);
});

test('InkText: instant speed, or no animation requested, renders plain text with no animated word', () => {
  const story = 'Kısa bir cümle.';
  for (const props of [{ speed: 'instant', animate: true }, { speed: 'normal', animate: false }]) {
    const html = renderToStaticMarkup(React.createElement(InkText, { text: story, quill: false, still: false, ...props }));
    assert.equal(html, '<p class="story-text">Kısa bir cümle.</p>');
  }
});

test('the quill tip is an empty aria-hidden span; still when effects are off or motion is reduced', () => {
  const moving = renderToStaticMarkup(React.createElement(InkText, { text: 'Son.', speed: 'normal', animate: false, quill: true, still: false }));
  assert.match(moving, /<span class="ink-tip" data-testid="ink-tip" aria-hidden="true"><\/span>/);
  const still = renderToStaticMarkup(React.createElement(InkText, { text: 'Son.', speed: 'normal', animate: false, quill: true, still: true }));
  assert.match(still, /<span class="ink-tip ink-tip-still" data-testid="ink-tip" aria-hidden="true"><\/span>/);
  assert.equal(textOf(still), 'Son.');
  assert.doesNotMatch(renderToStaticMarkup(React.createElement(InkText, { text: 'Son.', speed: 'normal', animate: false, quill: false, still: false })), /ink-tip/);
});

/* ---------- Transcript: tip on the last narration only, reveal rendering path ---------- */

const entries = [
  { kind: 'narration', text: 'Birinci anlatı.' },
  { kind: 'player', text: 'Kapıyı iterim.', mode: 'do' },
  { kind: 'narration', text: 'İkinci anlatı.' },
];
const renderTranscript = (list, settings) => {
  const store = settings
    ? { localStorage: { getItem: () => JSON.stringify(settings), setItem() {} }, matchMedia: () => ({ matches: false }) }
    : undefined;
  const run = () => renderToStaticMarkup(React.createElement(AppearanceProvider, null, React.createElement(Transcript, {
    entries: list, scrollRef: { current: null }, onScroll() {}, newResponseEntryIndex: null, onJumpToNewResponse() {},
  })));
  if (!store) return run();
  const had = 'window' in globalThis;
  const previous = globalThis.window;
  globalThis.window = store;
  try { return run(); } finally { if (had) globalThis.window = previous; else delete globalThis.window; }
};

test('Transcript: a saved history is never written out, and only the last narration carries the quill tip', () => {
  const html = renderTranscript(entries);
  assert.equal((html.match(/data-testid="ink-tip"/g) ?? []).length, 1);
  assert.doesNotMatch(html, /ink-word|ink-fresh/);
  const lastNarration = html.slice(html.indexOf('transcript-narration-2'));
  assert.match(lastNarration, /İkinci anlatı\.<span class="ink-tip"/);
  assert.doesNotMatch(html.slice(0, html.indexOf('transcript-player-1')), /ink-tip/);
});

test('Transcript: with a player line last, no tip waits at the end', () => {
  assert.doesNotMatch(renderTranscript(entries.slice(0, 2)), /ink-tip/);
});

test('Transcript: effects Kapalı draws the tip still', () => {
  const html = renderTranscript(entries, { effectsLevel: 'off' });
  assert.match(html, /class="ink-tip ink-tip-still"/);
});

/* ---------- wiring (source contracts) ---------- */

test('the provider applies the reading attributes to <html> before paint; the atmosphere layer gets the resolved theme', () => {
  const provider = read('../src/components/appearance-provider.tsx');
  assert.match(provider, /useLayoutEffect\(\(\) => \{\s*applyReadingAttributes\(document\.documentElement, settings, systemPrefersDark\);/);
  assert.match(provider, /\[settings\.theme, settings\.highContrast, settings\.dyslexiaFont, systemPrefersDark\]/);
  const atmosphere = read('../src/components/environment-atmosphere.tsx');
  assert.match(atmosphere, /theme=\{resolvedTheme\}/);
  assert.doesNotMatch(atmosphere, /theme="night"/);
});

test('system theme helpers read and follow prefers-color-scheme: dark and tolerate a missing matchMedia', () => {
  const listeners = new Set();
  const query = { matches: true, addEventListener: (_t, l) => listeners.add(l), removeEventListener: (_t, l) => listeners.delete(l) };
  const seen = [];
  const win = { matchMedia: (q) => { seen.push(q); return query; } };
  assert.equal(readPrefersDark(win), true);
  let calls = 0;
  const off = subscribePrefersDark(win, () => { calls += 1; });
  for (const l of listeners) l();
  assert.equal(calls, 1);
  off();
  assert.equal(listeners.size, 0);
  assert.ok(seen.every((q) => q === '(prefers-color-scheme: dark)'));
  assert.equal(readPrefersDark(null), false);
  assert.equal(readPrefersDark({}), false);
});

test('Transcript and the story column use the one reading-size control that already exists (Aa); fontScale has no second control', () => {
  const source = readGameBrowserSource();
  assert.match(source, /<ReadingSettings value=\{readingPreferences\} onChange=\{setReadingPreferences\} \/>/);
  const panel = read('../src/components/appearance-settings-panel.tsx');
  assert.doesNotMatch(panel, /fontScale|diceSet|hpGauge|spellSlots/);
});

/* ---------- CSS contracts ---------- */

test('unwritten-reading.css sets colours only through the --unw-* tokens (no hex, rgb or hsl literal)', () => {
  const withoutComments = readingCss.replace(/\/\*[\s\S]*?\*\//g, '');
  assert.doesNotMatch(withoutComments, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(withoutComments, /\b(?:rgba?|hsla?)\(\s*\d/);
});

test('ink reveal CSS: words fade in by delay, the tip waits, and reduced motion shows everything with no animation', () => {
  assert.match(readingCss, /\.ink-fresh \.ink-word \{[^}]*animation-delay: calc\(var\(--ink-i\) \* var\(--ink-step\)\)/);
  assert.match(readingCss, /@media \(prefers-reduced-motion: reduce\) \{[^@]*\.ink-fresh \.ink-word \{ opacity: 1; animation: none; \}[^@]*\.ink-tip \{ opacity: 0\.9; animation: none; \}/);
  assert.match(readingCss, /\.ink-tip\.ink-tip-still \{ opacity: 0\.9; animation: none; \}/);
  // The reveal only ever changes opacity and colour: never content, font, size or position of the text.
  const keyframes = /@keyframes ink-dry \{([^@]*?)\n\}/.exec(readingCss)?.[1] ?? '';
  assert.ok(keyframes.length > 0);
  assert.doesNotMatch(keyframes, /content|font|transform|margin|padding|width|height|text-/);
});

test('the story text is never produced or altered by the atmosphere: the layer and table files do not read or write text', () => {
  for (const file of ['../src/lib/scene-atmosphere.ts', '../src/components/scene-atmosphere-layer.tsx', '../src/components/scene-atmosphere-layer.css']) {
    const source = read(file);
    assert.doesNotMatch(source, /story-text|\.text\b|textContent|innerText|innerHTML/, file);
  }
});

test('reading faces and dyslexia setting reach the story text, the player lines and the composer input', () => {
  assert.match(readingCss, /\.story-text,[\s\S]*?\.player-text,[\s\S]*?\.command-input \{\s*font-family: var\(--unw-font-read\);\s*letter-spacing: var\(--unw-read-letter-spacing\);\s*word-spacing: var\(--unw-read-word-spacing\);/);
});
