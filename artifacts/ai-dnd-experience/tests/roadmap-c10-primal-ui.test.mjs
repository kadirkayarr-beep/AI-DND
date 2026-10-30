import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import path from 'node:path';
import ts from 'typescript';
import { QueryClient } from '@tanstack/react-query';
import { createActionLifetime, reconcileState, ReconciliationError, RETRY_MESSAGE } from '../src/lib/action-reconciliation.ts';
import { closePending, createIntentKey, readPending, resumePending, speciesActionUnresolved } from '../src/lib/pending-action.ts';
import { askServer, settlePending, unresolvedActionFrom } from '../src/lib/action-recovery.ts';
import { transcriptFollowsBottom } from '../src/lib/play-viewport.ts';
import { getTurnInteractionMetadata } from '../src/lib/action-suggestions.ts';
import { gateInjection } from './support/state-gate-env.mjs';

const source = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const component = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
const declaration = name => component.body.statements.find(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(ast) === name));
const code = ts.transpileModule([
  (await readFile(new URL('../src/lib/advisory-cache.ts', import.meta.url), 'utf8')).replace(/^export\s+/gm, ''),
  declaration('blockingMutation').getText(ast), declaration('submitTurn').getText(ast), declaration('serverRecovery').getText(ast),
  'globalThis.submit = submitTurn; globalThis.recover = serverRecovery;',
].join('\n'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
let vite, page, card, controls, React, render;
before(async () => {
  process.env.PORT ||= '4184'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent', plugins: [{ name: 'primal-test-view', enforce: 'pre', transform(code, id) { if (id.replaceAll('\\', '/').endsWith('/src/pages/game-browser.tsx')) return code + '\nexport { StoryColumn as TestStoryColumn };'; } }] });
  page = await vite.ssrLoadModule('/src/pages/game-browser.tsx');
  card = await vite.ssrLoadModule('/src/components/skill-check-result.tsx');
  controls = await vite.ssrLoadModule('/src/components/primal-knowledge-controls.tsx');
  React = await import('react'); render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });
const skills = ['Acrobatics', 'Intimidation', 'Perception', 'Stealth', 'Survival'];
const projection = { available: true, reason: null, skills };
const state = { turn_index: 2, character: { primal_knowledge_check: projection }, combat: { active: false, participant_records: [] }, scene: { npcs: [] }, conversation: { active: false }, quests: [] };
function storage() { const values = new Map(); return { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) }; }
function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; }
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness({ sessionStorage = storage(), transport, refresh } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const requests = [], notices = [];
  const intent = controls.createPrimalKnowledgeIntent();
  intent.sync({ key: JSON.stringify(['owner', 'campaign', 'session', 'do']), available: true });
  const env = {
    ...gateInjection(), reconcileState, ReconciliationError, RETRY_MESSAGE, closePending, createIntentKey, readPending, resumePending, speciesActionUnresolved, askServer, settlePending, unresolvedActionFrom, transcriptFollowsBottom, getTurnInteractionMetadata,
    ...controls, primalKnowledgeIntent: intent, redrawPrimalKnowledge() {}, tacticalMindIntent: controls.createPrimalKnowledgeIntent(), tacticalMindAvailable: () => false,
    currentAccountOwner: () => 'owner', LOCAL_OWNER: 'local', campaignId: 'campaign', sessionId: 'session', interactionMode: 'do', conversationTargetId: '', combatTargetId: '', state: structuredClone(state),
    pendingAmbientActionRef: { current: null }, turnLifetime: createActionLifetime(), undoPendingRef: { current: new Set() }, undoRequestsRef: { current: new Map() }, inFlightSessionsRef: { current: new Set() }, activeSessionRef: { current: 'session' },
    messageRef: { current: 'Takla atıyorum' }, entries: [], wasAtBottom: { current: true }, currentAuthEpoch: () => 1,
    pendingTurnNotice: () => ({ title: 'pending' }), recoveryHandlers: () => ({}), retryPendingTurn() {},
    RECOVERY_API: { status: async (_s,id) => ({ action_id:id, state:'unknown' }), abandon: async (_s,id) => ({action_id:id,state:'not_applied',detail:{not_applied:true,code:'abandoned'}}) },
    setNotice: n => { if (n) notices.push(n); }, setResultCue() {}, setInFlightSessions() {}, setNewResponseEntryIndex() {}, setEntries() {}, setCombatEntries() {}, setCombatEndNotice() {}, setCombatTargetId() {}, setConversationTargetId() {}, setLastTurn() {}, setComposerOpen() {},
    setMessage: value => { env.messageRef.current = value; },
    playGameTurn: async (_session, body) => { requests.push(structuredClone(body)); return transport ? transport(body) : { state: env.state, narration: 'server receipt' }; },
    queryClient, getGetGameSessionStateQueryKey: id => ['state', id], getGetCampaignsQueryKey: () => ['campaigns'],
    getCampaign: async () => ({ state: refresh ? await refresh() : env.state, history: [], combat_history: [] }),
    mergeCombatHistory: h => h, TRANSCRIPT_KEY: 'transcript-', statusCode: e => e.status, friendlyError: e => e.message,
    window: { sessionStorage, localStorage: storage(), crypto: { randomUUID: () => crypto.randomUUID() } },
  };
  globalThis.window = env.window;
  vm.runInNewContext(code, env);
  return { env, intent, requests, notices, sessionStorage, queryClient, choose(value=true) { intent.choose(value); env.primalKnowledgeOptIn = value; },
    submit(text='Takla atıyorum', command, mode='do', retry=false) { globalThis.window=env.window; env.submit(text, command, mode, retry); },
    async settled() { for (let i=0; i<100 && env.inFlightSessionsRef.current.size; i++) await tick(); assert.equal(env.inFlightSessionsRef.current.size, 0); }, close() { queryClient.clear(); } };
}
function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
const find = (tree,id) => tree.find(n => n.props?.['data-testid'] === id);

