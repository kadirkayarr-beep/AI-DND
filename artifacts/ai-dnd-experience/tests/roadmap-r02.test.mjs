import { primalKnowledgeInjection } from './support/primal-knowledge-env.mjs';
// R02: a technical retry (same action id) is separate from a deliberate new action with identical text.
// The server here is a test double of the receipt rule (owner + campaign + id); the real backend's
// ownership and replay rules stay covered by the Python campaign/turn tests.
import { gateInjection } from './support/state-gate-env.mjs';
import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { currentAuthEpoch, rotateAuthEpoch } from '@workspace/api-client-react/custom-fetch';
import * as account from '../src/lib/account-session.ts';
import * as pending from '../src/lib/pending-action.ts';
import * as recovery from '../src/lib/action-recovery.ts';

const originalWindow = globalThis.window;
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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

// Receipts are looked up by the full owner+campaign+id; text is never part of the lookup.
function fakeServer() {
  const receipts = new Map();
  const effects = new Map();
  return {
    effects,
    send(key, text) {
      const slot = `${key.ownerId}|${key.campaignId}|${key.actionId}`;
      const known = [...receipts.keys()].find((existing) => existing.endsWith(`|${key.actionId}`));
      if (known && known !== slot) return { status: 403, replay: false };
      if (receipts.has(slot)) return { status: 200, replay: true, receipt: receipts.get(slot) };
      const receipt = { actionId: key.actionId, text };
      receipts.set(slot, receipt);
      effects.set(key.actionId, (effects.get(key.actionId) ?? 0) + 1);
      return { status: 200, replay: false, receipt };
    },
  };
}

beforeEach(() => {
  globalThis.window = {
    location: { origin: 'http://127.0.0.1:5173' },
    localStorage: memoryStorage(),
    sessionStorage: memoryStorage(),
    crypto: globalThis.crypto,
  };
});

