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
  assert.equal(screen.includes('Öneri durumu alındı'), false);
  assert.match(screen, /applyObservedJob/);
});

test('a late status for an older request does not replace the current job', () => {
  const current = job({ requestId: 'B', status: 'running', suggestion: null, revision: 4 });
  const late = job({ requestId: 'A', suggestion: 'A metni', revision: 2 });
  const gate = {
    requestId: 'A',
    draftId: 'draft-1',
    field: 'personality',
    revision: 2,
    epoch: 1,
    currentEpoch: 1,
    currentRevision: 2,
    locked: false,
    discarded: false,
  };
  assert.equal(logic.applyObservedJob(current, late, gate), current);
  const edited = logic.applyObservedJob(job(), job({ suggestion: 'Geç yazı' }), {
    ...gate,
    requestId: 'request-1',
    revision: 2,
    currentRevision: 3,
  });
  assert.equal(edited.suggestion, 'Sakin ve ölçülü.');
  const lockedOut = logic.applyObservedJob(job(), job({ suggestion: 'Kilit geç' }), {
    ...gate,
    requestId: 'request-1',
    locked: true,
  });
  assert.equal(lockedOut.suggestion, 'Sakin ve ölçülü.');
  const discarded = logic.applyObservedJob(job(), job({ suggestion: 'Vazgeç geç' }), {
    ...gate,
    requestId: 'request-1',
    discarded: true,
  });
  assert.equal(discarded.suggestion, 'Sakin ve ölçülü.');
  const stepped = logic.applyObservedJob(job(), job({ suggestion: 'Adım geç' }), {
    ...gate,
    requestId: 'request-1',
    epoch: 1,
    currentEpoch: 2,
  });
  assert.equal(stepped.suggestion, 'Sakin ve ölçülü.');
});

test('status failures stay visible and do not start another request', async () => {
  for (const status of ['failed', 'rejected', 'timed_out']) {
    assert.equal(logic.noticeForJob(status).includes('Öneri durumu alındı'), false);
  }
  assert.match(logic.noticeForJob('failed', 'status_unavailable'), /Kabul edilen metin duruyor/);
  let posts = 0;
  const result = await logic.submitIdentitySuggestion(
    async () => {
      posts += 1;
      return {
        request_id: 'request-hang',
        draft_id: 'draft-1',
        field: 'origin',
        input_revision: 1,
        status: 'running',
        suggestion: null,
        code: null,
      };
    },
    () => new Promise(() => {}),
    {
      draft_id: 'draft-1',
      request_id: 'request-hang',
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
    { timeoutMs: 30, pollMs: 10 },
  );
  assert.equal(posts, 1);
  assert.equal(result.code, 'status_unavailable');
  assert.equal(result.baseText, 'Kuzey');
});

test('an older poll does not roll back ready text and a late get error keeps it', () => {
  const ready = job({ status: 'ready', suggestion: 'Hazır metin' });
  const gate = {
    requestId: 'request-1',
    draftId: 'draft-1',
    field: 'personality',
    revision: 2,
    epoch: 1,
    currentEpoch: 1,
    currentRevision: 2,
    locked: false,
    discarded: false,
  };
  const stale = logic.applyObservedJob(ready, job({ status: 'running', suggestion: null }), gate);
  assert.equal(stale.status, 'ready');
  assert.equal(stale.suggestion, 'Hazır metin');
  const lateError = logic.applyObservedJob(ready, job({
    status: 'failed',
    suggestion: null,
    code: 'status_unavailable',
  }), gate);
  assert.equal(lateError.status, 'ready');
  assert.equal(lateError.suggestion, 'Hazır metin');
});

test('a get connection error keeps the same id available to poll', async () => {
  let posts = 0;
  const body = {
    draft_id: 'draft-1',
    request_id: 'same-id',
    field: 'origin',
    input_revision: 1,
    current_text: 'Kuzey',
    locked: false,
    name: null,
    species: null,
    character_class: null,
    context_fields: [],
  };
  const result = await logic.submitIdentitySuggestion(
    async () => {
      posts += 1;
      return {
        request_id: 'same-id',
        draft_id: 'draft-1',
        field: 'origin',
        input_revision: 1,
        status: 'running',
        suggestion: null,
        code: null,
      };
    },
    async () => {
      throw new Error('connection reset');
    },
    body,
    'Kuzey',
    { timeoutMs: 40, pollMs: 10 },
  );
  assert.equal(posts, 1);
  assert.equal(result.requestId, 'same-id');
  assert.equal(result.status, 'running');
  assert.notEqual(result.status, 'failed');
  assert.equal(result.code, 'status_unavailable');
  assert.equal(result.baseText, 'Kuzey');
  const html = renderSuggestion({
    values,
    revisions,
    locked,
    allowLockedContext: false,
    activeField: 'origin',
    job: { ...result, field: 'origin', revision: 1, baseText: 'Kuzey' },
    open: true,
    notice: logic.noticeForJob(result.status, result.code),
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
  assert.match(html, /Durumu sor/);
  assert.equal(html.includes('Öneri üretilemedi'), false);
});
