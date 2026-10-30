import assert from 'node:assert/strict';
import { test } from 'node:test';
import { PlayGameTurnBody, PlayLegacyTurnBody } from '../../../lib/api-zod/src/generated/api.ts';
for (const [name, schema] of [['canonical',PlayGameTurnBody],['legacy',PlayLegacyTurnBody]]) {
  test(`${name} retains explicit bounded Rage Bonus commands`, () => {
    for (const kind of ['activate_rage','extend_rage']) {
      const parsed = schema.parse({message:'Rage',combat_action:{steps:[{kind,resource:'bonus'}]}});
      assert.equal(parsed.combat_action.steps[0].kind, kind);
      assert.equal(parsed.combat_action.steps[0].resource, 'bonus');
    }
  });
  test(`${name} retains historical ordinary action defaults`, () => {
    const parsed = schema.parse({message:'Dash',combat_action:{steps:[{kind:'dash'}]}});
    assert.equal(parsed.combat_action.steps[0].resource,'action');
  });
}
