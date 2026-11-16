import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: the sticky sheet heading has the same tone as the sheet body (no odd band on top).
const css = await readFile('src/components/unwritten-play.css', 'utf8');
test('drawer heading uses the sheet body background', () => {
  assert.match(css, /\.drawer-heading\s*\{[^}]*background:\s*var\(--unw-surface-sunken\)/);
});
