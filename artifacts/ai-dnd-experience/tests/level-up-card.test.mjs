import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part L (decision 17): a card on the scene when the turn raised the level; it links to the existing choice screen.
const card = await readFile('src/components/level-up-card.tsx', 'utf8');
const page = await readFile('src/pages/game-browser.tsx', 'utf8');

test('the card names the new level and HP gained and has a link to the choices and a close button', () => {
  assert.match(card, /Seviye \{levelUp\.new_level\}/);
  assert.match(card, /levelUp\.hit_points_gained/);
  assert.match(card, /data-testid="level-up-card"/);
  assert.match(card, /data-testid="button-level-up-goto-choices"/);
  assert.match(card, /data-testid="button-level-up-card-close"/);
  assert.match(card, /level-up-choices/);
});
test('the card only shows for a real level change', () => {
  assert.match(card, /new_level\s*<=\s*levelUp\.previous_level/);
});
test('game-browser stores the turn level_up and clears it on dismiss, new campaign and resume', () => {
  assert.match(page, /const \[levelUpCard, setLevelUpCard\] = useState<LevelUpResult \| null>\(null\)/);
  assert.match(page, /setLevelUpCard\(result\.level_up \?\? null\)/);
  assert.match(page, /<LevelUpCard levelUp=\{levelUpCard\} onClose=\{\(\) => setLevelUpCard\(null\)\} \/>/);
});
