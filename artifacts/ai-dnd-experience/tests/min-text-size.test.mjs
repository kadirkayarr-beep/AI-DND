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

// Rem-sized text counts too (16 px root): 0.75rem is the floor.
for (const file of ['src/components/reading-settings.css', 'src/components/skill-check-result.css', 'src/index.css', 'src/components/unwritten-play.css', 'src/components/unwritten-reading.css']) {
  test(`${file} has no rem text smaller than 0.75rem`, async () => {
    const source = await readFile(file, 'utf8');
    const small = [...source.matchAll(/font-size:\s*(\d*\.?\d+)rem/g)].filter(m => Number(m[1]) < 0.75).map(m => m[0]);
    assert.deepEqual(small, []);
  });
}
