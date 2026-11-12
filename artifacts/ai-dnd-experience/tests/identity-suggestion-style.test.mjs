import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: the Köken suggestion panel is themed (tokens, no browser-default buttons/checkbox).
const css = await readFile('src/components/character-creation-screen.css', 'utf8');
const block = (selector) => css.split('}').find(p => p.split('{')[0].trim() === selector) ?? '';

test('suggestion buttons use theme tokens', () => {
  const b = block('.identity-suggestion-action');
  assert.match(b, /border:\s*1px solid var\(--unw-border\)/);
  assert.match(b, /color:\s*var\(--unw-text\)/);
  assert.match(b, /background:\s*var\(--unw-surface\)/);
});
test('pressed target tab and checkbox are themed', () => {
  assert.match(css, /\.identity-suggestion-action\[aria-pressed="true"\]\s*\{[^}]*var\(--unw-accent-light\)/);
  assert.match(block('.identity-suggestion-context input'), /accent-color:\s*var\(--unw-accent-light\)/);
});
test('compare boxes are cards with theme text colour and stack on narrow screens', () => {
  const b = block('.identity-suggestion-compare > div');
  assert.match(b, /border:\s*1px solid var\(--unw-border\)/);
  assert.match(b, /color:\s*var\(--unw-text\)/);
  assert.match(css, /@media \(max-width: 700px\)\s*\{\s*\.identity-suggestion-compare\s*\{\s*grid-template-columns:\s*1fr/);
});
