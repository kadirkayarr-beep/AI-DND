import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ApplyGameSessionLevelUpBody} from '../../../lib/api-zod/src/generated/api.ts';
const base={action_id:'22222222-2222-4222-8222-222222222222',campaign_id:'11111111-1111-4111-8111-111111111111',expected_revision:7};
const rows=[[2,{}],[2,{prepared_spells:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell']}],[3,{prepared_spells:['Disguise Self','Detect Magic'],subclass_id:'phb2024:subclass:sorcerer:aberrant-sorcery'}],[4,{prepared_spells:['Mage Armor'],cantrips:['Shocking Grasp'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}}],[5,{prepared_spells:['Fog Cloud','Silent Image']}]];
test('actual generated levelup validator retains every valid2/3/4/5 choice field',()=>{for(const [target_level,choices] of rows){const body={...base,target_level,choices};assert.deepEqual(ApplyGameSessionLevelUpBody.parse(body),body);}});
test('actual generated empty noncaster branch rejects nonempty JSON objects and null',()=>{for(const choices of [{forged:true},{prepared_spells:[]},{metamagic:[]},null,{...rows[1][1],extra:true}])assert.equal(ApplyGameSessionLevelUpBody.safeParse({...base,target_level:2,choices}).success,false,JSON.stringify(choices));});