afterEach(() => {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

test('test_retry_and_new_identical_text_have_distinct_semantics', () => {
  const server = fakeServer();
  const original = pending.createIntentKey('user-a', 'camp-1');
  assert.match(original.actionId, UUID_V4);
  assert.deepEqual(Object.keys(original).sort(), ['actionId', 'campaignId', 'ownerId']);
  server.send(original, 'walk to the gate'); // commit happened, the response was lost

  const retry = pending.resumePending(original, currentAuthEpoch()).key;
  const replayed = server.send(retry, 'walk to the gate');
  assert.equal(replayed.replay, true);
  assert.equal(retry.actionId, original.actionId);

  pending.closePending(original, 'confirmed');
  const deliberateRepeat = pending.createIntentKey('user-a', 'camp-1');
  server.send(deliberateRepeat, 'walk to the gate');
  assert.notEqual(deliberateRepeat.actionId, original.actionId);
  assert.equal(server.effects.get(original.actionId), 1);
  assert.equal(server.effects.get(deliberateRepeat.actionId), 1);
});

test('a new auth epoch does not invalidate a legitimate pending receipt', () => {
  const server = fakeServer();
  const original = pending.createIntentKey('user-a', 'camp-1');
  server.send(original, 'open the door');
  rotateAuthEpoch();
  const resumed = pending.resumePending(original, currentAuthEpoch());
  assert.equal(resumed.key.actionId, original.actionId);
  assert.equal(resumed.epoch, currentAuthEpoch());
  assert.equal(server.send(resumed.key, 'open the door').replay, true);
  assert.equal(server.effects.get(original.actionId), 1);
});

test('another owner or campaign can neither resume nor replay the pending action', () => {
  const server = fakeServer();
  const original = pending.createIntentKey('user-a', 'camp-1');
  server.send(original, 'steal the key');
  const wrongOwner = { ...original, ownerId: 'user-b' };
  const wrongCampaign = { ...original, campaignId: 'camp-2' };
  for (const key of [wrongOwner, wrongCampaign]) {
    assert.throws(() => pending.resumePending(key, currentAuthEpoch()));
    assert.equal(server.send(key, 'steal the key').replay, false);
  }
  assert.equal(server.effects.get(original.actionId), 1);
});

test('an unresolved pending action is never replaced by an automatic new id', () => {
  const first = pending.createIntentKey('user-a', 'camp-1');
  assert.throws(() => pending.createIntentKey('user-a', 'camp-1'), /pending/i);
  // Another campaign or owner is independent.
  assert.notEqual(pending.createIntentKey('user-a', 'camp-2').actionId, first.actionId);
  assert.notEqual(pending.createIntentKey('user-b', 'camp-1').actionId, first.actionId);
  assert.equal(pending.resumePending(first, currentAuthEpoch()).key.actionId, first.actionId);
});

test('pending closes only on a confirmed result or a proven server rejection', () => {
  const key = pending.createIntentKey('user-a', 'camp-1');
  assert.throws(() => pending.closePending(key, 'timeout'));
  assert.throws(() => pending.closePending(key, undefined));
  // A bare cancel (closed screen, timeout, lost connection) proves nothing about the server.
  assert.throws(() => pending.closePending(key, 'cancelled'));
  assert.throws(() => pending.closePending(key, 'cancelled', { kind: 'server_rejected', status: 503 }));
  assert.equal(pending.resumePending(key, currentAuthEpoch()).key.actionId, key.actionId);
  assert.throws(() => pending.closePending(key, 'cancelled', { kind: 'server_rejected', status: 400 }), 'a bare 400 proves nothing');
  assert.throws(() => pending.closePending(key, 'cancelled', { kind: 'server_not_applied', code: '' }));
  pending.closePending(key, 'cancelled', { kind: 'server_not_applied', code: 'stale_combat' });
  assert.throws(() => pending.resumePending(key, currentAuthEpoch()));
  assert.notEqual(pending.createIntentKey('user-a', 'camp-1').actionId, key.actionId);
});

test('pending survives a reload for the same owner and is gone for another owner', () => {
  account.nextAccountClient(null, 'user-a:sess-1');
  const key = pending.createIntentKey('user-a', 'camp-1');
  account.nextAccountClient(null, 'user-a:sess-2'); // reload or token refresh, same owner
  assert.equal(pending.resumePending(key, currentAuthEpoch()).key.actionId, key.actionId);
  account.nextAccountClient(null, 'user-b:sess-9'); // someone else opens the tab
  assert.throws(() => pending.resumePending(key, currentAuthEpoch()));
});

test('replay authority never comes from the text', () => {
  const server = fakeServer();
  const first = pending.createIntentKey('user-a', 'camp-1');
  server.send(first, 'same words');
  pending.closePending(first, 'confirmed');
  const second = pending.createIntentKey('user-a', 'camp-1');
  const result = server.send(second, 'same words');
  assert.equal(result.replay, false);
  assert.equal(server.effects.size, 2);
});

// ---------------------------------------------------------------------------------------------
// Real GameBrowser.submitTurn body (AST-selected from the production file, run in a vm); only hooks,
// transport and view setters are replaced. The "server" below is a test double of the receipt rule,
// NOT backend evidence: owner/campaign/id lookup, one spend and one time advance per unique id.
// ---------------------------------------------------------------------------------------------
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';
import { createActionLifetime, reconcileState, RETRY_MESSAGE, ReconciliationError } from '../src/lib/action-reconciliation.ts';
import { transcriptFollowsBottom } from '../src/lib/play-viewport.ts';

const gameSource = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const gameAst = ts.createSourceFile('game-browser.tsx', gameSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const gameComponent = gameAst.statements.find((n) => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
const submitDeclaration = gameComponent.body.statements.find((n) => ts.isVariableStatement(n)
  && n.declarationList.declarations.some((d) => d.name.getText(gameAst) === 'submitTurn'));
assert.ok(submitDeclaration, 'the real submitTurn exists');
const cacheCode = (await readFile(new URL('../src/lib/advisory-cache.ts', import.meta.url), 'utf8')).replace(/^export\s+/gm, '');
const blockingDeclaration = gameComponent.body.statements.find((n) => ts.isVariableStatement(n)
  && n.declarationList.declarations.some((d) => d.name.getText(gameAst) === 'blockingMutation'));
assert.ok(blockingDeclaration, 'the real blockingMutation exists');
const submitCode = ts.transpileModule([cacheCode, blockingDeclaration.getText(gameAst), submitDeclaration.getText(gameAst), 'globalThis.submit = submitTurn;'].join('\n'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;

const OWNER_A = 'user-a';
const baseState = { revision: 'r1', turn_index: 3, combat: { active: false }, quests: [] };

function receiptServer() {
  const receipts = new Map();
  const world = { spent: 0, time: 0 };
  return {
    world,
    handle(owner, campaign, data) {
      const slot = `${owner}|${campaign}|${data.action_id}`;
      const elsewhere = [...receipts.keys()].find((existing) => existing.endsWith(`|${data.action_id}`) && existing !== slot);
      if (elsewhere) throw Object.assign(new Error('not your action'), { status: 403 });
      if (!receipts.has(slot)) {
        world.spent += 1; // one spend ...
        world.time += 1; // ... and one time advance per unique action
        receipts.set(slot, { state: { ...baseState, revision: `r-${data.action_id}` }, narration: `done:${data.message}` });
      }
      return receipts.get(slot);
    },
  };
}

function harness({ sessionStorage = memoryStorage(), localStorage = memoryStorage(), server = receiptServer(), transport, state = baseState } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const requests = [];
  const notices = [];
  const messages = [];
  const entries = [];
  const life = createActionLifetime();
  const env = {
    reconcileState, RETRY_MESSAGE, ReconciliationError, turnLifetime: life,
    closePending: pending.closePending, createIntentKey: pending.createIntentKey, readPending: pending.readPending, resumePending: pending.resumePending,
    speciesActionUnresolved: pending.speciesActionUnresolved, pendingAmbientActionRef: { current: null }, notice: null,
    currentAccountOwner: account.currentAccountOwner, LOCAL_OWNER: 'local',
    PENDING_TURN_NOTICE: { tone: 'warning', title: 'pending', detail: 'pending' }, retryPendingTurn() {}, messageRef: { current: '' },
    pendingTurnNotice: () => ({ tone: 'warning', title: 'pending', detail: 'pending', retry() {}, recover: { check() {}, abandon() {} } }),
    recoveryHandlers: (serverActionId) => ({ check() {}, abandon() {}, serverActionId }), unresolvedActionFrom: recovery.unresolvedActionFrom,
    wasAtBottom: { current: true }, storyScrollRef: { current: null }, setResultCue() {}, setLastTurn() {}, transcriptFollowsBottom,
    window: { sessionStorage, localStorage, crypto: globalThis.crypto },
    sessionId: 'session-a', campaignId: 'campaign-a', interactionMode: 'do', conversationTargetId: '', combatTargetId: '', state,
    inFlightSessionsRef: { current: new Set() }, undoPendingRef: { current: new Set() }, undoRequestsRef: { current: new Map() },
    activeSessionRef: { current: 'session-a' },
    setInFlightSessions() {}, setNotice: (value) => { notices.push(value); }, getTurnInteractionMetadata: () => ({ interaction_mode: 'do' }),
    currentAuthEpoch, accountWriteAllowed: () => true,
    playGameTurn: async (sessionId, data) => {
      requests.push({ sessionId, data });
      const owner = account.currentAccountOwner();
      return transport ? transport({ sessionId, data, server, owner }) : server.handle(owner, 'campaign-a', data);
    },
    queryClient: client, getGetGameSessionStateQueryKey: (id) => ['state', id], ...gateInjection(), ...primalKnowledgeInjection(),
    getGameSessionState: async () => state,
    getCampaign: async () => ({ state, history: [{ player_message: 'x', narration: 'y' }], combat_history: [] }),
    mergeCombatHistory: (value) => value,
    getGetCampaignsQueryKey: () => ['campaigns'], entries: [], TRANSCRIPT_KEY: 'transcript-',
    setEntries: (value) => { entries.push(value); }, setNewResponseEntryIndex() {}, setCombatEntries() {}, setCombatEndNotice() {},
    setCombatTargetId() {}, setConversationTargetId() {}, setMessage: (value) => { messages.push(value); }, setComposerOpen() {},
    statusCode: (error) => error?.status, friendlyError: (error) => error?.message ?? 'Synthetic error',
  };
  vm.runInNewContext(submitCode, env);
  client.setQueryData(['state', 'session-a'], state);
  const settle = async () => { for (let i = 0; i < 200 && env.inFlightSessionsRef.current.size; i++) await new Promise((r) => setImmediate(r)); };
  return {
    env, client, requests, notices, messages, entries, server, sessionStorage, localStorage, life, settle,
    async send(text) { globalThis.window = env.window; env.submit(text); await settle(); },
    async retry(draft = '') { globalThis.window = env.window; env.submit(draft, undefined, 'do', true); await settle(); },
  };
}

function signedIn(h, owner = OWNER_A, session = 'sess-1') {
  globalThis.window = h.env.window;
  account.nextAccountClient(null, `${owner}:${session}`);
}

const lostResponse = async ({ server, data, owner }) => { server.handle(owner, 'campaign-a', data); throw new Error('response lost after commit'); };

test('double click sends one request and one effect', async () => {
  const h = harness();
  signedIn(h);
  h.env.submit('walk to the gate');
  h.env.submit('walk to the gate');
  await h.settle();
  assert.equal(h.requests.length, 1);
  assert.deepEqual(h.server.world, { spent: 1, time: 1 });
});

test('lost reply: retry reuses the same UUID and original request, and the effect happens once', async () => {
  const h = harness({ transport: lostResponse });
  signedIn(h);
  await h.send('walk to the gate');
  const original = h.requests[0].data;
  assert.ok(h.notices.at(-1).retry, 'the failure offers a retry');
  assert.ok(pending.readPending(OWNER_A, 'campaign-a'), 'the unresolved move is kept');

  const second = harness({ sessionStorage: h.sessionStorage, localStorage: h.localStorage, server: h.server });
  second.env.messageRef.current = 'a different draft typed meanwhile';
  await second.retry();
  assert.equal(second.requests[0].data.action_id, original.action_id);
  assert.equal(second.requests[0].data.message, 'walk to the gate');
  assert.deepEqual(h.server.world, { spent: 1, time: 1 });
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'confirmed result closes the pending move');
  assert.deepEqual(second.messages, [], 'the newer draft is not cleared or sent by the retry');

  const third = harness({ transport: lostResponse });
  signedIn(third);
  await third.send('open the chest');
  const same = harness({ sessionStorage: third.sessionStorage, localStorage: third.localStorage, server: third.server });
  same.env.messageRef.current = 'open the chest';
  await same.retry();
  assert.deepEqual(same.messages, [''], 'a draft that is still the retried text is consumed with it');
});

test('an unresolved move blocks a new move; the draft is kept and no request goes out', async () => {
  const h = harness({ transport: lostResponse });
  signedIn(h);
  await h.send('walk to the gate');
  const before = h.requests.length;
  await h.send('open the other door');
  assert.equal(h.requests.length, before);
  assert.equal(h.notices.at(-1).title, 'pending');
  assert.deepEqual(h.messages, [], 'the draft is never cleared while pending');
});

test('after the move is confirmed, identical text is a new deliberate move with a new UUID', async () => {
  const h = harness();
  signedIn(h);
  await h.send('walk to the gate');
  await h.send('walk to the gate');
  assert.equal(h.requests.length, 2);
  assert.notEqual(h.requests[0].data.action_id, h.requests[1].data.action_id);
  assert.deepEqual(h.server.world, { spent: 2, time: 2 });
});

test('reload keeps the unresolved move for the same owner and gives another owner nothing to retry', async () => {
  const h = harness({ transport: lostResponse });
  signedIn(h);
  await h.send('walk to the gate');
  const original = h.requests[0].data.action_id;

  const reloaded = harness({ sessionStorage: h.sessionStorage, localStorage: h.localStorage, server: h.server });
  signedIn(reloaded, OWNER_A, 'sess-2'); // same owner, new session after the reload
  await reloaded.retry();
  assert.equal(reloaded.requests[0].data.action_id, original);
  assert.deepEqual(h.server.world, { spent: 1, time: 1 });

  const first = harness({ transport: lostResponse });
  signedIn(first);
  await first.send('second move');
  const stranger = harness({ sessionStorage: first.sessionStorage, localStorage: first.localStorage, server: first.server });
  signedIn(stranger, 'user-b', 'sess-9');
  await stranger.retry();
  assert.equal(stranger.requests.length, 0, 'another owner has nothing to retry and cannot replay the old id');
});

test('an epoch change keeps the UUID but the old continuation cannot update the new screen', async () => {
  const gate = {};
  const h = harness({ transport: async ({ server, data, owner }) => { await new Promise((resolve) => { gate.release = resolve; }); return server.handle(owner, 'campaign-a', data); } });
  signedIn(h);
  h.env.submit('walk to the gate');
  await new Promise((r) => setImmediate(r));
  const original = h.requests[0].data.action_id;
  rotateAuthEpoch();
  gate.release();
  await h.settle();
  assert.deepEqual(h.entries, [], 'the stale continuation wrote nothing to the new screen');
  assert.deepEqual(h.messages, []);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a').key.actionId, original, 'the legitimate pending move survives the epoch');

  const next = harness({ sessionStorage: h.sessionStorage, localStorage: h.localStorage, server: h.server });
  signedIn(next, OWNER_A, 'sess-2');
  await next.retry();
  assert.equal(next.requests[0].data.action_id, original);
  assert.deepEqual(h.server.world, { spent: 1, time: 1 });
});

test('unavailable browser storage still keeps the unresolved move in this tab', async () => {
  const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); }, key: () => null, length: 0 };
  let calls = 0;
  const h = harness({ sessionStorage: broken, transport: async (call) => { calls += 1; if (calls === 1) return lostResponse(call); return call.server.handle(call.owner, 'campaign-a', call.data); } });
  signedIn(h);
  await h.send('walk to the gate');
  const original = h.requests[0].data.action_id;
  await h.send('something else');
  assert.equal(h.requests.length, 1, 'a new move is still blocked');
  await h.retry();
  assert.equal(h.requests[1].data.action_id, original);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null);
});

test('closing the waiting screen or an unclear failure is not a cancel; only the servers own never-applied answer is', async () => {
  const refusal = (status, extra = {}) => Object.assign(new Error('refused'), { status, ...extra });
  for (const status of [503, 409, 500, 404, 400, undefined]) {
    const h = harness({ transport: async () => { throw refusal(status); } });
    signedIn(h);
    await h.send('walk to the gate');
    assert.ok(pending.readPending(OWNER_A, 'campaign-a'), `a bare status ${status} keeps the pending move`);
    await h.send('another move');
    assert.equal(h.requests.length, 1, `status ${status} still blocks a new move`);
    pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
  }
  const closing = [
    [422, {}],
    [409, { data: { detail: { code: 'stale_combat', not_applied: true } } }],
    [400, { data: { detail: { code: 'invalid_combat_target', not_applied: true } } }],
  ];
  for (const [status, extra] of closing) {
    const h = harness({ transport: async () => { throw refusal(status, extra); } });
    signedIn(h);
    h.env.messageRef.current = 'walk to the gate'; // the composer still holds the text, as in real use
    await h.send('walk to the gate');
    assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, `status ${status} with the server's proof closes the move`);
    assert.deepEqual(h.messages, [], 'the draft is kept');
    assert.equal(h.notices.at(-1).retry, undefined, 'a closed move offers no retry of the old id');
    await h.send('walk to the gate');
    assert.equal(h.requests.length, 2);
    assert.notEqual(h.requests[0].data.action_id, h.requests[1].data.action_id, 'Send after a proven refusal is a new move with a new UUID');
  }
  const wrongClaim = harness({ transport: async () => { throw refusal(409, { data: { detail: { code: 'x', not_applied: 'yes' } } }); } });
  signedIn(wrongClaim);
  await wrongClaim.send('walk to the gate');
  assert.ok(pending.readPending(OWNER_A, 'campaign-a'), 'only a literal true counts');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
  const closed = harness({ transport: async ({ server, data, owner }) => { await new Promise((r) => setTimeout(r, 30)); return server.handle(owner, 'campaign-a', data); } });
  signedIn(closed);
  closed.env.submit('walk to the gate');
  await new Promise((r) => setImmediate(r));
  closed.life.dispose(); // the waiting screen is closed
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(pending.readPending(OWNER_A, 'campaign-a'), 'closing the screen does not cancel the server move');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
});

