import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { writeAdvisoryCache, removeAdvisoryCache } from '../src/lib/advisory-cache.ts';

function withWindow(value, run) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value });
  try { run(); } finally {
    if (previous) Object.defineProperty(globalThis, 'window', previous);
    else delete globalThis.window;
  }
}

test('advisory cache preserves ordinary write and remove behavior', () => {
  const values = new Map();
  withWindow({ localStorage: {
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  } }, () => {
    assert.equal(writeAdvisoryCache('history', 'server receipt'), true);
    assert.equal(values.get('history'), 'server receipt');
    assert.equal(removeAdvisoryCache('history'), true);
    assert.equal(values.has('history'), false);
  });
});

test('quota and denied storage are reported without throwing', () => {
  for (const name of ['QuotaExceededError', 'SecurityError']) {
    const fail = () => { throw new DOMException('Synthetic cache failure', name); };
    withWindow({ localStorage: { setItem: fail, removeItem: fail } }, () => {
      assert.equal(writeAdvisoryCache('history', 'server receipt'), false);
      assert.equal(removeAdvisoryCache('history'), false);
    });
  }
  withWindow({ get localStorage() { throw new DOMException('Denied', 'SecurityError'); } }, () => {
    assert.equal(writeAdvisoryCache('history', 'server receipt'), false);
    assert.equal(removeAdvisoryCache('history'), false);
  });
});

test('campaign create, reveal, resume and turn writes use the nonfatal cache boundary', async () => {
  const source = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /window\.localStorage\.(?:setItem|removeItem)\s*\(/);
  assert.equal((source.match(/writeAdvisoryCache\s*\(/g) ?? []).length, 5);
  assert.equal((source.match(/removeAdvisoryCache\s*\(/g) ?? []).length, 1);
});
