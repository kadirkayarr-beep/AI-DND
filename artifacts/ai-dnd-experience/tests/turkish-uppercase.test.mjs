import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panel = await readFile('src/components/spellcasting-panel.tsx', 'utf8');

test('English spell names are marked lang="en" so CSS uppercase does not turn i into a dotted capital', () => {
  const pills = panel.match(/<li className="status-pill"[^>]*>\{spell\}<\/li>/g) ?? [];
  assert.equal(pills.length, 2);
  for (const pill of pills) assert.match(pill, /lang="en"/);
});