test('the receipt double refuses another owner replaying the same id', async () => {
  const h = harness({ transport: lostResponse });
  signedIn(h);
  await h.send('walk to the gate');
  const original = h.requests[0].data;
  assert.throws(() => h.server.handle('user-b', 'campaign-a', original), /not your action/);
  assert.deepEqual(h.server.world, { spent: 1, time: 1 });
});

test('the production submit no longer derives an action id from the message text', () => {
  assert.doesNotMatch(gameSource, /stableTurnActionId|actionFingerprint|signature = JSON\.stringify/);
  assert.match(gameSource, /createIntentKey\(ownerId, actionScope, request\)/);
  assert.match(gameSource, /closePending\(key, 'confirmed'\)/);
  assert.match(gameSource, /closePending\(key, 'cancelled', evidence\)/);
  assert.match(gameSource, /refusal\?\.not_applied === true/);
});

test('reading the pending move before a campaign or owner exists returns nothing instead of crashing the opening screen', () => {
  assert.equal(pending.readPending('user-a', ''), null);
  assert.equal(pending.readPending('', 'campaign-a'), null);
  assert.equal(pending.readPending('', ''), null);
  assert.throws(() => pending.createIntentKey('user-a', ''), 'only creating a move needs both');
});

test('another unresolved mutation in the same campaign blocks a new play move (species, ambient) without clearing the draft', async () => {
  const withSpecies = harness();
  signedIn(withSpecies);
  withSpecies.sessionStorage.setItem('ai-dnd-turn-context:species:campaign-a:retry', '{"action":"healing_hands","action_id":"species-uncertain"}');
  await withSpecies.send('walk to the gate');
  assert.equal(withSpecies.requests.length, 0);
  assert.match(withSpecies.notices.at(-1).title, /Tür yeteneği/);
  assert.deepEqual(withSpecies.messages, []);

  const withAmbient = harness();
  signedIn(withAmbient);
  withAmbient.env.pendingAmbientActionRef.current = { sessionId: 'session-a', eventInstanceId: 'event-1', data: {} };
  await withAmbient.send('walk to the gate');
  assert.equal(withAmbient.requests.length, 0);
  assert.match(withAmbient.notices.at(-1).title, /Çevre olayı/);

  const clear = harness();
  signedIn(clear);
  await clear.send('walk to the gate');
  assert.equal(clear.requests.length, 1, 'with nothing unresolved the move goes out');
});

