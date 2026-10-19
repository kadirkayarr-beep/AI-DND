import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const source = await readFile(process.env.AI_DND_TEST_SOURCE ?? new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
function declaration(name) {
  return component.body.statements.find(n => ts.isVariableStatement(n)
    && n.declarationList.declarations.some(d => d.name.getText(ast) === name));
}
const undoCode = declaration('undoLastTurn');
const submitCode = declaration('submitTurn');
assert.ok(undoCode);
assert.ok(submitCode);
const executable = ts.transpileModule([
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

function harness() {
  const undoResponse = deferred();
  const turnResponse = deferred();
  const undoRequests = [];
  const turnRequests = [];
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
    turnLifetime: { begin: () => ({ signal: new AbortController().signal, isCurrent: () => true, close() {} }) },
    state, entries: [{ kind: 'narration', text: 'Before' }], message: 'draft before',
    undoGameTurn: (...args) => { undoRequests.push(args); return undoResponse.promise; },
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
    getGetGameSessionStateQueryKey: id => ['state', id],
    getGetCampaignsQueryKey: () => ['campaigns'],
    setUndoPendingSessions() {},
    setLastTurn(value) { env.visibleLastTurn = value; env.lastTurnRef.current = value; },
    setEntries(value) { env.entries = typeof value === 'function' ? value(env.entries) : value; },
    setMessage(value) { env.message = value; },
    setNotice(value) { env.notice = value; },
    setInFlightSessions() {},
    setCombatEntries() {},
    setCombatEndNotice() {},
    setCombatTargetId() {},
    setConversationTargetId() {},
    getTurnInteractionMetadata: () => ({ interaction_mode: 'do' }),
    stableTurnActionId: () => 'new-action',
    storedTurnContext: () => ({}),
    clearPendingTurnAction() {},
    currentAuthEpoch: () => 1,
    accountWriteAllowed: () => true,
    statusCode: error => error?.status,
    friendlyError: () => 'Synthetic error',
    mergeCombatHistory: history => history,
    getGameSessionState: async () => ({ ...state, revision: 'after-turn' }),
    getCampaign: async () => ({ state, history: [], combat_history: [] }),
    TRANSCRIPT_KEY: 'transcript-',
    window: {
      sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
      localStorage: { setItem() {}, getItem: () => null, removeItem() {} },
      crypto: { randomUUID: () => 'new-action' },
    },
    crypto: { randomUUID: () => 'undo-action' },
    setTimeout, clearTimeout, AbortController, Promise, JSON,
  };
  vm.runInNewContext(executable, env);
  env.queryClient.setQueryData(['state', 'session-a'], state);
  return { env, undoResponse, turnResponse, undoRequests, turnRequests };
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
  h.env.queryClient.setQueryData(['state', 'session-a'], {
    revision: 'newer-turn', combat: { active: false }, quests: [],
  });
  h.env.entries = [{ kind: 'narration', text: 'Newer turn transcript' }];
  h.env.message = 'draft after the new turn';
  h.undoResponse.resolve({ state: { revision: 'stale-undo' }, narration: 'Stale undo' });
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.queryClient.getQueryData(['state', 'session-a']).revision, 'newer-turn');
  assert.deepEqual(h.env.entries, [{ kind: 'narration', text: 'Newer turn transcript' }]);
  assert.equal(h.env.message, 'draft after the new turn');
});

test('failed undo releases its lock and retains the target so the user can retry', async () => {
  const h = harness();
  h.env.undo();
  h.undoResponse.reject(new Error('temporary undo failure'));
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.env.visibleLastTurn?.actionId, 'old-action');
  h.env.undo();
  assert.equal(h.undoRequests.length, 2);
});
