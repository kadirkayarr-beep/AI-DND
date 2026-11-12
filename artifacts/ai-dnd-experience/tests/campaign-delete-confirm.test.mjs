import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile('src/components/campaign-library.tsx', 'utf8');

test('deleting an adventure never opens a browser dialog', () => {
  assert.doesNotMatch(source, /window\.confirm|\bconfirm\(|\balert\(|\bprompt\(/);
});

test('the delete confirmation is an in-app alert dialog that names the adventure and defaults to cancel', () => {
  assert.match(source, /role="alertdialog"/);
  assert.match(source, /data-testid="delete-confirm"/);
  assert.match(source, /Geri alınamaz/);
  assert.match(source, /Vazgeç/);
  assert.match(source, /autoFocus/);
  assert.match(source, /Escape/);
});
