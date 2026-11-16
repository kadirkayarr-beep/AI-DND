import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part L (decision 17): XP bar on the character sheet.
const lib = await readFile('src/lib/xp-progress.ts', 'utf8');
const panel = await readFile('src/components/character-panel.tsx', 'utf8');
const python = await readFile('../../ai-dnd/xp.py', 'utf8');

test('the thresholds mirror the engine table in ai-dnd/xp.py (drift guard)', () => {
  const engine = [...python.slice(python.indexOf('LEVEL_THRESHOLDS')).split(')\n\n')[0].matchAll(/\((\d+),\s*(\d+)\)/g)].map(m => [Number(m[1]), Number(m[2])]);
  const ui = [...lib.slice(lib.indexOf('= [', lib.indexOf('XP_THRESHOLDS'))).split('];')[0].matchAll(/\[(\d+),\s*(\d+)\]/g)].map(m => [Number(m[1]), Number(m[2])]);
  assert.ok(engine.length >= 5);
  assert.deepEqual(ui, engine);
});
test('character panel shows an XP progress bar instead of a bare number', () => {
  assert.match(panel, /<XpBar /);
  assert.match(panel, /data-testid="text-character-xp"/);
  assert.match(panel, /role="progressbar"/);
});
test('the top level shows the total only, no bar to a next level', () => {
  assert.match(lib, /En yüksek seviye/);
});