test('after a reload a proven refusal gives the stored text back to the empty composer', async () => {
  const first = harness({ transport: lostResponse });
  signedIn(first);
  await first.send('walk to the gate');
  const reloaded = harness({
    sessionStorage: first.sessionStorage, localStorage: first.localStorage, server: first.server,
    transport: async () => { throw Object.assign(new Error('refused'), { status: 409, data: { detail: { code: 'stale_combat', not_applied: true } } }); },
  });
  signedIn(reloaded, OWNER_A, 'sess-2');
  reloaded.env.messageRef.current = '';
  await reloaded.retry();
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null);
  assert.deepEqual(reloaded.messages, ['walk to the gate'], 'the text lived only in the pending record, so it is restored');
});

test('a 422 on a retry with a lost or damaged stored request is not proof of cancellation', async () => {
  const h = harness({ transport: async () => { throw Object.assign(new Error('invalid'), { status: 422 }); } });
  signedIn(h);
  pending.createIntentKey(OWNER_A, 'campaign-a', {}); // the stored request body is missing
  await h.retry();
  assert.ok(pending.readPending(OWNER_A, 'campaign-a'), 'the original body may have committed, so the move stays pending');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
});

// ---- death-wait runs the real component body (hooks and transport replaced) ----
const deathSource = await readFile(new URL('../src/components/death-recovery-controls.tsx', import.meta.url), 'utf8');
const deathCode = ts.transpileModule(
  `${deathSource.replace(/^import[\s\S]*?;\s*$/gm, '').replace(/^export /gm, '')}
globalThis.DeathWait = DeathRecoveryControls;`,
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } },
).outputText;

