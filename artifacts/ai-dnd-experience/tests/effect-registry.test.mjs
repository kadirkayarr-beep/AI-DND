import assert from 'node:assert/strict';
import test from 'node:test';
import {
  MAX_ACTIVE_EFFECTS,
  attachBrowserGuards,
  createEffectRegistry,
  effectIntensity,
  shouldPlayEffects,
} from '../src/lib/effect-registry.ts';

function fakeClock() {
  let time = 0;
  let next = 1;
  const timers = new Map();
  return {
    setTimer(fn, ms) { const id = next++; timers.set(id, { at: time + ms, fn }); return id; },
    clearTimer(id) { timers.delete(id); },
    now: () => time,
    pending: () => timers.size,
    advance(ms) {
      time += ms;
      for (const [id, t] of [...timers]) {
        if (t.at <= time && timers.has(id)) { timers.delete(id); t.fn(); }
      }
    },
  };
}

function setup() {
  const clock = fakeClock();
  const registry = createEffectRegistry(clock);
  return { clock, registry };
}

function counted(extra = {}) {
  const fx = { calls: 0, dispose() { fx.calls += 1; }, durationMs: 100, ...extra };
  return fx;
}

test('finish disposes exactly once and double finish is a no-op', () => {
  const { registry, clock } = setup();
  const fx = counted();
  const handle = registry.start(fx);
  assert.equal(registry.leftovers(), 1);
  registry.finish(handle);
  registry.finish(handle);
  clock.advance(1000);
  assert.equal(fx.calls, 1);
  assert.equal(handle.finished, true);
  assert.equal(registry.leftovers(), 0);
  assert.equal(clock.pending(), 0);
});

test('failsafe fires at durationMs + 400 and not before', () => {
  const { registry, clock } = setup();
  const fx = counted({ durationMs: 1000 });
  registry.start(fx);
  clock.advance(1399);
  assert.equal(fx.calls, 0);
  assert.equal(registry.leftovers(), 1);
  clock.advance(1);
  assert.equal(fx.calls, 1);
  assert.equal(registry.leftovers(), 0);
});

test('a throwing dispose is counted, swallowed and never stays registered', () => {
  const { registry, clock } = setup();
  const bad = counted({ dispose() { bad.calls += 1; throw new Error('boom'); } });
  const h1 = registry.start(bad);
  registry.finish(h1);
  assert.equal(registry.leftovers(), 0);
  assert.equal(registry.errors(), 1);
  const bad2 = counted({ dispose() { bad2.calls += 1; throw new Error('boom'); } });
  registry.start(bad2);
  clock.advance(500);
  assert.equal(registry.leftovers(), 0);
  assert.equal(registry.errors(), 2);
  assert.equal(bad.calls + bad2.calls, 2);
});

test('cap evicts the oldest effect first', () => {
  const { registry } = setup();
  const all = [];
  let firstHandle;
  for (let i = 0; i < MAX_ACTIVE_EFFECTS; i += 1) {
    const fx = counted();
    all.push(fx);
    const h = registry.start(fx);
    if (i === 0) firstHandle = h;
  }
  assert.equal(registry.leftovers(), MAX_ACTIVE_EFFECTS);
  const extra = counted();
  registry.start(extra);
  assert.equal(registry.leftovers(), MAX_ACTIVE_EFFECTS);
  assert.equal(all[0].calls, 1);
  assert.equal(firstHandle.finished, true);
  assert.ok(all.slice(1).every((fx) => fx.calls === 0));
  assert.equal(extra.calls, 0);
  for (let i = 0; i < 40; i += 1) registry.start(counted());
  assert.equal(registry.leftovers(), MAX_ACTIVE_EFFECTS);
});

test('flushAll disposes everything once and clears timers', () => {
  const { registry, clock } = setup();
  const list = [counted(), counted(), counted()];
  list.forEach((fx) => registry.start(fx));
  registry.flushAll();
  registry.flushAll();
  clock.advance(5000);
  assert.deepEqual(list.map((fx) => fx.calls), [1, 1, 1]);
  assert.equal(registry.leftovers(), 0);
  assert.equal(clock.pending(), 0);
});

test('cancelOnHidden disposes all and calls the hidden hook', () => {
  const clock = fakeClock();
  let hooked = 0;
  const registry = createEffectRegistry({ ...clock, onVisibilityHidden: () => { hooked += 1; } });
  const a = counted();
  const b = counted();
  registry.start(a);
  registry.start(b);
  registry.cancelOnHidden();
  assert.deepEqual([a.calls, b.calls], [1, 1]);
  assert.equal(registry.leftovers(), 0);
  assert.equal(hooked, 1);
});