test('actual composer offers unchecked one-shot consent and five skills with immediate-only limitation', () => {
  const html = render(React.createElement(page.TestStoryColumn, { state, entries: [], readingPreferences: { fontSizePx: null, lineHeight: null }, composerOpen: true, message: '', interactionMode: 'do', conversationTargetId: '', combatTargetId: '', sending: false, scrollRef: { current: null }, newResponseEntryIndex: null, primalKnowledgeOptIn: false, onPrimalKnowledgeChange() {} }));
  assert.match(html, /data-testid="primal-knowledge-confirm"/);
  assert.doesNotMatch(html, /data-testid="primal-knowledge-confirm"[^>]*checked/);
  for (const skill of skills) assert.match(html, new RegExp(skill));
  assert.match(html, /anlık/); assert.match(html, /zaman alan/);
});

test('actual submit sends only explicit enum on Do and consumes consent once', async () => {
  const h=harness(); h.choose(); h.submit(); await h.settled();
  assert.equal(h.requests[0].check_feature, 'primal_knowledge');
  assert.deepEqual(Object.keys(h.requests[0]).sort(), ['action_id', 'check_feature', 'interaction_mode', 'message']);
  assert.equal(h.intent.selected, false);
  h.submit('Başka hamle'); await h.settled(); assert.equal(Object.hasOwn(h.requests[1], 'check_feature'), false); h.close();
});