test('unresolvedElsewhere names the blocking mutation and ignores other campaigns', () => {
  const key = pending.createIntentKey(OWNER_A, 'campaign-a', { message: 'x' });
  assert.equal(pending.unresolvedElsewhere(OWNER_A, 'campaign-a'), 'play');
  assert.equal(pending.unresolvedElsewhere(OWNER_A, 'campaign-b'), null);
  assert.equal(pending.unresolvedElsewhere('user-b', 'campaign-a'), null);
  pending.closePending(key, 'confirmed');
  window.sessionStorage.setItem('ai-dnd-turn-context:species:campaign-a:retry', '{}');
  assert.equal(pending.unresolvedElsewhere(OWNER_A, 'campaign-a'), 'species');
  window.sessionStorage.removeItem('ai-dnd-turn-context:species:campaign-a:retry');
  assert.equal(pending.unresolvedElsewhere(OWNER_A, 'campaign-a'), null);
});

test('the quest commands call the shared gate before mutating', () => {
  assert.match(gameSource, /const questBlocked = \(\) => \{[\s\S]*unresolvedElsewhere\(currentAccountOwner\(\) \?\? LOCAL_OWNER, campaignId \|\| sessionId\)/);
  assert.match(gameSource, /onAccept=\{\(questId\) => \{ if \(!questBlocked\(\)\) acceptQuest\.mutate/);
  assert.match(gameSource, /onCancel=\{\(questId\) => \{ if \(!questBlocked\(\)\) cancelQuest\.mutate/);
});

// ---- death-wait uses the same durable pending slot as every other mutation of the campaign ----
const WAIT_MESSAGE = 'Ölüm kurtarma zarımı atıyorum.';

function durableDeathWait({ storage = memoryStorage() } = {}) {
  const mutations = [];
  const callbacks = [];
  const hooks = [];
  let options;
  let cursor = 0;
  globalThis.window = { sessionStorage: storage, localStorage: memoryStorage(), crypto: globalThis.crypto };
  const env = {
    React: { createElement: (type, props, ...children) => ({ type, props: props ?? {}, children: children.flat() }) },
    useState: (initial) => {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = initial;
      return [hooks[index], (value) => { hooks[index] = typeof value === 'function' ? value(hooks[index]) : value; }];
    },
    useEffect() {}, useQueryClient: () => ({ setQueryData() {}, invalidateQueries() {} }),
    usePlayGameTurn: (given) => { options = given; return { mutate: (call, perCall) => { mutations.push(call); callbacks.push(perCall ?? {}); }, isPending: false, isError: false }; },
    getGetGameSessionStateQueryKey: (id) => ['state', id], ...gateInjection(), ...primalKnowledgeInjection(), currentAccountOwner: () => OWNER_A, currentAuthEpoch,
    readPending: pending.readPending, createIntentKey: pending.createIntentKey, resumePending: pending.resumePending,
    closePending: pending.closePending, unresolvedElsewhere: pending.unresolvedElsewhere, crypto: globalThis.crypto,
  };
  vm.runInNewContext(deathCode, env);
  const render = () => {
    cursor = 0;
    return env.DeathWait({
      state: { character: { current_hp: 0 }, death_state: { status: 'unconscious' }, combat: { active: false } },
      sessionId: 'session-a', campaignId: 'campaign-a',
    });
  };
  const find = (node, id) => (node && typeof node === 'object'
    ? (node.props?.['data-testid'] === id ? node : [...(node.children ?? [])].map((child) => find(child, id)).find(Boolean))
    : undefined);
  return {
    storage, mutations,
    click: () => find(render(), 'button-death-wait').props.onClick(),
    callbacks,
    // The component hands its callbacks to each mutate call, bound to the move that call sent.
    succeed: (index = callbacks.length - 1) => callbacks[index].onSuccess({ state: { revision: 'after-wait' } }),
    fail: (error, index = callbacks.length - 1) => callbacks[index].onError(error),
    shows: (id) => Boolean(find(render(), id)),
  };
}

test('death-wait records a durable pending move in the shared slot and sends exactly that id', () => {
  const wait = durableDeathWait();
  wait.click();
  const stored = pending.readPending(OWNER_A, 'campaign-a');
  assert.ok(stored, 'the wait is an unresolved move of this campaign');
  assert.equal(stored.request.message, WAIT_MESSAGE);
  assert.deepEqual(JSON.parse(JSON.stringify(wait.mutations[0].data)), { message: WAIT_MESSAGE, action_id: stored.key.actionId });
  assert.equal(pending.unresolvedElsewhere(OWNER_A, 'campaign-a'), 'play', 'every other path now sees it');
});

test('death-wait survives a remount: the next click resumes the same id instead of waiting twice', () => {
  const first = durableDeathWait();
  first.click();
  first.fail(Object.assign(new Error('lost reply'), { status: 500 }));
  const reloaded = durableDeathWait({ storage: first.storage });
  reloaded.click();
  assert.equal(reloaded.mutations[0].data.action_id, first.mutations[0].data.action_id);
  assert.equal(reloaded.mutations[0].data.message, WAIT_MESSAGE);
});

test('death-wait closes on success and on the server\'s proof, and a refused wait becomes a new wait', () => {
  const ok = durableDeathWait();
  ok.click();
  ok.succeed();
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null);

  const refused = durableDeathWait();
  refused.click();
  refused.fail(Object.assign(new Error('refused'), { status: 409, data: { detail: { code: 'engine_error', not_applied: true } } }));
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null);
  refused.click();
  assert.notEqual(refused.mutations[1].data.action_id, refused.mutations[0].data.action_id);
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');

  const unclear = durableDeathWait();
  for (const status of [404, 409, 500, 503]) {
    unclear.click();
    unclear.fail(Object.assign(new Error('unclear'), { status }));
    assert.ok(pending.readPending(OWNER_A, 'campaign-a'), `status ${status} alone never closes the wait`);
  }
  assert.equal(new Set(unclear.mutations.map((call) => call.data.action_id)).size, 1, 'every retry reuses the one id');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
});

test('an unresolved death-wait blocks play moves, and an unresolved play move blocks death-wait', async () => {
  const wait = durableDeathWait();
  const play = harness();
  play.env.window.sessionStorage = wait.storage;
  signedIn(play); // establishes the owner first (an unknown owner would clear the slot, see R01)
  wait.click();
  await play.send('walk to the gate');
  assert.equal(play.requests.length, 0, 'the play move waits behind the unresolved wait');
  assert.equal(play.notices.at(-1).title, 'pending', 'the play move is told an earlier move is unresolved');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');

  const move = pending.createIntentKey(OWNER_A, 'campaign-a', { message: 'walk to the gate' });
  const blocked = durableDeathWait({ storage: wait.storage });
  blocked.click();
  assert.equal(blocked.mutations.length, 0, 'a different unresolved move is never resumed or overtaken by the wait button');
  pending.closePending(move, 'confirmed');
});

test('death-wait is blocked by an unresolved species action, and the play retry can resolve a pending wait', async () => {
  const withSpecies = durableDeathWait();
  withSpecies.storage.setItem('ai-dnd-turn-context:species:campaign-a:retry', '{"action_id":"species-uncertain"}');
  withSpecies.click();
  assert.equal(withSpecies.mutations.length, 0);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'a blocked click creates no pending move');

  // A pending wait is an ordinary pending move: the retry button of the play screen resends it with the same id.
  const wait = durableDeathWait();
  const play = harness();
  play.env.window.sessionStorage = wait.storage;
  signedIn(play);
  wait.click();
  const waitId = wait.mutations[0].data.action_id;
  await play.retry();
  assert.equal(play.requests.length, 1);
  assert.equal(play.requests[0].data.action_id, waitId);
  assert.equal(play.requests[0].data.message, WAIT_MESSAGE);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'the confirmed result closes the wait');
});

test('a late callback of an earlier wait never closes or overwrites a newer move in the slot', () => {
  const wait = durableDeathWait();
  wait.click(); // W1
  const w1 = pending.readPending(OWNER_A, 'campaign-a').key;
  pending.closePending(w1, 'confirmed'); // resolved elsewhere, e.g. through the play-screen retry
  wait.click(); // W2 gets a new id
  const w2 = pending.readPending(OWNER_A, 'campaign-a').key;
  assert.notEqual(w1.actionId, w2.actionId);
  wait.succeed(0); // W1's late success arrives now
  assert.equal(pending.readPending(OWNER_A, 'campaign-a')?.key.actionId, w2.actionId, 'W2 stays pending: W1 had no authority over it');
  wait.fail(Object.assign(new Error('late'), { status: 409, data: { detail: { code: 'engine_error', not_applied: true } } }), 0);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a')?.key.actionId, w2.actionId, 'a late proof for W1 does not cancel W2');
  pending.closePending(w2, 'confirmed');
});

test('a wait result from an old auth epoch changes nothing', () => {
  const wait = durableDeathWait();
  wait.click();
  const id = pending.readPending(OWNER_A, 'campaign-a').key.actionId;
  rotateAuthEpoch();
  wait.succeed();
  assert.equal(pending.readPending(OWNER_A, 'campaign-a')?.key.actionId, id, 'the old-epoch answer neither closes the wait nor touches the new screen');
  pending.closePending(pending.readPending(OWNER_A, 'campaign-a').key, 'confirmed');
});

test('a retried play-screen wait that the server refuses does not put the wait text into the composer', async () => {
  const wait = durableDeathWait();
  const play = harness({ transport: async () => { throw Object.assign(new Error('refused'), { status: 409, data: { detail: { code: 'engine_error', not_applied: true } } }); } });
  play.env.window.sessionStorage = wait.storage;
  signedIn(play);
  wait.click();
  play.env.messageRef.current = '';
  await play.retry();
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null);
  assert.deepEqual(play.messages, [], 'only the players own draft is ever restored to the composer');
});

