// R02: the species stuck-key exit. The REAL settleWithServer body of SpeciesTraitControls (AST-selected from
// src/components/species-trait-controls.tsx, run in a vm) with the transport replaced by the shared backend bodies
// (r02_intent_contract.json). Client wiring only; the backend contract is covered by the Python tests.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';
import { clearPendingTurnAction, createActionLifetime, reconcileState, RETRY_MESSAGE } from '../src/lib/action-reconciliation.ts';
import * as recovery from '../src/lib/action-recovery.ts';
import * as pending from '../src/lib/pending-action.ts';

const contract = JSON.parse(await readFile(new URL('../../../ai-dnd/api/tests/fixtures/r02_intent_contract.json', import.meta.url), 'utf8'));
const source = await readFile(new URL('../src/components/species-trait-controls.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('species-trait-controls.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find((n) => ts.isFunctionDeclaration(n) && n.name?.text === 'SpeciesTraitControls');
const declaration = component.body.statements.find((n) => ts.isVariableStatement(n)
  && n.declarationList.declarations.some((d) => d.name.getText(ast) === 'settleWithServer'));
assert.ok(declaration, 'the real settleWithServer exists');
const code = ts.transpileModule([declaration.getText(ast), 'globalThis.settleWithServer = settleWithServer;'].join('\n'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;

const originalWindow = globalThis.window;
const ACTION = contract.ids.open;

function memoryStorage() {
  const map = new Map();
  return {
    get length() { return map.size; },
    key(index) { return [...map.keys()][index] ?? null; },
    getItem(key) { return map.has(key) ? map.get(key) : null; },
    setItem(key, value) { map.set(String(key), String(value)); },
    removeItem(key) { map.delete(key); },
  };
}

beforeEach(() => {
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173' }, localStorage: memoryStorage(), sessionStorage: memoryStorage(), crypto: globalThis.crypto };
});
afterEach(() => {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

function mount({ answers = {}, stateFails = false } = {}) {
  const scope = 'species:campaign-a';
  const retryKey = `ai-dnd-turn-context:${scope}:retry`;
  window.sessionStorage.setItem(retryKey, JSON.stringify({ action: 'healing_hands', action_id: ACTION }));
  const calls = [];
  const failures = [];
  const retryInputs = [];
  const sending = [];
  const reply = (kind) => ({ ...(answers[kind] ?? {}), action_id: ACTION });
  const state = { revision: 'r' };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const env = {
    busy: { current: false }, lifetime: createActionLifetime(), sessionId: 'session-a', scope, retryKey,
    pendingRequest: { current: { action: 'healing_hands', action_id: ACTION } },
    setSending: (v) => sending.push(v), setFailure: (v) => failures.push(v), setRetryInput: (v) => retryInputs.push(v),
    askServer: recovery.askServer, queryClient: client, reconcileState, RETRY_MESSAGE, clearPendingTurnAction,
    getGetGameSessionStateQueryKey: (id) => ['state', id],
    getGameSessionState: async () => { calls.push('state'); if (stateFails) throw new Error('state read failed'); return state; },
    getGameActionStatus: async (sid, id) => { calls.push(`status ${sid} ${id}`); return reply('status'); },
    abandonGameAction: async (sid, id) => { calls.push(`abandon ${sid} ${id}`); return reply('abandon'); },
    getUnresolvedGameAction: async () => ({ unresolved: null }),
    window: globalThis.window,
  };
  vm.runInNewContext(code, env);
  return { env, calls, failures, retryInputs, sending, retryKey, scope };
}

const keyPresent = (view) => window.sessionStorage.getItem(view.retryKey) !== null;

test('applied: the state is re-read first, then the stale key is cleared', async () => {
  const view = mount({ answers: { status: { state: 'applied', response: null } } });
  await view.env.settleWithServer('check', ACTION);
  assert.deepEqual(view.calls, [`status session-a ${ACTION}`, 'state']);
  assert.equal(keyPresent(view), false);
  assert.deepEqual(view.retryInputs, [null]);
  assert.match(view.failures.at(-1), /uygulandığını doğruladı/);
  assert.equal(view.env.pendingRequest.current, null);
});

test('a failing state read keeps the key: nothing is cleared without a reconciled result', async () => {
  const view = mount({ stateFails: true, answers: { status: { state: 'applied', response: null } } });
  await view.env.settleWithServer('check', ACTION);
  assert.equal(keyPresent(view), true);
  assert.deepEqual(view.retryInputs, []);
  assert.match(view.failures.at(-1), /kimliği korunuyor|Aynı işlemi yeniden dene/);
});

test('abandon clears the key only on the server durable not_applied', async () => {
  const view = mount({ answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await view.env.settleWithServer('abandon', ACTION);
  assert.deepEqual(view.calls, [`abandon session-a ${ACTION}`]);
  assert.equal(keyPresent(view), false);
  assert.match(view.failures.at(-1), /hiç uygulanmadığını/);
});

test('open, unknown, processing and a proof-less not_applied keep the key and the identity', async () => {
  for (const answer of [{ state: 'open' }, { state: 'unknown' }, { state: 'processing' }, { state: 'not_applied' }]) {
    const view = mount({ answers: { status: answer } });
    await view.env.settleWithServer('check', ACTION);
    assert.equal(keyPresent(view), true, `${answer.state} keeps the retry key`);
    assert.deepEqual(view.retryInputs, []);
  }
});

test('an answer about another id never clears this key', async () => {
  const view = mount({ answers: { abandon: { action_id: contract.ids.newer, state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  view.env.getGameActionStatus = async () => ({ action_id: contract.ids.newer, state: 'not_applied', detail: contract.abandon_not_applied.body.detail });
  view.env.abandonGameAction = async () => ({ action_id: contract.ids.newer, state: 'not_applied', detail: contract.abandon_not_applied.body.detail });
  await view.env.settleWithServer('abandon', ACTION);
  assert.equal(keyPresent(view), true);
});

test('a transport error keeps the key and says it is not cancel evidence', async () => {
  const view = mount();
  view.env.getGameActionStatus = async () => { throw new TypeError('Failed to fetch'); };
  await view.env.settleWithServer('check', ACTION);
  assert.equal(keyPresent(view), true);
  assert.match(view.failures.at(-1), /iptal kanıtı değildir/);
});

test('a second click while one runs asks the server once', async () => {
  const view = mount({ answers: { status: { state: 'open' } } });
  await Promise.all([view.env.settleWithServer('check', ACTION), view.env.settleWithServer('check', ACTION)]);
  assert.equal(view.calls.filter((c) => c.startsWith('status')).length, 1);
});

test('pending-action play slot is untouched by a species settle', async () => {
  const play = pending.createIntentKey('user-a', 'campaign-a', { message: 'x', interaction_mode: 'do' });
  const view = mount({ answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await view.env.settleWithServer('abandon', ACTION);
  assert.equal(pending.readPending('user-a', 'campaign-a')?.key.actionId, play.actionId);
});
