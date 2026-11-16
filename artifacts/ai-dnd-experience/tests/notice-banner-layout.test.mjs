import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// D-236: three long uppercase recovery buttons must wrap, not overlap, inside the notice.
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');
const rule = (selector) => {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `missing rule ${selector}`);
  return css.slice(start, css.indexOf('}', start));
};

test('notice row wraps so long buttons drop to a new line instead of overlapping', () => {
  assert.match(rule('.notice'), /flex-wrap:\s*wrap/);
});

test('notice buttons wrap their own text and do not each push to the right edge', () => {
  const body = rule('.notice button');
  assert.doesNotMatch(body, /margin-left:\s*auto/);
  assert.match(body, /white-space:\s*normal/);
  assert.match(body, /min-width:\s*0/);
});

test('notice text block can shrink and takes the free width', () => {
  assert.match(rule('.notice > div'), /flex:\s*1 1/);
});
