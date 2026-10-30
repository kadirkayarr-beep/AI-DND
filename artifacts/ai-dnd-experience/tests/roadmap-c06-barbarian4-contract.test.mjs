import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ApplyGameSessionLevelUpBody,CreateCampaignBody,CreateLegacyCampaignBody} from '../../../lib/api-zod/src/generated/api.ts';
const base={action_id:'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c',campaign_id:'abf0ccf8-3b08-4fd7-b657-4a2324ed6dc0',expected_revision:3,target_level:4};
const pick=increase=>({asi:{feat:'Ability Score Improvement',increase}});
const patterns=[{strength:2},{constitution:2},{intelligence:2},{wisdom:2},{charisma:2},{strength:1,constitution:1},{strength:1,intelligence:1},{strength:1,wisdom:1},{strength:1,charisma:1},{constitution:1,intelligence:1},{constitution:1,wisdom:1},{constitution:1,charisma:1},{intelligence:1,wisdom:1},{intelligence:1,charisma:1},{wisdom:1,charisma:1}];
test('generated earned Barbarian4 accepts and exactly retains all15 sole-ASI shapes',()=>{for(const increase of patterns){const body={...base,choices:pick(increase)};assert.deepEqual(ApplyGameSessionLevelUpBody.parse(body),body);}});
test('generated sole-ASI rejects caster/null/extra/aliases and invalid patterns rather than stripping',()=>{
 for(const choices of [null, {...pick({constitution:2}),cantrips:[]},{...pick({constitution:2}),prepared_spells:[]},{...pick({constitution:2}),extra:null},{asi:null},...[{dexterity:3},{CON:2},{constitution:'2'},{constitution:true},{constitution:1},{constitution:2,strength:1},{constitution:1,strength:1,wisdom:1}].map(pick)])assert.equal(ApplyGameSessionLevelUpBody.safeParse({...base,choices}).success,false,JSON.stringify(choices));
});
test('ordinary Sorcerer4 three-field body is unchanged and Barbarian start-4 creation takes only the exact sole-ASI step',()=>{
 const choices={prepared_spells:['Mage Armor'],cantrips:['Shocking Grasp'],...pick({constitution:2})};assert.deepEqual(ApplyGameSessionLevelUpBody.parse({...base,choices}),{...base,choices});
 // Superseded: Barbarian creation at 4/5 is public now (roadmap-c06-barbarian-start45-ui); only the exact shapes parse.
 const three={'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'}};
 for(const schema of [CreateCampaignBody,CreateLegacyCampaignBody]){
  const parse=(level_choices,starting_level=4)=>schema.safeParse({character:{mode:'custom',class:'Barbarian',starting_level,level_choices}});
  assert.equal(parse({...three,'4':pick({constitution:2})}).success,true);
  assert.equal(parse({...three,'4':pick({constitution:2}),'5':{}},5).success,true);
  assert.deepEqual(parse({...three,'4':pick({strength:1,wisdom:1})}).data.character.level_choices['4'],pick({strength:1,wisdom:1}));
  for(const bad of [{...three,'4':{}},{...three,'4':{...pick({constitution:2}),cantrips:[]}},{...three,'4':{...pick({constitution:2}),prepared_spells:[]}},{...three,'4':pick({dexterity:3})},{...three,'4':{asi:null}},{...three,'4':null},{...three,'4':pick({constitution:2}),'5':{extra:1}},{...three,'4':pick({constitution:2}),'6':{}}])
   assert.equal(parse(bad,bad['5']?5:4).success,false,JSON.stringify(bad));
 }
});
