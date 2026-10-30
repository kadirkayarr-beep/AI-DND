/** Execute generated request validators; mechanics and magic-only rule live on backend. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PlayGameTurnBody, PlayLegacyTurnBody } from '../../../lib/api-zod/src/generated/api.ts';

for (const [name, schema] of [['canonical', PlayGameTurnBody], ['legacy', PlayLegacyTurnBody]]) {
  const request = (slot) => ({ message: 'Cast', combat_action: { steps: [{ kind: 'magic', ability: 'Magic Missile', ...slot }] } });
  test(`${name} generated contract preserves explicit slot choice and legacy absence`, () => {
    assert.equal(schema.parse(request({slot_level: 2})).combat_action.steps[0].slot_level, 2);
    assert.equal(schema.parse(request({slot_level: null})).combat_action.steps[0].slot_level, null);
    assert.equal(Object.hasOwn(schema.parse(request({})).combat_action.steps[0], 'slot_level'), false);
  });
  test(`${name} generated contract rejects noninteger or out-of-range slot choices`, () => {
    for (const value of [true, 0, 10, '2', 2.5]) assert.equal(schema.safeParse(request({slot_level: value})).success, false, String(value));
  });
}
