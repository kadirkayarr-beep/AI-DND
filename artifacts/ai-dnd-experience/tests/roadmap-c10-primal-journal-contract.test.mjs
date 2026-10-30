import assert from 'node:assert/strict';
import {test} from 'node:test';
import {PlayGameTurnResponse,PlayLegacyTurnResponse,PlayGameTurnParams,PlayLegacyTurnParams} from '../../../lib/api-zod/src/generated/api.ts';

// Ordinary populated JSON journal: every pre-existing date-time field is a
// wire string, never a Date produced by browser-side state mutation.
export const journal={
 schema_version:1,
 discovered_locations:[{location_id:'tavern',name:'Taverna',environment:'tavern',first_discovered_at:'2026-10-29T16:00:00Z',last_visited_at:'2026-10-29T17:00:00Z',first_discovered_turn:1,last_visited_turn:2,visit_count:2}],
 known_npcs:[{npc_id:'npc_001',name:'Marek',role:'Barmen',first_met_at:'2026-10-29T16:01:00Z',last_seen_at:'2026-10-29T17:01:00Z',first_met_turn:1,last_seen_turn:2,last_known_location_id:'tavern',last_known_location:'Taverna'}],
 notable_events:[{event_id:'5df78dbd-3908-4a4d-bd91-1888fe1ccc0c',event_type:'npc_met',created_at:'2026-10-29T16:02:00Z',turn_index:1,summary:'Marek ile tanıştın.',location_id:'tavern',location_name:'Taverna',related_npc_id:'npc_001',related_item:null}],
 quests:[{quest_id:'abf0ccf8-3b08-4fd7-b657-4a2324ed6dc0',title:'Kayıt',description:'Kayıt tamamlandı.',status:'completed',giver_npc_id:'npc_001',objectives:[],created_at:'2026-10-29T16:03:00Z',updated_at:'2026-10-29T17:03:00Z',completed_at:'2026-10-29T17:04:00Z'}],
};
export const dateFields={discovered_locations:['first_discovered_at','last_visited_at'],known_npcs:['first_met_at','last_seen_at'],notable_events:['created_at'],quests:['created_at','updated_at','completed_at']};
for(const [name,response] of [['canonical',PlayGameTurnResponse],['legacy',PlayLegacyTurnResponse]]){
 test(`${name} ordinary populated journal preserves all eight ISO timestamp coercions`,()=>{
  const parser=response.shape.state.shape.journal;
  const parsed=parser.safeParse(journal);
  assert.equal(parsed.success,true,JSON.stringify(parsed.error?.issues));
  const expected=structuredClone(journal);
  for(const [collection,fields] of Object.entries(dateFields))for(const field of fields)expected[collection][0][field]=new Date(journal[collection][0][field]);
  assert.deepEqual(parsed.data,expected);
  const active=structuredClone(journal);active.quests[0].completed_at=null;
  assert.equal(parser.parse(active).quests[0].completed_at,null);
  for(const [collection,fields] of Object.entries(dateFields))for(const field of fields){
   const invalid=structuredClone(journal);invalid[collection][0][field]='not-a-timestamp';
   assert.equal(parser.safeParse(invalid).success,false,`${collection}.${field}`);
  }
 });
}
for(const [name,parser] of [['canonical',PlayGameTurnParams],['legacy',PlayLegacyTurnParams]]){
 test(`${name} session parameter retains inherited string coercion`,()=>{
  const id='5df78dbd-3908-4a4d-bd91-1888fe1ccc0c';
  assert.equal(parser.parse({session_id:new String(id)}).session_id,id);
 });
}
