import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { createActionLifetime, stableTurnActionId, storedTurnContext, clearPendingTurnAction, reconcileState, RETRY_MESSAGE, ReconciliationError } from '../src/lib/action-reconciliation.ts';
import { rotateAuthEpoch } from '@workspace/api-client-react/custom-fetch';
import { QueryClient } from '@tanstack/react-query';
// Execute production AST-selected bodies; replace only hook, transport and view boundaries.
const source = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
const submit = component.body.statements.find(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(ast) === 'submitTurn'));
assert.ok(submit);
const cacheCode = (await readFile(new URL('../src/lib/advisory-cache.ts', import.meta.url), 'utf8')).replace(/^export\s+/gm, '');
const code = ts.transpileModule([cacheCode, submit.getText(ast), 'globalThis.submit = submitTurn;'].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
function storage() {
 const values = new Map();
 return { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k), values };
}
const current = { revision: 'newer-at-same-turn', turn_index: 3, combat: { active: true, combat_id: 'combat-a', round: 1, current_turn_index: 0 }, quests: [] };
const old = { ...current, revision: 'receipt-snapshot' };
function harness({ sessionStorage = storage(), transport, refresh = async () => current, history = [{ player_message: 'Synthetic action', narration: 'Synthetic receipt' }] } = {}) {
 const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
 const requests = [], shown = [], errors = [], setters = [];
 const life = createActionLifetime();
 const env = {
  stableTurnActionId, storedTurnContext, clearPendingTurnAction, reconcileState, RETRY_MESSAGE, ReconciliationError,
  turnLifetime: life,
  wasAtBottom: { current: true }, storyScrollRef: { current: null }, setResultCue() {}, setLastTurn() {},
  window: { sessionStorage, localStorage: storage(), crypto: { randomUUID: () => crypto.randomUUID() } },
  sessionId: 'session-a', campaignId: 'campaign-a', interactionMode: 'do', conversationTargetId: '', combatTargetId: '', state: current,
  inFlightSessionsRef: { current: new Set() }, undoPendingRef: { current: new Set() }, undoRequestsRef: { current: new Map() }, pendingTurnRef: { current: null }, activeSessionRef: { current: 'session-a' },
  setInFlightSessions() {}, setNotice: value => { if (value) errors.push(value); }, getTurnInteractionMetadata: () => ({ interaction_mode: 'do' }),
  epoch: 1, currentAuthEpoch: () => 1, accountWriteAllowed: () => env.epoch === 1,
  playGameTurn: async (sessionId, data) => { const request = { sessionId, data }; requests.push(request); return transport ? transport(request) : { state: old, narration: 'Synthetic receipt' }; },
  queryClient: client, getGetGameSessionStateQueryKey: id => ['state', id],
  getGameSessionState: refresh,
  getCampaign: async () => ({ state: await env.getGameSessionState(), history, combat_history: [] }),
  mergeCombatHistory: history => history,
  getGetCampaignsQueryKey: () => ['campaigns'], entries: [], TRANSCRIPT_KEY: 'transcript-',
  setEntries: v => shown.push(v), setCombatEntries() {}, setCombatEndNotice() {}, setCombatTargetId() {}, setConversationTargetId() {}, setMessage() {},
  statusCode: e => e.status, friendlyError: () => 'Synthetic error',
 };
 for (const name of ['setInFlightSessions', 'setNotice', 'setEntries', 'setCombatEntries', 'setCombatEndNotice', 'setCombatTargetId', 'setConversationTargetId', 'setMessage']) {
  const original = env[name]; env[name] = (...args) => { setters.push([name, ...args]); return original(...args); };
 }
 vm.runInNewContext(code, env);
 client.setQueryData(['state', 'session-a'], current);
 return { env, client, requests, shown, errors, setters, life, sessionStorage, async run() {
  globalThis.window = env.window;
  env.submit('Synthetic action');
  for (let i=0; i<100 && env.inFlightSessionsRef.current.size; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(env.inFlightSessionsRef.current.size, 0, 'turn settled');
 } };
}
test('a failed optional transcript cache does not turn a committed turn into an error', async () => {
 const h = harness();
 h.env.window.localStorage.setItem = () => { throw new DOMException('Full', 'QuotaExceededError'); };
 let draft = 'Synthetic action';
 h.env.setMessage = value => { draft = value; };
 await h.run();
 assert.equal(h.requests.length, 1);
 assert.equal(h.errors.length, 0);
 assert.equal(h.shown.at(-1).at(-1).text, 'Synthetic receipt');
 assert.equal(h.client.getQueryData(['state', 'session-a']).revision, current.revision);
 assert.equal(draft, '');
 assert.equal(h.env.pendingTurnRef.current, null);
 h.client.clear();
});

test('only a validated own submission returns a scrolled transcript to the live end', async () => {
 const h = harness();
 const node = { scrollTop: 100, scrollHeight: 1200 };
 h.env.storyScrollRef.current = node;
 h.env.wasAtBottom.current = false;
 h.env.submit('');
 assert.equal(node.scrollTop, 100);
 assert.equal(h.env.wasAtBottom.current, false);
 await h.run();
 assert.equal(node.scrollTop, 1200);
 assert.equal(h.env.wasAtBottom.current, true);
 h.client.clear();
});

test('lost response then reload retries the same UUID/context and keeps authoritative same-turn revision', async () => {
 const first = harness({ transport: async () => { throw new Error('response lost after commit'); } });
 await first.run();
 const retry = harness({ sessionStorage: first.sessionStorage });
 retry.env.state = { ...current, combat: { ...current.combat, round: 2 } };
 await retry.run();
 assert.equal(retry.requests[0].data.action_id, first.requests[0].data.action_id);
 assert.equal(retry.requests[0].data.combat_id, first.requests[0].data.combat_id);
 assert.equal(retry.requests[0].data.combat_round, first.requests[0].data.combat_round);
 assert.equal(retry.client.getQueryData(['state','session-a']).revision, 'newer-at-same-turn');
 assert.equal(retry.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'), null);
 first.client.clear(); retry.client.clear();
});

function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; }
test('failed authoritative read keeps UUID/context even for a 409 read failure', async () => {
 const h = harness({ refresh: async () => { throw Object.assign(new Error('read failed'), { status: 409 }); } });
 await h.run();
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 assert.equal(h.shown.length, 0);
 assert.equal(h.client.getQueryData(['state','session-a']).revision, current.revision);
 h.env.getGameSessionState = async () => current;
 await h.run();
 assert.equal(h.requests[0].data.action_id, h.requests[1].data.action_id);
 assert.equal(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'), null);
 h.client.clear();
});
test('same-account A to B switch during reconciliation cannot change visible B', async () => {
 const read = deferred();
 const h = harness({ refresh: () => read.promise });
 h.client.setQueryData(['state','session-b'], { revision: 'B' });
 const done = h.run();
 await new Promise(resolve => setImmediate(resolve));
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 h.env.activeSessionRef.current = 'session-b';
 h.life.dispose();
 h.setters.length = 0;
 read.resolve(current);
 await done;
 assert.equal(h.shown.length, 0);
 assert.equal(h.setters.length, 0);
 assert.equal(h.env.window.localStorage.values.size, 0);
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 assert.equal(h.client.getQueryData(['state','session-b']).revision, 'B');
 assert.equal(h.client.getQueryData(['state','session-a']).revision, current.revision);
 h.client.clear();
});
test('account change during authoritative read prevents cache and transcript writes', async () => {
 const read = deferred();
 const h = harness({ refresh: () => read.promise });
 const done = h.run();
 await new Promise(resolve => setImmediate(resolve));
 rotateAuthEpoch();
 h.setters.length = 0;
 h.client.clear();
 read.resolve(current);
 await done;
 assert.equal(h.shown.length, 0);
 assert.equal(h.client.getQueryData(['state','session-a']), undefined);
 assert.equal(h.setters.length, 0);
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 assert.equal(h.env.window.localStorage.values.size, 0);
 h.client.clear();
});

test('a concurrent same-turn cache update during the read requires another authoritative read', async () => {
 const read = deferred();
 let calls = 0;
 const newest = { ...current, revision: 'concurrent-newest' };
 const h = harness({ refresh: () => ++calls === 1 ? read.promise : Promise.resolve(newest) });
 const done = h.run();
 await new Promise(resolve => setImmediate(resolve));
 h.client.setQueryData(['state','session-a'], newest);
 read.resolve(current);
 await done;
 assert.equal(calls, 2);
 assert.equal(h.client.getQueryData(['state','session-a']).revision, 'concurrent-newest');
 h.client.clear();
});

test('three cache conflicts stop reconciliation without transcript writes and retain UUID', async () => {
 let count = 0;
 const h = harness({ refresh: async () => { count++; h.client.setQueryData(['state','session-a'], { ...current, count }); return current; } });
 await h.run();
 assert.equal(count, 3);
 assert.equal(h.shown.length, 0);
 assert.equal(h.env.window.localStorage.values.size, 0);
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 assert.equal(h.errors.at(-1).detail, RETRY_MESSAGE);
 h.client.clear();
});
test('unmount then new lifetime cannot revive old continuation or finally setters', async () => {
 const read = deferred();
 const h = harness({ refresh: () => read.promise });
 const done = h.run();
 await new Promise(resolve => setImmediate(resolve));
 h.life.dispose();
 h.env.turnLifetime = createActionLifetime();
 h.setters.length = 0;
 read.resolve(current);
 await done;
 assert.equal(h.setters.length, 0);
 assert.equal(h.env.window.localStorage.values.size, 0);
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 h.client.clear();
});
test('receipt already present in resumed history is not appended again', async () => {
 const h = harness();
 h.env.entries = [{kind:'player',text:'Synthetic action'}, {kind:'narration',text:'Synthetic receipt'}];
 await h.run();
 assert.equal(h.shown[0].length, 2);
 assert.equal(JSON.parse(h.env.window.localStorage.getItem('transcript-session-a')).length, 2);
 h.client.clear();
});
test('deadline aborts a stalled read even if transport ignores cancellation', async () => {
 const life = createActionLifetime(); const op = life.begin(); const client = new QueryClient(); let signal;
 await assert.rejects(reconcileState(client, ['test'], op, s => { signal=s; return new Promise(() => {}); }, 10), ReconciliationError);
 assert.equal(signal.aborted, true);
 op.close(); life.dispose(); client.clear();
});


const speciesSource = await readFile(new URL('../src/components/species-trait-controls.tsx', import.meta.url), 'utf8');
const speciesAst = ts.createSourceFile('species.tsx', speciesSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const speciesComponent = speciesAst.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'SpeciesTraitControls');
const selected = speciesComponent.body.statements.filter(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => ['scope','retryKey','[retryInput, setRetryInput]','send'].includes(d.name.getText(speciesAst))));
assert.equal(selected.length, 4);
const speciesCode = ts.transpileModule(selected.map(n => n.getText(speciesAst)).join('\n') + '\nglobalThis.send = send; globalThis.restoredRetry = retryInput;', { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
function speciesHarness({ store = storage(), fail = false, refresh = async () => current } = {}) {
 const client = new QueryClient(); const life = createActionLifetime(); const requests = [], setters = [];
 const env = {
  campaignId:'campaign-a', sessionId:'session-a', lifetime:life, busy:{ current:false }, pendingRequest:{current:null},
  stableTurnActionId, clearPendingTurnAction, reconcileState, RETRY_MESSAGE,
  window:{ sessionStorage:store, crypto:{ randomUUID:() => crypto.randomUUID() } },
  useState: fn => [fn(), v => setters.push(['retry',v])],
  setSending:v => setters.push(['sending',v]), setFeedback:v => setters.push(['feedback',v]), setFailure:v => setters.push(['failure',v]), setStorageUnavailable:v => setters.push(['storageUnavailable',v]),
  queryClient:client, getGetGameSessionStateQueryKey:id => ['state',id], getGameSessionState:refresh,
  resolveSpeciesTraitAction:async (id,data) => { requests.push(data); if(fail) throw new Error('lost after commit'); return {state:old,result:{message:'Synthetic',effects:{}}}; },
 };
 globalThis.window = env.window;
 vm.runInNewContext(speciesCode, env);
 return {env,client,life,requests,setters,store,async run(data={action:'healing_hands'}) {
  globalThis.window=env.window; env.send(data);
  for(let i=0;i<100 && env.busy.current;i++) await new Promise(r => setImmediate(r));
  assert.equal(env.busy.current,false);
 }};
}
test('species lost response and reload restore retry input and reuse UUID without historical cache rollback', async () => {
 const first=speciesHarness({fail:true}); await first.run();
 const retry=speciesHarness({store:first.store});
 assert.equal(retry.env.restoredRetry.action,'healing_hands');
 await retry.run(retry.env.restoredRetry);
 assert.equal(first.requests[0].action_id,retry.requests[0].action_id);
 assert.equal(retry.client.getQueryData(['state','session-a']).revision,current.revision);
 assert.equal(retry.store.getItem('ai-dnd-pending-turns:species:campaign-a'),null);
 assert.equal(retry.store.getItem('ai-dnd-turn-context:species:campaign-a:retry'),null);
 first.client.clear(); retry.client.clear();
});
test('species unmount cancels reconciliation without feedback/cache/pending cleanup', async () => {
 const read=deferred(); const h=speciesHarness({refresh:()=>read.promise}); const done=h.run();
 await new Promise(r=>setImmediate(r)); h.life.dispose(); h.setters.length=0;
 read.resolve(current); await done;
 assert.equal(h.setters.length,0);
 assert.equal(h.client.getQueryData(['state','session-a']),undefined);
 assert.ok(h.store.getItem('ai-dnd-pending-turns:species:campaign-a'));
 assert.ok(h.store.getItem('ai-dnd-turn-context:species:campaign-a:retry'));
 h.client.clear();
});
test('species failed read retains retry input and never publishes receipt state', async () => {
 const h=speciesHarness({refresh:async()=>{throw new Error('read failed');}}); await h.run();
 assert.equal(h.client.getQueryData(['state','session-a']),undefined);
 assert.ok(h.store.getItem('ai-dnd-pending-turns:species:campaign-a'));
 assert.ok(h.setters.some(([name,value])=>name==='failure' && value));
 assert.ok(!h.setters.some(([name,value])=>name==='feedback' && value));
 h.client.clear();
});
// Executes the hook's real setup/cleanup function with an effect boundary double.
// This checks generation disposal, not React renderer mount semantics.
test('lifecycle hook cleanup and setup create distinct generations (effect-boundary test)', async () => {
 const helperSource=await readFile(new URL('../src/lib/action-reconciliation.ts',import.meta.url),'utf8');
 const helperAst=ts.createSourceFile('helper.ts',helperSource,ts.ScriptTarget.Latest,true);
 const hook=helperAst.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='useActionLifetime');
 let setup;
 const env={createActionLifetime,useRef:value=>({current:value}),useEffect:fn=>{setup=fn;},exports:{}};
 vm.runInNewContext(ts.transpileModule(hook.getText(helperAst),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,env);
 const lifetime=env.exports.useActionLifetime('A');
 const cleanup=setup(); const oldOp=lifetime.begin(); cleanup();
 const cleanup2=setup(); const nextOp=lifetime.begin();
 assert.equal(oldOp.signal.aborted,true); assert.equal(oldOp.isCurrent(),false); assert.equal(nextOp.isCurrent(),true);
 cleanup2(); assert.equal(nextOp.signal.aborted,true);
});

test('main read timeout retains UUID, shows retry message, and writes no transcript', async () => {
 const h=harness({refresh:()=>new Promise(()=>{})});
 h.env.reconcileState=(client,key,op,read)=>reconcileState(client,key,op,read,10);
 globalThis.window=h.env.window; h.env.submit('Synthetic action');
 await new Promise(r=>setTimeout(r,30));
 assert.equal(h.env.inFlightSessionsRef.current.size,0);
 assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
 assert.equal(h.env.window.localStorage.values.size,0);
 assert.equal(h.shown.length,0);
 assert.equal(h.errors.at(-1).detail,RETRY_MESSAGE);
 h.client.clear();
});
test('species auth epoch change prevents all post-await setters and pending cleanup', async () => {
 const read=deferred(); const h=speciesHarness({refresh:()=>read.promise}); const done=h.run();
 await new Promise(r=>setImmediate(r)); rotateAuthEpoch(); h.setters.length=0;
 read.resolve(current); await done;
 assert.equal(h.setters.length,0);
 assert.equal(h.client.getQueryData(['state','session-a']),undefined);
 assert.ok(h.store.getItem('ai-dnd-pending-turns:species:campaign-a'));
 h.client.clear();
});

test('species definite mutation 400/409/422 clears retry lock and allows a new selection', async () => {
 for (const status of [400,409,422]) {
  const h=speciesHarness();
  h.env.resolveSpeciesTraitAction=async(id,data)=>{h.requests.push(data); throw Object.assign(new Error('not applied'),{status});};
  await h.run();
  assert.equal(h.env.pendingRequest.current,null);
  assert.equal(h.store.getItem('ai-dnd-pending-turns:species:campaign-a'),null);
  assert.equal(h.store.getItem('ai-dnd-turn-context:species:campaign-a:retry'),null);
  assert.equal(h.setters.filter(([name])=>name==='retry').at(-1)[1],null);
  h.env.resolveSpeciesTraitAction=async(id,data)=>{h.requests.push(data);return {state:old,result:{message:'Synthetic',effects:{}}};};
  await h.run({action:'celestial_revelation',form:'heavenly_wings'});
  assert.equal(h.requests[1].action,'celestial_revelation');
  assert.notEqual(h.requests[1].action_id,h.requests[0].action_id);
  h.client.clear();
 }
});
function unavailableStorage() { return {getItem(){throw new Error('blocked');},setItem(){throw new Error('blocked');},removeItem(){throw new Error('blocked');}}; }
test('species storage throw and lost response retry retain the in-memory UUID', async () => {
 const h=speciesHarness({store:unavailableStorage(),fail:true});
 await h.run(); const request=h.env.pendingRequest.current;
 assert.ok(h.setters.some(([name,value])=>name==='storageUnavailable' && value));
 h.env.resolveSpeciesTraitAction=async(id,data)=>{h.requests.push(data);return {state:old,result:{message:'Synthetic',effects:{}}};};
 await h.run(request);
 assert.equal(h.requests[1].action_id,h.requests[0].action_id);
 assert.equal(h.env.pendingRequest.current,null);
 h.client.clear();
});
test('species post-receipt 409 read failure retains pending request and UUID', async () => {
 const h=speciesHarness({refresh:async()=>{throw Object.assign(new Error('read failed'),{status:409});}});
 await h.run();
 assert.ok(h.env.pendingRequest.current);
 assert.ok(h.store.getItem('ai-dnd-pending-turns:species:campaign-a'));
 assert.equal(h.setters.filter(([name])=>name==='failure').at(-1)[1],RETRY_MESSAGE);
 h.client.clear();
});
test('main storage throw and lost response retry reuse existing in-memory pending UUID', async () => {
 const h=harness({sessionStorage:unavailableStorage(),transport:async()=>{throw new Error('lost');}});
 await h.run(); await h.run();
 assert.equal(h.requests[0].data.action_id,h.requests[1].data.action_id);
 assert.ok(h.env.pendingTurnRef.current);
 h.client.clear();
});


test('F03 synthetic real HTTP save rollback component recovery retry', {skip: !process.env.F03_FAULT_UI_CONFIG}, async () => {
 const {writeFile} = await import('node:fs/promises');
 const {join} = await import('node:path');
 const {execFileSync} = await import('node:child_process');
 const config=JSON.parse(await readFile(process.env.F03_FAULT_UI_CONFIG,'utf8'));
 const control=stage=>writeFile(join(config.folder,'control.json'),JSON.stringify({mode:'normal',stage}));
 const request=async(path,body)=>{
  const response=await fetch(config.url+path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});
  const result=await response.json();
  if(!response.ok) throw Object.assign(new Error('Synthetic API fault'),{status:response.status,detail:result.detail});
  return result;
 };
 const refresh=()=>request(`/api/sessions/${config.sid}/state`);
 const before=await refresh();
 const first=speciesHarness({refresh});
 first.client.setQueryData(['state','session-a'],before);
 let failedStatus, accepted, sent;
 const transport=h=>async(_,body)=>{
  h.requests.push(body); sent=body;
  try {accepted=await request(`/api/game/sessions/${config.sid}/species-actions`,body);return accepted;}
  catch(error){failedStatus=error.status;throw error;}
 };
 const send=async(h,body)=>{
  globalThis.window=h.env.window;h.env.send(body);
  const deadline=Date.now()+15000;
  while(h.env.busy.current && Date.now()<deadline) await new Promise(r=>setTimeout(r,10));
  assert.equal(h.env.busy.current,false,'real HTTP component request settled');
 };
 first.env.resolveSpeciesTraitAction=transport(first);
 await control('ui-save-failed');
 await send(first,{action:config.action});
 assert.equal(failedStatus,503);
 assert.deepEqual(first.client.getQueryData(['state','session-a']),before);
 assert.ok(first.setters.some(([name,value])=>name==='failure' && value));
 assert.ok(!first.setters.some(([name,value])=>name==='feedback' && value));
 assert.ok(first.store.getItem('ai-dnd-pending-turns:species:campaign-a'));
 execFileSync(config.python,['-B','-c',"import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('DROP TRIGGER synthetic_f03_receipt'); c.close()",join(config.folder,'campaigns.sqlite3')]);
 // A new component lifetime restores retry input from the same storage.
 const retry=speciesHarness({store:first.store,refresh});
 retry.env.resolveSpeciesTraitAction=transport(retry);
 assert.equal(retry.env.restoredRetry.action,config.action);
 await control('ui-retry');
 await send(retry,retry.env.restoredRetry);
 assert.equal(retry.requests[0].action_id,first.requests[0].action_id);
 assert.ok(accepted);
 assert.deepEqual(retry.client.getQueryData(['state','session-a']),await refresh());
 assert.equal(retry.store.getItem('ai-dnd-pending-turns:species:campaign-a'),null);
 assert.equal(retry.store.getItem('ai-dnd-turn-context:species:campaign-a:retry'),null);
 assert.ok(retry.setters.some(([name,value])=>name==='feedback' && value));
 await writeFile(join(config.folder,'ui-result.json'),JSON.stringify({synthetic:true,real_browser:false,failed_status:failedStatus,retry_status:200,request:sent,response:accepted,same_id:true,cache_recovered:true}));
 first.client.clear();retry.client.clear();
});


// Synthetic render/effect boundary: execute the production hook, including its
// synchronous renderedScope guard. Transport intentionally ignores abort signals.
async function renderedLifetimeHarness() {
 const helperSource=await readFile(new URL('../src/lib/action-reconciliation.ts',import.meta.url),'utf8');
 const helperAst=ts.createSourceFile('helper.ts',helperSource,ts.ScriptTarget.Latest,true);
 const hook=helperAst.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='useActionLifetime');
 const refs=[];let index=0,setup;
 const env={createActionLifetime,useRef:value=>refs[index++]??(refs[index-1]={current:value}),useEffect:fn=>{setup=fn;},exports:{}};
 vm.runInNewContext(ts.transpileModule(hook.getText(helperAst),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,env);
 const render=scope=>{index=0;return env.exports.useActionLifetime(scope);};
 const lifetime=render('session-a');const cleanup=setup();
 return {lifetime,render,cleanup};
}

for(const boundary of ['mutation-response','authoritative-read']) {
 for(const outcome of ['success','error']) {
  test(`F03 AC005 synthetic B render before uncancelled A ${boundary} ${outcome}`,async()=>{
   const delayed=deferred();const lifecycle=await renderedLifetimeHarness();
   const h=harness();let requestSignal,readSignal,reads=0,delivered=false;
   const aState={...current,character:{current_hp:1},revision:'late-A'};
   const aReceipt={state:aState,narration:'Synthetic A narration',combat_history_entry:{id:'A-combat'}};
   const aSnapshot={state:aState,history:[{player_message:'A action',narration:'Synthetic A narration'}],combat_history:[{id:'A-combat'}]};
   h.env.turnLifetime=lifecycle.lifetime;
   h.env.playGameTurn=async(id,data,options)=>{
    h.requests.push({sessionId:id,data});requestSignal=options.signal;
    if(boundary==='mutation-response') {try{return await delayed.promise;}finally{delivered=true;}}
    return aReceipt;
   };
   h.env.getCampaign=async(id,options)=>{
    reads++;readSignal=options.signal;
    if(boundary==='authoritative-read') {try{return await delayed.promise;}finally{delivered=true;}}
    return aSnapshot;
   };
   globalThis.window=h.env.window;h.env.submit('Synthetic A action');
   for(let i=0;i<10 && (boundary==='authoritative-read' && reads===0);i++) await new Promise(r=>setImmediate(r));
   assert.equal(h.requests.length,1);
   if(boundary==='authoritative-read') assert.equal(reads,1);
   const bState={...current,character:{current_hp:17},revision:'B-authoritative'};
   const bHistory=[{kind:'narration',text:'Synthetic B narration'}];
   const bCombat=[{id:'B-combat'}];
   h.client.setQueryData(['state','session-b'],bState);
   h.client.setQueryData(['campaign','campaign-b'],{state:bState,history:bHistory,combat_history:bCombat});
   h.env.window.localStorage.setItem('transcript-session-b',JSON.stringify(bHistory));
   h.env.activeSessionRef.current='session-b';
   lifecycle.render('session-b'); // Real render guard updates before effect cleanup.
   const cacheBefore=structuredClone(h.client.getQueryData(['state','session-b']));
   const detailBefore=structuredClone(h.client.getQueryData(['campaign','campaign-b']));
   const storageBefore=[...h.env.window.localStorage.values];
   h.setters.length=0;h.shown.length=0;
   assert.equal(requestSignal.aborted,false,'response arrives before cleanup abort');
   if(readSignal) assert.equal(readSignal.aborted,false);
   if(outcome==='success') delayed.resolve(boundary==='mutation-response'?aReceipt:aSnapshot);
   else delayed.reject(Object.assign(new Error('Synthetic late A error'),{status:503}));
   for(let i=0;i<20 && h.env.inFlightSessionsRef.current.size;i++) await new Promise(r=>setImmediate(r));
   assert.equal(delivered,true,'transport delivered despite B render');
   assert.equal(h.env.inFlightSessionsRef.current.size,0);
   assert.deepEqual(h.client.getQueryData(['state','session-b']),cacheBefore);
   assert.deepEqual(h.client.getQueryData(['campaign','campaign-b']),detailBefore);
   assert.equal(h.client.getQueryData(['state','session-b']).character.current_hp,17);
   assert.deepEqual([...h.env.window.localStorage.values],storageBefore);
   assert.equal(h.shown.length,0);assert.equal(h.setters.length,0);
   assert.equal(h.client.getQueryData(['state','session-a']).revision,current.revision);
   assert.ok(h.sessionStorage.getItem('ai-dnd-pending-turns:campaign-a'));
   if(boundary==='mutation-response') assert.equal(reads,0,'stale mutation cannot initiate reconciliation');
   lifecycle.cleanup();h.life.dispose();h.client.clear();
  });
 }
}

test('real submitTurn keeps server skill_check_result when reconciling saved campaign history', async () => {
 const skill = {skill:'Stealth', ability:'dexterity', d20:2, ability_modifier:4,
  proficiency_modifier:4, total_modifier:8, total:10, dc:15, outcome:'failure',
  difficulty:'medium', proficient:true};
 const history = [{player_message:'Köşede gizlenmeye çalışıyorum.',
  narration:'Gizlenme girişimin başarısız olur.', skill_check_result:skill}];
 const h = harness({ history, transport:async () => ({
  state:old, narration:history[0].narration, skill_check_result:skill
 }) });
 await h.run();
 assert.deepEqual(h.shown.at(-1).at(-1).skillCheckResult, skill,
  'real submit/reconciliation must pass the persisted result to Transcript and SkillCheckResultCard');
 assert.deepEqual(JSON.parse(h.env.window.localStorage.getItem('transcript-session-a')).at(-1).skillCheckResult, skill,
  'the resume-friendly transcript cache must not drop the real skill result');
 h.client.clear();
});

test('resume history cannot be overwritten by stale local text cache on session-id change', () => {
 const effect=component.body.statements.find(node =>
  ts.isExpressionStatement(node) && node.getText(ast).startsWith('useEffect(')
  && node.getText(ast).includes('setEntries(restored)'));
 assert.ok(effect, 'real GameBrowser restore effect exists');
 const js=ts.transpileModule(
  'globalThis.restoreTranscript = '+effect.expression.arguments[0].getText(ast)+';',
  {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}
 ).outputText;
 const changes=[];
 const ctx={
  sessionId:'session-resumed',campaignId:'campaign-authoritative',
  TRANSCRIPT_KEY:'ai-dnd-transcript-',
  window:{localStorage:{getItem:()=>JSON.stringify([{kind:'player',text:'Stale local copy'}])}},
  setEntries:v=>changes.push(v), setCombatEndNotice:()=>{}, setCombatTargetId:()=>{},
 };
 vm.runInNewContext(js,ctx);
 ctx.restoreTranscript();
 assert.equal(changes.length,0,
  'resumed canonical campaign history must not be overwritten with a text-only cache');
});
