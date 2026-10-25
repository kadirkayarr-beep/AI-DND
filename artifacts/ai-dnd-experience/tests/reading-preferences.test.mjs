import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_READING_PREFERENCES,
  readReadingPreferences,
  writeReadingPreferences,
} from '../src/lib/reading-preferences.ts';

function memoryStorage(initial = null) {
  let value = initial;
  return {
    getItem() { return value; },
    setItem(_key, next) { value = next; },
    read() { return value; },
  };
}

test('reading preferences are limited to presentation values and survive storage round trips', () => {
  const storage = memoryStorage(JSON.stringify({ fontSizePx: 30, lineHeight: 1.86, campaignId: 'never-read' }));
  assert.deepEqual(readReadingPreferences(storage), { fontSizePx: 30, lineHeight: 1.86 });

  writeReadingPreferences({ fontSizePx: 28, lineHeight: 1.9 }, storage);
  assert.deepEqual(JSON.parse(storage.read()), { fontSizePx: 28, lineHeight: 1.9 });
});

test('invalid stored values fall back without affecting default presentation', () => {
  const storage = memoryStorage(JSON.stringify({ fontSizePx: 99, lineHeight: 'large' }));
  assert.deepEqual(readReadingPreferences(storage), DEFAULT_READING_PREFERENCES);
  assert.deepEqual(readReadingPreferences(memoryStorage('{broken')), DEFAULT_READING_PREFERENCES);
  assert.deepEqual(readReadingPreferences(null), DEFAULT_READING_PREFERENCES);
});

test('blocked or failing browser storage never throws', () => {
  const blocked = {
    getItem() { throw new Error('storage blocked'); },
    setItem() { throw new Error('storage blocked'); },
  };
  assert.deepEqual(readReadingPreferences(blocked), DEFAULT_READING_PREFERENCES);
  assert.doesNotThrow(() => writeReadingPreferences({ fontSizePx: 28, lineHeight: 1.8 }, blocked));
});
