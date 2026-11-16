import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { hasTrName, nameLang, trName } from '../src/lib/tr-names.ts';

// Plan part L (decision 15): one Turkish name table for the interface, the narrator prompt and the player-text parsers.
const table = JSON.parse(await readFile('../../content/names/tr_names.json', 'utf8'));

test('a spell and an item show their Turkish name; ids stay untouched', () => {
  assert.equal(trName('Magic Missile', 'spells'), table.spells['Magic Missile']);
  assert.equal(trName('Dagger', 'items'), table.items.Dagger);
  assert.equal(trName('Dagger'), table.items.Dagger);
  assert.notEqual(trName('Magic Missile'), 'Magic Missile');
});
test('a name without an entry is shown as it is and marked as English', () => {
  assert.equal(trName('Totally Unknown Thing'), 'Totally Unknown Thing');
  assert.equal(hasTrName('Totally Unknown Thing'), false);
  assert.equal(nameLang('Totally Unknown Thing'), 'en');
  assert.equal(nameLang('Magic Missile', 'spells'), undefined);
});
test('the UI reads the same JSON file the engine reads, not a copy', async () => {
  const lib = await readFile('src/lib/tr-names.ts', 'utf8');
  assert.match(lib, /content\/names\/tr_names\.json/);
  const python = await readFile('../../ai-dnd/tr_names.py', 'utf8').catch(() => '');
  if (python) assert.match(python, /content" \/ "names" \/ "tr_names\.json"/);
});
test('spell pills and inventory rows go through the table', async () => {
  const spells = await readFile('src/components/spellcasting-panel.tsx', 'utf8');
  const panel = await readFile('src/components/character-panel.tsx', 'utf8');
  assert.match(spells, /trName\(spell, 'spells'\)/);
  assert.doesNotMatch(spells, /lang="en"/);
  assert.match(panel, /trName\(display\.name, 'items'\)/);
});
