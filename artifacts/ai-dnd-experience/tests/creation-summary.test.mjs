import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { backgroundGoods, packageGoods } from '../src/lib/starting-purse.ts';

// Plan part L (play notes S and T): the step-8 summary shows the same empty-field wording as the character
// sheet, and lists everything the character will carry, background kit included.
const screen = await readFile('src/components/character-creation-screen.tsx', 'utf8');
const catalog = { backgrounds: { Scribe: { equipment: ['Hattat Takımı', 'Parşömen ve Mürekkep', 'Kadim Bir Teori Kitabı', '10 Altın'], coin_items: ['10 Altın'] } } };

test('option A lists the background kit without its coin; option B and unknowns list nothing', () => {
  assert.deepEqual(backgroundGoods(catalog, 'Scribe', 'A'), ['Hattat Takımı', 'Parşömen ve Mürekkep', 'Kadim Bir Teori Kitabı']);
  assert.deepEqual(backgroundGoods(catalog, 'Scribe', 'B'), []);
  assert.deepEqual(backgroundGoods(catalog, 'Nobody', 'A'), []);
  assert.deepEqual(backgroundGoods(undefined, 'Scribe', 'A'), []);
});
test('the class package list is unchanged', () => {
  assert.deepEqual(packageGoods({ items: ['Spear', '10 GP'], coin_items: ['10 GP'] }), ['Spear']);
});
test('the summary appends the background kit to the class package', () => {
  assert.match(screen, /backgroundGoods\(propCatalog, background, backgroundEquipmentOption\)/);
});
test('empty identity fields say "Kayıtta yok" in the summary, like the character sheet', () => {
  assert.doesNotMatch(screen, /Belirtilmedi/);
  assert.equal((screen.match(/\|\| 'Kayıtta yok'/g) ?? []).length, 4);
});
