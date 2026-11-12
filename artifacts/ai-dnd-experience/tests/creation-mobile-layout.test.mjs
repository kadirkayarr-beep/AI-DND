import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: at phone width the stepper is one scrollable row (no overlapping, truncated cards),
// the random-character block stacks and its help line is small text.
const css = await readFile('src/components/character-creation-screen.css', 'utf8');
const phone = css.slice(css.indexOf('@media (max-width: 600px)'));

test('stepper is a single horizontally scrollable row at phone width', () => {
  assert.match(phone, /\.cc-steps-nav\s*\{[^}]*display:\s*flex[^}]*overflow-x:\s*auto/);
  assert.match(phone, /\.cc-step-btn\s*\{[^}]*flex:\s*0 0 auto[^}]*white-space:\s*nowrap/);
  assert.match(phone, /\.cc-step-desc\s*\{[^}]*display:\s*none/);
});
test('random-character block stacks full width at phone width', () => {
  assert.match(phone, /\.cc-quick-actions\s*\{[^}]*flex-direction:\s*column[^}]*align-items:\s*stretch/);
  assert.match(phone, /\.cc-quick-actions p\s*\{[^}]*font-size:\s*14px/);
});
