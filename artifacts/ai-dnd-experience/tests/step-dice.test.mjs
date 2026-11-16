import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pickRandomKey } from '../src/lib/pick-random.ts';

// Plan part C: a die on each of Tür, Sınıf, Geçmiş.
const screen = await readFile('src/components/character-creation-screen.tsx', 'utf8');
const dice = await readFile('src/components/step-dice.tsx', 'utf8');
const css = await readFile('src/components/character-creation-screen.css', 'utf8');

test('a roll picks a different option than the current one when there are several', () => {
  const keys = ['A', 'B', 'C'];
  for (const r of [0, 0.34, 0.67, 0.999]) assert.notEqual(pickRandomKey(keys, 'B', () => r), 'B');
});
test('a roll can reach every other option', () => {
  const seen = new Set([0, 0.2, 0.6, 0.99].map(r => pickRandomKey(['A', 'B', 'C', 'D'], 'A', () => r)));
  assert.deepEqual([...seen].sort(), ['B', 'C', 'D']);
});
test('a single option or no selection still rolls; an empty list rolls nothing', () => {
  assert.equal(pickRandomKey(['A'], 'A', () => 0.5), 'A');
  assert.equal(pickRandomKey(['A', 'B'], '', () => 0), 'A');
  assert.equal(pickRandomKey([], '', () => 0.5), null);
});
test('each of the three steps has a die, and the old whole-character button is gone', () => {
  for (const id of ['button-dice-species', 'button-dice-class', 'button-dice-background']) assert.ok(screen.includes(`testId="${id}"`), id);
  assert.ok(!screen.includes('button-mode-random') && !screen.includes("mode: 'random'"));
});
test('the species die clears the giant ancestry like a card click; class/background use the same setters as cards', () => {
  assert.match(screen, /testId="button-dice-species"[\s\S]{0,300}setGiantAncestry\(''\)[\s\S]{0,40}setSpecies\(key\)/);
  assert.match(screen, /testId="button-dice-class"[\s\S]{0,200}onPick=\{setCharacterClass\}/);
  assert.match(screen, /testId="button-dice-background"[\s\S]{0,200}onPick=\{setBackground\}/);
});
test('the die is a labelled button, keyboard-reachable, with a focus ring', () => {
  assert.match(dice, /<button[\s\S]*type="button"[\s\S]*aria-label=\{label\}/);
  assert.match(css, /\.cc-step-dice:focus-visible/);
});
test('reduced motion replaces the spin with a colour change', () => {
  const block = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)', css.indexOf('.cc-step-dice')));
  assert.match(block, /\.cc-step-dice\.rolling svg \{ animation: none/);
  assert.match(block, /\.cc-step-dice\.rolling \{ background/);
});
