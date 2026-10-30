import assert from 'node:assert/strict';
import {test} from 'node:test';
import {CreateCampaignBody} from '../../../lib/api-zod/src/generated/api.ts';
const barb={mode:'custom',class:'Barbarian',starting_level:2,level_choices:{'2':{}}};
const two={prepared_spells:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell']};
const three={prepared_spells:['Disguise Self','Detect Magic'],subclass_id:'phb2024:subclass:sorcerer:aberrant-sorcery'};
const four={prepared_spells:['Mage Armor'],cantrips:['Shocking Grasp'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}};
const five={prepared_spells:['Fog Cloud','Silent Image']};
test('actual generated creation parser retains exact Barbarian2 and Sorcerer1–5 fields',()=>{
  assert.deepEqual(CreateCampaignBody.parse({character:barb}).character.level_choices,{'2':{}});
  for(let level=1;level<=5;level++){
    const level_choices=Object.fromEntries(Object.entries({'2':two,'3':three,'4':four,'5':five}).filter(([k])=>Number(k)<=level));
    const value={mode:'custom',class:'Sorcerer',starting_level:level,...(level>1?{level_choices}:{})};
    assert.deepEqual(CreateCampaignBody.parse({character:value}).character,value);
  }
});
test('actual generated empty Barbarian bundle cannot strip nonempty JSON or extra aliases',()=>{
  for(const level_choices of [{'2':{forged:true}},{'2':{},'3':{}},{'2':{},forged:true},{'2':null},{level_2:{}}])
    assert.equal(CreateCampaignBody.safeParse({character:{...barb,level_choices}}).success,false,JSON.stringify(level_choices));
});
