import { combatStartInjection } from './support/combat-start-env.mjs';
// B3: bounded recovery and panel reconciliation in the REAL GameBrowser source. serverRecovery, blockingMutation and their
// helpers are selected from src/pages/game-browser.tsx by AST and run in a vm; only hooks, view setters and the transport
// are replaced. Timers are node:test fake timers, so no test waits on a real clock and nothing touches the network.
// Each test has a real-time cap, so a regression fails instead of hanging. A recovery never re-sends the payment: the only POST a test may see is the one it made itself.
// Every path that could re-send a move (the play transport, submitTurn, the level-up transport, retry) is a counting stub, so a
// re-send through any of them is counted, not hidden behind a ReferenceError.
import { gateInjection } from './support/state-gate-env.mjs';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, mock, test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';
import { createActionLifetime, reconcileState, RETRY_MESSAGE, ReconciliationError } from '../src/lib/action-reconciliation.ts';
import * as pending from '../src/lib/pending-action.ts';
import * as recovery from '../src/lib/action-recovery.ts';
import { historyToEntries } from '../src/lib/transcript-history.ts';

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
  pick('recoveryHandlers'), pick('pendingTurnNotice'), pick('blockingMutation'), pick('serverRecovery'), pick('showServerOpenAction'),
  'serverRecoveryRef.current = serverRecovery;',
  'Object.assign(globalThis, { recoveryHandlers, blockingMutation, serverRecovery, showServerOpenAction });',
].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;

const OWNER = 'user-a';
const CAMPAIGN = 'campaign-a';
const SESSION = 'session-a';
const originalWindow = globalThis.window;

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
  mock.timers.reset();
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

const flush = async (rounds = 5) => { for (let i = 0; i < rounds; i++) await new Promise((resolve) => setImmediate(resolve)); };
const never = () => new Promise(() => {});

// The confirm the player pressed: one POST, the only one any test may ever count.
function confirmPressed() {
  const request = { message: 'Teklifi onayla', interaction_mode: 'do', economic_action: { kind: 'confirm', offer_id: 'offer-1', confirmation_digest: 'd1' } };
  const key = pending.createIntentKey(OWNER, CAMPAIGN, request);
  return { key, posts: [`POST play ${key.actionId}`] };
}

// One GameBrowser "render". `status` answers the status call (a function, so a test can hand out a never-settling promise).
function render({ status, abandon, unresolved, campaign, lifetime = createActionLifetime(), sessionId = SESSION, campaignId = CAMPAIGN } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const calls = [];
  const notices = [];
  const entries = [];
  const lastTurns = [];
  const panelEpochs = [];
  const sends = [];
  const api = {
    status: (sid, actionId, options) => { calls.push({ kind: 'status', sid, actionId, signal: options?.signal }); return status ? status(actionId, options) : never(); },
    abandon: (sid, actionId, options) => { calls.push({ kind: 'abandon', sid, actionId, signal: options?.signal }); return abandon ? abandon(actionId, options) : never(); },
    unresolved: (sid, options) => { calls.push({ kind: 'unresolved', sid, signal: options?.signal }); return unresolved ? unresolved(options) : never(); },
  };
  const env = { ...combatStartInjection(),
    sessionId, campaignId, serverRecoveryRef: { current: null },
    RECOVERY_API: api, askServer: recovery.askServer, settlePending: recovery.settlePending, findUnresolvedOnServer: recovery.findUnresolvedOnServer,
    RecoveryTimeoutError: recovery.RecoveryTimeoutError,
    playGameTurn: (...args) => { sends.push({ kind: 'playGameTurn', args }); return never(); },
    applyGameSessionLevelUp: (...args) => { sends.push({ kind: 'applyGameSessionLevelUp', args }); return never(); },
    submitTurn: (...args) => { sends.push({ kind: 'submitTurn', args }); },
    submitTurnRef: { current: (...args) => { sends.push({ kind: 'submitTurnRef', args }); } },
    submitLevelUpRef: { current: (...args) => { sends.push({ kind: 'submitLevelUpRef', args }); } },
    setPanelEpoch: (v) => { panelEpochs.push(typeof v === 'function' ? v(panelEpochs.at(-1) ?? 0) : v); },
    readPending: pending.readPending, speciesActionUnresolved: pending.speciesActionUnresolved, currentAccountOwner: () => OWNER, LOCAL_OWNER: 'local',
    PENDING_TURN_NOTICE: { tone: 'warning', title: 'Önceki hamle doğrulanmadı', detail: 'pending' }, pendingAmbientActionRef: { current: null },
    inFlightSessionsRef: { current: new Set() }, setInFlightSessions() {}, turnLifetime: lifetime,
    getGetGameSessionStateQueryKey: (id) => ['state', id], ...gateInjection(), reconcileState, ReconciliationError, RETRY_MESSAGE,
    getCampaign: async (id) => { calls.push({ kind: 'getCampaign', id }); return campaign(); },
    getGameSessionState: async () => campaign().state, queryClient: client, setEntries: (v) => entries.push(v),
    writeAdvisoryCache() {}, TRANSCRIPT_KEY: 't-', setCombatEntries() {}, mergeCombatHistory: (v) => v,
    getGetCampaignsQueryKey: () => ['campaigns'], setNotice: (v) => { notices.push(typeof v === 'function' ? v(notices.at(-1) ?? null) : v); },
    setLastTurn: (v) => lastTurns.push(v), setUndoneJustNow() {}, historyToEntries, retryPendingTurn: () => calls.push({ kind: 'retry' }),
    friendlyError: (e, fallback) => fallback ?? e?.message ?? 'error', messageRef: { current: '' }, setMessage() {},
    window: globalThis.window,
  };
  // GameBrowser's `notice` state: blockingMutation reads the notice currently on screen.
  Object.defineProperty(env, 'notice', { get: () => notices.at(-1) ?? null, enumerable: true });
  vm.runInNewContext(code, env);
  return { env, api, calls, notices, entries, lastTurns, client, lifetime, panelEpochs, sends };
}

