import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: creation shows choices, not explanations. The level picker stays; its lead-in sentence goes.
const source = await readFile('src/components/character-creation-screen.tsx', 'utf8');

test('the starting-level block keeps its controls but not the explanatory sentence', () => {
  assert.match(source, /data-testid="starting-level-block"/);
  assert.match(source, /<StartingLevelControl /);
  assert.doesNotMatch(source, /deneyimli başlamak istersen/);
});
