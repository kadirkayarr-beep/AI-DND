import assert from 'node:assert/strict';
import {test} from 'node:test';
import {PlayGameTurnBody,PlayLegacyTurnBody} from '../../../lib/api-zod/src/generated/api.ts';
const value={message:'Takla atıyorum',interaction_mode:'do',check_feature:'primal_knowledge'};
test('generated turn parsers retain explicit and null Primal Knowledge consent',()=>{
 for(const parser of [PlayGameTurnBody,PlayLegacyTurnBody]){
  assert.deepEqual(parser.parse(value),value);
  assert.deepEqual(parser.parse({...value,check_feature:null}),{...value,check_feature:null});
  assert.deepEqual(parser.parse({message:'Takla atıyorum'}),{message:'Takla atıyorum'});
 }
});
test('generated turn parsers reject malformed feature and client mechanics',()=>{
 for(const parser of [PlayGameTurnBody,PlayLegacyTurnBody]){
  for(const check_feature of [true,false,'other',1,{},[]])assert.equal(parser.safeParse({...value,check_feature}).success,false);
  for(const field of ['skill','dc','ability','modifier','check_evidence'])assert.equal(parser.safeParse({...value,[field]:1}).success,false);
 }
});

import {readFileSync} from 'node:fs';
import {PlayGameTurnResponse} from '../../../lib/api-zod/src/generated/api.ts';
const receipt=JSON.parse(readFileSync(new URL('../../../ai-dnd/api/tests/fixtures/c10_pre_primal_http_receipt.json',import.meta.url),'utf8')).response;
// Deliberately scoped to these generated nodes. The prechange full-response
// location/door mismatch is separately retained in the external Task 2 evidence.
const card = PlayGameTurnResponse.shape.skill_check_result;
const projection = PlayGameTurnResponse.shape.state.shape.character.shape.primal_knowledge_check;
test('generated card and projection nodes retain feature fields and preserve ordinary absence',()=>{
 const original=card.parse(receipt.skill_check_result);
 assert.deepEqual(original,receipt.skill_check_result);
 assert.equal('check_feature' in original,false);
 assert.equal(projection.parse(undefined),undefined);
 const annotated={...receipt.skill_check_result,ability:'strength',check_feature:'primal_knowledge',original_ability:'dexterity'};
 assert.deepEqual(card.parse(annotated),annotated);
 const availability={available:true,reason:null,skills:['Acrobatics','Intimidation','Perception','Stealth','Survival']};
 assert.deepEqual(projection.parse(availability),availability);
 for(const bad of ['other',true])assert.equal(card.safeParse({...annotated,check_feature:bad}).success,false);
 assert.equal(card.safeParse({...annotated,original_ability:'strength'}).success,false);
 assert.equal(projection.safeParse({...availability,skills:['Athletics']}).success,false);
});
