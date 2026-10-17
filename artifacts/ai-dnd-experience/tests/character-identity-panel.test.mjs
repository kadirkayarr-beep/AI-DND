import assert from 'node:assert/strict';
import { mkdir, readdir, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { after, before, test } from 'node:test';

const pnpm = path.resolve(process.cwd(), '../../node_modules/.pnpm');
const esbuildDir = (await readdir(pnpm)).find((name) => name.startsWith('esbuild@'));
const esbuild = await import(pathToFileURL(path.join(pnpm, esbuildDir, 'node_modules/esbuild/lib/main.js')).href);

let renderNotes;
let buildDir;

before(async () => {
  buildDir = path.join(process.cwd(), 'node_modules/.cache/character-identity-panel');
  await mkdir(buildDir, { recursive: true });
  const outfile = path.join(buildDir, 'character-identity-notes.mjs');
  await esbuild.build({
    absWorkingDir: process.cwd(),
    entryPoints: ['src/components/character-identity-notes.tsx'],
    outfile,
    bundle: true,
    format: 'esm',
    platform: 'node',
    jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  });
  const component = await import(pathToFileURL(outfile).href);
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  renderNotes = (character) => renderToStaticMarkup(React.createElement(component.CharacterIdentityNotes, { character }));
});

after(async () => {
  if (buildDir) await rm(buildDir, { recursive: true, force: true });
});

function character(identity) {
  return {
    origin: undefined,
    appearance: undefined,
    personality: undefined,
    backstory: undefined,
    ...identity,
  };
}

function notes(html) {
  const start = html.indexOf('data-testid="character-identity-notes"');
  assert.ok(start >= 0);
  return html.slice(start);
}

test('stored identity text is shown in full and is not editable', () => {
  const appearance = `Görünüş ${'ı'.repeat(1000)}`;
  const backstory = `Geçmiş ${'ş'.repeat(2000)}`;
  const value = character({
    origin: '  Kuzey köyü, şığüöçİ  ',
    appearance,
    personality: 'Sakin ve ölçülü',
    backstory,
  });
  const before = JSON.stringify(value);
  const html = renderNotes(value);
  const section = notes(html);
  assert.equal(JSON.stringify(value), before);
  assert.match(section, /Köken/);
  assert.ok(section.includes('  Kuzey köyü, şığüöçİ  '));
  assert.match(section, /Görünüş/);
  assert.ok(section.includes(appearance));
  assert.match(section, /Kişilik/);
  assert.match(section, /Sakin ve ölçülü/);
  assert.match(section, /Geçmiş/);
  assert.ok(section.includes(backstory));
  assert.equal((section.match(/data-state="present"/g) ?? []).length, 4);
  assert.doesNotMatch(section, /<button|<input|<textarea|<select|Belirtilmedi/);
});

test('missing and null fields stay unlabeled fiction and an empty string stays empty', () => {
  const absent = renderNotes(character({}));
  for (const field of ['origin', 'appearance', 'personality', 'backstory']) {
    const at = absent.indexOf(`data-testid="character-identity-${field}"`);
    const block = absent.slice(at, absent.indexOf('</div>', at));
    assert.match(block, /data-state="missing"/);
    assert.match(block, /Kayıtta yok/);
  }
  assert.doesNotMatch(notes(absent), /Kuzey|Sakin|Belirtilmedi/);
  const empty = renderNotes(character({
    origin: null,
    appearance: '',
    personality: null,
    backstory: null,
  }));
  assert.match(empty, /data-testid="character-identity-appearance"[^>]*data-state="empty"/);
  const appearanceAt = empty.indexOf('data-testid="character-identity-appearance"');
  const personalityAt = empty.indexOf('data-testid="character-identity-personality"');
  assert.doesNotMatch(empty.slice(appearanceAt, personalityAt), /Kayıtta yok/);
});

test('identity scroll stays inside the panel and the command box keeps its place', async () => {
  const css = await readFile('src/index.css', 'utf8');
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(css, /\.identity-notes \{[^}]*max-height: 9rem;[^}]*overflow: auto/);
  assert.match(css, /\.identity-note-text \{[^}]*white-space: pre-wrap/);
  assert.match(css, /\.play-shell \.command-box \{ position: static; flex: 0 0 auto;/);
  assert.match(css, /@media \(max-width: 760px\) \{[\s\S]*?\.workspace-left, \.world-column \{ display: none; \}/);
  assert.match(page, /<CharacterIdentityNotes character=\{character\} \/>/);
  assert.match(page, /<CharacterPanel character=\{state\.character\} \/>/);
  assert.match(page, /drawer === 'character' \? <LeftColumn state=\{state\} \/>/);
  assert.doesNotMatch(page, /command-input[\s\S]{0,200}character-identity-notes|character-identity-notes[\s\S]{0,200}command-input/);
});