test('restarting the same id disposes the old effect and the stale handle is inert', () => {
  const { registry, clock } = setup();
  const first = counted({ id: 'hit' });
  const second = counted({ id: 'hit' });
  const h1 = registry.start(first);
  const h2 = registry.start(second);
  assert.equal(first.calls, 1);
  assert.equal(second.calls, 0);
  assert.equal(registry.leftovers(), 1);
  registry.finish(h1);
  assert.equal(second.calls, 0);
  assert.equal(registry.leftovers(), 1);
  registry.finish(h2);
  clock.advance(1000);
  assert.equal(second.calls, 1);
  assert.equal(registry.leftovers(), 0);
});

test('the old failsafe of a restarted id cannot dispose the new effect', () => {
  const { registry, clock } = setup();
  const oldFx = counted({ id: 'x', durationMs: 100 });
  registry.start(oldFx);
  const next = counted({ id: 'x', durationMs: 1000 });
  registry.start(next);
  assert.equal(oldFx.calls, 1);
  assert.equal(clock.pending(), 1, 'the old failsafe timer must be cleared via clearTimer');
  clock.advance(300);
  assert.equal(next.calls, 0);
  clock.advance(1100);
  assert.equal(next.calls, 1);
});

test('real timers: leftovers() reaches 0 after the failsafe within a bounded wait', async () => {
  const registry = createEffectRegistry();
  const fx = counted({ durationMs: 20 });
  registry.start(fx);
  assert.equal(registry.leftovers(), 1);
  const deadline = Date.now() + 2000;
  while (registry.leftovers() > 0 && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(registry.leftovers(), 0);
  assert.equal(fx.calls, 1);
});

test('effects level helpers', () => {
  assert.equal(shouldPlayEffects('off'), false);
  assert.equal(shouldPlayEffects('low'), true);
  assert.equal(shouldPlayEffects('full'), true);
  assert.equal(effectIntensity('off'), 0);
  assert.ok(effectIntensity('low') > 0 && effectIntensity('low') < effectIntensity('full'));
  assert.equal(effectIntensity('full'), 1);
});

test('attachBrowserGuards is safe without a browser and wires hidden events in one', () => {
  const { registry } = setup();
  assert.doesNotThrow(() => attachBrowserGuards(registry, null)());
  const listeners = {};
  const doc = {
    hidden: false,
    addEventListener(type, fn) { listeners[`doc:${type}`] = fn; },
    removeEventListener(type) { delete listeners[`doc:${type}`]; },
  };
  const win = {
    document: doc,
    addEventListener(type, fn) { listeners[`win:${type}`] = fn; },
    removeEventListener(type) { delete listeners[`win:${type}`]; },
  };
  const fx = counted();
  registry.start(fx);
  const detach = attachBrowserGuards(registry, win, true);
  assert.equal(win.__effectLeftovers(), 1);
  listeners['doc:visibilitychange']();
  assert.equal(fx.calls, 0);
  doc.hidden = true;
  listeners['doc:visibilitychange']();
  assert.equal(fx.calls, 1);
  const fx2 = counted();
  registry.start(fx2);
  win.__flushEffects();
  assert.equal(fx2.calls, 1);
  const fx3 = counted();
  registry.start(fx3);
  listeners['win:pagehide']();
  assert.equal(fx3.calls, 1);
  detach();
  assert.equal(win.__effectLeftovers, undefined);
  assert.deepEqual(Object.keys(listeners), []);
});

test('attachBrowserGuards does not expose debug hooks outside dev', () => {
  const { registry } = setup();
  const win = { addEventListener() {}, removeEventListener() {} };
  attachBrowserGuards(registry, win, false);
  assert.equal(win.__effectLeftovers, undefined);
  assert.equal(win.__flushEffects, undefined);
});

test('re-entrant start of the same id inside dispose leaves no orphan', () => {
  const { registry, clock } = setup();
  const inner = counted({ id: 'a' });
  const outer = counted({
    id: 'a',
    dispose() { outer.calls += 1; if (outer.calls === 1) registry.start(inner); },
  });
  registry.start(outer);
  const replacement = counted({ id: 'a' });
  registry.start(replacement);
  assert.equal(registry.leftovers(), 1);
  registry.flushAll();
  assert.equal(registry.leftovers(), 0);
  assert.equal(inner.calls, 1, 'inner must be disposed by flushAll, not by its failsafe');
  assert.equal(clock.pending(), 0);
  clock.advance(5000);
  assert.equal(outer.calls, 1);
  assert.equal(inner.calls, 1);
  assert.equal(replacement.calls, 1);
  assert.equal(clock.pending(), 0);
});

test('re-entrant start of a different id inside dispose is tracked', () => {
  const { registry } = setup();
  const child = counted({ id: 'child' });
  const parent = counted({ id: 'parent', dispose() { parent.calls += 1; registry.start(child); } });
  const h = registry.start(parent);
  registry.finish(h);
  assert.equal(registry.leftovers(), 1);
  registry.flushAll();
  assert.equal(registry.leftovers(), 0);
  assert.equal(child.calls, 1);
  assert.equal(parent.calls, 1);
});

test('finish called inside dispose does not double dispose', () => {
  const { registry } = setup();
  let handle;
  const fx = counted({ dispose() { fx.calls += 1; registry.finish(handle); } });
  handle = registry.start(fx);
  registry.finish(handle);
  assert.equal(fx.calls, 1);
  assert.equal(registry.leftovers(), 0);
});

test('flushAll also disposes an effect started mid-flush', () => {
  const { registry } = setup();
  const late = counted({ id: 'late' });
  const first = counted({ id: 'first', dispose() { first.calls += 1; registry.start(late); } });
  registry.start(first);
  registry.flushAll();
  assert.equal(registry.leftovers(), 0);
  assert.equal(late.calls, 1);
});

test('endless re-spawning dispose terminates and counts an error', () => {
  const { registry } = setup();
  let n = 0;
  const spawn = () => ({ id: `s${n++}`, durationMs: 10, dispose() { registry.start(spawn()); } });
  registry.start(spawn());
  registry.flushAll();
  assert.ok(registry.errors() >= 1);
  const evictor = () => ({ durationMs: 10, dispose() { registry.start(evictor()); } });
  for (let i = 0; i < MAX_ACTIVE_EFFECTS + 3; i += 1) registry.start(evictor());
  // Termination is the guarantee here: the cascade is cut off and reported.
  assert.ok(registry.errors() >= 2);
});

test('a throwing setTimer disposes the effect immediately and counts an error', () => {
  const registry = createEffectRegistry({ setTimer() { throw new Error('no timer'); }, clearTimer() {} });
  const fx = counted();
  const h = registry.start(fx);
  assert.equal(fx.calls, 1);
  assert.equal(h.finished, true);
  assert.equal(registry.leftovers(), 0);
  assert.equal(registry.errors(), 1);
});

test('a throwing clearTimer is counted and the effect is still disposed once', () => {
  const clock = fakeClock();
  const registry = createEffectRegistry({ ...clock, clearTimer() { throw new Error('no clear'); } });
  const fx = counted();
  const h = registry.start(fx);
  registry.finish(h);
  assert.equal(fx.calls, 1);
  assert.equal(registry.leftovers(), 0);
  assert.equal(registry.errors(), 1);
});

test('a throwing onVisibilityHidden is counted, not thrown', () => {
  const clock = fakeClock();
  const registry = createEffectRegistry({ ...clock, onVisibilityHidden() { throw new Error('hook'); } });
  const fx = counted();
  registry.start(fx);
  assert.doesNotThrow(() => registry.cancelOnHidden());
  assert.equal(fx.calls, 1);
  assert.equal(registry.errors(), 1);
});

test('caller ids cannot collide with generated ids', () => {
  const { registry } = setup();
  const a = counted();
  const b = counted({ id: 'effect-1' });
  const c = counted();
  registry.start(a);
  registry.start(b);
  registry.start(c);
  assert.equal(registry.leftovers(), 3);
  assert.equal(a.calls + b.calls + c.calls, 0);
  registry.flushAll();
  assert.deepEqual([a.calls, b.calls, c.calls], [1, 1, 1]);
});

test('huge or infinite durations are clamped to a legal timer delay', () => {
  const delays = [];
  const registry = createEffectRegistry({ setTimer(_fn, ms) { delays.push(ms); return 1; }, clearTimer() {} });
  registry.start(counted({ durationMs: Infinity }));
  registry.start(counted({ durationMs: 1e15 }));
  registry.start(counted({ durationMs: NaN }));
  assert.ok(delays.slice(0, 2).every((d) => d <= 2 ** 31 - 1));
  assert.equal(delays[2], 400);
  registry.flushAll();
});