// ---- the REAL backend refusal body, carried by the REAL customFetch/ApiError, closes the pending move ----
import { ApiError, customFetch, setAuthTokenGetter, setProtectedRequestCredentials } from '@workspace/api-client-react/custom-fetch';

const refusalFixture = JSON.parse(await readFile(new URL('../../../ai-dnd/api/tests/fixtures/r02_refusal_409.json', import.meta.url), 'utf8'));

async function realRefusalError() {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173' } };
  globalThis.fetch = async () => new Response(JSON.stringify(refusalFixture.body), {
    status: refusalFixture.status, headers: { 'content-type': 'application/json' },
  });
  setAuthTokenGetter(async () => 'test-token');
  setProtectedRequestCredentials('include');
  try {
    return await customFetch('/api/game/sessions/session-a/turn', { method: 'POST', body: '{}' }).then(() => null, (error) => error);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    setAuthTokenGetter(null);
    setProtectedRequestCredentials('omit');
  }
}

test('the backend refusal body reaches the client as a real ApiError with the never-applied proof', async () => {
  const error = await realRefusalError();
  assert.ok(error instanceof ApiError, 'the shared fixture goes through the real transport layer');
  assert.equal(error.status, 409);
  assert.equal(error.data.detail.not_applied, true);
  assert.equal(typeof error.data.detail.code, 'string');
});

