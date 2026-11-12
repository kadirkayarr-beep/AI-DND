import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part L: death-save counter is visible on the scene (pips with a text alternative), not only in the combat panel.
const source = await readFile('src/components/death-recovery-controls.tsx', 'utf8');

test('death controls show successes and failures as pips with a spoken equivalent', () => {
  assert.match(source, /function DeathTally/);
  assert.match(source, /data-testid="death-save-tally"/);
  assert.match(source, /Başarı \{death\.successes\}\/3/);
  assert.match(source, /Başarısızlık \{death\.failures\}\/3/);
  assert.match(source, /aria-hidden="true"/);
});
test('the tally appears only while the character is unconscious or stable', () => {
  assert.match(source, /death\.status === 'unconscious' \|\| death\.status === 'stable'/);
  assert.match(source, /<DeathTally death=\{state\.death_state\} \/>/);
});
test('the end-of-character card is a themed card with a heading, not a bare data row', () => {
  assert.match(source, /className="death-card /);
});
