import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
let vite, ui;
before(async () => {
  process.env.PORT ||= '4184'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
});
after(async () => await vite?.close());
const projection = { available: true, active: false, reason: null };
const context = (overrides = {}) => ({ decisionKey: 'combat:1:0', projection, sending: false, attackEnabled: true, continueEnabled: true, reactionEnabled: false, ...overrides });
function controller(ctx = context()) { assert.equal(typeof ui.createRecklessIntent, 'function', 'real action panel must expose its consent controller'); const value = ui.createRecklessIntent(); value.sync(ctx); return value; }
function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
test('legacy, missing and malformed server projections fail closed', () => {
  for (const value of [undefined, null, {}, {available: 'true', active: false, reason: null}, {available: true, active: 0, reason: null}, {available: true, active: false}, {available:true,active:true,reason:null}]) {
    const c = controller(context({ projection: value })); c.choose(true); assert.equal(c.selected, false); assert.equal(c.available, false);
  }
});
test('unchecked legacy payload remains exactly omitted; only explicit consent sends true', () => {
  const c = controller(); const calls = []; const send = (label, command) => calls.push(command);
  c.submit('attack', {kind:'attack', target_id:'npc'}, send);
  assert.deepEqual(calls, [{steps:[{kind:'attack',target_id:'npc'}]}]);
  c.sync(context({sending:true})); c.sync(context()); c.choose(true);
  c.submit('attack', {kind:'attack',target_id:'npc'}, send);
  assert.deepEqual(calls[1], {steps:[{kind:'attack',target_id:'npc',reckless_attack:true}]});
  assert.equal(c.selected, false); assert.deepEqual(projection, {available:true,active:false,reason:null});
});
test('turn, availability and reaction decision changes reset consent; no automatic reactivation', () => {
  const c = controller(); c.choose(true); assert.equal(c.selected,true);
  c.sync(context({decisionKey:'combat:2:0'})); assert.equal(c.selected,false);
  c.choose(true); c.sync(context({decisionKey:'combat:2:0',projection:{available:false,active:false,reason:'first_roll_closed'}})); assert.equal(c.selected,false);
  c.sync(context()); assert.equal(c.selected,false); c.choose(true);
  c.sync(context({decisionKey:'combat:1:0:opportunity-2'})); assert.equal(c.selected,false);
});
test('pending, duplicate and unavailable attack dispatch never submit', () => {
  for (const ctx of [context({sending:true}), context({attackEnabled:false,continueEnabled:false,reactionEnabled:true})]) {
    const c = controller(ctx); c.choose(true); let count=0;
    c.submit('attack',{kind:'attack',target_id:'npc'},()=>count++); assert.equal(count,0);
  }
  const c = controller(); c.choose(true); let count=0;
  c.submit('attack',{kind:'attack'},()=>count++); c.submit('attack',{kind:'attack'},()=>count++); assert.equal(count,1);
});
test('own-turn eligible attack reaction can opt in without base Action; movement reaction cannot', () => {
  const c=controller(context({attackEnabled:false,continueEnabled:false,reactionEnabled:true})); c.choose(true); let sent;
  c.submit('reaction',{kind:'react',opportunity_id:'ready-1'},(_,value)=>sent=value);
  assert.deepEqual(sent,{steps:[{kind:'react',opportunity_id:'ready-1',reckless_attack:true}]});
  const move=controller(context({reactionEnabled:false})); move.choose(true);
  move.submit('reaction',{kind:'react',opportunity_id:'move-1'},(_,value)=>sent=value);
  assert.deepEqual(sent,{steps:[{kind:'react',opportunity_id:'move-1'}]});
});
test('server refusal leaves authority unchanged and retry requires fresh explicit consent', () => {
  const c=controller(); c.choose(true); const calls=[];
  c.submit('attack',{kind:'attack'},(_,v)=>calls.push(v));
  c.sync(context({sending:true})); c.sync(context());
  assert.equal(c.selected,false); assert.equal(c.active,false);
  c.submit('attack',{kind:'attack'},(_,v)=>calls.push(v));
  assert.deepEqual(calls[1],{steps:[{kind:'attack'}]});
});
test('real control shows both Advantage consequences, is unchecked, and disables pending choice', () => {
  assert.equal(typeof ui.RecklessAttackControl,'function'); let chosen;
  const tree=nodes(ui.RecklessAttackControl({available:true,active:false,selected:false,disabled:false,onChange:v=>chosen=v}));
  const input=tree.find(n=>n.type==='input'); assert.equal(input.props.checked,false);
  input.props.onChange({target:{checked:true}}); assert.equal(chosen,true);
  const text=JSON.stringify(tree); assert.match(text,/Strength/); assert.match(text,/Avantaj/); assert.match(text,/sana/); assert.match(text,/sonraki/i);
  const disabled=nodes(ui.RecklessAttackControl({available:true,active:false,selected:false,disabled:true,onChange:v=>chosen=v})).find(n=>n.type==='input');
  chosen=false; disabled.props.onChange({target:{checked:true}}); assert.equal(chosen,false);
});
function panelState(overrides={}) { return {combat:{active:true,combat_id:'combat',round:1,current_turn_index:0,current_actor_id:'player',participant_records:[],action_economy:{actors:{player:{base_action_spent:false,additional_actions:[],bonus_action_available:false,bonus_action_spent:false,bonus_rules:[],reaction_available:true,movement_remaining:30,speed_ft:30,ready:null,opportunity:null,legal_actions:[{kind:'attack',legal:true,reason:null}],reckless_attack:projection,...overrides}}}}}; }
test('actual action panel consumes projection, shows own-turn attack reaction with spent Action, hides move reaction', async()=>{
  const React=await import('react'); const {renderToStaticMarkup}=await import('react-dom/server');
  const render=(state,sending=false)=>renderToStaticMarkup(React.createElement(ui.ActionEconomyPanel,{state,targetId:'npc',sending,onCommand(){}}));
  assert.match(render(panelState()), /reckless-attack-control/);
  assert.doesNotMatch(render(panelState({reckless_attack:undefined})), /reckless-attack-control/);
  const reaction={base_action_spent:true,legal_actions:[],opportunity:{id:'ready-1'},ready:{trigger:{event:'actor_attacks',actor_id:'player'},response:{kind:'attack'}}};
  assert.match(render(panelState(reaction)), /reckless-attack-control/);
  assert.doesNotMatch(render(panelState({...reaction,ready:{...reaction.ready,response:{kind:'move'}}})), /reckless-attack-control/);
  assert.doesNotMatch(render(panelState({...reaction,reaction_available:false})), /reckless-attack-control/);
  assert.match(render(panelState(),true), /type="checkbox"[^>]*disabled/);
  assert.match(render(panelState({reckless_attack:{available:false,active:true,reason:'already_active'}})), /reckless-attack-active/);
});
test('authoritative Reckless refusal has an actionable presentation',async()=>{
 const {combatErrorMessage}=await import('../src/lib/combat-ui-contract.ts');
 assert.ok(combatErrorMessage({data:{detail:{code:'reckless_attack_unavailable'}}}));
});
// Execute the actual panel body with a bounded hook store, replacing only React's
// hook/view boundary. SSR above separately verifies the real React renderer.
async function panelHarness(initialState=panelState()) {
 const ts=await import('typescript'); const vm=await import('node:vm'); const {readFile}=await import('node:fs/promises');
 const source=await readFile(new URL('../src/components/action-economy-panel.tsx',import.meta.url),'utf8');
 const ast=ts.createSourceFile('panel.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const fn=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='ActionEconomyPanel');
 const dependencies=['createQuickenedIntent','quickenedProjection'].map(name=>ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name).getText(ast).replace(/^export /,'')).join('\n');
 const code=ts.transpileModule(dependencies+'\n'+fn.getText(ast).replace(/^export /,'')+'\nglobalThis.panel=ActionEconomyPanel;', {compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 const slots=[]; let cursor=0; const sent=[];
 const env={FighterControl:'FighterControl',MonkControl:'MonkControl',RogueControl:'RogueControl',CunningStrikeControl:'CunningStrikeControl',readRogueProjection:()=>null,cunningStrikeFields:()=>({}),readRageProjection:ui.readRageProjection,RageControl:ui.RageControl,createRecklessIntent:ui.createRecklessIntent,RecklessAttackControl:ui.RecklessAttackControl,MagicMissileControl:ui.MagicMissileControl,
  React:{createElement:(type,props,...children)=>({type,props:{...props,children}})},
  useRef(value){const index=cursor++;return slots[index]??=( {current:value} );},
  useState(value){const index=cursor++;if(!(index in slots))slots[index]=value;return[slots[index],next=>{slots[index]=typeof next==='function'?next(slots[index]):next;}];}};
 vm.runInNewContext(code,env);
 const props={state:initialState,targetId:'npc',sending:false,onCommand:(_,command)=>sent.push(JSON.parse(JSON.stringify(command)))};
 const render=()=>{cursor=0;return nodes(env.panel(props));};
 const choose=()=>render().find(n=>n.type===ui.RecklessAttackControl).props.onChange(true);
 const click=(kind)=>{const labels={attack:'Saldır · Action',reaction:'Reaction kullan',continue:'Attack Action devamı'};render().find(n=>n.type==='button'&&n.props.children.includes(labels[kind])).props.onClick();};
 return {props,sent,render,choose,click};
}
test('actual panel sends opt-in through existing typed attack owner and blocks duplicate/pending handlers',async()=>{
 const h=await panelHarness();h.click('attack');assert.deepEqual(h.sent,[{steps:[{kind:'attack',target_id:'npc'}]}]);
 h.click('attack');assert.equal(h.sent.length,1);
 h.props.sending=true;h.render();h.props.sending=false;h.render();h.choose();h.click('attack');
 assert.deepEqual(h.sent[1],{steps:[{kind:'attack',target_id:'npc',reckless_attack:true}]});
 assert.equal(h.render().find(n=>n.type===ui.RecklessAttackControl).props.selected,false);
 h.props.sending=true;h.click('attack');assert.equal(h.sent.length,2);
});
test('actual panel resets next turn and emits explicit true only for eligible attack reaction',async()=>{
 const h=await panelHarness();h.choose();h.props.state=structuredClone(h.props.state);h.props.state.combat.round++;h.click('attack');
 assert.deepEqual(h.sent[0],{steps:[{kind:'attack',target_id:'npc'}]});
 const r=await panelHarness(panelState({base_action_spent:true,legal_actions:[],ready:{trigger:{event:'actor_attacks',actor_id:'player'},response:{kind:'attack'}},opportunity:{id:'op1'}}));
 r.choose();r.click('reaction');assert.deepEqual(r.sent[0],{steps:[{kind:'react',opportunity_id:'op1',reckless_attack:true}]});
 const before=JSON.stringify(r.props.state);r.props.sending=true;r.render();r.props.sending=false;r.render();r.click('reaction');
 assert.deepEqual(r.sent[1],{steps:[{kind:'react',opportunity_id:'op1'}]});assert.equal(JSON.stringify(r.props.state),before);
});
test('actual continuation control uses server availability even when base Action is spent',async()=>{
 const h=await panelHarness(panelState({base_action_spent:true,legal_actions:[{kind:'attack',legal:false,reason:'spent'}],attack_action:{remaining_attacks:1}}));
 h.choose();h.click('continue');assert.deepEqual(h.sent,[{steps:[{kind:'continue_attack',target_id:'npc',reckless_attack:true}]}]);
});
