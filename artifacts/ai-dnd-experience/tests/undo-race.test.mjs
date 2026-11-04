import { primalKnowledgeInjection } from './support/primal-knowledge-env.mjs';
import { gateInjection } from './support/state-gate-env.mjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { ReconciliationError } from '../src/lib/action-reconciliation.ts';
import { transcriptFollowsBottom } from '../src/lib/play-viewport.ts';
import { historyToEntries } from '../src/lib/transcript-history.ts';

const source = await readFile(process.env.AI_DND_TEST_SOURCE ?? new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
function declaration(name) {
  return component.body.statements.find(n => ts.isVariableStatement(n)
    && n.declarationList.declarations.some(d => d.name.getText(ast) === name));
}
const undoCode = declaration('undoLastTurn');
const submitCode = declaration('submitTurn');
const blockingCode = declaration('blockingMutation');
assert.ok(blockingCode);
assert.ok(undoCode);
assert.ok(submitCode);
const executable = ts.transpileModule([
  (await readFile(new URL('../src/lib/advisory-cache.ts', import.meta.url), 'utf8')).replace(/^export\s+/gm, ''),
  blockingCode.getText(ast),
  undoCode.getText(ast),
  submitCode.getText(ast),
  'globalThis.undo = undoLastTurn; globalThis.submit = submitTurn;',
].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

class ApiError extends Error {
  constructor(status) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

function harness() {
  const undoResponse = deferred();
  const retryUndoResponse = deferred();
  const turnResponse = deferred();
  const undoRequests = [];
  const turnRequests = [];
  let uuidCounter = 0;
  let statusReadCount = 0;
  const state = { revision: 'before-undo', combat: { active: false }, quests: [] };
  const env = {
    sessionId: 'session-a', campaignId: 'campaign-a', interactionMode: 'do',
    conversationTargetId: '', combatTargetId: '',
    visibleLastTurn: { sessionId: 'session-a', actionId: 'old-action', outcome: null },
    undoPendingRef: { current: new Set() }, undoRequestsRef: { current: new Map() },
    undoGenerationRef: { current: 0 },
    undoScope: 'campaign-a:session-a', undoScopeRef: { current: 'campaign-a:session-a' },
    lastTurnRef: { current: { sessionId: 'session-a', actionId: 'old-action', outcome: null } },
    inFlightSessionsRef: { current: new Set() },
    activeSessionRef: { current: 'session-a' },
    pendingTurnRef: { current: null },
  wasAtBottom: { current: true }, storyScrollRef: { current: null }, setResultCue() {}, transcriptFollowsBottom,
  setNewResponseEntryIndex() {},
    turnLifetime: { begin: () => ({ signal: new AbortController().signal, isCurrent: () => true, close() {} }) },
    state, entries: [{ kind: 'narration', text: 'Before' }], message: 'draft before',
    undoGameTurn: (...args) => {
      undoRequests.push(args);
      return (undoRequests.length === 1 ? undoResponse : retryUndoResponse).promise;
    },
    playGameTurn: (...args) => { turnRequests.push(args); return turnResponse.promise; },
    queryClient: {
      cache: new Map(),
      counts: new Map(),
      setQueryData(key, value) {
        const serialized = JSON.stringify(key);
        this.cache.set(serialized, value);
        this.counts.set(serialized, (this.counts.get(serialized) ?? 0) + 1);
      },
      getQueryData(key) { return this.cache.get(JSON.stringify(key)); },
      getQueryState(key) { return { dataUpdateCount: this.counts.get(JSON.stringify(key)) ?? 0 }; },
      invalidateQueries() { return Promise.resolve(); },
    },
    getGetGameSessionStateQueryKey: id => ['state', id], ...gateInjection(), ...primalKnowledgeInjection(),
    getGetCampaignsQueryKey: () => ['campaigns'],
    setUndoPendingSessions() {},
    setLastTurn(value) { env.visibleLastTurn = value; env.lastTurnRef.current = value; },
    setUndoneJustNow(value) { env.undoneJustNow = value; }, historyToEntries,
    setEntries(value) { env.entries = typeof value === 'function' ? value(env.entries) : value; },
    setMessage(value) { env.message = value; },
    setNotice(value) { env.notice = value; },
    setInFlightSessions() {},
    setCombatEntries() {},
    setCombatEndNotice() {},
    setCombatTargetId() {},
    setConversationTargetId() {},
    setComposerOpen() {},
    getTurnInteractionMetadata: () => ({ interaction_mode: 'do' }),
    // Stubs for the pending-action owner: this suite only needs a fixed action id and no stored pending turn.
    readPending: () => null,
    speciesActionUnresolved: () => false,
    pendingAmbientActionRef: { current: null }, notice: null,
    createIntentKey: (ownerId, campaignId) => ({ ownerId, campaignId, actionId: 'new-action' }),
    resumePending: (key) => ({ key }),
    closePending() {},
    currentAccountOwner: () => 'user-a',
    LOCAL_OWNER: 'local',
    PENDING_TURN_NOTICE: { tone: 'warning', title: 'pending', detail: 'pending' },
    retryPendingTurn() {}, messageRef: { current: '' },
    pendingTurnNotice: () => ({ tone: 'warning', title: 'pending', detail: 'pending', retry() {}, recover: { check() {}, abandon() {} } }),
    currentAuthEpoch: () => 1,
    accountWriteAllowed: () => true,
    statusCode: error => error?.status,
    friendlyError: () => 'Synthetic error',
    mergeCombatHistory: history => history,
    getGameSessionState: async () => {
      statusReadCount += 1;
      return { ...state, revision: 'canonical-after-undo' };
    },
    getCampaign: async () => ({ state, history: [], combat_history: [] }),
    reconcileState: async (_client, _key, _operation, fetcher) => fetcher(),
    TRANSCRIPT_KEY: 'transcript-',
    window: {
      sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
      localStorage: { setItem() {}, getItem: () => null, removeItem() {} },
      crypto: { randomUUID: () => 'new-action' },
    },
    crypto: { randomUUID: () => `undo-action-${++uuidCounter}` },
    ApiError,
    ReconciliationError,
    setTimeout, clearTimeout, AbortController, Promise, JSON,
  };
  vm.runInNewContext(executable, env);
  env.queryClient.setQueryData(['state', 'session-a'], state);
  return { env, undoResponse, retryUndoResponse, turnResponse, undoRequests, turnRequests, statusReadCount: () => statusReadCount };
}

test('undo serializes against new turns and ignores a late response after switching away and back', async () => {
  const h = harness();
  h.env.undo();
  h.env.undo();
  h.env.submit('A newer turn');
  assert.equal(h.turnRequests.length, 0, 'a turn must not be sent while undo is pending');
  assert.equal(h.undoRequests.length, 1, 'rapid repeat click must not send a second undo');

  const newerState = { revision: 'new-session-state', combat: { active: false }, quests: [] };
  h.env.activeSessionRef.current = 'session-b';
  h.env.undoGenerationRef.current += 1;
  h.env.activeSessionRef.current = 'session-a';
  h.env.undoGenerationRef.current += 1;
  h.env.queryClient.setQueryData(['state', 'session-a'], newerState);
  h.env.entries = [{ kind: 'narration', text: 'Newer transcript' }];
  h.env.message = 'draft typed after switching back';
  h.undoResponse.resolve({ state: { revision: 'stale-undo-state' }, narration: 'Stale undo' });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-a']).revision, 'new-session-state');
  assert.deepEqual(h.env.entries, [{ kind: 'narration', text: 'Newer transcript' }]);
  assert.equal(h.env.message, 'draft typed after switching back');
});

test('a late undo result does not replace a newer same-session state, transcript, or draft', async () => {
  const h = harness();
  h.env.undo();
  const newerState = { revision: 'newer-turn', combat: { active: false }, quests: [] };
  const newerHistory = [{ player_message: 'Newer turn', narration: 'Newer turn transcript' }];
  h.env.queryClient.setQueryData(['state', 'session-a'], newerState);
  h.env.getCampaign = async () => ({ state: newerState, history: newerHistory, combat_history: [] });
  h.env.entries = [
    { kind: 'player', text: 'Newer turn' },
    { kind: 'narration', text: 'Newer turn transcript' },
  ];
  h.env.message = 'draft after the new turn';
  h.undoResponse.resolve({ state: { revision: 'stale-undo' }, narration: 'Stale undo' });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-a']).revision, 'newer-turn');
  assert.equal(JSON.stringify(h.env.entries), JSON.stringify([
    { kind: 'player', text: 'Newer turn' },
    { kind: 'narration', text: 'Newer turn transcript' },
  ]));
  assert.equal(h.env.message, 'draft after the new turn');
});

test('failed undo releases its lock and retains the target so the user can retry', async () => {
  const h = harness();
  h.env.undo();
  h.undoResponse.reject(new Error('temporary undo failure'));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.visibleLastTurn?.actionId, 'old-action');
  assert.notEqual(h.env.undoneJustNow, true, 'a failed undo never says the one-step rule');
  h.env.undo();
  assert.equal(h.undoRequests.length, 2);
});

test('lost undo response keeps its action ID and reconciles current campaign state and history on replay', async () => {
  const h = harness();
  h.env.undo();
  const firstActionId = h.undoRequests[0][1].action_id;
  h.undoResponse.reject(new TypeError('fetch failed after server commit'));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  const canonicalRevision = h.env.queryClient.getQueryData(['state', 'session-a'])?.revision;
  const currentState = { revision: 'other-tab-new-turn', combat: { active: false }, quests: [] };
  const currentHistory = [{
    player_message: 'Other tab: yeni hamle',
    narration: 'Güncel kampanya geçmişi',
    skill_check_result: null,
  }];
  h.env.queryClient.setQueryData(['state', 'session-a'], currentState);
  h.env.message = 'Keep this unsent draft';
  h.env.undo();
  const retryActionId = h.undoRequests[1]?.[1].action_id;
  assert.equal(h.statusReadCount(), 1, 'transport ambiguity must trigger an authoritative state read');
  assert.equal(canonicalRevision, 'canonical-after-undo');
  assert.equal(retryActionId, firstActionId, 'retry must reuse the logical undo action ID');
  h.env.getCampaign = async () => ({ state: currentState, history: currentHistory, combat_history: [] });
  h.retryUndoResponse.resolve({
    state: { revision: 'historical-undo-receipt', combat: { active: false }, quests: [] },
    narration: 'Historical receipt narration',
  });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-a']).revision, 'other-tab-new-turn');
  assert.equal(Array.from(h.env.entries, entry => entry.text).join('|'), 'Other tab: yeni hamle|Güncel kampanya geçmişi');
  assert.equal(h.env.message, 'Keep this unsent draft');
  assert.equal(h.env.lastTurnRef.current, null);
  assert.equal(h.env.undoneJustNow, true, 'a committed undo says the one-step rule until the next turn');
  assert.equal(h.env.undoRequestsRef.current.has('session-a'), false);
});

test('A undo can be recovered after B completes a move without changing B state', async () => {
  const h = harness();
  h.env.undo();
  const firstId = h.undoRequests[0][1].action_id;
  h.undoResponse.reject(new TypeError('lost A undo response'));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.undoRequestsRef.current.has('session-a'), true);

  const bState = { revision: 'b-before', combat: { active: false }, quests: [] };
  h.env.sessionId = 'session-b';
  h.env.campaignId = '';
  h.env.undoScope = ':session-b';
  h.env.undoScopeRef.current = h.env.undoScope;
  h.env.undoGenerationRef.current += 1;
  h.env.activeSessionRef.current = 'session-b';
  h.env.visibleLastTurn = null;
  h.env.state = bState;
  h.env.getGameSessionState = async () => bState;
  h.env.queryClient.setQueryData(['state', 'session-b'], bState);
  h.env.submit('B completed move');
  h.turnResponse.resolve({ state: bState, narration: 'B move completed' });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.lastTurnRef.current.sessionId, 'session-b');

  h.env.sessionId = 'session-a';
  h.env.campaignId = 'campaign-a';
  h.env.undoScope = 'campaign-a:session-a';
  h.env.undoScopeRef.current = h.env.undoScope;
  h.env.undoGenerationRef.current += 1;
  h.env.activeSessionRef.current = 'session-a';
  h.env.visibleLastTurn = null;
  h.env.submit('A must remain locked');
  assert.equal(h.turnRequests.length, 1);
  h.env.undo();
  assert.equal(h.undoRequests.length, 2);
  assert.equal(h.undoRequests[1][1].action_id, firstId);
  h.retryUndoResponse.resolve({
    state: { revision: 'a-recovered', combat: { active: false }, quests: [] },
    narration: 'A recovered',
  });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-b']).revision, 'b-before');
  assert.equal(h.env.lastTurnRef.current.sessionId, 'session-b');
});

