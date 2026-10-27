// R02 recovery wiring in the REAL GameBrowser source: serverRecovery, recoveryHandlers and showServerOpenAction are selected
// from src/pages/game-browser.tsx by AST and run in a vm; only hooks, view setters and the transport are replaced. The
// transport answers with the shared backend bodies (ai-dnd/api/tests/fixtures/r02_intent_contract.json). This proves the
// client wiring, NOT backend behaviour (that is covered by the Python tests against the real app).
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';
import { createActionLifetime, reconcileState, RETRY_MESSAGE, ReconciliationError } from '../src/lib/action-reconciliation.ts';
import * as pending from '../src/lib/pending-action.ts';
import * as recovery from '../src/lib/action-recovery.ts';

const contract = JSON.parse(await readFile(new URL('../../../ai-dnd/api/tests/fixtures/r02_intent_contract.json', import.meta.url), 'utf8'));
const source = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find((n) => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
const pick = (name) => {
  const found = component.body.statements.find((n) => ts.isVariableStatement(n)
    && n.declarationList.declarations.some((d) => d.name.getText(ast) === name));
  assert.ok(found, `the real ${name} exists in GameBrowser`);
  return found.getText(ast);
};
const code = ts.transpileModule([
  pick('recoveryHandlers'), pick('serverRecovery'), pick('showServerOpenAction'),
  'serverRecoveryRef.current = serverRecovery;',
  'globalThis.recoveryHandlers = recoveryHandlers; globalThis.serverRecovery = serverRecovery; globalThis.showServerOpenAction = showServerOpenAction;',
].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;

const originalWindow = globalThis.window;
const OWNER = 'user-a';
const OPEN = contract.ids.open;

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

// One GameBrowser "render" for a session; instances share the recovery ref the way real renders share the ref object.
function render({ sessionId = 'session-a', campaignId = 'campaign-a', sharedRef, answers = {}, campaignFails = false, composer = '' } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const calls = [];
  const notices = [];
  const entries = [];
  const messages = [];
  const state = { revision: 'r', turn_index: 1, combat: { active: false }, quests: [], scene: null };
  const reply = (kind, actionId) => {
    const base = { ...(answers[kind] ?? {}) };
    return { ...base, action_id: base.action_id ?? actionId };
  };
  const api = {
    status: async (sid, actionId) => { calls.push(`status ${sid} ${actionId}`); return reply('status', actionId); },
    abandon: async (sid, actionId) => { calls.push(`abandon ${sid} ${actionId}`); return reply('abandon', actionId); },
    unresolved: async (sid) => {
      calls.push(`unresolved ${sid}`);
      if (answers.unresolvedError) throw new TypeError('Failed to fetch');
      return answers.unresolved ?? { unresolved: null };
    },
  };
  const env = {
    sessionId, campaignId, serverRecoveryRef: sharedRef ?? { current: null },
    RECOVERY_API: api, askServer: recovery.askServer, settlePending: recovery.settlePending, findUnresolvedOnServer: recovery.findUnresolvedOnServer,
    readPending: pending.readPending, currentAccountOwner: () => OWNER, LOCAL_OWNER: 'local',
    inFlightSessionsRef: { current: new Set() }, setInFlightSessions() {}, turnLifetime: createActionLifetime(),
    getGetGameSessionStateQueryKey: (id) => ['state', id], reconcileState, ReconciliationError, RETRY_MESSAGE,
    getCampaign: async (id) => {
      calls.push(`getCampaign ${id}`);
      if (campaignFails) throw new Error('campaign read failed');
      return { state, history: [{ player_message: 'x', narration: 'y' }], combat_history: [] };
    },
    getGameSessionState: async () => state, queryClient: client, setEntries: (v) => entries.push(v),
    writeAdvisoryCache() {}, TRANSCRIPT_KEY: 't-', setCombatEntries() {}, mergeCombatHistory: (v) => v,
    getGetCampaignsQueryKey: () => ['campaigns'], setNotice: (v) => { notices.push(typeof v === 'function' ? v(notices.at(-1) ?? null) : v); },
    retryPendingTurn() {}, friendlyError: (e) => e?.message ?? 'error', messageRef: { current: composer }, setMessage: (v) => messages.push(v),
    window: globalThis.window,
  };
  vm.runInNewContext(code, env);
  return { env, calls, notices, entries, messages, api };
}

const settleAsync = () => new Promise((resolve) => setImmediate(resolve));

test('applied: authoritative state is reconciled BEFORE the pending move closes, and the story is rebuilt', async () => {
  const key = pending.createIntentKey(OWNER, 'campaign-a', { message: 'open the door', interaction_mode: 'do' });
  const view = render({ answers: { status: { state: 'applied', response: null } } });
  const seenWhileReconciling = [];
  const realGetCampaign = view.env.getCampaign;
  view.env.getCampaign = async (...args) => { seenWhileReconciling.push(Boolean(pending.readPending(OWNER, 'campaign-a'))); return realGetCampaign(...args); };
  await view.env.serverRecovery('check');
  assert.deepEqual(seenWhileReconciling, [true], 'still pending while the state is read');
  assert.equal(pending.readPending(OWNER, 'campaign-a'), null, 'closed only after the reconcile');
  assert.equal(view.entries.length, 1, 'the story is rebuilt from the server history');
  assert.equal(view.notices.at(-1).tone, 'success');
  assert.deepEqual(view.calls.filter((c) => c.startsWith('status') || c.startsWith('abandon')), [`status session-a ${key.actionId}`]);
});

test('a failing reconcile keeps the pending move and offers retry plus the server check again', async () => {
  const key = pending.createIntentKey(OWNER, 'campaign-a', { message: 'open the door', interaction_mode: 'do' });
  const view = render({ campaignFails: true, answers: { status: { state: 'applied', response: null } } });
  await view.env.serverRecovery('check');
  assert.equal(pending.readPending(OWNER, 'campaign-a')?.key.actionId, key.actionId, 'identity kept');
  const notice = view.notices.at(-1);
  assert.equal(notice.tone, 'error');
  assert.ok(notice.retry && notice.recover, 'the player can retry or ask again');
});

test('abandon closes only on the server durable not_applied, restores the draft once and never resends', async () => {
  const key = pending.createIntentKey(OWNER, 'campaign-a', { message: 'open the door', interaction_mode: 'do' });
  const view = render({ answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await view.env.serverRecovery('abandon');
  assert.equal(pending.readPending(OWNER, 'campaign-a'), null);
  assert.deepEqual(view.messages, ['open the door'], 'the draft returns to the empty composer');
  assert.deepEqual(view.calls, [`abandon session-a ${key.actionId}`], 'nothing but the abandon call, no resend and no new id');
  pending.createIntentKey(OWNER, 'campaign-a', { message: 'again', interaction_mode: 'do' });
  const typed = render({ composer: 'something newer', answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await typed.env.serverRecovery('abandon');
  assert.deepEqual(typed.messages, [], 'a draft the player typed meanwhile is never overwritten');
});

test('open, unknown, processing and a detail-less not_applied keep the identity; nothing closes', async () => {
  const key = pending.createIntentKey(OWNER, 'campaign-a', { message: 'x', interaction_mode: 'do' });
  for (const answer of [{ state: 'open' }, { state: 'unknown' }, { state: 'processing' }, { state: 'not_applied' }]) {
    const view = render({ answers: { status: answer } });
    await view.env.serverRecovery('check');
    assert.equal(pending.readPending(OWNER, 'campaign-a')?.key.actionId, key.actionId, `${answer.state} keeps the pending move`);
    assert.ok(view.notices.at(-1).recover, 'the way out stays offered');
  }
});

test('an answer about ANOTHER id never closes this campaign pending move', async () => {
  const key = pending.createIntentKey(OWNER, 'campaign-a', { message: 'x', interaction_mode: 'do' });
  const view = render({ answers: { abandon: { action_id: contract.ids.newer, state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await view.env.serverRecovery('abandon');
  assert.equal(pending.readPending(OWNER, 'campaign-a')?.key.actionId, key.actionId);
});

test('the open action named by the server is settled by ITS id; an unrelated local record is untouched', async () => {
  const local = pending.createIntentKey(OWNER, 'campaign-a', { message: 'local', interaction_mode: 'do' });
  const view = render({ answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  await view.env.serverRecovery('abandon', OPEN);
  assert.deepEqual(view.calls, [`abandon session-a ${OPEN}`]);
  assert.equal(pending.readPending(OWNER, 'campaign-a')?.key.actionId, local.actionId, 'a different local id is not closed by the server id verdict');
});

test('a notice created for one session cannot ask or close anything after a switch to another session', async () => {
  const sharedRef = { current: null };
  const first = render({ sessionId: 'session-a', campaignId: 'campaign-a', sharedRef });
  const handlers = first.env.recoveryHandlers(OPEN); // the notice of campaign A
  const other = render({ sessionId: 'session-b', campaignId: 'campaign-b', sharedRef, answers: { abandon: { state: 'not_applied', detail: contract.abandon_not_applied.body.detail } } });
  other.notices.push({ tone: 'warning', title: 'old', detail: 'old', recover: handlers });
  handlers.abandon();
  await settleAsync();
  assert.deepEqual(other.calls, [], 'no request is made for another campaign id');
  assert.equal(other.notices.at(-1), null, 'the stale recovery notice is removed');
  handlers.check();
  await settleAsync();
  assert.deepEqual(other.calls, []);
});

test('the open-action lookup: second tab or re-login shows the server action; failures and stale lookups show nothing', async () => {
  const found = render({ answers: { unresolved: contract.unresolved_list.body } });
  await found.env.showServerOpenAction('session-a', 'campaign-a', () => true);
  assert.deepEqual(found.calls, ['unresolved session-a']);
  assert.ok(found.notices.at(-1).recover, 'check / abandon are offered');
  assert.equal(found.notices.at(-1).retry, undefined, 'there is no request body to resend');
  assert.equal(pending.readPending(OWNER, 'campaign-a'), null, 'no browser record is fabricated');

  const failed = render({ answers: { unresolvedError: true } });
  await failed.env.showServerOpenAction('session-a', 'campaign-a', () => true);
  assert.equal(failed.notices.length, 0, 'a failed lookup is neither "nothing is open" nor an error banner');

  const stale = render({ answers: { unresolved: contract.unresolved_list.body } });
  await stale.env.showServerOpenAction('session-a', 'campaign-a', () => false);
  assert.equal(stale.notices.length, 0, 'a lookup that finishes after a session switch shows nothing');

  pending.createIntentKey(OWNER, 'campaign-a', { message: 'x', interaction_mode: 'do' });
  const withLocal = render({ answers: { unresolved: contract.unresolved_list.body } });
  await withLocal.env.showServerOpenAction('session-a', 'campaign-a', () => true);
  assert.equal(withLocal.notices.length, 0, 'an existing local pending notice is not replaced by the server lookup');
});

test('a second recovery while one runs does nothing', async () => {
  pending.createIntentKey(OWNER, 'campaign-a', { message: 'x', interaction_mode: 'do' });
  const view = render({ answers: { status: { state: 'open' } } });
  await Promise.all([view.env.serverRecovery('check'), view.env.serverRecovery('check')]);
  assert.equal(view.calls.filter((c) => c.startsWith('status')).length, 1, 'double click asks the server once');
});
