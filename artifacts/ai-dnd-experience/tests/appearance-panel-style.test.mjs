import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: the Görünüm sheet uses themed controls and a compact segmented layout, not a long default list.
const css = await readFile('src/components/appearance-settings-panel.css', 'utf8');

test('radios and checkboxes use the theme accent', () => {
  assert.match(css, /\.appearance-settings input\s*\{[^}]*accent-color:\s*var\(--unw-accent-light\)/);
});
test('options sit in a compact grid and the chosen one is filled', () => {
  assert.match(css, /\.appearance-settings fieldset\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/);
  assert.match(css, /\.appearance-option:has\(input:checked\)\s*\{[^}]*background:\s*var\(--unw-surface\)/);
});