test('ambiguous undo with a failed state read still blocks turns and preserves the draft', async () => {
  const h = harness();
  h.env.getGameSessionState = async () => { throw new TypeError('state endpoint unavailable'); };
  h.env.undo();
  h.undoResponse.reject(new TypeError('fetch failed after server commit'));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  h.env.submit('Do not race the unresolved undo');
  assert.equal(h.turnRequests.length, 0);
  assert.equal(h.env.message, 'draft before');
  assert.equal(h.env.undoRequestsRef.current.has('session-a'), true);
  h.env.undo();
  assert.equal(h.undoRequests[1][1].action_id, h.undoRequests[0][1].action_id);
  h.retryUndoResponse.resolve({
    state: { revision: 'recovered-after-retry', combat: { active: false }, quests: [] },
    narration: 'Undo recovered',
  });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.undoRequestsRef.current.has('session-a'), false);
  assert.equal(h.env.lastTurnRef.current, null);
});

test('definitive HTTP rejection releases the uncertain action so a later attempt is new', async () => {
  const h = harness();
  h.env.undo();
  h.undoResponse.reject(new ApiError(409));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  h.env.undo();
  assert.notEqual(h.undoRequests[1]?.[1].action_id, h.undoRequests[0][1].action_id);
});

test('a delayed canonical status read from the old campaign cannot overwrite the new session', async () => {
  const h = harness();
  const statusResponse = deferred();
  h.env.getGameSessionState = () => statusResponse.promise;
  h.env.undo();
  h.undoResponse.reject(new TypeError('transport lost after commit'));
  await new Promise(resolve => setImmediate(resolve));

  const newSessionState = { revision: 'session-b-state', combat: { active: false }, quests: [] };
  h.env.sessionId = 'session-b';
  h.env.campaignId = 'campaign-b';
  h.env.undoScope = 'campaign-b:session-b';
  h.env.undoScopeRef.current = h.env.undoScope;
  h.env.undoGenerationRef.current += 1;
  h.env.activeSessionRef.current = 'session-b';
  h.env.queryClient.setQueryData(['state', 'session-b'], newSessionState);
  h.env.entries = [{ kind: 'narration', text: 'Session B transcript' }];
  h.env.message = 'Session B draft';
  h.env.submit('Session B turn');
  assert.equal(h.turnRequests.length, 1, 'an unresolved undo for A must not block campaign B');

  statusResponse.resolve({ revision: 'stale-session-a-status', combat: { active: false }, quests: [] });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-b']).revision, 'session-b-state');
  assert.deepEqual(h.env.entries, [{ kind: 'narration', text: 'Session B transcript' }]);
  assert.equal(h.env.message, 'Session B draft');
});

