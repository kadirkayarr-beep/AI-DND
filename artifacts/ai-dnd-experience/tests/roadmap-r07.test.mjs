// R07: one absolute monotonic deadline per action. Token read, mutation, undo and reconciliation draw from the SAME
// budget; hanging at any step is bounded; an expired deadline is an UNKNOWN outcome (draft and ActionKey stay, no automatic
// new action), and a late commit cannot create a second effect. The number is a technical default, not a performance target.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { QueryClient } from '@tanstack/react-query';
import { setAuthTokenGetter, customFetch } from '@workspace/api-client-react/custom-fetch';
import * as deadline from '../src/lib/action-deadline.ts';
import { reconcileState, ReconciliationError } from '../src/lib/action-reconciliation.ts';

// A hand-driven clock and timer queue: no real waiting, exact boundaries.
function fakeTime(start = 1000) {
  let current = start;
  const timers = [];
  return {
    now: () => current,
    setTimer: (callback, ms) => { const timer = { at: current + ms, callback, cleared: false }; timers.push(timer); return timer; },
    clearTimer: (timer) => { if (timer) timer.cleared = true; },
    advance(ms) {
      current += ms;
      for (const timer of timers.filter((item) => !item.cleared && item.at <= current)) { timer.cleared = true; timer.callback(); }
    },
  };
}

test('remainingMs is budget arithmetic that never goes negative', () => {
  assert.equal(deadline.remainingMs(1000 + 45000, 1000), 45000);
  assert.equal(deadline.remainingMs(1000 + 45000, 1000 + 44999), 1);
  assert.equal(deadline.remainingMs(1000 + 45000, 1000 + 45000), 0);
  assert.equal(deadline.remainingMs(1000 + 45000, 1000 + 99999), 0);
});

test('the default is a technical starting value, not a promise', () => {
  assert.equal(deadline.DEFAULT_ACTION_DEADLINE_MS, 45000);
  const source = readFileSync(new URL('../src/lib/action-deadline.ts', import.meta.url), 'utf8');
  assert.match(source, /not a performance target|technical default/i);
});

test('44999 ms is inside the budget and 45000 ms is the boundary that cancels', async () => {
  const time = fakeTime();
  const until = deadline.startDeadline(deadline.DEFAULT_ACTION_DEADLINE_MS, time);
  let settled = 'pending';
  const run = deadline.runWithDeadline(until, () => new Promise(() => {}), time).then(() => { settled = 'ok'; }, (error) => { settled = error; });
  time.advance(44999);
  await Promise.resolve();
  assert.equal(settled, 'pending', 'one millisecond is still left');
  time.advance(1);
  await run;
  assert.ok(settled instanceof deadline.ActionDeadlineError);
  assert.equal(settled.outcome, 'unknown');
});

test('a transport that ignores the abort signal is still bounded, and its late reply is dropped', async () => {
  const time = fakeTime();
  const until = deadline.startDeadline(1000, time);
  let late;
  let observedSignal;
  const run = deadline.runWithDeadline(until, (signal) => {
    observedSignal = signal;
    return new Promise((resolve) => { late = resolve; }); // never listens to the signal
  }, time);
  time.advance(1000);
  await assert.rejects(run, deadline.ActionDeadlineError);
  assert.equal(observedSignal.aborted, true, 'the work was told to stop');
  late('late commit reply');
  await Promise.resolve();
  // The rejection above is final: the caller never receives the late reply, so it cannot apply it (no second effect).
  await assert.rejects(run, deadline.ActionDeadlineError);
});

test('a step that retries inside the action never resets the total clock', () => {
  const time = fakeTime();
  const until = deadline.startDeadline(10000, time);
  time.advance(9000);
  assert.equal(deadline.remainingMs(until, time.now()), 1000);
  // The next sub-step (e.g. a reconciliation read) may be given at most what is left, never a fresh budget.
  assert.equal(deadline.stepBudgetMs(until, time.now(), 8000), 1000);
  time.advance(900);
  assert.equal(deadline.stepBudgetMs(until, time.now(), 8000), 100);
  assert.equal(deadline.stepBudgetMs(until, time.now() + 5000, 8000), 0);
});