const statusCalls = (view) => view.calls.filter((c) => c.kind === 'status').length;
const postCount = (view, posts) => posts.length + view.sends.length + view.calls.filter((c) => c.kind === 'abandon' || c.kind === 'retry').length;

test('test_never_settling_status_exits_loading', { timeout: 30_000 }, async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  const { key, posts } = confirmPressed();
  const view = render();
  let finished = false;
  const run = view.env.serverRecovery('check').then(() => { finished = true; });
  await flush();
  assert.equal(statusCalls(view), 1);
  assert.ok(view.calls[0].signal, 'the status call carries an AbortSignal');
  assert.ok(view.env.inFlightSessionsRef.current.has(SESSION), 'loading while the server is asked');

  mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS);
  await flush();
  assert.equal(view.calls[0].signal.aborted, true, 'the timed-out call is told to stop');
  assert.equal(statusCalls(view), recovery.RECOVERY_AUTO_ATTEMPTS, 'one automatic re-check, never more');
  assert.equal(finished, false);

  mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS);
  await flush();
  await run;
  assert.equal(finished, true, 'the check ends on its own; no endless loading');
  const notice = view.notices.at(-1);
  const recoveryState = notice.recovery;
  assert.equal(recoveryState.status, 'unknown');
  assert.equal(recoveryState.loading, false);
  assert.equal(recoveryState.mutationAllowed, false);
  assert.equal(view.env.inFlightSessionsRef.current.has(SESSION), false, 'the screen is no longer busy');
  assert.equal(notice.checkLabel, 'Tekrar kontrol et', 'the manual re-check is offered');
  assert.ok(notice.recover?.check, 'the re-check button is wired');
  assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, key.actionId, 'the identity is kept');

  mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS * 5);
  await flush();
  assert.equal(statusCalls(view), recovery.RECOVERY_AUTO_ATTEMPTS, 'no hidden polling after unknown');
  assert.deepEqual(view.panelEpochs, [], 'an unknown outcome does not reset the panel as if it had settled');
  assert.equal(postCount(view, posts), 1, 'paymentPostCount stays 1');
});

test('test_unknown_keeps_mutations_blocked', { timeout: 30_000 }, async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  const { key, posts } = confirmPressed();
  const view = render();
  const run = view.env.serverRecovery('check');
  for (let i = 0; i < recovery.RECOVERY_AUTO_ATTEMPTS; i++) { await flush(); mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS); }
  await flush();
  await run;
  const recoveryState = view.notices.at(-1).recovery;
  assert.equal(recoveryState.status, 'unknown');
  assert.equal(recoveryState.loading, false);
  assert.equal(recoveryState.mutationAllowed, false);
  assert.ok(view.env.blockingMutation(), 'a new move, card or panel action is refused while the outcome is unknown');
  assert.equal(view.calls.filter((c) => c.kind === 'abandon').length, 0, 'unknown never abandons on its own');

  // Unmount (scope change) and a reload do not grant permission: the stored identity still blocks.
  view.lifetime.dispose();
  const reloaded = render();
  assert.ok(reloaded.env.blockingMutation(), 'after a reload the unknown move still blocks');
  assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, key.actionId);
  assert.equal(postCount(view, posts) + postCount(reloaded, []), 1, 'paymentPostCount === 1');

  // A server-only open action (second tab): a timed-out check is unknown, offers the re-check and closes nothing.
  pending.closePending(key, 'confirmed');
  const second = render();
  const runSecond = second.env.serverRecovery('check', 'server-open-id');
  for (let i = 0; i < recovery.RECOVERY_AUTO_ATTEMPTS; i++) { await flush(); mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS); }
  await flush();
  await runSecond;
  assert.equal(second.notices.at(-1).recovery.status, 'unknown');
  assert.equal(second.notices.at(-1).recovery.mutationAllowed, false);
  assert.ok(second.notices.at(-1).recover, 'check and abandon stay offered');
  assert.equal(second.calls.filter((c) => c.kind === 'abandon').length, 0);
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null, 'only the server holds the open action');
  assert.ok(second.env.blockingMutation(), 'the client guard locks the composer, card and panels on the server-only unknown');
  assert.equal(second.env.blockingMutation(), second.notices.at(-1), 'the refusal keeps the unknown notice and its re-check on screen');
  assert.equal(postCount(second, []), 0, 'nothing is re-sent for the server-only action');
  // The lock is bound to its campaign: another campaign is not blocked by it.
  const elsewhere = render({ campaignId: 'campaign-b', sessionId: 'session-b' });
  elsewhere.notices.push(second.notices.at(-1));
  assert.equal(elsewhere.env.blockingMutation(), null, 'a lock for campaign A never blocks campaign B');
});

