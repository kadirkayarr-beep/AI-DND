import assert from 'node:assert/strict';
import test from 'node:test';
import { classLevelingNote } from '../src/lib/campaign-presentation.ts';

test('classes the engine cannot level up carry the experimental label', () => {
  for (const name of ['Bard', 'Druid', 'Ranger', 'Warlock']) {
    assert.equal(classLevelingNote(name), 'seviye atlamaz (deneysel)', name);
  }
});

test('classes with a level-up table carry no label', () => {
  for (const name of ['Sorcerer', 'Barbarian', 'Cleric', 'Fighter', 'Monk', 'Paladin', 'Rogue', 'Wizard']) {
    assert.equal(classLevelingNote(name), null, name);
  }
});