test('a delayed status read cannot overwrite a newer same-session state or draft', async () => {
  const h = harness();
  const statusResponse = deferred();
  h.env.getGameSessionState = () => statusResponse.promise;
  h.env.undo();
  h.undoResponse.reject(new TypeError('transport lost after commit'));
  await new Promise(resolve => setImmediate(resolve));

  h.env.queryClient.setQueryData(['state', 'session-a'], {
    revision: 'newer-session-state', combat: { active: false }, quests: [],
  });
  h.env.entries = [{ kind: 'narration', text: 'Newer transcript' }];
  h.env.message = 'newer draft';
  statusResponse.resolve({ revision: 'stale-status', combat: { active: false }, quests: [] });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(h.env.queryClient.getQueryData(['state', 'session-a']).revision, 'newer-session-state');
  assert.deepEqual(h.env.entries, [{ kind: 'narration', text: 'Newer transcript' }]);
  assert.equal(h.env.message, 'newer draft');
  assert.equal(h.env.undoRequestsRef.current.has('session-a'), true);
});

test('undo is blocked while a move is unresolved and sends no request', async () => {
  const h = harness();
  h.env.readPending = () => ({ key: { ownerId: 'user-a', campaignId: 'campaign-a', actionId: 'uncertain-move' }, request: {} });
  const notices = [];
  h.env.setNotice = (value) => { notices.push(value); };
  h.env.undo();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.undoRequests.length, 0, 'an unresolved move may still commit; undo must not run around it');
  assert.equal(notices.at(-1).title, 'pending');
  h.env.readPending = () => null;
  h.env.undo();
  assert.equal(h.undoRequests.length, 1, 'with nothing unresolved the same undo goes out');
});
