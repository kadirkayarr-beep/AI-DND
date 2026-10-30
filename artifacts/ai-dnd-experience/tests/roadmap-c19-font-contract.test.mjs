import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PlayGameTurnBody, PlayLegacyTurnBody } from '../../../lib/api-zod/src/generated/api.ts';
for (const [name, schema] of [['canonical', PlayGameTurnBody], ['legacy', PlayLegacyTurnBody]]) {
  const request = (slot) => ({message: 'Convert slot', combat_action: {steps: [{kind: 'convert_spell_slot', slot_level: slot}]}});
  test(`${name} retains explicit slot-to-point conversion step`, () => {
    for (const slot of [1,2,3]) {
      const parsed = schema.parse(request(slot)).combat_action.steps[0];
      assert.equal(parsed.kind, 'convert_spell_slot');
      assert.equal(parsed.slot_level, slot);
    }
  });
  test(`${name} rejects coerced slot levels`, () => {
    for (const value of [true,false,'1',1.5]) assert.equal(schema.safeParse(request(value)).success, false);
  });
}
