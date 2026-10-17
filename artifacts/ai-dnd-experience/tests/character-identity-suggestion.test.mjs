import assert from 'node:assert/strict';
import { mkdir, readFile, readdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { after, before, test } from 'node:test';

const pnpm = path.resolve(process.cwd(), '../../node_modules/.pnpm');
const esbuildDir = (await readdir(pnpm)).find((name) => name.startsWith('esbuild@'));
const esbuild = await import(pathToFileURL(path.join(pnpm, esbuildDir, 'node_modules/esbuild/lib/main.js')).href);

let logic;
let renderSuggestion;
let buildDir;

const values = { origin: 'Kuzey', appearance: '', personality: 'Sakin', backstory: '' };
const revisions = { origin: 1, appearance: 0, personality: 2, backstory: 0 };
const locked = { origin: false, appearance: true, personality: false, backstory: false };

function job(overrides = {}) {
  return {
    requestId: 'request-1',
    draftId: 'draft-1',
    field: 'personality',
    revision: 2,
    baseText: 'Sakin',
    status: 'ready',
    suggestion: 'Sakin ve ölçülü.',
    code: null,
    ...overrides,
  };
}

before(async () => {
  buildDir = path.join(process.cwd(), 'node_modules/.cache/character-identity-suggestion');
  await mkdir(buildDir, { recursive: true });
  const logicFile = path.join(buildDir, 'logic.mjs');
  const viewFile = path.join(buildDir, 'view.mjs');
  await esbuild.build({
    absWorkingDir: process.cwd(),
    entryPoints: ['src/lib/character-identity-suggestion.ts'],
    outfile: logicFile,
    bundle: true,
    format: 'esm',
    platform: 'node',
  });
  await esbuild.build({
    absWorkingDir: process.cwd(),
    entryPoints: ['src/components/character-identity-suggestion.tsx'],
    outfile: viewFile,
    bundle: true,
    format: 'esm',
    platform: 'node',
    jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  });
  logic = await import(pathToFileURL(logicFile).href);
  const view = await import(pathToFileURL(viewFile).href);
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  renderSuggestion = (props) => renderToStaticMarkup(React.createElement(view.CharacterIdentitySuggestion, props));
});

after(async () => {
  if (buildDir) await rm(buildDir, { recursive: true, force: true });
});

test('accept writes only the suggested field and a stale edit cannot overwrite it', () => {
  const applied = logic.applySuggestion(values, job(), revisions, locked);
  assert.equal(applied.applied, true);
  assert.equal(applied.values.personality, 'Sakin ve ölçülü.');
  assert.equal(applied.values.origin, 'Kuzey');
  const edited = logic.applySuggestion(
    { ...values, personality: 'Elle yazıldı' },
    job(),
    { ...revisions, personality: 3 },
    locked,
  );
  assert.equal(edited.applied, false);
  assert.equal(edited.values.personality, 'Elle yazıldı');
});

test('a locked field is not a change target and becomes context only by permission', () => {
  const blocked = logic.applySuggestion(values, job({ field: 'appearance', baseText: '', revision: 0 }), revisions, locked);
  assert.equal(blocked.applied, false);
  const request = logic.buildSuggestionRequest({
    draftId: 'draft-1',
    requestId: 'request-2',
    field: 'personality',
    revision: 2,
    values: { ...values, appearance: 'Sol yanak izi' },
    locked,
    allowLockedContext: true,
    name: 'Riven',
  });
  assert.equal(request.locked, false);
  assert.deepEqual(request.context_fields, [{
    field: 'appearance',
    text: 'Sol yanak izi',
    locked: true,
    allow_as_context: true,
  }]);
  assert.equal(JSON.stringify(request).includes('current_hp'), false);
  const hidden = logic.buildSuggestionRequest({
    draftId: 'draft-1',
    requestId: 'request-3',
    field: 'personality',
    revision: 2,
    values,
    locked,
    allowLockedContext: false,
  });
  assert.deepEqual(hidden.context_fields, []);
});

test('timeout asks for status and does not post a second time', async () => {
  let posts = 0;
  let gets = 0;
  const result = await logic.submitIdentitySuggestion(
    () => {
      posts += 1;
      return new Promise(() => {});
    },
    async (requestId) => {
      gets += 1;
      return {
        request_id: requestId,
        draft_id: 'draft-1',
        field: 'origin',
        input_revision: 1,
        status: 'running',
        suggestion: null,
        code: null,
      };
    },
    {
      draft_id: 'draft-1',
      request_id: 'request-timeout',
      field: 'origin',
      input_revision: 1,
      current_text: 'Kuzey',
      locked: false,
      name: null,
      species: null,
      character_class: null,
      context_fields: [],
    },
    'Kuzey',
    { timeoutMs: 20 },
  );
  assert.equal(posts, 1);
  assert.equal(gets, 1);
  assert.equal(result.status, 'running');
  assert.equal(logic.dismissNotice().includes('durdur'), false);
});

test('suggestion controls keep a 44px target and stack at 390px', async () => {
  const html = renderSuggestion({
    values,
    revisions,
    locked,
    allowLockedContext: false,
    activeField: 'personality',
    job: job(),
    open: true,
    notice: 'Öneri hazır.',
    busy: false,
    onActivate: () => {},
    onToggleLock: () => {},
    onAllowLockedContext: () => {},
    onAsk: () => {},
    onAccept: () => {},
    onDiscard: () => {},
    onDismiss: () => {},
    onPoll: () => {},
  });
  assert.match(html, /data-testid="identity-suggestion-accept"/);
  assert.match(html, /data-testid="identity-suggestion-discard"/);
  assert.match(html, /Şimdiki metin/);
  assert.match(html, /Sakin ve ölçülü\./);
  assert.match(html, /role="status"/);
  assert.match(html, /tabindex="-1"/);
  const pending = renderSuggestion({
    values,
    revisions,
    locked: { ...locked, personality: true },
    allowLockedContext: false,
    activeField: 'personality',
    job: job({ status: 'running', suggestion: null }),
    open: true,
    notice: 'Öneri durumu alındı.',
    busy: true,
    onActivate: () => {},
    onToggleLock: () => {},
    onAllowLockedContext: () => {},
    onAsk: () => {},
    onAccept: () => {},
    onDiscard: () => {},
    onDismiss: () => {},
    onPoll: () => {},
  });
  assert.equal(pending.includes('identity-suggestion-accept'), false);
  assert.match(pending, /Durumu sor/);
  const css = await readFile(new URL('../src/components/character-creation-screen.css', import.meta.url), 'utf8');
  const screen = await readFile(new URL('../src/components/character-creation-screen.tsx', import.meta.url), 'utf8');
  assert.match(css, /\.identity-suggestion-action \{[^}]*min-height: 44px;/);
  assert.match(css, /@media \(max-width: 390px\) \{[\s\S]*\.identity-suggestion-compare \{ grid-template-columns: 1fr; \}/);
  assert.match(screen, /<CharacterIdentitySuggestion/);
  assert.equal(screen.includes('localStorage'), false);
  assert.match(screen, /customFetch\('\/api\/game\/character-identity-suggestions'/);
});
