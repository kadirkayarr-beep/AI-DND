import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import path from 'node:path';
let vite,ui;
before(async()=>{process.env.PORT||='4184';process.env.BASE_PATH||='/';const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});ui=await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');});
after(async()=>await vite?.close());
function nodes(e){return Array.isArray(e)?e.flatMap(nodes):e&&typeof e==='object'?[e,...nodes(e.props?.children)]:[];}
const state={spellcasting:{prepared:['Magic Missile'],slots:{1:3,2:2,3:2},sorcery_points:{current:3,max:3}},combat:{active:true,current_actor_id:'player',participant_records:[{id:'npc-1',kind:'npc',status:'active',current_hp:20}],action_economy:{actors:{player:{quickened_spell:{available:true,reason:null}}}}}};
const props={state,targetId:'npc-1',slot:'3',onSlotChange:()=>{},blocked:false,magicAvailable:false};
function render(extra={}){return nodes(ui.MagicMissileControl({...props,...extra}));}
function find(tree,id){return tree.find(n=>n.props?.['data-testid']===id);}
test('Quickened explicit opt-in uses separate server availability and exact existing command without mutating points',()=>{let selected=false,sent;const before=structuredClone(state);const tree=()=>render({quickened:selected,onQuickenedChange:v=>selected=v,onCommand:(_m,c)=>sent=c});const checkbox=find(tree(),'select-quickened-spell');assert.ok(checkbox,'adopted Quickened opt-in');checkbox.props.onChange({target:{checked:true}});assert.equal(selected,true);const cast=find(tree(),'button-cast-magic-missile');assert.equal(cast.props.disabled,false);cast.props.onClick();assert.deepEqual(sent,{steps:[{kind:'magic',ability:'Magic Missile',target_id:'npc-1',slot_level:3,metamagic:'quickened_spell'}]});assert.deepEqual(state,before);assert.ok(find(tree(),'sorcery-points'));});
test('ordinary casts omit mode; legacy state hides new controls even with stale selected prop',()=>{let sent;const legacy=structuredClone(state);delete legacy.spellcasting.sorcery_points;delete legacy.combat.action_economy.actors.player.quickened_spell;const tree=render({state:legacy,quickened:true,magicAvailable:true,onCommand:(_m,c)=>sent=c});assert.equal(find(tree,'select-quickened-spell'),undefined);assert.equal(find(tree,'sorcery-points'),undefined);find(tree,'button-cast-magic-missile').props.onClick();assert.deepEqual(sent,{steps:[{kind:'magic',ability:'Magic Missile',target_id:'npc-1',slot_level:3}]});});
test('unavailable Quickened and pending gate refuse opt-in and cast; authoritative refusal shown',()=>{for(const pending of [false,true]){let sends=0,choices=0;const unavailable=structuredClone(state);unavailable.combat.action_economy.actors.player.quickened_spell={available:false,reason:'insufficient_sorcery_points'};const tree=render({state:unavailable,blocked:pending,quickened:true,onQuickenedChange:()=>choices++,onCommand:()=>sends++});const checkbox=find(tree,'select-quickened-spell');assert.ok(checkbox);assert.equal(checkbox.props.disabled,true);checkbox.props.onChange({target:{checked:true}});find(tree,'button-cast-magic-missile').props.onClick();assert.equal(choices,0);assert.equal(sends,0);assert.ok(JSON.stringify(tree).includes('insufficient_sorcery_points'));}});
test('consent resets on context/source loss and submission, never restores itself',()=>{assert.equal(typeof ui.createQuickenedIntent,'function');const intent=ui.createQuickenedIntent();const context={key:'campaign-a/turn1',available:true,blocked:false};intent.sync(context);intent.choose(true);assert.equal(intent.selected,true);intent.sync({...context,key:'campaign-b/turn1'});assert.equal(intent.selected,false);intent.choose(true);intent.sync({...context,available:false});assert.equal(intent.selected,false);intent.sync(context);assert.equal(intent.selected,false);intent.choose(true);intent.sync({...context,blocked:true});assert.equal(intent.selected,false);});

