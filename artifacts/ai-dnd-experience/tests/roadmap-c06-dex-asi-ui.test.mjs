// DEX in the ASI picker: server offers it, the client shows and sends it, and an option the server dropped stays unavailable.
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import path from 'node:path';
import { asiChoiceKey, asiChoiceLabel, readAsiChoices, sourceAsiChoice } from '../src/lib/asi-choices.ts';

const choice = (increase) => ({ feat: 'Ability Score Improvement', increase });
const dexTwo = choice({ dexterity: 2 });
const dexSplit = choice({ dexterity: 1, charisma: 1 });
const con = choice({ constitution: 2 });
let vite, picker;

before(async () => {
  process.env.PORT ||= '4185';
  process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true, hmr: false, ws: false },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  picker = await vite.ssrLoadModule('/src/components/asi-choice-picker.tsx');
});
after(async () => await vite?.close());

function nodes(element) {
  if (Array.isArray(element)) return element.flatMap(nodes);
  if (!element || typeof element !== 'object') return [];
  return [element, ...nodes(element.props?.children)];
}

test('a served DEX pattern is read, labelled and kept exactly', () => {
  const choices = readAsiChoices([con, dexTwo, dexSplit]);
  assert.deepEqual(choices, [con, dexTwo, dexSplit]);
  assert.equal(asiChoiceLabel(dexTwo), 'dexterity +2');
  assert.equal(asiChoiceLabel(dexSplit), 'dexterity +1 / charisma +1');
  assert.deepEqual(sourceAsiChoice([con, dexTwo], dexTwo), dexTwo);
});

test('a DEX shape the family does not have fails the whole list', () => {
  for (const bad of [{ dexterity: 3 }, { dexterity: 1 }, { dexterity: 1, dex: 1 }]) {
    assert.equal(readAsiChoices([con, choice(bad)]), undefined, JSON.stringify(bad));
  }
});

test('a DEX option the server left out cannot be kept by an old draft', () => {
  assert.equal(sourceAsiChoice([con], dexTwo), undefined);
});

test('the picker offers DEX and no longer says it is closed', () => {
  const tree = nodes(picker.AsiChoicePicker({ choices: [con, dexTwo], onChange: () => {}, testId: 'asi' }));
  const options = tree.filter((node) => node.type === 'option').map((node) => node.props.value);
  assert.ok(options.includes(asiChoiceKey(dexTwo)));
  const text = tree.filter((node) => node.type === 'p').map((node) => [node.props.children].flat().join('')).join(' ');
  assert.match(text, /Strength, Dexterity, Constitution/);
  assert.doesNotMatch(text, /kapalıdır/);
});
