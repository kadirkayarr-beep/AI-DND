import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import path from 'node:path';
let vite,ui;
before(async()=>{process.env.PORT||='4184';process.env.BASE_PATH||='/';const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent',plugins:[{name:'font-test-surface',enforce:'pre',transform(code,id){if(id.replaceAll('\\','/').endsWith('/src/pages/game/world-panels.tsx'))return code+'\nexport {LeftColumn as TestLeftColumn};';}}]});ui=await vite.ssrLoadModule('/src/components/spellcasting-panel.tsx');});
after(async()=>await vite?.close());
function nodes(e){return Array.isArray(e)?e.flatMap(nodes):e&&typeof e==='object'?[e,...nodes(e.props?.children)]:[];}
const casting={cantrips:[],prepared:[],slots:{1:2,2:1},slot_turn:null,sorcery_points:{current:0,max:3},convert_spell_slot:{options:[{slot_level:1,points_gained:1,available:true,reason:null},{slot_level:2,points_gained:2,available:true,reason:null}]}};
function find(tree,id){return tree.find(n=>n.props?.['data-testid']===id);}
function render(extra={}){assert.equal(typeof ui.SpellSlotConversionChoice,'function');return nodes(ui.SpellSlotConversionChoice({spellcasting:casting,slot:'',onSlotChange:()=>{},blocked:false,onCommand:()=>{},...extra}));}
test('explicit slot conversion sends exact single typed request without caster choices, target or resource arithmetic',()=>{let slot='',sent;const before=structuredClone(casting);const tree=()=>render({slot,onSlotChange:v=>slot=v,onCommand:(_m,c)=>sent=c});assert.equal(find(tree(),'button-convert-spell-slot').props.disabled,true);find(tree(),'select-convert-spell-slot').props.onChange({target:{value:'2'}});find(tree(),'select-convert-spell-slot').props.onChange({target:{value:''}});assert.equal(slot,'');assert.equal(sent,undefined);find(tree(),'select-convert-spell-slot').props.onChange({target:{value:'2'}});find(tree(),'button-convert-spell-slot').props.onClick();assert.deepEqual(sent,{steps:[{kind:'convert_spell_slot',slot_level:2}]});assert.deepEqual(casting,before);});
test('legacy source absent hides conversion; unavailable option and pending never send',()=>{for(const change of [{spellcasting:{...casting,convert_spell_slot:undefined}},{blocked:true},{spellcasting:{...casting,convert_spell_slot:{options:[{slot_level:2,points_gained:2,available:false,reason:'sorcery_points_overflow'}]}}}]){let sends=0;const tree=render({slot:'2',onCommand:()=>sends++,...change});const button=find(tree,'button-convert-spell-slot');assert.ok(!button||button.props.disabled);button?.props.onClick();assert.equal(sends,0);}const tree=render({slot:'2',spellcasting:{...casting,convert_spell_slot:{options:[{slot_level:2,points_gained:2,available:false,reason:'sorcery_points_overflow'}]}}});assert.ok(JSON.stringify(tree).includes('sorcery_points_overflow'));});
test('no Magic Missile, Quickened choice, ordinary Action or Bonus budget is required by conversion control',()=>{let sent;const tree=render({slot:'1',onCommand:(_m,c)=>sent=c});assert.equal(find(tree,'button-convert-spell-slot').props.disabled,false);find(tree,'button-convert-spell-slot').props.onClick();assert.deepEqual(sent,{steps:[{kind:'convert_spell_slot',slot_level:1}]});});

test('actual character spell surface forwards same typed command owner and pending scope outside combat',async()=>{
 const {TestLeftColumn}=await vite.ssrLoadModule('/src/pages/game/world-panels.tsx');let sent;
 const command={steps:[{kind:'convert_spell_slot',slot_level:1}]};const onCommand=(_m,c)=>sent=c;
 const tree=nodes(TestLeftColumn({state:{spellcasting:casting,character:{},inventory:[],combat:{active:false}},decisionScope:'owner:campaign:session',conversionBlocked:true,onCommand}));
 const panel=tree.find(n=>n.type?.name==='SpellcastingPanel');assert.equal(panel.props.onCommand,onCommand);assert.equal(panel.props.conversionBlocked,true);assert.match(panel.props.decisionScope,/owner:campaign:session/);panel.props.onCommand('convert',command);assert.deepEqual(sent,command);
});

test('conversion draft drops selected slot across account/campaign/turn/source loss/pending and never auto-restores',()=>{assert.equal(typeof ui.createConversionDraft,'function');const draft=ui.createConversionDraft();for(const next of ['other-account','other-campaign','next-turn','source-missing','pending']){draft.sync('current');draft.choose('2');assert.equal(draft.slot,'2');draft.sync(next);assert.equal(draft.slot,'');draft.sync('current');assert.equal(draft.slot,'');}});

test('actual conversion wrapper clears draft on source/pending/scope changes without restoring previous slot',async()=>{
 const {readFile}=await import('node:fs/promises');const {default:ts}=await import('typescript');const {default:vm}=await import('node:vm');
 const source=await readFile(new URL('../src/components/spell-slot-conversion.tsx',import.meta.url),'utf8');const ast=ts.createSourceFile('conversion.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const functions=['conversionOptions','createConversionDraft','SpellSlotConversionControl'].map(name=>ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name).getText(ast).replace(/^export /,''));
 const code=ts.transpileModule(functions.join('\n')+'\nglobalThis.Control=SpellSlotConversionControl;',{compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
 const slots=[];let index=0;const env={SpellSlotConversionChoice:'Choice',React:{createElement:(type,props,...children)=>({type,props:{...props,children}})},useRef:value=>{const i=index++;return slots[i]??={current:value};},useState:value=>{const i=index++;slots[i]??=value;return[slots[i],next=>{slots[i]=typeof next==='function'?next(slots[i]):next;}];}};
 vm.runInNewContext(code,env);const render=(extra={})=>{index=0;return env.Control({spellcasting:casting,decisionScope:'owner-a:campaign-a:turn-1',blocked:false,onCommand:()=>{},...extra});};
 render().props.onSlotChange('2');assert.equal(render().props.slot,'2');assert.equal(render({decisionScope:'owner-b:campaign-b:turn-1'}).props.slot,'');assert.equal(render().props.slot,'');
 render().props.onSlotChange('2');assert.equal(render({blocked:true}).props.slot,'');assert.equal(render().props.slot,'');
 render().props.onSlotChange('2');assert.equal(render({spellcasting:{...casting,convert_spell_slot:undefined}}).props.slot,'');assert.equal(render().props.slot,'');
 let sent;render().props.onSlotChange('1');const command={steps:[{kind:'convert_spell_slot',slot_level:1}]};render({onCommand:(_m,c)=>sent=c}).props.onCommand('convert',command);assert.deepEqual(sent,command);assert.equal(render().props.slot,'');
});
