import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const css = await readFile('src/index.css', 'utf8');

test('every scroll area uses the theme tokens instead of the white browser default', () => {
  assert.match(css, /\*\s*\{[^}]*scrollbar-width:\s*thin;[^}]*scrollbar-color:\s*var\(--unw-border\)\s+transparent/s);
});
