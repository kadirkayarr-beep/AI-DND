import { combatStartInjection } from './support/combat-start-env.mjs';
import { primalKnowledgeInjection } from './support/primal-knowledge-env.mjs';
// Actual GameBrowser closures extracted by TypeScript AST; scripted transport is not real HTTP evidence.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {beforeEach,test} from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import {QueryClient} from '@tanstack/react-query';
import {gateInjection} from './support/state-gate-env.mjs';
import * as pending from '../src/lib/pending-action.ts';
import * as recovery from '../src/lib/action-recovery.ts';
import { historyToEntries } from '../src/lib/transcript-history.ts';
import {createActionLifetime,reconcileState,ReconciliationError,RETRY_MESSAGE} from '../src/lib/action-reconciliation.ts';
import {startDeadline,withActionDeadline,ActionDeadlineError} from '../src/lib/action-deadline.ts';
import {currentAuthEpoch,rotateAuthEpoch} from '@workspace/api-client-react/custom-fetch';
const source=await readFile(new URL('../src/pages/game-browser.tsx',import.meta.url),'utf8');
const ast=ts.createSourceFile('game-browser.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const component=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='GameBrowser');
const pick=name=>{const n=component.body.statements.find(n=>ts.isVariableStatement(n)&&n.declarationList.declarations.some(d=>d.name.getText(ast)===name));assert.ok(n,`real ${name}`);return n.getText(ast);};
const code=ts.transpileModule(['retryPendingTurn','recoveryHandlers','pendingTurnNotice','blockingMutation','submitLevelUp','serverRecovery','submitTurn'].map(pick).join('\n')+'\nsubmitLevelUpRef.current=submitLevelUp; serverRecoveryRef.current=serverRecovery; Object.assign(globalThis,{submitLevelUp,retryPendingTurn,blockingMutation,serverRecovery,submitTurn});',{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
function storage(){const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
beforeEach(()=>{globalThis.window={sessionStorage:storage(),crypto:globalThis.crypto};pending.clearPendingFallback();});
const request={campaign_id:'c',expected_revision:7,target_level:4,choices:{cantrips:['Light'],prepared_spells:['Web'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}}};
const tick=()=>new Promise(r=>setImmediate(r));
function render({owner='a',campaignId='c',sessionId='s',apply,canonical}={}){
 const calls=[],notices=[],client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}}),life=createActionLifetime();
 const env={ ...combatStartInjection(),...pending,...recovery,...gateInjection(), ...primalKnowledgeInjection(),currentAuthEpoch,rotateAuthEpoch,sessionId,campaignId,currentAccountOwner:()=>owner,LOCAL_OWNER:'local',accountWriteAllowed:()=>true,
 submitLevelUpRef:{current:null},submitTurnRef:{current:()=>calls.push('play')},serverRecoveryRef:{current:null},pendingAmbientActionRef:{current:null},notice:null,setPanelEpoch(){},PENDING_TURN_NOTICE:{title:'pending'},
 inFlightSessionsRef:{current:new Set()},undoPendingRef:{current:new Set()},undoRequestsRef:{current:new Map()},setInFlightSessions(){},turnLifetime:life,
 startDeadline,withActionDeadline,ActionDeadlineError,reconcileState,ReconciliationError,RETRY_MESSAGE,queryClient:client,
 getGetGameSessionStateQueryKey:id=>['state',id],getGetCampaignsQueryKey:()=>['campaigns'],
 applyGameSessionLevelUp:async(s,r)=>{calls.push(structuredClone(r));if(apply)return apply(s,r);return {session_id:s,action_id:r.action_id,result:{status:'applied'}};},
 getCampaign:async id=>{calls.push('canonical '+id);if(canonical)return canonical(id);return {state:{hp:30},history:null,combat_history:null};},
 setLastTurn:()=>calls.push('clearUndo'),setUndoneJustNow(){},historyToEntries,setNotice:n=>notices.push(n),friendlyError:e=>e.message,statusCode:e=>e.status,
 RECOVERY_API:{status:async(s,id)=>({action_id:id,state:'applied',response:null}),abandon:async(s,id)=>({action_id:id,state:'not_applied',detail:{not_applied:true,code:'abandoned'}})},
 state:{combat:{active:false}}, interactionMode:'do', conversationTargetId:'',combatTargetId:'npc-1',activeSessionRef:{current:sessionId},setResultCue(){},getTurnInteractionMetadata:()=>({interaction_mode:'do'}),
 setEntries(){},setCombatEntries(){},writeAdvisoryCache(){},mergeCombatHistory:v=>v,TRANSCRIPT_KEY:'t',messageRef:{current:''},setMessage(){},
 };
 vm.runInNewContext(code,env);return {env,calls,notices,client,life};
}
test('real submit duplicate clicks send one id; canonical saved state precedes slot close',async()=>{let finish;const view=render({apply:(_,r)=>new Promise(resolve=>finish=()=>resolve({session_id:'s',action_id:r.action_id,result:{status:'applied'}}))});view.env.submitLevelUp(request);view.env.submitLevelUp(request);assert.equal(view.calls.length,1);assert.equal(pending.readPending('a','c').kind,'level_up');finish();await tick();assert.equal(pending.readPending('a','c'),null);assert.equal(view.calls[1],'canonical c');assert.deepEqual(view.client.getQueryData(['state','s']),{hp:30});});
test('lost response + new render routes exact id/body to level-up, never play',async()=>{const first=render({apply:async()=>{throw Error('lost reply')}});first.env.submitLevelUp(request);await tick();const body=first.calls[0];const second=render();second.env.retryPendingTurn();await tick();assert.deepEqual(second.calls[0],body);assert.ok(!second.calls.includes('play'));assert.equal(pending.readPending('a','c'),null);});
test('applied-null recovery uses canonical campaign and failed read preserves identity',async()=>{const key=pending.createIntentKey('a','c',request,'level_up');const first=render({canonical:async()=>{throw Error('offline')}});await first.env.serverRecovery('check');assert.equal(pending.readPending('a','c').key.actionId,key.actionId);const second=render();await second.env.serverRecovery('check');assert.equal(pending.readPending('a','c'),null);assert.ok(second.calls.includes('canonical c'));assert.ok(second.calls.includes('clearUndo'));});
test('server-proven abandon closes but unknown abandon retains exact action',async()=>{const key=pending.createIntentKey('a','c',request,'level_up');const view=render();view.env.RECOVERY_API.abandon=async()=>({action_id:key.actionId,state:'unknown'});await view.env.serverRecovery('abandon');assert.equal(pending.readPending('a','c').key.actionId,key.actionId);view.env.RECOVERY_API.abandon=async()=>({action_id:key.actionId,state:'not_applied',detail:{not_applied:true,code:'abandoned'}});await view.env.serverRecovery('abandon');assert.equal(pending.readPending('a','c'),null);assert.equal(view.calls.length,0);});
test('existing play and species pending block level-up; level-up blocks competing mutation guard',async()=>{const key=pending.createIntentKey('a','c',{},'play');const view=render();view.env.submitLevelUp(request);assert.equal(view.calls.length,0);pending.closePending(key,'confirmed');window.sessionStorage.setItem('ai-dnd-turn-context:species:c:retry','{}');view.env.submitLevelUp(request);assert.equal(view.calls.length,0);window.sessionStorage.removeItem('ai-dnd-turn-context:species:c:retry');pending.createIntentKey('a','c',request,'level_up');assert.ok(view.env.blockingMutation());});
test('account epoch change and session disposal ignore delayed applied replies and keep original slot',async()=>{for(const change of ['epoch','dispose']){window.sessionStorage=storage();let finish;const view=render({apply:(_,r)=>new Promise(resolve=>finish=()=>resolve({session_id:'s',action_id:r.action_id,result:{status:'applied'}}))});view.env.submitLevelUp(request);if(change==='epoch')rotateAuthEpoch();else view.life.dispose();finish();await tick();assert.equal(view.calls.length,1);assert.equal(view.client.getQueryData(['state','s']),undefined);assert.equal(pending.readPending('a','c').kind,'level_up');const other=render({owner:'b',campaignId:'different',sessionId:'different'});other.env.retryPendingTurn();assert.deepEqual(other.calls,['play']);}});
test('account switch during canonical read cannot write state or close original identity',async()=>{let finish;const view=render({canonical:()=>new Promise(resolve=>finish=()=>resolve({state:{hp:30},history:null,combat_history:null}))});view.env.submitLevelUp(request);await tick();rotateAuthEpoch();finish();await tick();assert.equal(view.client.getQueryData(['state','s']),undefined);assert.equal(pending.readPending('a','c').kind,'level_up');});
test('level-up recovery retains pending when revision gate rejects canonical projection',async()=>{const key=pending.createIntentKey('a','c',request,'level_up');const view=render();view.env.applyGameState=()=>false;await view.env.serverRecovery('check');assert.equal(pending.readPending('a','c')?.key.actionId,key.actionId);assert.equal(view.notices.at(-1).tone,'error');});
test('successful POST followed by canonical HTTP422 retains original pending identity',async()=>{const view=render({canonical:async()=>{throw Object.assign(Error('invalid canonical read'),{status:422})}});view.env.submitLevelUp(request);const key=pending.readPending('a','c').key;await tick();assert.equal(pending.readPending('a','c')?.key.actionId,key.actionId);assert.equal(view.client.getQueryData(['state','s']),undefined);});
test('server-only applied recovery rejects stale canonical gate without success feedback',async()=>{const view=render();view.env.applyGameState=()=>false;await view.env.serverRecovery('check','server-only-id');assert.equal(view.notices.at(-1).tone,'error');});
test('level5 uses same durable path and describes target5 without claiming another CON increase',async()=>{const view=render();view.env.submitLevelUp({campaign_id:'c',expected_revision:8,target_level:5,choices:{prepared_spells:['Fog Cloud','Silent Image']}});await tick();assert.match(view.notices.at(-1).title,/5\. seviye/);assert.doesNotMatch(view.notices.at(-1).detail,/Constitution \+2/);assert.deepEqual(Object.keys(view.calls[0].choices),['prepared_spells']);});

test('typed slot3 cast shares pending gate, duplicate suppression and surfaces durable server refusal without resource writes',async()=>{
 const view=render(); const command={steps:[{kind:'magic',ability:'Magic Missile',target_id:'npc-1',slot_level:3}]};
 const key=pending.createIntentKey('a','c',request,'level_up');
 view.env.playGameTurn=async()=>{throw Error('must not send while level-up pending')};
 view.env.submitTurn('Magic Missile kullanıyorum.',command,'do');assert.equal(view.calls.length,0);pending.closePending(key,'confirmed');
 let refuse;view.env.playGameTurn=async(s,r)=>{view.calls.push(structuredClone(r));return new Promise((resolve,reject)=>refuse=()=>reject(Object.assign(Error('Target is outside the sourced spell range.'),{status:409,data:{detail:{not_applied:true,code:'spell_out_of_range'}}})));};
 view.env.submitTurn('Magic Missile kullanıyorum.',command,'do');view.env.submitTurn('Magic Missile kullanıyorum.',command,'do');
 assert.equal(view.calls.length,1);assert.deepEqual(view.calls[0].combat_action,command);refuse();await tick();
 assert.equal(pending.readPending('a','c'),null);assert.match(view.notices.at(-1).detail,/outside.*range/);assert.equal(view.client.getQueryData(['state','s']),undefined);
});
test('early Sorcerer2/3 and empty Barbarian2 retry the exact stored shape through the unchanged shared owner',async()=>{for(const fresh of [{campaign_id:'c',expected_revision:2,target_level:2,choices:{prepared_spells:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell']}},{campaign_id:'c',expected_revision:3,target_level:3,choices:{prepared_spells:['Fog Cloud','Silent Image'],subclass_id:'aberrant'}},{campaign_id:'c',expected_revision:2,target_level:2,choices:{}}]){const first=render({apply:async()=>{throw Error('lost reply')}});first.env.submitLevelUp(fresh);await tick();const original=first.calls[0];const next=render();next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls[0],original);assert.equal(Object.hasOwn(next.calls[0],'class_name'),false);assert.equal(pending.readPending('a','c'),null);}});

test('Quickened typed cast duplicate/lost-response retry preserves exact original option and UUID',async()=>{
 const command={steps:[{kind:'magic',ability:'Magic Missile',target_id:'npc-1',slot_level:3,metamagic:'quickened_spell'}]};
 const first=render(); first.env.playGameTurn=async(_s,r)=>{first.calls.push(structuredClone(r));throw Error('lost reply')};
 first.env.submitTurn('Magic Missile kullanıyorum.',command,'do');first.env.submitTurn('Magic Missile kullanıyorum.',command,'do');await tick();
 assert.equal(first.calls.length,1);const original=first.calls[0];assert.deepEqual(original.combat_action,command);
 assert.deepEqual(pending.readPending('a','c').request.combat_action,command);
 const next=render();next.env.submitTurnRef.current=next.env.submitTurn;
 next.env.playGameTurn=async(_s,r)=>{next.calls.push(structuredClone(r));throw Error('still unknown')};
 next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls,[original]);
 assert.equal(pending.readPending('a','c').key.actionId,original.action_id);
 const other=render({owner:'b',campaignId:'other'});other.env.submitTurnRef.current=other.env.submitTurn;
 other.env.playGameTurn=async()=>{throw Error('must not send original campaign action')};other.env.retryPendingTurn();assert.deepEqual(other.calls,[]);
});

test('outside-combat slot conversion uses shared pending gate, suppresses duplicate and retries exact slot/UUID',async()=>{
 const command={steps:[{kind:'convert_spell_slot',slot_level:2}]};const first=render();
 const other=pending.createIntentKey('a','c',request,'level_up');first.env.playGameTurn=async()=>{throw Error('blocked')};first.env.submitTurn('convert',command,'do');assert.equal(first.calls.length,0);pending.closePending(other,'confirmed');
 first.env.playGameTurn=async(_s,r)=>{first.calls.push(structuredClone(r));throw Error('lost reply')};first.env.submitTurn('convert',command,'do');first.env.submitTurn('convert',command,'do');await tick();assert.equal(first.calls.length,1);const original=first.calls[0];assert.deepEqual(original.combat_action,command);assert.equal(Object.hasOwn(original,'combat_id'),false);
 const next=render();next.env.submitTurnRef.current=next.env.submitTurn;next.env.playGameTurn=async(_s,r)=>{next.calls.push(structuredClone(r));throw Error('still unknown')};next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls,[original]);assert.equal(pending.readPending('a','c').key.actionId,original.action_id);
});

test('chosen nonDEX ASI retries exact original pattern and UUID, not the historic CON default',async()=>{for(const increase of [{charisma:2},{strength:1,wisdom:1}]){const chosen={...request,choices:{...request.choices,asi:{feat:'Ability Score Improvement',increase}}};const first=render({apply:async()=>{throw Error('lost reply')}});first.env.submitLevelUp(chosen);await tick();const original=first.calls[0];assert.deepEqual(original.choices.asi.increase,increase);const next=render();next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls[0],original);assert.equal(pending.readPending('a','c'),null);}});

test('Rage activate/extend share pending gate and exact Bonus command UUID on lost-response retry',async()=>{for(const kind of ['activate_rage','extend_rage']){const command={steps:[{kind,resource:'bonus'}]};const first=render();const blocked=pending.createIntentKey('a','c',request,'level_up');first.env.playGameTurn=async()=>{throw Error('must stay blocked')};first.env.submitTurn('Rage',command,'do');assert.equal(first.calls.length,0);pending.closePending(blocked,'confirmed');first.env.playGameTurn=async(_s,r)=>{first.calls.push(structuredClone(r));throw Error('lost reply')};first.env.submitTurn('Rage',command,'do');first.env.submitTurn('Rage',command,'do');await tick();assert.equal(first.calls.length,1);assert.deepEqual(first.calls[0].combat_action,command);const original=first.calls[0];const second=render();second.env.submitTurnRef.current=second.env.submitTurn;second.env.playGameTurn=async(_s,r)=>{second.calls.push(structuredClone(r));throw Error('unknown')};second.env.retryPendingTurn();await tick();assert.deepEqual(second.calls,[original]);assert.equal(pending.readPending('a','c').key.actionId,original.action_id);pending.closePending(pending.readPending('a','c').key,'confirmed');}});

test('Berserker earned3 lost response retries original skill and UUID through shared pending owner',async()=>{const chosen={campaign_id:'c',expected_revision:3,target_level:3,choices:{subclass_id:'berserker',primal_knowledge_skill:'Survival'}};const first=render({apply:async()=>{throw Error('lost reply')}});first.env.submitLevelUp(chosen);first.env.submitLevelUp(chosen);await tick();assert.equal(first.calls.length,1);const original=first.calls[0];assert.deepEqual(original.choices,chosen.choices);const switched=render({owner:'other',campaignId:'different',sessionId:'different'});assert.equal(pending.readPending('other','different'),null);assert.equal(switched.calls.length,0);const next=render();next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls[0],original);assert.equal(pending.readPending('a','c'),null);});

test('Barbarian4 sole-ASI duplicate and lost response preserve exact original UUID/body across contexts',async()=>{
 for(const increase of [{constitution:2},{strength:1,wisdom:1}]){
  const chosen={campaign_id:'c',expected_revision:3,target_level:4,choices:{asi:{feat:'Ability Score Improvement',increase}}};
  const first=render({apply:async()=>{throw Error('lost Barbarian4 reply')}});first.env.submitLevelUp(chosen);first.env.submitLevelUp(chosen);await tick();assert.equal(first.calls.length,1);
  const original=first.calls[0];assert.deepEqual(original.choices,chosen.choices);assert.deepEqual(Object.keys(original.choices),['asi']);
  for(const context of [{owner:'other'},{campaignId:'other'},{sessionId:'other'}]){const other=render(context);other.env.submitTurnRef.current=()=>{};if(context.sessionId){other.env.applyGameSessionLevelUp=async(_s,r)=>{other.calls.push(structuredClone(r));throw Error('unknown')};other.env.retryPendingTurn();await tick();assert.deepEqual(other.calls,[original]);}else{other.env.retryPendingTurn();assert.deepEqual(other.calls,[]);}}
  const next=render();next.env.retryPendingTurn();await tick();assert.deepEqual(next.calls[0],original);assert.equal(pending.readPending('a','c'),null);
 }
});
test('Barbarian4 applied-null recovery waits for authoritative HP/AC card and never manufactures mechanics',async()=>{
 const chosen={campaign_id:'c',expected_revision:3,target_level:4,choices:{asi:{feat:'Ability Score Improvement',increase:{constitution:2}}}};
 const first=render({apply:async()=>{throw Error('lost reply')}});first.env.submitLevelUp(chosen);await tick();const original=first.calls[0];
 const state={character:{class:'Barbarian',level:4,progression_level:4,constitution:16,max_hp:45,current_hp:41,armor_class:16}};
 const next=render({canonical:async()=>({state,history:[],combat_history:[]})});await next.env.serverRecovery();await tick();assert.equal(pending.readPending('a','c'),null);assert.deepEqual(next.client.getQueryData(['state','s']),state);assert.equal(first.calls[0].action_id,original.action_id);assert.deepEqual(original.choices,chosen.choices);
});


test('accepted recovery clears the combat banner only after the canonical projection is accepted',async()=>{
 for(const accepted of [true,false]){
  window.sessionStorage=storage();pending.clearPendingFallback();
  pending.createIntentKey('a','c',request,'level_up');
  const view=render();view.env.applyGameState=()=>accepted;
  await view.env.serverRecovery('check');
  assert.deepEqual(view.env.combatStartNotices,accepted?[null]:[]);
  assert.equal(pending.readPending('a','c')===null,accepted);
  view.client.clear();
 }
});