test('ordinary absent projection, unchecked, Say, Ask, combat, structured command, target never acquire opt-in or lose target', async () => {
  for (const variant of ['unchecked', 'legacy', 'unavailable', 'say', 'ask_dm', 'combat', 'command', 'target']) {
    const h=harness(); h.choose(variant !== 'unchecked');
    if (variant === 'legacy') delete h.env.state.character.primal_knowledge_check;
    if (variant === 'unavailable') h.env.state.character.primal_knowledge_check.available=false;
    if (variant === 'combat') h.env.state.combat={ active:true, combat_id:'combat', round:1, current_turn_index:2 };
    if (variant === 'target') h.env.getTurnInteractionMetadata=()=>({interaction_mode:'do',target_id:'npc-original'});
    h.submit('Aynı söz', variant === 'command' ? { steps:[{kind:'dodge',resource:'action'}] } : undefined, ['say','ask_dm'].includes(variant)?variant:'do'); await h.settled();
    assert.equal(Object.hasOwn(h.requests[0], 'check_feature'), false, variant);
    if (variant === 'target') assert.equal(h.requests[0].target_id, 'npc-original');
    h.close();
  }
});

test('lost response and reload retry exact opted request + UUID despite changed current checkbox, mode, projection and draft', async () => {
  const first=harness({transport:async()=>{throw new Error('response lost');}}); first.choose(); first.submit(); await first.settled();
  assert.equal(first.requests[0].check_feature,'primal_knowledge');
  const retry=harness({sessionStorage:first.sessionStorage}); retry.env.state.character.primal_knowledge_check.available=false; retry.env.interactionMode='say'; retry.env.messageRef.current='Unrelated new draft'; retry.choose(false); retry.submit('',undefined,'say',true); await retry.settled();
  assert.deepEqual(retry.requests[0],first.requests[0]); assert.equal(retry.env.messageRef.current,'Unrelated new draft'); assert.equal(readPending('owner','campaign'),null); first.close(); retry.close();
});

test('duplicate submit sends one opted request and stale completion retains original pending payload', async () => {
  const held=deferred(); const h=harness({transport:()=>held.promise}); h.choose(); h.submit(); h.submit();
  h.env.turnLifetime.dispose(); held.resolve({state:h.env.state,narration:'stale'}); await h.settled();
  assert.equal(h.requests.length,1); assert.equal(h.requests[0].check_feature,'primal_knowledge');
  assert.equal(readPending('owner','campaign').request.check_feature,'primal_knowledge'); h.close();
});

test('proven refusal consumes original consent, keeps unrelated draft, and a deliberate new send gets new UUID without opt-in', async () => {
  const held=deferred(); const h=harness({transport:()=>held.promise}); h.choose(); h.submit(); h.env.messageRef.current='Unrelated draft';
  held.reject(Object.assign(new Error('server unsupported'),{status:422})); await h.settled();
  assert.equal(h.env.messageRef.current,'Unrelated draft'); assert.equal(h.intent.selected,false); assert.equal(readPending('owner','campaign'),null);
  h.env.playGameTurn=async(_s,body)=>{h.requests.push(structuredClone(body));return{state:h.env.state,narration:'ordinary'}};h.submit('Unrelated draft');await h.settled();assert.notEqual(h.requests[0].action_id,h.requests[1].action_id);assert.equal(Object.hasOwn(h.requests[1],'check_feature'),false);h.close();
});

test('feature historical card names actual Strength and original ability; ordinary card stays unannotated', () => {
  const ordinary={skill:'Stealth',ability:'dexterity',ability_modifier:2,proficient:true,proficiency_modifier:2,total_modifier:4,d20:9,total:13,difficulty:'medium',dc:15,outcome:'failure'};
  const feature={...ordinary,ability:'strength',ability_modifier:3,total_modifier:5,total:14,check_feature:'primal_knowledge',original_ability:'dexterity'};
  const html=render(React.createElement(card.SkillCheckResultCard,{result:feature}));assert.match(html,/Kuvvet \(Primal Knowledge\)/);assert.match(html,/Asıl yetenek.*ÇEV/);assert.match(html,/\+3/);assert.match(html,/14/);
  const old=render(React.createElement(card.SkillCheckResultCard,{result:ordinary}));assert.doesNotMatch(old,/Primal Knowledge|Asıl yetenek/);assert.match(old,/Yetenek · ÇEV/);
});