test('that real ApiError closes a play move and a death-wait, keeps the draft, and the next Send is a new id', async () => {
  const error = await realRefusalError();

  const play = harness({ transport: async () => { throw error; } });
  signedIn(play);
  play.env.messageRef.current = 'walk to the gate';
  await play.send('walk to the gate');
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'the real proof closes the pending move');
  assert.deepEqual(play.messages, [], 'the draft is kept');
  await play.send('walk to the gate');
  assert.notEqual(play.requests[1].data.action_id, play.requests[0].data.action_id, 'the next Send is a new move with a new id');

  const wait = durableDeathWait();
  wait.click();
  wait.fail(error);
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'the same real proof closes the death-wait');
  wait.click();
  assert.notEqual(wait.mutations[1].data.action_id, wait.mutations[0].data.action_id, 'only the player\'s explicit click creates the new wait');
});

const intentContract = JSON.parse(await readFile(new URL('../../../ai-dnd/api/tests/fixtures/r02_intent_contract.json', import.meta.url), 'utf8'));

async function realIntentRefusalError() {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173' } };
  globalThis.fetch = async () => new Response(JSON.stringify(intentContract.unresolved_action_refusal.body), {
    status: intentContract.unresolved_action_refusal.status, headers: { 'content-type': 'application/json' },
  });
  setAuthTokenGetter(async () => 'test-token');
  setProtectedRequestCredentials('include');
  try {
    return await customFetch('/api/game/sessions/session-a/turn', { method: 'POST', body: '{}' }).then(() => null, (error) => error);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    setAuthTokenGetter(null);
    setProtectedRequestCredentials('omit');
  }
}

