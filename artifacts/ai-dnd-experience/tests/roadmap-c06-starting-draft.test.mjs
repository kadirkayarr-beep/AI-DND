import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {CreateCampaignBody} from '../../../lib/api-zod/src/generated/api.ts';
const target = new URL('../src/lib/sorcerer-starting-creation.ts', import.meta.url);
// Only target absence is handled. Unrelated import/dependency errors still fail the harness.
const subject = existsSync(fileURLToPath(target)) ? await import(target.href) : {};
const fn = (name) => { assert.equal(typeof subject[name], 'function', `Missing helper export: ${name}`); return subject[name]; };
const ids = ['Magic Missile','Shield','Burning Hands','Chromatic Orb','Disguise Self','Detect Magic','Chaos Bolt'];
const raw = () => ({supported_starting_levels:[1,2,3],level_2:{prepared_spell_count:2,prepared_spell_ids:[...ids],metamagic_count:2,metamagic_options:['Quickened Spell','Twinned Spell','Careful Spell']},level_3:{prepared_spell_count:2,prepared_spell_ids:[...ids],subclass_options:[{id:'aberrant',name:'Aberrant'},{id:'draconic',name:'Draconic'}]},effects_pending_by_level:{'1':['Innate'],'2':['Font','Metamagic'],'3':['Subclass']}});
const metadata = () => fn('readStartingCreationOptions')(raw());
const initial = ['Magic Missile','Shield'];
const full = () => ({startingLevel:3,level2Prepared:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell'],level3Prepared:['Disguise Self','Detect Magic'],subclassId:'aberrant'});

test('fixed metadata is validated and detached; fallback never grants progression',()=>{
 const source=raw(), before=structuredClone(source); const parsed=fn('readStartingCreationOptions')(source);
 assert.deepEqual(parsed, source);parsed.level_2.prepared_spell_ids.push('mutation');assert.deepEqual(source,before);
 for(const value of [undefined,null,{}, {...raw(),supported_starting_levels:[1,2,3,4]}, {...raw(),level_2:null}]) assert.equal(fn('readStartingCreationOptions')(value),undefined);
 for(const mode of ['count','duplicate-id','duplicate-name','pending-key','empty-name']) {
  const value=raw();
  if(mode==='count')value.level_2.prepared_spell_count=3;
  if(mode==='duplicate-id')value.level_3.subclass_options[1].id='aberrant';
  if(mode==='duplicate-name')value.level_2.metamagic_options=['Quickened Spell','Quickened Spell'];
  if(mode==='pending-key')value.effects_pending_by_level={'level_1':[],'2':[],'3':[]};
  if(mode==='empty-name')value.level_3.subclass_options[0].name='';
  assert.equal(fn('readStartingCreationOptions')(value),undefined,mode);
 }
});

test('level changes are pure, never auto-pick, and clear only unearned sections',()=>{
 const empty=fn('emptyStartingDraft')();assert.deepEqual(empty,{startingLevel:1,level2Prepared:[],metamagic:[],level3Prepared:[],subclassId:''});
 assert.equal(fn('validateStartingDraft')('Sorcerer',empty,[],undefined).ok,true);
 const up=fn('changeStartingLevel')(empty,3);assert.equal(up.startingLevel,3);assert.deepEqual(up.level2Prepared,[]);assert.equal(up.subclassId,'');
 const source=full(), before=structuredClone(source);const two=fn('changeStartingLevel')(source,2);
 assert.deepEqual(two.level2Prepared,source.level2Prepared);assert.deepEqual(two.metamagic,source.metamagic);assert.deepEqual(two.level3Prepared,[]);assert.equal(two.subclassId,'');
 assert.deepEqual(fn('changeStartingLevel')(source,1),empty);assert.deepEqual(source,before);
 assert.throws(()=>fn('changeStartingLevel')(source,6));
});

test('missing live source retains draft/reference, blocks high submit, allows explicit downgrade',()=>{
 const draft=full();assert.equal(fn('pruneStartingDraft')(draft,initial,undefined),draft);
 assert.equal(fn('validateStartingDraft')('Sorcerer',draft,initial,undefined).ok,false);
 assert.equal(fn('startingCreationFields')('Sorcerer',draft,initial,undefined).ok,false);
 const low=fn('changeStartingLevel')(draft,1);
 assert.deepEqual(fn('startingCreationFields')('Sorcerer',low,initial,undefined),{ok:true,fields:{}});
});

test('available spells and pruning exclude conflicts without auto replacements or mutation',()=>{
 const meta=metadata(), draft=full(), before=structuredClone(draft), source=structuredClone(meta);
 const available=fn('availableStartingSpells')(meta,initial,draft);
 assert.deepEqual(available.level2,['Burning Hands','Chromatic Orb','Disguise Self','Detect Magic','Chaos Bolt']);
 assert.deepEqual(available.level3,['Disguise Self','Detect Magic','Chaos Bolt']);
 assert.equal(fn('pruneStartingDraft')(draft,initial,meta),draft,'stable result must not loop React effects');
 const edited=fn('pruneStartingDraft')(draft,['Magic Missile','Burning Hands'],meta);
 assert.deepEqual(edited.level2Prepared,['Chromatic Orb']);assert.deepEqual(edited.level3Prepared,draft.level3Prepared);
 const conflict=full();conflict.level2Prepared=['Disguise Self','Chromatic Orb'];
 assert.deepEqual(fn('pruneStartingDraft')(conflict,initial,meta).level3Prepared,['Detect Magic']);
 const stale=full();stale.metamagic.push('Not available');stale.subclassId='unknown';
 const pruned=fn('pruneStartingDraft')(stale,initial,meta);assert.deepEqual(pruned.metamagic,full().metamagic);assert.equal(pruned.subclassId,'');
 assert.deepEqual(draft,before);assert.deepEqual(meta,source);
});

test('valid typed numeric payload survives generated validator and is detached',()=>{
 const meta=metadata(), draft=full();const result=fn('startingCreationFields')('Sorcerer',draft,initial,meta);
 assert.equal(result.ok,true);assert.deepEqual(result.fields,{starting_level:3,level_choices:{'2':{prepared_spells:draft.level2Prepared,metamagic:draft.metamagic},'3':{prepared_spells:draft.level3Prepared,subclass_id:'aberrant'}}});
 const parsed=CreateCampaignBody.parse({character:{mode:'custom',name:'Vael',species:'Human',class:'Sorcerer',spells:initial,...result.fields}}).character;
 assert.deepEqual(parsed.level_choices,result.fields.level_choices);assert.deepEqual(parsed.spells,initial);
 result.fields.level_choices['2'].prepared_spells.push('client edit');assert.deepEqual(draft.level2Prepared,full().level2Prepared);
 const two=fn('changeStartingLevel')(draft,2);assert.deepEqual(Object.keys(fn('startingCreationFields')('Sorcerer',two,initial,meta).fields.level_choices),['2']);
 assert.deepEqual(fn('startingCreationFields')('Fighter',fn('emptyStartingDraft')(),[],undefined),{ok:true,fields:{}});
 assert.equal(fn('startingCreationFields')('Fighter',draft,initial,meta).ok,false);
});

test('submit rejects stale, conflicting, duplicate and unavailable choices without relying on pruning',()=>{
 const meta=metadata();
 for(const mode of ['stale-three','cross-level','duplicate','unknown-meta','unknown-subclass','missing-choice','unknown-initial']) {
  const draft=full();let base=initial;
  if(mode==='stale-three')draft.startingLevel=2;
  if(mode==='cross-level')draft.level3Prepared=['Burning Hands','Detect Magic'];
  if(mode==='duplicate')draft.level2Prepared=['Burning Hands','Burning Hands'];
  if(mode==='unknown-meta')draft.metamagic=['Not available','Twinned Spell'];
  if(mode==='unknown-subclass')draft.subclassId='missing';
  if(mode==='missing-choice')draft.level3Prepared=[];
  if(mode==='unknown-initial')base=['Unknown spell','Shield'];
  const before=structuredClone(draft);
  assert.equal(fn('validateStartingDraft')('Sorcerer',draft,base,meta).ok,false,mode);
  const fields=fn('startingCreationFields')('Sorcerer',draft,base,meta);assert.equal(fields.ok,false,mode);assert.ok(fields.message);
  assert.deepEqual(draft,before);
 }
});
