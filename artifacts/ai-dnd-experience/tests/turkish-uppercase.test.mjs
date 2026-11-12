import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panel = await readFile('src/components/spellcasting-panel.tsx', 'utf8');

test('spell names without a Turkish entry are marked lang="en" so CSS uppercase does not turn i into a dotted capital', () => {
  // Plan part L: translated names carry no lang (Turkish); the rest keep lang="en" through nameLang.
  const pills = panel.match(/<li className="status-pill"[^>]*>\{trName\(spell, 'spells'\)\}<\/li>/g) ?? [];
  assert.equal(pills.length, 2);
  for (const pill of pills) assert.match(pill, /lang=\{nameLang\(spell, 'spells'\)\}/);
});
