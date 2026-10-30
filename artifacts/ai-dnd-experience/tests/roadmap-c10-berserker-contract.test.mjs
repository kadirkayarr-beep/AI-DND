import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ApplyGameSessionLevelUpBody,CreateCampaignBody} from '../../../lib/api-zod/src/generated/api.ts';
const base={action_id:'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c',campaign_id:'abf0ccf8-3b08-4fd7-b657-4a2324ed6dc0',expected_revision:1,target_level:3};
const pick={subclass_id:'berserker',primal_knowledge_skill:'Survival'};
test('earned Berserker preserves exact canonical skill choices',()=>{
 for(const skill of ['Animal Handling','Athletics','Intimidation','Nature','Perception','Survival']){
  const choices={...pick,primal_knowledge_skill:skill};
  assert.deepEqual(ApplyGameSessionLevelUpBody.parse({...base,choices}).choices,choices);
 }
});
test('earned Berserker rejects aliases null extra caster fields and wrong scalars',()=>{
 for(const choices of [{...pick,subclass_id:'Berserker'},{...pick,subclass_id:null},{...pick,primal_knowledge_skill:'survival'},
 {...pick,primal_knowledge_skill:null},{...pick,primal_knowledge_skill:true},{...pick,primal_knowledge_skill:['Survival']},
 {subclass_id:'berserker'},{...pick,prepared_spells:[]},{...pick,unknown:null}])assert.equal(ApplyGameSessionLevelUpBody.safeParse({...base,choices}).success,false);
});
test('existing empty Barbarian2 and CON ASI payloads retain old shapes',()=>{
 assert.deepEqual(ApplyGameSessionLevelUpBody.parse({...base,target_level:2,choices:{}}).choices,{});
 const choices={prepared_spells:['Mage Armor'],cantrips:['Shocking Grasp'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}};
 assert.deepEqual(ApplyGameSessionLevelUpBody.parse({...base,target_level:4,choices}).choices,choices);
});
test('start-3 creation body accepts exactly the empty step 2 plus the canonical step 3 and nothing looser',()=>{
 const body=(level_choices,starting_level=3)=>CreateCampaignBody.safeParse({character:{mode:'custom',class:'Barbarian',starting_level,level_choices}});
 assert.equal(body({'2':{},'3':pick}).success,true);
 // The level/choices pairing (e.g. {'2':{}} with start 3) is a server-side cross-field rule covered by the Python HTTP tests.
 for(const level_choices of [{'3':pick},{'2':{},'3':{}},{'2':{},'3':{subclass_id:'berserker'}},{'2':{},'3':{...pick,prepared_spells:[]}},
   {'2':{},'3':{...pick,subclass_id:'Berserker'}},{'2':{},'3':{...pick,primal_knowledge_skill:'Arcana'}},{'2':{},'3':null}])assert.equal(body(level_choices).success,false,JSON.stringify(level_choices));
});
