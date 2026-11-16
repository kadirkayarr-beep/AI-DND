import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

// D-154: after a finished Short Rest the server offers Hit Dice (effects.hit_dice); the screen must show the offer,
// a button that sends spend_hit_die, and a receipt with the rolled die and the healing.
let species, vite;
before(async () => {
  process.env.PORT ||= '4187'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  species = await vite.ssrLoadModule('/src/components/species-trait-controls.tsx');
});
after(async () => await vite?.close());

test('hit dice offer is read only from a valid open window with dice left', () => {
  const read = species.readHitDiceOffer;
  assert.deepEqual(read({ hit_dice: { die: 8, remaining: 2, total: 3, can_spend: true } }), { die: 8, remaining: 2, total: 3 });
  assert.equal(read({ hit_dice: { die: 8, remaining: 0, total: 3, can_spend: true } }), null);
  assert.equal(read({ hit_dice: { die: 8, remaining: 2, total: 3, can_spend: false } }), null);
  assert.equal(read({ hit_dice: { die: '8', remaining: 2, total: 3, can_spend: true } }), null);
  assert.equal(read({}), null);
  assert.equal(read(undefined), null);
});

test('hit dice receipt names the die, the roll, the healing and the dice left', () => {
  const text = species.hitDiceReceiptText({ dice: [5], healing: 7, remaining: 1, hit_dice: { die: 8, remaining: 1, total: 3, can_spend: true } });
  assert.match(text, /d8/); assert.match(text, /5/); assert.match(text, /7 can/); assert.match(text, /1 \/ 3|1 zar/);
  assert.equal(species.hitDiceReceiptText({ healing: 7 }), null);
});

test('the controls send spend_hit_die from a button', async () => {
  const source = await readFile('src/components/species-trait-controls.tsx', 'utf8');
  assert.match(source, /data-testid="species-action-spend-hit-die"/);
  assert.match(source, /send\(\{ action: 'spend_hit_die' \}\)/);
});

// Review: the offer must follow the server's window rule (same second, same Hit Points), not stay for as long as the last result stays.
test('hit dice offer closes when time moved or Hit Points changed since the offer', () => {
  const at = (hp, second) => ({ character: { current_hp: hp }, campaign_time: { detail: `1 Hammer 1490 DR - 08:00:${second}` }, combat: { active: false } });
  const same = species.hitDiceWindowStillOpen;
  assert.equal(same(at(10, '00'), at(10, '00')), true);
  assert.equal(same(at(10, '00'), at(10, '30')), false);
  assert.equal(same(at(10, '00'), at(7, '00')), false);
  assert.equal(same(at(10, '00'), { ...at(10, '00'), combat: { active: true } }), false);
  assert.equal(same(undefined, at(10, '00')), false);
});
