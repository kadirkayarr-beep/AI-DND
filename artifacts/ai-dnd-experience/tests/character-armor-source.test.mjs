import assert from 'node:assert/strict';
import { test } from 'node:test';
import { calculateCharacterPreviewStats } from '../src/lib/character-preview-stats.ts';

const abilityScores = { strength: 15, dexterity: 16, constitution: 14, intelligence: 10, wisdom: 18, charisma: 8 };
for (const [characterClass, training, items, expected] of [
  ['Monk', [], [], 17],
  ['Monk', [], ['Shield'], 13],
  ['Monk', [], ['Leather Armor', 'Shield'], 14],
  ['Monk', ['Shields'], ['Shield'], 15], // prerequisite fixture only
  ['Barbarian', ['Shields'], ['Shield'], 17],
  ['Fighter', ['Shields'], ['Chain Mail', 'Shield'], 18],
  ['Wizard', [], ['Shield'], 13],
]) {
  test(`PHB 101/219 preview: ${characterClass}, ${training}, ${items}`, () => {
    const result = calculateCharacterPreviewStats({ characterClass, abilityScores,
      classData: { hit_die: 8, armor_proficiencies: training, equipment_packages: [{ id: 'A', items }] },
      equipmentPackage: 'A', backgroundEquipmentOption: 'B' });
    assert.equal(result.ac, expected);
    assert.equal(result.hasShield, items.includes('Shield'));
  });
}

test('legacy preview catalog fallback preserves Fighter training but never invents Monk training', () => {
  const classData = { equipment_packages: [{ id: 'A', items: ['Shield'] }] };
  for (const [characterClass, expected] of [['Fighter', 15], ['Monk', 13]]) {
    assert.equal(calculateCharacterPreviewStats({ characterClass, classData,
      abilityScores, equipmentPackage: 'A' }).ac, expected);
  }
  assert.equal(calculateCharacterPreviewStats({ characterClass: 'Fighter',
    classData: { ...classData, armor_proficiencies: [] },
    abilityScores, equipmentPackage: 'A' }).ac, 13);
});
