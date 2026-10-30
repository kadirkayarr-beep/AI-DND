/** Generated structural validators only; semantic/mode/keyset rules are backend-owned. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CreateCampaignBody, CreateLegacyCampaignBody } from '../../../lib/api-zod/src/generated/api.ts';
const two = {prepared_spells: ['Burning Hands', 'Chromatic Orb'], metamagic: ['Quickened Spell', 'Twinned Spell']};
const three = {prepared_spells: ['Disguise Self', 'Detect Magic'], subclass_id: 'phb2024:subclass:sorcerer:aberrant-sorcery'};
const four = {prepared_spells:['Mage Armor'],cantrips:['Ray of Frost'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}};
const five = {prepared_spells:['Fog Cloud','Silent Image']};
const request = (extra = {}) => ({character: {mode: 'custom', name: 'Vael', species: 'Human', class: 'Sorcerer', ...extra}});
for (const [name, schema] of [['canonical', CreateCampaignBody], ['legacy', CreateLegacyCampaignBody]]) {
  test(`${name} creation retains exact numeric choice keys through supported level five`, () => {
    const c = schema.parse(request({starting_level: 3, level_choices: {'2': two, '3': three}})).character;
    assert.equal(c.starting_level, 3);
    assert.deepEqual(c.level_choices, {'2': two, '3': three});
    const l2 = schema.parse(request({starting_level: 2, level_choices: {'2': two}})).character;
    assert.deepEqual(l2.level_choices, {'2': two});
    for (const level of [4,5]) {
      const level_choices = {'2':two,'3':three,'4':four,...(level===5?{'5':five}:{})};
      const higher = schema.parse(request({starting_level:level,level_choices})).character;
      assert.equal(higher.starting_level,level);
      assert.deepEqual(higher.level_choices,level_choices);
    }
  });
  test(`${name} creation omission still defaults to level one`, () => {
    assert.equal(schema.parse(request()).character.starting_level, 1);
    assert.equal(schema.parse({character: {mode: 'random'}}).character.starting_level, 1);
    assert.equal(schema.parse({}).character, undefined);
  });
  test(`${name} creation rejects primitive bounds and invalid choice counts`, () => {
    for (const starting_level of [true, 0, 6, '3', 2.5, null]) assert.equal(schema.safeParse(request({starting_level})).success, false);
    for (const prepared_spells of [[], ['Burning Hands'], ['a', 'b', 'c'], [1, 2]]) {
      assert.equal(schema.safeParse(request({starting_level: 2, level_choices: {'2': {...two, prepared_spells}}})).success, false);
    }
    assert.equal(schema.safeParse(request({starting_level: 2, level_choices: {'2': null}})).success, false);
  });
}
