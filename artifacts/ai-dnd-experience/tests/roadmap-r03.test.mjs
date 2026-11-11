// R03: one freshness gate for every response that wants to write the visible game state.
// Order is the client-observed order (a read is as old as the moment it was issued, a mutation as old as the
// moment its reply arrived); the server exposes no state revision to the page yet.
import assert from 'node:assert/strict';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { reconcileState, ReconciliationError } from '../src/lib/action-reconciliation.ts';
import * as gate from '../src/lib/state-envelope.ts';

const KEY = ['game', 'session', 's1'];
const WHO = { ownerId: 'owner-a', campaignId: 'c1', epoch: 1 };
const stateOf = (hp, label) => ({ character: { hp }, label });
const hpOf = (client) => client.getQueryData(KEY)?.character.hp;

function harness() {
  const client = new QueryClient();
  let refetches = 0;
  client.invalidateQueries = () => { refetches += 1; return Promise.resolve(); };
  return { client, refetches: () => refetches };
}

test('test_stale_response_cannot_regress_view', () => {
  const { client, refetches } = harness();
  const ambientIssued = gate.nextRevision();
  const turnIssued = gate.nextRevision();
  assert.equal(gate.applyState(client, KEY, WHO, turnIssued, stateOf(5, 'turn')), true);
  const stale = gate.applyState(client, KEY, WHO, ambientIssued, stateOf(9, 'ambient-old'));
  assert.equal(stale, false);
  assert.equal(hpOf(client), 5);
  assert.equal(refetches(), 1, 'a rejected response starts an authoritative refetch instead of keeping blind old cache');
  const newer = gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(3, 'undo'));
  assert.equal(newer, true);
  assert.equal(hpOf(client), 3);
});

test('same revision with the wrong owner, campaign or epoch is refused by the predicate', () => {
  const current = { ...WHO, revision: 7 };
  assert.equal(gate.mayApplyState(current, { ...WHO, revision: 7 }), true);
  assert.equal(gate.mayApplyState(current, { ...WHO, ownerId: 'owner-b', revision: 7 }), false);
  assert.equal(gate.mayApplyState(current, { ...WHO, campaignId: 'c2', revision: 7 }), false);
  assert.equal(gate.mayApplyState(current, { ...WHO, epoch: 2, revision: 7 }), false);
  assert.equal(gate.mayApplyState(current, { ...WHO, revision: 6 }), false);
  assert.equal(gate.mayApplyState(current, { ...WHO, revision: 8 }), true);
});

test('a response for another campaign never lands in this view, even with a newer revision', () => {
  const { client } = harness();
  assert.equal(gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(5, 'mine')), true);
  const wrong = gate.applyState(client, KEY, { ...WHO, campaignId: 'c2' }, gate.nextRevision(), stateOf(1, 'other campaign'));
  assert.equal(wrong, false);
  assert.equal(hpOf(client), 5);
});

test('a late callback whose operation is no longer current writes nothing', () => {
  const { client } = harness();
  let current = true;
  const issued = gate.nextRevision();
  current = false;
  assert.equal(gate.applyState(client, KEY, WHO, issued, stateOf(4, 'late'), { isCurrent: () => current }), false);
  assert.equal(client.getQueryData(KEY), undefined);
});

test('a rejected older response never blocks the later authoritative refetch', () => {
  const { client } = harness();
  const old = gate.nextRevision();
  assert.equal(gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(5, 'a')), true);
  assert.equal(gate.applyState(client, KEY, WHO, old, stateOf(8, 'older')), false);
  assert.equal(gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(5, 'refetched')), true);
});

test('random reply order: the view always ends on the newest authoritative response', () => {
  let seed = 12345;
  const random = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  for (let round = 0; round < 200; round += 1) {
    const { client } = harness();
    const responses = Array.from({ length: 2 + Math.floor(random() * 6) }, (_, index) => ({
      revision: gate.nextRevision(), state: stateOf(index + 1, `r${index}`),
    }));
    const newest = responses[responses.length - 1];
    const order = [...responses].sort(() => random() - 0.5);
    for (const response of order) gate.applyState(client, KEY, WHO, response.revision, response.state);
    assert.equal(hpOf(client), newest.state.character.hp, `round ${round}`);
    assert.equal(client.getQueryData(KEY).label, newest.state.label);
  }
});

