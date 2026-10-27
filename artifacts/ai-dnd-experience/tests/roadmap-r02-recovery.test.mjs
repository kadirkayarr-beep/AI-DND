// R02 recovery: the way out of an unresolved action is a SERVER-PROVEN verdict, never a guess.
// The bodies below are the real backend bodies (ai-dnd/api/tests/fixtures/r02_intent_contract.json, which a Python test
// compares with the live app); they travel through the REAL generated client and the REAL customFetch/ApiError.
// 404, 503, a network error, a missing receipt or a timeout are errors/"unresolved", never a verdict.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, test } from 'node:test';
import {
  ApiError, customFetch, rotateAuthEpoch, setAuthTokenGetter, setProtectedRequestCredentials,
} from '@workspace/api-client-react/custom-fetch';
import * as pending from '../src/lib/pending-action.ts';
import * as recovery from '../src/lib/action-recovery.ts';

const contract = JSON.parse(await readFile(new URL('../../../ai-dnd/api/tests/fixtures/r02_intent_contract.json', import.meta.url), 'utf8'));
const originalWindow = globalThis.window;
const originalFetch = globalThis.fetch;
const OWNER = 'user-a';
const CAMPAIGN = 'camp-1';

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

// Scripted transport: answers by URL with the shared backend bodies, or fails like a network would.
function installTransport(routes) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url), 'http://127.0.0.1:5173').pathname;
    const method = (init.method ?? 'GET').toUpperCase();
    calls.push(`${method} ${path}`);
    const answer = routes(method, path);
    if (answer instanceof Error) throw answer;
    return new Response(JSON.stringify(answer.body), { status: answer.status, headers: { 'content-type': 'application/json' } });
  };
  return calls;
}

beforeEach(() => {
  globalThis.window = {
    location: { origin: 'http://127.0.0.1:5173' },
    localStorage: memoryStorage(),
    sessionStorage: memoryStorage(),
    crypto: globalThis.crypto,
  };
  setAuthTokenGetter(async () => 'test-token');
  setProtectedRequestCredentials('include');
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  setAuthTokenGetter(null);
  setProtectedRequestCredentials('omit');
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

// The generated client's index cannot be imported by plain node (extensionless re-exports), so the same three calls are made
// with the REAL customFetch; the first test below pins the generated URLs/methods so the two cannot drift apart silently.
const getGameActionStatus = (sessionId, actionId) => customFetch(`/api/game/sessions/${sessionId}/actions/${actionId}`, { method: 'GET' });
const abandonGameAction = (sessionId, actionId) => customFetch(`/api/game/sessions/${sessionId}/actions/${actionId}/abandon`, { method: 'POST' });
const getUnresolvedGameAction = (sessionId) => customFetch(`/api/game/sessions/${sessionId}/actions/unresolved`, { method: 'GET' });
const api = { status: getGameActionStatus, abandon: abandonGameAction, unresolved: getUnresolvedGameAction };
const OPEN = contract.ids.open;

test('the calls above match the generated client calls (same URLs and methods)', async () => {
  const generated = await readFile(new URL('../../../lib/api-client-react/src/generated/api.ts', import.meta.url), 'utf8');
  assert.match(generated, /`\/api\/game\/sessions\/\$\{sessionId\}\/actions\/unresolved`/);
  assert.match(generated, /`\/api\/game\/sessions\/\$\{sessionId\}\/actions\/\$\{actionId\}`/);
  assert.match(generated, /`\/api\/game\/sessions\/\$\{sessionId\}\/actions\/\$\{actionId\}\/abandon`/);
  const abandon = generated.slice(generated.indexOf('export const abandonGameAction'));
  assert.match(abandon.slice(0, 400), /method: ['"]POST['"]/);
});

test('the real bodies become verdicts, and only a durable not_applied can ever close anything', async () => {
  installTransport((method, path) => {
    if (method === 'POST' && path.endsWith('/abandon')) return contract.abandon_not_applied;
    if (path.endsWith(`/actions/${contract.ids.never_seen}`)) return contract.status_unknown;
    return contract.status_open;
  });
  assert.deepEqual(await recovery.askServer(api, 'check', 's1', OPEN), { kind: 'unresolved', state: 'open', processing: false });
  assert.deepEqual(await recovery.askServer(api, 'check', 's1', contract.ids.never_seen), { kind: 'unresolved', state: 'unknown', processing: false },
    'a never-seen id is not evidence that it never happened');
  assert.deepEqual(await recovery.askServer(api, 'abandon', 's1', OPEN), { kind: 'not_applied', code: 'action_abandoned' });
});

test('errors and malformed answers are never a verdict', async () => {
  for (const [label, answer] of [
    ['404', { status: 404, body: { detail: { code: 'unknown_session', message: 'x' } } }],
    ['503', { status: 503, body: { detail: { code: 'ollama_unavailable', message: 'x' } } }],
    ['network', new TypeError('Failed to fetch')],
  ]) {
    installTransport(() => answer);
    await assert.rejects(() => recovery.askServer(api, 'check', 's1', OPEN), undefined, `${label} must reject, not decide`);
    await assert.rejects(() => recovery.askServer(api, 'abandon', 's1', OPEN), undefined, `${label} must reject, not decide`);
  }
  for (const body of [
    { action_id: OPEN, state: 'not_applied' },
    { action_id: OPEN, state: 'not_applied', detail: { code: 'x' } },
    { action_id: OPEN, state: 'not_applied', detail: { not_applied: true } },
    { action_id: OPEN, state: 'applied-ish' },
    { state: 'not_applied', detail: { code: 'x', not_applied: true } },
  ]) {
    assert.equal(recovery.readVerdict(body, OPEN).kind, 'unresolved', `${JSON.stringify(body)} proves nothing`);
  }
  assert.equal(recovery.readVerdict({ action_id: contract.ids.newer, state: 'not_applied', detail: { code: 'x', not_applied: true } }, OPEN).kind, 'unresolved',
    'an answer about another id never closes this one');
  assert.deepEqual(recovery.readVerdict({ action_id: OPEN, state: 'processing' }, OPEN), { kind: 'unresolved', state: 'processing', processing: true });
  assert.equal(recovery.readVerdict({ action_id: OPEN, state: 'applied', response: null }, OPEN).kind, 'applied');
});

test('applied is reconciled from the server BEFORE the pending record closes; a failed reconcile keeps it', async () => {
  const key = pending.createIntentKey(OWNER, CAMPAIGN, { message: 'x', interaction_mode: 'do' });
  const order = [];
  const closed = await recovery.settlePending(key, { kind: 'applied', response: { narration: 'n' } }, async () => {
    order.push('reconcile');
    assert.ok(pending.readPending(OWNER, CAMPAIGN), 'still pending while the state is being reconciled');
  });
  order.push('closed');
  assert.equal(closed, 'confirmed');
  assert.deepEqual(order, ['reconcile', 'closed']);
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null);

  const again = pending.createIntentKey(OWNER, CAMPAIGN, { message: 'y', interaction_mode: 'do' });
  await assert.rejects(() => recovery.settlePending(again, { kind: 'applied', response: null }, async () => { throw new Error('state read failed'); }), /state read failed/);
  assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, again.actionId, 'unreconciled results keep the identity');
});

test('not_applied closes with the server evidence; open, unknown and processing keep the identity', async () => {
  const key = pending.createIntentKey(OWNER, CAMPAIGN, { message: 'x', interaction_mode: 'do' });
  for (const state of ['open', 'unknown', 'processing']) {
    assert.equal(await recovery.settlePending(key, { kind: 'unresolved', state }, async () => assert.fail('no reconcile')), 'kept');
    assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, key.actionId);
  }
  assert.equal(await recovery.settlePending(key, { kind: 'not_applied', code: 'action_abandoned' }, async () => assert.fail('no reconcile')), 'cancelled');
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null);
  const next = pending.createIntentKey(OWNER, CAMPAIGN, { message: 'z', interaction_mode: 'do' });
  assert.notEqual(next.actionId, key.actionId, 'only an explicit new send creates a new id; settling never does');
});

