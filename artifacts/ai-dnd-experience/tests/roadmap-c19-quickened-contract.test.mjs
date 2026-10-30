import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PlayGameTurnBody, PlayLegacyTurnBody } from '../../../lib/api-zod/src/generated/api.ts';
for (const [name, schema] of [['canonical', PlayGameTurnBody], ['legacy', PlayLegacyTurnBody]]) {
  const request = (choice) => ({message: 'Cast', combat_action: {steps: [{kind: 'magic', ability: 'Magic Missile', ...choice}]}});
  test(`${name} retains explicit Quickened choice without adding an ordinary default`, () => {
    assert.equal(schema.parse(request({metamagic:'quickened_spell'})).combat_action.steps[0].metamagic, 'quickened_spell');
    assert.equal(schema.parse(request({metamagic:null})).combat_action.steps[0].metamagic, null);
    assert.equal(Object.hasOwn(schema.parse(request({})).combat_action.steps[0], 'metamagic'), false);
  });
  test(`${name} rejects unknown or coercible metamagic selectors`, () => {
    for (const value of [true,false,0,1,'true','Quickened Spell',[],{}])
      assert.equal(schema.safeParse(request({metamagic:value})).success, false, JSON.stringify(value));
  });
}
