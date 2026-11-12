import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const files = ['src/components/cinematic-gate.css', 'src/components/character-creation-screen.css'];
const selectors = ['cc-wizard-footer', 'reveal-actions'];

test('creation footer and reveal actions are never sticky, so they cannot cover content', async () => {
  for (const file of files) {
    const css = await readFile(file, 'utf8');
    for (const block of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!selectors.some(name => block[1].includes(name))) continue;
      assert.doesNotMatch(block[2], /position:\s*sticky/, `${file}: ${block[1].trim()}`);
    }
  }
});
