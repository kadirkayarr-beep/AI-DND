import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_APPEARANCE_SETTINGS,
  motionAllowed,
  readAppearanceSettings,
  resolveEffectsLevel,
  writeAppearanceSettings,
} from '../src/lib/appearance-settings.ts';

function memoryStorage(initial = null) {
  let value = initial;
  return {
    getItem() { return value; },
    setItem(_key, next) { value = next; },
    read() { return value; },
  };
}

test('defaults are returned for empty, null and missing storage', () => {
  assert.deepEqual(readAppearanceSettings(memoryStorage()), DEFAULT_APPEARANCE_SETTINGS);
  assert.deepEqual(readAppearanceSettings(null), DEFAULT_APPEARANCE_SETTINGS);
  assert.notEqual(readAppearanceSettings(null), DEFAULT_APPEARANCE_SETTINGS);
  assert.equal(DEFAULT_APPEARANCE_SETTINGS.fontScale, 1);
});

test('valid settings round trip and unknown keys are dropped', () => {
  const storage = memoryStorage();
  const settings = {
    diceSet: 'obsidian', hpGauge: 'ink', spellSlots: 'inkwells', theme: 'system',
    effectsLevel: 'low', fontScale: 1.25, dyslexiaFont: true, highContrast: true, inkRevealSpeed: 'instant',
  };
  writeAppearanceSettings({ ...settings, campaignId: 'x' }, storage);
  assert.deepEqual(JSON.parse(storage.read()), settings);
  assert.deepEqual(readAppearanceSettings(storage), settings);
});

test('each invalid field falls back alone while valid fields survive', () => {
  const storage = memoryStorage(JSON.stringify({
    diceSet: 'plastic', hpGauge: 'ink', spellSlots: 7, theme: 'neon', effectsLevel: 'full',
    fontScale: 9, dyslexiaFont: 'yes', highContrast: true, inkRevealSpeed: 'warp',
  }));
  assert.deepEqual(readAppearanceSettings(storage), {
    ...DEFAULT_APPEARANCE_SETTINGS, hpGauge: 'ink', effectsLevel: 'full', highContrast: true,
  });
});

test('font scale is bounded, rejects non-numbers and NaN', () => {
  for (const bad of [0.5, 2, NaN, '1.2', null]) {
    const storage = memoryStorage(JSON.stringify({ fontScale: bad }));
    assert.equal(readAppearanceSettings(storage).fontScale, 1);
  }
  assert.equal(readAppearanceSettings(memoryStorage(JSON.stringify({ fontScale: 1.234 }))).fontScale, 1.23);
});

test('corrupt or non-object JSON yields defaults', () => {
  for (const raw of ['{broken', '[]', '"str"', 'null', '42']) {
    assert.deepEqual(readAppearanceSettings(memoryStorage(raw)), DEFAULT_APPEARANCE_SETTINGS);
  }
});

test('throwing storage never throws', () => {
  const blocked = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  assert.deepEqual(readAppearanceSettings(blocked), DEFAULT_APPEARANCE_SETTINGS);
  assert.doesNotThrow(() => writeAppearanceSettings(DEFAULT_APPEARANCE_SETTINGS, blocked));
  assert.doesNotThrow(() => writeAppearanceSettings(DEFAULT_APPEARANCE_SETTINGS, null));
});

test('reduced motion forces effects off and motionAllowed follows', () => {
  const full = { ...DEFAULT_APPEARANCE_SETTINGS, effectsLevel: 'full' };
  const low = { ...DEFAULT_APPEARANCE_SETTINGS, effectsLevel: 'low' };
  const off = { ...DEFAULT_APPEARANCE_SETTINGS, effectsLevel: 'off' };
  assert.equal(resolveEffectsLevel(full, false), 'full');
  assert.equal(resolveEffectsLevel(low, false), 'low');
  assert.equal(resolveEffectsLevel(full, true), 'off');
  assert.equal(motionAllowed(full, false), true);
  assert.equal(motionAllowed(low, true), false);
  assert.equal(motionAllowed(off, false), false);
});
