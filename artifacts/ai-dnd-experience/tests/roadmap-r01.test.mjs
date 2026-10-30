// R01: a verified same-owner reload keeps the pending action; an unverified or different owner never sees it.
// Synthetic storage and a stub window only: no browser, no Clerk, no network.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, test } from 'node:test';
import { currentAuthEpoch, setAuthTokenGetter, setProtectedRequestCredentials } from '@workspace/api-client-react/custom-fetch';
import * as account from '../src/lib/account-session.ts';
import { clearPendingTurnAction, stableTurnActionId, storedTurnContext } from '../src/lib/action-reconciliation.ts';

const originalWindow = globalThis.window;
const SCOPE = 'campaign-1';
const COMBAT = { combat_id: 'combat-1', combat_round: 2, combat_turn_index: 1 };

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    get length() { return map.size; },
    key(index) { return [...map.keys()][index] ?? null; },
    getItem(key) { return map.has(key) ? map.get(key) : null; },
    setItem(key, value) { map.set(String(key), String(value)); },
    removeItem(key) { map.delete(key); },
    entries() { return [...map.entries()]; },
  };
}

// One browser tab: both stores survive a "reload"; module and React state do not.
function browser() {
  const localStorage = memoryStorage();
  const sessionStorage = memoryStorage();
  globalThis.window = { location: { origin: 'http://127.0.0.1:5173' }, localStorage, sessionStorage, crypto: globalThis.crypto };
  return { localStorage, sessionStorage };
}

function accountEntries(tab) {
  return [...tab.localStorage.entries(), ...tab.sessionStorage.entries()]
    .filter(([key]) => account.isAccountScopedStorageKey(key));
}

function seedAction(tab, identity) {
  const boundary = account.nextAccountClient(null, identity);
  const actionId = stableTurnActionId(SCOPE, 'walk to the gate', COMBAT);
  tab.localStorage.setItem('ai-dnd-transcript-campaign-1', 'once upon a time');
  tab.localStorage.setItem('ai-dnd-last-selected-campaign-id', SCOPE);
  return { boundary, actionId };
}