test('actual panel clears consent for a different owner/campaign/session despite identical combat ids',async()=>{
 const {readFile}=await import('node:fs/promises');const {default:ts}=await import('typescript');const {default:vm}=await import('node:vm');
 const source=await readFile(new URL('../src/components/action-economy-panel.tsx',import.meta.url),'utf8');
 const ast=ts.createSourceFile('panel.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const functions=['quickenedProjection','ActionEconomyPanel'].map(name=>ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name).getText(ast).replace(/^export /,''));
 const code=ts.transpileModule(functions.join('\n')+'\nglobalThis.Panel=ActionEconomyPanel;',{compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
 const slots=[];let index=0;const env={readRageProjection:ui.readRageProjection,RageControl:ui.RageControl,createQuickenedIntent:ui.createQuickenedIntent,createRecklessIntent:ui.createRecklessIntent,MagicMissileControl:'MagicMissileControl',RecklessAttackControl:'RecklessAttackControl',React:{createElement:(type,props,...children)=>({type,props:{...props,children}})},useRef:value=>{const i=index++;return slots[i]??=( {current:value} );},useState:value=>{const i=index++;slots[i]??=value;return [slots[i],next=>{slots[i]=typeof next==='function'?next(slots[i]):next;}];}};
 vm.runInNewContext(code,env);const actual=structuredClone(state);Object.assign(actual.combat,{combat_id:'same',round:1,current_turn_index:0});Object.assign(actual.combat.action_economy.actors.player,{legal_actions:[],additional_actions:[],bonus_rules:[]});
 const sends=[];
 let targetId='npc-1';
 const renderPanel=scope=>{index=0;return nodes(env.Panel({state:actual,targetId,sending:false,decisionScope:scope,onCommand:(_label,command)=>sends.push(command)})).find(n=>n.type==='MagicMissileControl');};
 renderPanel('owner-a:campaign-a:session-a').props.onQuickenedChange(true);assert.equal(renderPanel('owner-a:campaign-a:session-a').props.quickened,true);
 assert.equal(renderPanel('owner-b:campaign-b:session-b').props.quickened,false);
 index=0;const summary=nodes(env.Panel({state:actual,targetId:'npc-1',sending:false,onCommand:()=>{}})).find(n=>n.type==='span'&&n.props.children[0]==='Bonus: ');assert.equal(summary.props.children[1],'hazır');
 const scope='owner-b:campaign-b:session-b';renderPanel(scope).props.onQuickenedChange(true);
 delete actual.spellcasting.sorcery_points;assert.equal(renderPanel(scope).props.quickened,false);
 actual.spellcasting.sorcery_points={current:3,max:3};assert.equal(renderPanel(scope).props.quickened,false);
 renderPanel(scope).props.onQuickenedChange(true);targetId='unavailable-target';assert.equal(renderPanel(scope).props.quickened,false);targetId='npc-1';
 renderPanel(scope).props.onQuickenedChange(true);renderPanel(scope).props.onSlotChange('2');assert.equal(renderPanel(scope).props.quickened,false);
 renderPanel(scope).props.onQuickenedChange(true);const selected=renderPanel(scope);
 const command={steps:[{kind:'magic',ability:'Magic Missile',target_id:'npc-1',slot_level:3,metamagic:'quickened_spell'}]};
 selected.props.onCommand('cast',command);selected.props.onCommand('cast',command);
 assert.equal(sends.length,1);assert.deepEqual(JSON.parse(JSON.stringify(sends[0])),command);assert.equal(renderPanel(scope).props.quickened,false);
});

test('character spell panel displays adopted authoritative points outside combat and leaves legacy absence unchanged',async()=>{
 const {SpellcastingPanel}=await vite.ssrLoadModule('/src/components/spellcasting-panel.tsx');
 const casting={cantrips:[],prepared:['Magic Missile'],slots:{1:1},slot_turn:null,sorcery_points:{current:0,max:3}};
 const tree=nodes(SpellcastingPanel({spellcasting:casting}));const pool=find(tree,'spell-sorcery-points');assert.ok(pool);assert.match(JSON.stringify(pool),/Sorcery Points/);assert.deepEqual(pool.props.children,['Sorcery Points: ',0,'/',3]);
 const legacy={...casting};delete legacy.sorcery_points;assert.equal(find(nodes(SpellcastingPanel({spellcasting:legacy})),'spell-sorcery-points'),undefined);
});