test('test_applied_reconciles_last_turn_wallet_and_card', { timeout: 30_000 }, async () => {
  const { posts } = confirmPressed();
  const fresh = { revision: 'r2', turn_index: 5, combat: { active: false }, quests: [], scene: null, wallet: { total_cp: 96 }, economic_offer: null };
  const view = render({
    status: async (actionId) => ({ action_id: actionId, state: 'applied', response: { narration: 'Bahşiş verildi.', economic_resolution: { status: 'applied', net_debit_cp: 4 }, turn_outcome: { kind: 'x' } } }),
    campaign: () => ({ state: fresh, history: [{ player_message: 'Teklifi onayla', narration: 'Bahşiş verildi.' }], combat_history: [] }),
  });
  await view.env.serverRecovery('check');
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null, 'the confirm is closed only after the reconcile');
  const shown = view.client.getQueryData(['state', SESSION]);
  assert.deepEqual(shown.wallet, { total_cp: 96 }, 'the purse is the server purse');
  assert.equal(shown.economic_offer, null, 'the consumed card is gone');
  assert.equal(view.entries.length, 1, 'the story is rebuilt from the same server read');
  assert.deepEqual(view.env.combatStartNotices, [null]);
  assert.deepEqual(view.lastTurns, [null], 'the last-turn slot is refreshed: no stale earlier turn stays as the undo target or outcome');
  const recoveryState = view.notices.at(-1).recovery;
  assert.equal(recoveryState.status, 'applied');
  assert.equal(recoveryState.loading, false);
  assert.equal(recoveryState.mutationAllowed, true);
  assert.equal(view.env.blockingMutation(), null);
  assert.deepEqual(view.panelEpochs, [1], 'the counter panel is reset from the same settled read (no stale waiting gate or old quote)');
  assert.match(source, /<ShopControls key=\{`[^`]*\$\{panelEpoch\}`\}/, 'the counter panel is keyed by the recovery epoch');
  assert.equal(postCount(view, posts), 1, 'paymentPostCount === 1');
});

test('test_undone_replay_does_not_restore_old_success', { timeout: 30_000 }, async () => {
  const { posts } = confirmPressed();
  // The stored answer is the historical success; the present (after the undo) has the purse back and the card open again.
  const historical = { narration: 'Hancıya 4 bakır verdin.', economic_resolution: { status: 'applied', net_debit_cp: 4, public_summary: '4 bakır ödendi.' }, state: { wallet: { total_cp: 96 }, economic_offer: null }, turn_outcome: { kind: 'paid' } };
  const present = { revision: 'r3', turn_index: 4, combat: { active: false }, quests: [], scene: null, wallet: { total_cp: 100 }, economic_offer: { offer_id: 'offer-1', confirmation_digest: 'd1' } };
  const view = render({
    status: async (actionId) => ({ action_id: actionId, state: 'applied', response: historical }),
    campaign: () => ({ state: present, history: [], combat_history: [] }),
  });
  await view.env.serverRecovery('check');
  const shown = view.client.getQueryData(['state', SESSION]);
  assert.deepEqual(shown.wallet, { total_cp: 100 }, 'the screen shows the undone present, not the old purse');
  assert.equal(shown.economic_offer?.offer_id, 'offer-1', 'the card the undo opened again is shown');
  assert.deepEqual(view.env.combatStartNotices, [null]);
  assert.deepEqual(view.lastTurns, [null], 'the old success is never put back as the last turn');
  const notice = view.notices.at(-1);
  assert.doesNotMatch(`${notice.title} ${notice.detail}`, /4 bakır ödendi|uygulandığını doğruladı/, 'the old receipt is not presented as current');
  assert.match(notice.detail, /güncel durum/);
  assert.match(notice.detail, /yeniden gönderilmedi/);
  assert.deepEqual(view.calls.filter((c) => c.kind !== 'getCampaign').map((c) => c.kind), ['status'], 'nothing is re-sent');
  assert.deepEqual(view.panelEpochs, [1], 'the counter panel is reset to the undone present');
  assert.equal(postCount(view, posts), 1, 'paymentPostCount === 1');
});

test('test_campaign_switch_drops_stale_promise', { timeout: 30_000 }, async () => {
  const { key, posts } = confirmPressed();
  let answer;
  const view = render({
    status: () => new Promise((resolve) => { answer = resolve; }),
    campaign: () => ({ state: { revision: 'old', wallet: { total_cp: 1 } }, history: [{ player_message: 'old', narration: 'old' }], combat_history: [] }),
  });
  let finished = false;
  const run = view.env.serverRecovery('check').then(() => { finished = true; });
  await flush();
  const noticesBefore = view.notices.length;
  // The player opens another campaign: the screen's lifetime for campaign A ends.
  view.lifetime.dispose();
  await flush();
  assert.equal(finished, true, 'the old recovery ends at the switch instead of hanging');
  assert.equal(view.calls[0].signal.aborted, true, 'the old request is aborted');
  assert.equal(view.env.inFlightSessionsRef.current.has(SESSION), false, 'campaign A is not left busy for when the player returns');
  answer({ action_id: key.actionId, state: 'applied', response: null });
  await flush();
  await run;
  assert.equal(view.notices.length, noticesBefore, 'the late answer writes no notice');
  assert.equal(view.client.getQueryData(['state', SESSION]), undefined, 'the late answer writes no state');
  assert.deepEqual(view.entries, [], 'the late answer writes no story');
  assert.deepEqual(view.lastTurns, []);
  assert.deepEqual(view.env.combatStartNotices, []);
  assert.equal(view.calls.some((c) => c.kind === 'getCampaign'), false);
  assert.equal(pending.readPending(OWNER, CAMPAIGN)?.key.actionId, key.actionId, 'the identity is kept for the next visit');
  assert.equal(postCount(view, posts), 1, 'paymentPostCount === 1');
});

test('test_open_action_lookup_timeout_offers_recheck', { timeout: 30_000 }, async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  let answer = never;
  const view = render({ unresolved: () => answer() });
  const run = view.env.showServerOpenAction(SESSION, CAMPAIGN, () => true);
  for (let i = 0; i < recovery.RECOVERY_AUTO_ATTEMPTS; i++) { await flush(); mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS); }
  await flush();
  await run;
  assert.equal(view.calls.filter((c) => c.kind === 'unresolved').length, recovery.RECOVERY_AUTO_ATTEMPTS, 'bounded: one automatic re-ask, no more');
  const notice = view.notices.at(-1);
  assert.equal(notice.recovery.status, 'unknown', 'a lookup that ran out of time is unknown, not "nothing is open"');
  assert.equal(notice.recovery.loading, false);
  assert.equal(notice.recovery.mutationAllowed, false);
  assert.equal(typeof notice.recheck, 'function', 'the manual re-check is offered');
  assert.ok(view.env.blockingMutation(), 'mutations stay locked while the lookup is unknown');
  assert.equal(pending.readPending(OWNER, CAMPAIGN), null, 'no browser record is fabricated');
  mock.timers.tick(recovery.RECOVERY_CALL_TIMEOUT_MS * 5);
  await flush();
  assert.equal(view.calls.filter((c) => c.kind === 'unresolved').length, recovery.RECOVERY_AUTO_ATTEMPTS, 'no hidden polling');

  // The server is back and nothing is open: the re-check runs the same lookup and clears the unknown lock.
  answer = async () => ({ unresolved: null });
  notice.recheck();
  await flush();
  assert.equal(view.calls.filter((c) => c.kind === 'unresolved').length, recovery.RECOVERY_AUTO_ATTEMPTS + 1);
  assert.equal(view.notices.at(-1), null, 'the unknown notice is cleared');
  assert.equal(view.env.blockingMutation(), null, 'the lock lifts only after a real answer');
  assert.equal(view.calls.filter((c) => c.kind === 'abandon').length, 0);
  assert.equal(postCount(view, []), 0, 'nothing is re-sent');

  // A lookup the screen abandoned (campaign switch) ends without any notice.
  const switched = render();
  const owner = new AbortController();
  const gone = switched.env.showServerOpenAction(SESSION, CAMPAIGN, () => true, owner.signal);
  await flush();
  owner.abort();
  await gone;
  assert.equal(switched.notices.length, 0, 'an aborted lookup shows nothing');
});
