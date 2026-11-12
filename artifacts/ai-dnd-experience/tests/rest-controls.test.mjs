import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part L (decision 16): Dinlen is a button pair (short/long) that sends the same words a player may type.
const controls = await readFile('src/components/rest-controls.tsx', 'utf8');
const column = await readFile('src/pages/game/story-column.tsx', 'utf8');

test('rest controls send the spoken rest phrases through the normal move path', () => {
  // The engine's timed owner reads a rest only when the line names how long it lasts (probed against
  // timed_gameplay.resolve_input: "Kısa dinlenme yapıyorum." alone returns None and no rest happens).
  assert.match(controls, /const SHORT_REST = 'Bir saat kısa dinleniyorum\.'/);
  assert.match(controls, /const LONG_REST = '8 saat uyuyarak uzun dinlenme yapıyorum\.'/);
  assert.match(controls, /data-testid="button-rest-short"/);
  assert.match(controls, /data-testid="button-rest-long"/);
  assert.match(controls, /onSend\(/);
});
test('rest controls are hidden in combat and while down or dead', () => {
  assert.match(controls, /state\.combat\.active/);
  assert.match(controls, /current_hp\s*(<=|===)\s*0|current_hp\s*!==\s*0|death_state/);
});
test('the story column offers rest next to the death controls and disables it while sending', () => {
  assert.match(column, /import \{ RestControls \} from '@\/components\/rest-controls'/);
  assert.match(column, /<RestControls state=\{state\} onSend=\{onDeathMove\} sending=\{sending\} \/>/);
  assert.match(controls, /disabled=\{sending\}/);
});