test('the query cache path (structural sharing) refuses an older fetch result and keeps the newer state', async () => {
  const { client, refetches } = harness();
  const read = gate.gatedStateRead(WHO);
  const sharing = gate.stateStructuralSharing(client, KEY);
  const olderFetch = await read(async () => stateOf(9, 'older fetch'));
  gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(5, 'mutation reply'));
  const kept = sharing(client.getQueryData(KEY), olderFetch);
  assert.equal(kept.character.hp, 5);
  await Promise.resolve();
  assert.equal(refetches(), 1);
  const newerFetch = await read(async () => stateOf(6, 'newer fetch'));
  assert.equal(sharing(client.getQueryData(KEY), newerFetch).character.hp, 6);
});

// Every writer of the visible state goes through the gate: no component may call setQueryData on a state key.
test('no mutation path writes the game state cache without the gate', () => {
  for (const file of ['../src/pages/game-browser.tsx', '../src/components/species-trait-controls.tsx', '../src/components/death-recovery-controls.tsx']) {
    const source = file === '../src/pages/game-browser.tsx' ? readGameBrowserSource() : readFileSync(new URL(file, import.meta.url), 'utf8');
    assert.ok(!/queryClient\.setQueryData\(/.test(source), `${file} still writes the cache directly`);
  }
  const browser = readGameBrowserSource();
  const uses = browser.match(/applyGameState\(/g) ?? [];
  assert.ok(uses.length >= 8, `expected the quest, ambient, turn, undo, create and resume paths to use the gate, found ${uses.length}`);
  assert.match(browser, /stateStructuralSharing\(/);
  const species = readFileSync(new URL('../src/components/species-trait-controls.tsx', import.meta.url), 'utf8');
  assert.match(species, /applyGameState\(/);
  // The death wait only invalidates; that refetch lands through the gated state query asserted above.
});

test('a mutation reply is as old as its issue: a turn applied meanwhile is not overwritten by it', () => {
  const { client, refetches } = harness();
  const issued = gate.nextRevision(); // ambient/quest command sent
  const turnRead = gate.nextRevision(); // a turn read is issued after it
  assert.equal(gate.applyState(client, KEY, WHO, turnRead, stateOf(5, 'turn')), true);
  assert.equal(gate.applyState(client, KEY, WHO, issued, stateOf(9, 'late ambient reply')), false);
  assert.equal(hpOf(client), 5);
  assert.equal(refetches(), 1);
});

test('production mutation paths stamp the reply at issue time, not at arrival', () => {
  const browser = readGameBrowserSource();
  assert.equal((browser.match(/onMutate: \(\) => \(\{ issued: nextRevision\(\) \}\)/g) ?? []).length, 2);
  assert.match(browser, /revision: context\?\.issued/);
  assert.match(browser, /const issued = nextRevision\(\);\s+resolveAmbientEventAction\.mutate\(/);
  assert.match(browser, /response\.state, \{ revision: issued \}/);
});

test('an identity change (owner reseated) is healed by the next read instead of refusing forever', async () => {
  const { client, refetches } = harness();
  const sharing = gate.stateStructuralSharing(client, KEY);
  const first = await gate.gatedStateRead(WHO)(async () => stateOf(5, 'as local'));
  sharing(undefined, first);
  const resolvedOwner = { ...WHO, ownerId: 'owner-b' };
  const next = await gate.gatedStateRead(resolvedOwner)(async () => stateOf(6, 'as resolved owner'));
  assert.equal(sharing(first, next).character.hp, 6);
  assert.equal(refetches(), 0);
});

test('applyState reports false when the account client dropped the write', () => {
  const client = new QueryClient();
  client.invalidateQueries = () => Promise.resolve();
  client.setQueryData = () => undefined;
  assert.equal(gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(1, 'dropped')), false);
});

// Death-wait success only invalidates the state query (death-recovery-controls.tsx). That refetch is a real react-query
// fetch on the mounted query, so it must land through the same gate as every other response.
test('death-wait path: an invalidate refetch that was issued before a newer mutation cannot regress the view', async () => {
  const client = new QueryClient();
  const slow = { release: () => {} };
  const server = { hp: 12 };
  const samples = [];
  let calls = 0;
  const observer = new QueryObserver(client, {
    queryKey: KEY,
    structuralSharing: gate.stateStructuralSharing(client, KEY),
    queryFn: () => gate.gatedStateRead(WHO)(async () => {
      calls += 1;
      const frozen = server.hp; // the server answers with the world as it was when it processed the read
      if (calls === 2) await new Promise((resolve) => { slow.release = resolve; });
      return stateOf(frozen, `fetch-${calls}`);
    }),
  });
  const unsubscribe = observer.subscribe(() => samples.push(hpOf(client)));
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(hpOf(client), 12);
  const refetch = client.invalidateQueries({ queryKey: KEY }); // what the death wait does on success
  await new Promise((resolve) => setTimeout(resolve, 20));
  server.hp = 7;
  assert.equal(gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(7, 'newer mutation')), true);
  slow.release();
  await refetch;
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(hpOf(client), 7, 'the older refetch result must not overwrite the newer mutation state');
  assert.ok(!samples.slice(samples.lastIndexOf(7)).includes(12), 'the old value never reappears after the newer one');
  assert.ok(calls <= 3, `bounded refetching, saw ${calls} reads`);
  unsubscribe();
  client.clear();
});

// A refused background read still bumps dataUpdateCount. reconcileState reads that as "something else wrote": it must
// never turn that into success, and it stops after its bounded attempts (so a pending action is not closed by it).
test('a refused read that bumps dataUpdateCount only causes bounded retries and never counts as reconciliation', async () => {
  const client = new QueryClient();
  const observer = new QueryObserver(client, {
    queryKey: KEY, structuralSharing: gate.stateStructuralSharing(client, KEY),
    queryFn: () => gate.gatedStateRead(WHO)(async () => stateOf(1, 'seed')),
  });
  const unsubscribe = observer.subscribe(() => {});
  await new Promise((resolve) => setTimeout(resolve, 20));
  const operation = { signal: new AbortController().signal, isCurrent: () => true, close() {} };
  let reads = 0;
  const outcome = await reconcileState(client, KEY, operation, async () => {
    reads += 1;
    // During the authoritative read a stale background fetch is refused by the gate; the cache still counts an update.
    const stale = await gate.gatedStateRead(WHO)(async () => stateOf(0, 'stale'));
    gate.applyState(client, KEY, WHO, gate.nextRevision(), stateOf(5, 'newer'));
    observer.getCurrentQuery().setData(stale);
    return stateOf(5, 'read');
  }).then(() => 'resolved', (error) => error);
  assert.ok(outcome instanceof ReconciliationError, 'a changing cache must not be reported as reconciled');
  assert.equal(reads, 3, 'bounded: exactly the three allowed reads');
  unsubscribe();
  client.clear();
});

test('an older read from another identity cannot reseat the view or overwrite the newer state', async () => {
  const { client, refetches } = harness();
  const sharing = gate.stateStructuralSharing(client, KEY);
  const oldForeign = await gate.gatedStateRead({ ...WHO, ownerId: 'owner-old' })(async () => stateOf(9, 'old owner read'));
  const current = await gate.gatedStateRead(WHO)(async () => stateOf(5, 'current owner read'));
  const kept = sharing(undefined, current);
  const result = sharing(kept, oldForeign);
  assert.equal(result.character.hp, 5);
  await Promise.resolve();
  assert.equal(refetches(), 1);
  const next = await gate.gatedStateRead(WHO)(async () => stateOf(4, 'fresh read'));
  assert.equal(sharing(result, next).character.hp, 4, 'the view was not reseated to the older identity');
});
