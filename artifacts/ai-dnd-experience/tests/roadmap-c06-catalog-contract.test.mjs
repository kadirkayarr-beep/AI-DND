import assert from 'node:assert/strict';
import {test} from 'node:test';
import {GetCharacterCreationCatalogResponse, GetLegacyCharacterCreationCatalogResponse} from '../../../lib/api-zod/src/generated/api.ts';
const base = {races:{},classes:{},backgrounds:{},ability_score_methods:[],alignments:[],origin_feats:{},spells_catalog:{},skills:{},equipment_rules:{}};
// Synthetic structural catalogue; live option mechanics are backend-owned.
import {metadata as options} from './fixtures/c06-starts45-metadata.mjs';
for (const [name,schema] of [['canonical',GetCharacterCreationCatalogResponse],['legacy',GetLegacyCharacterCreationCatalogResponse]]) {
 test(`${name} catalog preserves source-owned metadata and numeric pending keys`,()=>{
   assert.deepEqual(schema.parse({...base,sorcerer_starting_creation:options}).sorcerer_starting_creation,options);
   assert.equal(schema.parse(base).sorcerer_starting_creation,undefined);
   assert.equal(schema.parse({...base,sorcerer_starting_creation:null}).sorcerer_starting_creation,null);
 });
 test(`${name} advertised bundle rejects missing or null required nested fields`,()=>{
   for(const field of ['level_2','level_3','level_4','level_5','effects_pending_by_level']) {
     const missing=structuredClone(options);delete missing[field];
     assert.equal(schema.safeParse({...base,sorcerer_starting_creation:missing}).success,false);
     assert.equal(schema.safeParse({...base,sorcerer_starting_creation:{...options,[field]:null}}).success,false);
   }
   const wrong=structuredClone(options);wrong.effects_pending_by_level['level_1']=wrong.effects_pending_by_level['1'];delete wrong.effects_pending_by_level['1'];
   assert.equal(schema.safeParse({...base,sorcerer_starting_creation:wrong}).success,false);
 });
}