afterEach(() => {
  setAuthTokenGetter(null);
  setProtectedRequestCredentials('omit');
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

test('classifyOwnerTransition separates unresolved, same and changed owners', () => {
  const classify = account.classifyOwnerTransition;
  assert.equal(typeof classify, 'function');
  assert.equal(classify('user-a', null), 'unresolved');
  assert.equal(classify(null, null), 'unresolved');
  assert.equal(classify('user-a', ''), 'unresolved');
  assert.equal(classify('user-a', 'user-a'), 'same');
  assert.equal(classify('user-a', 'user-b'), 'changed');
  // Stored data with no recorded owner cannot be verified, so it is never "same".
  assert.equal(classify(null, 'user-a'), 'changed');
});

test('test_same_owner_mount_preserves_pending', () => {
  const tab = browser();
  const { actionId: sameOwnerBefore } = seedAction(tab, 'user-a:sess-1');
  assert.equal(storedTurnContext(SCOPE, sameOwnerBefore).combat_id, 'combat-1');

  // Reload: fresh module state, same stores, same verified owner and campaign.
  account.nextAccountClient(null, 'user-a:sess-1');
  const sameOwnerAfter = stableTurnActionId(SCOPE, 'walk to the gate', COMBAT);
  assert.equal(sameOwnerAfter, sameOwnerBefore);
  assert.deepEqual(storedTurnContext(SCOPE, sameOwnerBefore), COMBAT);
  assert.equal(tab.localStorage.getItem('ai-dnd-transcript-campaign-1'), 'once upon a time');
  assert.equal(tab.localStorage.getItem('ai-dnd-last-selected-campaign-id'), SCOPE);
});

test('token expiry on the same owner does not mint a new action id', () => {
  const tab = browser();
  const { boundary, actionId } = seedAction(tab, 'user-a:sess-1');
  const reloaded = account.nextAccountClient(null, 'user-a:sess-2');
  assert.equal(stableTurnActionId(SCOPE, 'walk to the gate', COMBAT), actionId);
  const rotated = account.nextAccountClient(boundary, 'user-a:sess-3');
  assert.equal(stableTurnActionId(SCOPE, 'walk to the gate', COMBAT), actionId);
  assert.notEqual(reloaded.client, rotated.client);
});

test('a different owner never sees the old draft or pending action', () => {
  const tab = browser();
  const { actionId } = seedAction(tab, 'user-a:sess-1');
  account.nextAccountClient(null, 'user-b:sess-9');
  assert.deepEqual(accountEntries(tab), []);
  const next = stableTurnActionId(SCOPE, 'walk to the gate', COMBAT);
  assert.notEqual(next, actionId);
  assert.deepEqual(storedTurnContext(SCOPE, actionId), {});
});

test('a running boundary that changes owner clears storage and keeps epoch isolation', () => {
  const tab = browser();
  const { boundary, actionId } = seedAction(tab, 'user-a:sess-1');
  const epoch = currentAuthEpoch();
  const oldClient = boundary.client;
  const next = account.nextAccountClient(boundary, 'user-b:sess-2');
  assert.notEqual(currentAuthEpoch(), epoch);
  assert.equal(account.accountWriteAllowed(epoch), false);
  oldClient.setQueryData(['late-write'], 'stale');
  assert.equal(oldClient.getQueryData(['late-write']), undefined);
  assert.notEqual(next.client, oldClient);
  assert.notEqual(stableTurnActionId(SCOPE, 'walk to the gate', COMBAT), actionId);
});

test('stored data without a verified owner is cleared instead of recovered', () => {
  const tab = browser();
  // Entries from an older build: account-scoped keys but no owner record at all.
  tab.sessionStorage.setItem(`ai-dnd-pending-turns:${SCOPE}`, '{"x":"legacy-action"}');
  tab.sessionStorage.setItem(`ai-dnd-turn-context:${SCOPE}:legacy-action`, '{}');
  tab.localStorage.setItem('ai-dnd-transcript-campaign-1', 'unowned');
  account.nextAccountClient(null, 'user-a:sess-1');
  assert.deepEqual(accountEntries(tab), []);
});

test('an unresolved identity touches nothing and the gate keeps content hidden', async () => {
  const tab = browser();
  const { actionId } = seedAction(tab, 'user-a:sess-1');
  const before = JSON.stringify([...tab.localStorage.entries(), ...tab.sessionStorage.entries()]);
  assert.equal(account.clerkSessionIdentity({ isLoaded: false, isSignedIn: true, userId: 'user-a', sessionId: 'sess-1' }), '');
  assert.equal(account.clerkSessionIdentity({ isLoaded: true, isSignedIn: true, userId: 'user-a', sessionId: null }), '');
  // Clerk still loading: the session component must not mount children or clear anything.
  const gate = await readFile(new URL('../src/components/clerk-api-session.tsx', import.meta.url), 'utf8');
  assert.match(gate, /if \(!identity \|\| !activeClient\) return <GateWaiting \/>/);
  assert.equal(JSON.stringify([...tab.localStorage.entries(), ...tab.sessionStorage.entries()]), before);
  // Once the same owner resolves, the pending action is still there.
  account.nextAccountClient(null, 'user-a:sess-1');
  assert.equal(stableTurnActionId(SCOPE, 'walk to the gate', COMBAT), actionId);
});

test('the owner record holds no session id or token', () => {
  const tab = browser();
  seedAction(tab, 'user-a:sess-secret');
  for (const [, value] of [...tab.localStorage.entries(), ...tab.sessionStorage.entries()]) {
    assert.equal(String(value).includes('sess-secret'), false);
  }
  clearPendingTurnAction(SCOPE, 'anything');
});