test('the real unresolved_action refusal closes the NEW id, keeps the draft, and offers the server-proven way out for the OPEN one', async () => {
  const error = await realIntentRefusalError();
  const play = harness({ transport: async () => { throw error; } });
  signedIn(play);
  play.env.messageRef.current = 'walk to the gate';
  await play.send('walk to the gate');
  assert.equal(pending.readPending(OWNER_A, 'campaign-a'), null, 'the refused new id is closed by the server proof');
  assert.deepEqual(play.messages, [], 'the draft is kept');
  const notice = play.notices.at(-1);
  assert.ok(notice.recover, 'the player is offered check / abandon');
  assert.equal(notice.retry, undefined, 'there is no local request to resend for the open action');
  await play.send('walk to the gate');
  assert.notEqual(play.requests[1].data.action_id, play.requests[0].data.action_id, 'only the explicit second Send makes a new id; nothing resends automatically');
});

test('death-wait is its own operation kind in the shared slot, not a text guess', () => {
  const wait = durableDeathWait();
  wait.click();
  const stored = pending.readPending(OWNER_A, 'campaign-a');
  assert.equal(stored.kind, 'death_wait');
  assert.equal(JSON.stringify(wait.mutations[0].data).includes('kind'), false, 'the kind is bookkeeping, never part of the request body');
  pending.closePending(stored.key, 'confirmed');

  // A play move that happens to have exactly the wait text is still a play move: the wait button neither resumes nor closes it.
  const move = pending.createIntentKey(OWNER_A, 'campaign-a', { message: WAIT_MESSAGE, interaction_mode: 'do' });
  assert.equal(pending.readPending(OWNER_A, 'campaign-a').kind, 'play');
  const other = durableDeathWait({ storage: wait.storage });
  other.click();
  assert.equal(other.mutations.length, 0);
  other.callbacks.length = 0;
  pending.closePending(move, 'confirmed');
});
