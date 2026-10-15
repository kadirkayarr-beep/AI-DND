import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { RETRY_MESSAGE, ReconciliationError } from '../src/lib/action-reconciliation.ts';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
const python = process.env.PYTHON || 'python';
// Synthetic in-memory character states; no database, requests, model or gameplay grants.
// Each supplied snapshot traverses the production API serializer. This is not gameplay/save acceptance.
const fixtureProgram = String.raw`
import contextlib, copy, io, json
with contextlib.redirect_stdout(io.StringIO()):
 import game
 from api.serializers import serialize_session_state
 cases={}
 def emit(name, species, **fields):
  s=game.GameSession(seed=1729)
  s.character.update({'name':'Synthetic renderer','species':species,'race':species,'class':'Fighter','strength':16,'dexterity':14,'constitution':14,'intelligence':10,'wisdom':12,'charisma':10,'proficient_skills':[],'level':1,'proficiency_bonus':2,'max_hp':20,'current_hp':10,'armor_class':12})
  snapshot=s.serialize_game_state()
  snapshot['player'].update(fields)
  class SuppliedSnapshot:
   character=snapshot['player']
   world_state=snapshot['world_state']
   def serialize_game_state(self): return copy.deepcopy(snapshot)
   def quest_offers(self): return []
  cases[name]={'input':copy.deepcopy(snapshot['player']),'state':serialize_session_state(SuppliedSnapshot())}
 emit('human','Human',origin='Neverwinter test origin',origin_feat='Tough',species_bonus_feat='Skilled',species_bonus_skills=['Insight'])
 emit('empty','Human',origin='',origin_feat=None,species_bonus_feat=None,species_bonus_skills=[])
 emit('aasimar','Aasimar',level=3,species_trait_state={'healing_hands_uses_remaining':2,'celestial_revelation_uses_remaining':0,'active_celestial_form':'inner_radiance','celestial_revelation_turns_remaining':7})
 emit('cloud','Goliath',level=5,giant_ancestry='cloud',species_trait_state={'giant_ancestry_uses_remaining':2,'large_form_uses_remaining':0,'large_form_turns_remaining':6})
 emit('unselected','Goliath',level=5,giant_ancestry=None,species_trait_state={'giant_ancestry_uses_remaining':2,'large_form_uses_remaining':1,'large_form_turns_remaining':0})
 for ancestry in ('fire','frost','hill','stone','storm'):
  for armed in (False,True):
   emit(ancestry+str(armed),'Goliath',level=5,giant_ancestry=ancestry,species_trait_state={'giant_ancestry_uses_remaining':3,'giant_ancestry_armed':armed,'large_form_uses_remaining':1})
 emit('orc','Orc',species_trait_state={'adrenaline_rush_uses_remaining':1,'temporary_hit_points':5,'relentless_endurance_available':False})
 emit('half-orc','Half-Orc',species_trait_state={'relentless_endurance_available':False})
print(json.dumps(cases,ensure_ascii=True))
`;
let vite, cases, reveal, traits;
before(async()=>{
 cases=JSON.parse(execFileSync(python,['-B','-c',fixtureProgram],{cwd:path.resolve('../../ai-dnd'),encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}}));
 const { createServer }=await import('vite');
 vite=await createServer({configFile:path.resolve('vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent',plugins:[{name:'test-only-reveal-export',enforce:'pre',transform(code,id){if(id.replaceAll('\\','/').endsWith('/src/pages/game-browser.tsx'))return code+'\nexport { CharacterReveal as TestCharacterReveal };';}}]});
 const { TestCharacterReveal }=await vite.ssrLoadModule('/src/pages/game-browser.tsx');
 const { SpeciesTraitControls }=await vite.ssrLoadModule('/src/components/species-trait-controls.tsx');
 const React=await import('react');const {renderToStaticMarkup}=await import('react-dom/server');
 const { QueryClient,QueryClientProvider }=await import('@tanstack/react-query');
 reveal=state=>renderToStaticMarkup(React.createElement(TestCharacterReveal,{state,onContinue(){},onBack(){}}));
 traits=state=>renderToStaticMarkup(React.createElement(QueryClientProvider,{client:new QueryClient()},React.createElement(SpeciesTraitControls,{state,sessionId:'synthetic'})));
});
after(async()=>{
 if(process.env.CONDITIONAL_RENDER_EVIDENCE && cases && reveal && traits){
  await writeFile(process.env.CONDITIONAL_RENDER_EVIDENCE,JSON.stringify({synthetic:true,boundary:'supplied snapshot -> production API serializer -> actual SSR component',cases,html:Object.fromEntries(Object.entries(cases).map(([name,c])=>[name,(name==='human'||name==='empty'?reveal:traits)(c.state)]))},null,2));
 }
 await vite?.close();
});
function exact(name,keys){const c=cases[name];for(const key of keys)assert.deepEqual(c.state.character[key],c.input[key],`${name}.${key}: serializer truth`);return c.state;}
function renderWithoutMutation(render,state){const before=JSON.stringify(state);const html=render(state);assert.equal(JSON.stringify(state),before);return html;}
test('Human postcommit reveal renders serialized origin, separate feats and bonus skill; empty values grant nothing',()=>{
 const state=exact('human',['origin','origin_feat','species_bonus_feat','species_bonus_skills']);
 const html=renderWithoutMutation(reveal,state);
 for(const [id,value] of [['reveal-character-origin','Neverwinter test origin'],['reveal-background-origin-feat','Geçmiş: Tough'],['reveal-species-bonus-feat','Tür: Skilled'],['reveal-species-bonus-skills','Insight']]){
  assert.ok(html.includes(`data-testid="${id}"`));assert.ok(html.includes(value),value);
 }
 const empty=renderWithoutMutation(reveal,exact('empty',['origin','origin_feat','species_bonus_feat','species_bonus_skills']));
 for(const id of ['reveal-character-origin','reveal-character-origin-feats','reveal-species-bonus-skills'])assert.ok(!empty.includes(`data-testid="${id}"`));
});
test('Aasimar active duration and exact resource counts follow serialized trait state',()=>{
 const html=renderWithoutMutation(traits,exact('aasimar',['species_trait_state']));
 assert.match(html,/Şifa Veren Eller · 2 kullanım/);assert.match(html,/Göksel Tecelli · 0 kullanım · 7 tur etkin/);
 assert.match(html,/data-testid="species-action-celestial-revelation"[^>]*disabled/);
});
test('Goliath cloud, unselected ancestry and active large-form duration are distinct serialized branches',()=>{
 const cloud=renderWithoutMutation(traits,exact('cloud',['giant_ancestry','species_trait_state']));
 assert.match(cloud,/Dev Atası: Bulut Devi · 2 kullanım/);assert.match(cloud,/species-action-cloud-jaunt/);assert.match(cloud,/6 tur etkin/);assert.doesNotMatch(cloud,/species-action-arm-giant-ancestry/);
 const unselected=renderWithoutMutation(traits,exact('unselected',['giant_ancestry','species_trait_state']));
 assert.match(unselected,/species-action-choose-giant-ancestry/);assert.doesNotMatch(unselected,/species-action-cloud-jaunt|species-action-arm-giant-ancestry|tur etkin/);
});
test('all five supplied attack ancestries retain armed and unarmed presentation',()=>{
 for(const ancestry of ['fire','frost','hill','stone','storm'])for(const armed of [false,true]){
  const state=exact(ancestry+(armed?'True':'False'),['giant_ancestry','species_trait_state']);
  const html=renderWithoutMutation(traits,state);assert.match(html,/species-action-arm-giant-ancestry/);
  assert.ok(html.includes(armed?'Dev Atası etkisini hazır beklemeden çıkar':'Dev Atası etkisini hazırla'));assert.match(html,/3 kullanım/);assert.doesNotMatch(html,/species-action-cloud-jaunt/);
 }
});
test('Orc temporary HP and spent endurance, and Half-Orc endurance-only, preserve supplied values',()=>{
 const orc=renderWithoutMutation(traits,exact('orc',['species_trait_state']));assert.match(orc,/1 kullanım · 5 geçici can/);assert.match(orc,/uzun dinlenmeye kadar kullanıldı/);
 const half=renderWithoutMutation(traits,exact('half-orc',['species_trait_state']));assert.match(half,/uzun dinlenmeye kadar kullanıldı/);assert.doesNotMatch(half,/species-action-adrenaline-rush|geçici can/);
});
test('retry copy has exact Turkish Unicode and real failure consumers retain the shared text',async()=>{
 const expected='Güncel durum doğrulanamadı. Aynı işlemi yeniden dene; kayıtlı işlem kimliği korunuyor.';
 assert.equal(RETRY_MESSAGE,expected);assert.equal(new ReconciliationError().message,expected);
 const source=await readFile('src/components/species-trait-controls.tsx','utf8');
 assert.match(source,/setFailure\(RETRY_MESSAGE\)/);assert.match(source,/role="alert">\{failure\}/);
});
