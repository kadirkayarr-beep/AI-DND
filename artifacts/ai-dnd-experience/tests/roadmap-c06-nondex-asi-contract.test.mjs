import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApplyGameSessionLevelUpBody, CreateCampaignBody, CreateLegacyCampaignBody } from '../../../lib/api-zod/src/generated/api.ts';
const patterns = [
 {strength:2},{dexterity:2},{constitution:2},{intelligence:2},{wisdom:2},{charisma:2},
 {strength:1,dexterity:1},{strength:1,constitution:1},{strength:1,intelligence:1},{strength:1,wisdom:1},{strength:1,charisma:1},
 {dexterity:1,constitution:1},{dexterity:1,intelligence:1},{dexterity:1,wisdom:1},{dexterity:1,charisma:1},
 {constitution:1,intelligence:1},{constitution:1,wisdom:1},{constitution:1,charisma:1},
 {intelligence:1,wisdom:1},{intelligence:1,charisma:1},{wisdom:1,charisma:1},
];
const malformed = [{}, {dexterity:3}, {dexterity:1}, {dexterity:'2'}, {CHA:2}, {charisma:'2'}, {charisma:2.0,unknown:1}, {charisma:1},
 {charisma:true,wisdom:1}, {charisma:null,wisdom:1}, {charisma:1.5,wisdom:0.5},
 {charisma:2,wisdom:1}, {strength:1,wisdom:1,charisma:1}, {charisma:2,dexterity:null},
 {constitution:2,charisma:0}, {charisma:3}, {wisdom:1,charisma:-1}];
const choice = (increase) => ({prepared_spells:['Mage Armor'],cantrips:['Shocking Grasp'],asi:{feat:'Ability Score Improvement',increase}});
const wrappers = [
 ['earned',ApplyGameSessionLevelUpBody,(increase)=>({action_id:'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c',campaign_id:'abf0ccf8-3b08-4fd7-b657-4a2324ed6dc0',expected_revision:1,target_level:4,choices:choice(increase)}),(r)=>r.choices.asi.increase],
 ...[['create',CreateCampaignBody],['legacy-create',CreateLegacyCampaignBody]].map(([name,schema])=>[
 name,schema,(increase)=>({character:{mode:'custom',class:'Sorcerer',starting_level:4,level_choices:{
 '2':{prepared_spells:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell']},
 '3':{prepared_spells:['Disguise Self','Detect Magic'],subclass_id:'phb2024:subclass:sorcerer:aberrant-sorcery'},'4':choice(increase)}}}),
 (r)=>r.character.level_choices['4'].asi.increase])
];
for (const [name,schema,request,read] of wrappers) {
 test(`${name} generated parser preserves all twenty-one exact patterns`,()=>{
  for(const pattern of patterns) assert.deepEqual(read(schema.parse(request(pattern))),pattern);
 });
 test(`${name} generated parser rejects malformed/alias/split/extra fields`,()=>{
  for(const pattern of malformed) assert.equal(schema.safeParse(request(pattern)).success,false,JSON.stringify(pattern));
 });
}
