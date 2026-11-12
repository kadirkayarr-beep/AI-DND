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

// Plan part L: at the death moment the writing box closes; one clear communication remains.
test('a dead character gets no writing box, except the final call into the dark', async () => {
  const { readFile } = await import('node:fs/promises');
  const column = await readFile('src/pages/game/story-column.tsx', 'utf8');
  assert.match(column, /const lastCall = state\.death_state\?\.status === 'dead' && Boolean\(state\.death_state\.last_call_open\)/);
  assert.match(column, /const writingClosed = state\.death_state\?\.status === 'dead' && !lastCall/);
  assert.match(column, /\{!composerOpen && !writingClosed && <button/);
  assert.match(column, /\{composerOpen && !writingClosed && <div className="command-box"/);
  assert.match(column, /lastCall \? 'Karanlığa seslen' : 'Hamle yap'/);
});