test('a damaged stored request no longer locks the campaign: the server decides, not the local copy', async () => {
  const key = pending.createIntentKey(OWNER, CAMPAIGN, {}); // the lost/damaged body of an unresolved move
  // The server answers about the id it was asked about (the fixture's shape, this key's id).
  const calls = installTransport(() => ({
    status: contract.abandon_not_applied.status,
    body: { ...contract.abandon_not_applied.body, action_id: key.actionId },
  }));
  const verdict = await recovery.askServer(api, 'abandon', 's1', key.actionId);
  assert.equal(await recovery.settlePending(key, verdict, async () => {}), 'cancelled');
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null);
  assert.deepEqual(calls, [`POST /api/game/sessions/s1/actions/${key.actionId}/abandon`], 'nothing was resent automatically');
});

test('second tab or re-login: the server names the open action; nothing is invented locally', async () => {
  // Fresh browser state (sign-out cleared it, or this is another tab): no local pending record at all.
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null);
  const calls = installTransport(() => contract.unresolved_list);
  const found = await recovery.findUnresolvedOnServer(api, 's1');
  assert.deepEqual(found, { actionId: OPEN, state: 'open' });
  assert.deepEqual(calls, ['GET /api/game/sessions/s1/actions/unresolved']);
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null, 'the browser record is not the authority and is not fabricated');
  installTransport(() => ({ status: 200, body: { unresolved: null } }));
  assert.equal(await recovery.findUnresolvedOnServer(api, 's1'), null);
  installTransport(() => new TypeError('Failed to fetch'));
  await assert.rejects(() => recovery.findUnresolvedOnServer(api, 's1'), undefined, 'a failed lookup is an error, not "nothing is open"');
});

test('the real unresolved_action refusal is the never-applied proof for the NEW id and names the open one', async () => {
  installTransport(() => contract.unresolved_action_refusal);
  const error = await getGameActionStatus('s1', contract.ids.newer).then(() => null, (e) => e);
  assert.ok(error instanceof ApiError);
  assert.equal(error.status, 409);
  assert.deepEqual(recovery.unresolvedActionFrom(error), { actionId: OPEN, code: 'unresolved_action' });
  const other = await (async () => {
    installTransport(() => ({ status: 409, body: { detail: { code: 'stale_combat', message: 'x', not_applied: true } } }));
    return getGameActionStatus('s1', contract.ids.newer).then(() => null, (e) => e);
  })();
  assert.equal(recovery.unresolvedActionFrom(other), null, 'only unresolved_action names an open action');
});

test('a new auth epoch or a signed-out clean slate never turns an unresolved action into a closed one', () => {
  const key = pending.createIntentKey(OWNER, CAMPAIGN, { message: 'x', interaction_mode: 'do' });
  rotateAuthEpoch();
  assert.equal(pending.resumePending(key, 1).key.actionId, key.actionId);
  assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, key.actionId, 'the stored record is still the source of truth');
});