test('token read, mutation, undo and reconciliation each hang separately and each is bounded by the same total', async () => {
  for (const hangingStep of ['token', 'mutation', 'undo', 'reconciliation']) {
    const time = fakeTime();
    const until = deadline.startDeadline(deadline.DEFAULT_ACTION_DEADLINE_MS, time);
    const steps = [];
    const run = deadline.runWithDeadline(until, async () => {
      for (const step of ['token', 'mutation', 'undo', 'reconciliation']) {
        steps.push(step);
        if (step === hangingStep) await new Promise(() => {});
        time.advance(100); // a healthy step spends a little of the shared budget
      }
    }, time);
    await Promise.resolve();
    time.advance(deadline.DEFAULT_ACTION_DEADLINE_MS);
    await assert.rejects(run, deadline.ActionDeadlineError, hangingStep);
    assert.equal(steps.at(-1), hangingStep, `${hangingStep} was where it hung`);
  }
});

test('customFetch: a token read that never answers is released by the deadline signal', async () => {
  setAuthTokenGetter(() => new Promise(() => {}));
  const controller = new AbortController();
  const pending = customFetch('/api/game/sessions/x/state', { method: 'GET', signal: controller.signal });
  setTimeout(() => controller.abort(), 20);
  const outcome = await Promise.race([
    pending.then(() => 'resolved', (error) => error?.name ?? 'rejected'),
    new Promise((resolve) => setTimeout(() => resolve('still hanging'), 1500)),
  ]);
  setAuthTokenGetter(null);
  assert.notEqual(outcome, 'still hanging', 'the abort signal must also release a hanging token read');
});

test('reconcileState is capped by what is left of the shared deadline', async () => {
  const client = new QueryClient();
  const until = deadline.startDeadline(150);
  const operation = deadline.withActionDeadline({ signal: new AbortController().signal, isCurrent: () => true, close() {} }, until);
  const started = Date.now();
  const outcome = await reconcileState(client, ['k'], operation, () => new Promise(() => {}), deadline.stepBudgetMs(until, deadline.monotonicNow(), 8000))
    .then(() => 'resolved', (error) => error);
  assert.ok(outcome instanceof ReconciliationError);
  assert.ok(Date.now() - started < 2000, 'bounded by the remaining budget, not the 8000 ms step default');
});

test('production paths draw one deadline and keep the draft and ActionKey on expiry', () => {
  const browser = readFileSync(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
  assert.ok((browser.match(/startDeadline\(/g) ?? []).length >= 2, 'turn and undo each start one deadline');
  assert.ok((browser.match(/withActionDeadline\(/g) ?? []).length >= 2, 'the deadline travels in the operation');
  assert.match(browser, /ActionDeadlineError/, 'expiry is a typed, unknown outcome');
  assert.doesNotMatch(browser, /setTimeout\([^)]*submitTurn/, 'an expired deadline never schedules a new action');
});

// The production primitive (submitTurn and undo use withActionDeadline, not runWithDeadline).
test('withActionDeadline: 44999 ms leaves the operation alive and 45000 ms aborts it and records that the deadline fired', () => {
  const time = fakeTime();
  const until = deadline.startDeadline(deadline.DEFAULT_ACTION_DEADLINE_MS, time);
  const owner = new AbortController();
  let closed = 0;
  const operation = deadline.withActionDeadline({ signal: owner.signal, isCurrent: () => true, close: () => { closed += 1; } }, until, time);
  time.advance(44999);
  assert.equal(operation.signal.aborted, false, 'one millisecond is still left');
  assert.equal(operation.deadlineExpired(), false);
  time.advance(1);
  assert.equal(operation.signal.aborted, true);
  assert.equal(operation.deadlineExpired(), true, 'the timer itself records expiry; no clock arithmetic is re-derived');
  operation.close();
  assert.equal(closed, 1, 'closing still closes the owning operation');
});

test('withActionDeadline: an owner abort is not mistaken for the deadline', () => {
  const time = fakeTime();
  const owner = new AbortController();
  const operation = deadline.withActionDeadline({ signal: owner.signal, isCurrent: () => true, close() {} }, deadline.startDeadline(45000, time), time);
  time.advance(1000);
  owner.abort();
  assert.equal(operation.signal.aborted, true);
  assert.equal(operation.deadlineExpired(), false);
});