test('actual parent lifetime clears consent on owner, campaign, session, mode, unavailable projection and return transitions', () => {
  const start = component.body.statements.findIndex(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(ast) === 'primalKnowledgeRef'));
  const end = component.body.statements.findIndex(n => ts.isVariableStatement(n) && n.declarationList.declarations.some(d => d.name.getText(ast) === '[ambientActionResult, setAmbientActionResult]'));
  assert.ok(start >= 0 && end > start, 'real parent consent owner');
  const executable=ts.transpileModule('globalThis.draw=()=>{'+component.body.statements.slice(start,end).map(n=>n.getText(ast)).join('\n')+';return primalKnowledgeIntent;};', {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
  let owner='owner'; const refs=[{current:null},{current:null}]; let refIndex=0; const env={...controls, tacticalMindAvailable:()=>false, useRef:()=>refs[refIndex++%2],useState:()=>[0,()=>{}],currentAccountOwner:()=>owner,LOCAL_OWNER:'local',campaignId:'campaign',sessionId:'session',interactionMode:'do',state:structuredClone(state),conversationTargetId:'',combatTargetId:'',getTurnInteractionMetadata};
  vm.runInNewContext(executable,env);
  assert.equal(env.draw().selected,false);
  for (const change of ['owner','campaignId','sessionId','interactionMode','projection','combat']) {
    env.draw().choose(true); assert.equal(env.draw().selected,true,change+' starts checked');
    const old=env[change];
    if(change==='owner') owner='other'; else if(change==='projection') env.state.character.primal_knowledge_check.available=false; else if(change==='combat') env.state.combat.active=true; else env[change]=change==='interactionMode'?'say':'other';
    assert.equal(env.draw().selected,false,change+' clears');
    if(change==='owner') owner='owner'; else if(change==='projection') env.state.character.primal_knowledge_check.available=true; else if(change==='combat') env.state.combat.active=false; else env[change]=old;
    assert.equal(env.draw().selected,false,change+' return cannot resurrect');
  }
});

function storyAttribute(name) {
  let value;
  const visit=n=>{if((ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n))&&n.tagName.getText(ast)==='StoryColumn')value=n.attributes.properties.find(p=>ts.isJsxAttribute(p)&&p.name.text===name)?.initializer?.expression?.getText(ast);ts.forEachChild(n,visit);};visit(component);
  assert.ok(value,'real parent '+name);return value;
}
test('actual composer checkbox and Close callbacks cancel local consent without changing draft, target or pending original', () => {
  const h=harness(); h.env.setComposerOpen=value=>{h.env.composerOpen=value};
  vm.runInNewContext('globalThis.change='+storyAttribute('onPrimalKnowledgeChange')+'; globalThis.close='+storyAttribute('setComposerOpen')+';',h.env);
  h.env.change(true); assert.equal(h.intent.selected,true); h.env.close(false); assert.equal(h.intent.selected,false);
  assert.equal(h.env.messageRef.current,'Takla atıyorum'); assert.equal(h.env.combatTargetId,''); assert.equal(readPending('owner','campaign'),null); assert.equal(h.requests.length,0);h.close();
});

test('optional projection is fail-closed, truthful and has no enabled callback outside immediate untargeted Do', () => {
  assert.equal(controls.readPrimalKnowledgeProjection(undefined),null);
  for(const value of [null,{}, {...projection,available:'true'}, {...projection,skills:['Athletics']}, {...projection,skills:[...skills,'Athletics']}, {...projection,reason:false}])assert.equal(controls.readPrimalKnowledgeProjection(value),null);
  for(const variant of ['absent','unavailable','say','ask_dm','combat','target','pending']){
    const current=structuredClone(state);if(variant==='absent')delete current.character.primal_knowledge_check;if(variant==='unavailable')current.character.primal_knowledge_check={...projection,available:false,reason:'primal_knowledge_rage_required'};if(variant==='combat')current.combat.active=true;
    let changes=0; const tree=nodes(controls.PrimalKnowledgeControl({state:current,mode:['say','ask_dm'].includes(variant)?variant:'do',targetId:variant==='target'?'original-target':null,checked:true,blocked:variant==='pending',onChange:()=>changes++}));
    const checkbox=find(tree,'primal-knowledge-confirm');if(variant==='absent')assert.equal(checkbox,undefined);else{assert.equal(checkbox.props.disabled,true,variant);checkbox.props.onChange({target:{checked:true}});assert.equal(changes,0);if(variant!=='pending')assert.equal(checkbox.props.checked,false);}
  }
});

