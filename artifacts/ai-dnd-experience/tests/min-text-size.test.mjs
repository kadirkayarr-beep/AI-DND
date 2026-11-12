import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: no text below 12 px anywhere in the player UI.
const files = [
  'src/index.css', 'src/components/campaign-library.tsx', 'src/components/character-creation-screen.css',
  'src/components/cinematic-gate.css', 'src/components/combat-panel.css', 'src/components/unwritten-play.css',
];
for (const file of files) {
  test(`${file} has no text smaller than 12 px`, async () => {
    const source = await readFile(file, 'utf8');
    const small = [...source.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px|text-\[(\d+(?:\.\d+)?)px\]/g)]
      .filter(m => Number(m[1] ?? m[2]) < 12).map(m => m[0]);
    assert.deepEqual(small, []);
  });
}
