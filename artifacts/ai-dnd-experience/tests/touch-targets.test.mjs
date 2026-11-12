import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Plan part A: tap targets in character creation are at least 44 px.
const css = await readFile('src/components/character-creation-screen.css', 'utf8');
const rule = (selector) => {
  const block = css.split('}').find(part => part.split('{')[0].trim() === selector);
  assert.ok(block, `${selector} rule exists`);
  return block;
};
const px = (block, prop) => Number(new RegExp(prop + ':\\s*(\\d+)px').exec(block)?.[1] ?? 0);

test('point-buy +/- buttons are 44 px', () => {
  const block = rule('.cc-calc-btn');
  assert.ok(px(block, 'width') >= 44 && px(block, 'height') >= 44);
});
test('text inputs and the step dice are at least 44 px tall', () => {
  assert.ok(px(rule('.cc-input'), 'min-height') >= 44);
  assert.ok(px(rule('.cc-start-fields .cc-input'), 'min-height') >= 44);
  assert.ok(px(rule('.cc-step-dice'), 'height') >= 44);
});