test('legacy uncertain retry cannot acquire current checked consent, and retry refusal does not consume a later draft consent', async () => {
  const first=harness({transport:async()=>{throw Error('lost ordinary reply')}});first.submit();await first.settled();assert.equal(Object.hasOwn(first.requests[0],'check_feature'),false);
  const retry=harness({sessionStorage:first.sessionStorage,transport:async()=>{throw Object.assign(Error('refused original'),{status:422})}});retry.choose();retry.env.messageRef.current='New unrelated draft';retry.submit('',undefined,'do',true);await retry.settled();assert.deepEqual(retry.requests[0],first.requests[0]);assert.equal(retry.intent.selected,true);assert.equal(retry.env.messageRef.current,'New unrelated draft');first.close();retry.close();
});

test('actual unknown recovery does not resend or alter opted payload; explicit server-proven abandon preserves unrelated draft', async () => {
  const h=harness({transport:async()=>{throw Error('lost feature reply')}});h.choose();h.submit();await h.settled();const original=readPending('owner','campaign');
  h.env.messageRef.current='Unrelated draft';h.choose();await h.env.recover('check');assert.equal(h.requests.length,1);assert.deepEqual(readPending('owner','campaign'),original);assert.equal(h.intent.selected,true);
  await h.env.recover('abandon');assert.equal(readPending('owner','campaign'),null);assert.equal(h.env.messageRef.current,'Unrelated draft');assert.equal(h.intent.selected,true);assert.equal(h.requests.length,1);h.close();
});

test('actual applied recovery reconciles history card without replaying a request or reading current Rage', async () => {
  const h=harness({transport:async()=>{throw Error('lost feature reply')}});h.choose();h.submit();await h.settled();const pending=readPending('owner','campaign');
  const result={skill:'Survival',ability:'strength',original_ability:'wisdom',check_feature:'primal_knowledge',d20:8,total:13,ability_modifier:3,proficiency_modifier:2,total_modifier:5,difficulty:'medium',outcome:'failure'};
  h.env.state.character.primal_knowledge_check.available=false;h.env.RECOVERY_API.status=async()=>({action_id:pending.key.actionId,state:'applied',response:null});let entries;h.env.setEntries=value=>entries=value;h.env.getCampaign=async()=>({state:h.env.state,history:[{player_message:'İzlere bakıyorum',narration:'Eski izler',skill_check_result:result}],combat_history:[]});
  await h.env.recover('check');assert.equal(h.requests.length,1);assert.equal(readPending('owner','campaign'),null);assert.deepEqual(entries.at(-1).skillCheckResult,result);const html=render(React.createElement(card.SkillCheckResultCard,{result:entries.at(-1).skillCheckResult}));assert.match(html,/Kuvvet \(Primal Knowledge\)/);assert.match(html,/Asıl yetenek.*BİL/);h.close();
});

test('actual frontend opted request survives generated parser with no client mechanics added', async () => {
  const {PlayGameTurnBody}=await import('../../../lib/api-zod/src/generated/api.ts');const h=harness();h.choose();h.submit('Gizleniyorum');await h.settled();assert.deepEqual(PlayGameTurnBody.parse(h.requests[0]),h.requests[0]);assert.equal(h.requests[0].check_feature,'primal_knowledge');h.close();
});
