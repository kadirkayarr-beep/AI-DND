/** Real controlled UI presenters, SSR only; live interactions are a separate gate. */
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {before,after,test} from 'node:test';
process.env.PORT ||= '4184';process.env.BASE_PATH ||= '/';
let vite, React, render, ui={};
const meta={supported_starting_levels:[1,2,3],level_2:{prepared_spell_count:2,prepared_spell_ids:['Magic Missile','Shield','Burning Hands','Chromatic Orb','Disguise Self','Detect Magic'],metamagic_count:2,metamagic_options:['Quickened Spell','Twinned Spell']},level_3:{prepared_spell_count:2,prepared_spell_ids:['Magic Missile','Shield','Burning Hands','Chromatic Orb','Disguise Self','Detect Magic'],subclass_options:[{id:'aberrant',name:'Aberrant Sorcery'},{id:'draconic',name:'Draconic Sorcery'}]},effects_pending_by_level:{'1':['Innate pending'],'2':['Font pending'],'3':['Subclass effects pending']}};
const empty={startingLevel:1,level2Prepared:[],metamagic:[],level3Prepared:[],subclassId:''};
const full={startingLevel:3,level2Prepared:['Burning Hands','Chromatic Orb'],metamagic:['Quickened Spell','Twinned Spell'],level3Prepared:['Disguise Self','Detect Magic'],subclassId:'aberrant'};
before(async()=>{
 const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
 if(existsSync(path.join(process.cwd(),'src/components/sorcerer-starting-creation.tsx'))) ui=await vite.ssrLoadModule('/src/components/sorcerer-starting-creation.tsx');
 React=await import('react');const {renderToStaticMarkup}=await import('react-dom/server');
 render=(name,props)=>{assert.equal(typeof ui[name],'function',`Missing real presenter ${name}`);return renderToStaticMarkup(React.createElement(ui[name],props));};
});
after(async()=>{if(vite)await vite.close();});
test('live metadata exposes labelled level control and missing data never offers unearned levels',()=>{
 const props={draft:empty,metadata:meta,onChange:()=>{},onRetry:()=>{}};
 const html=render('StartingLevelControl',props);
 assert.match(html,/Başlangıç seviyesi/);for(const n of [1,2,3])assert.match(html,new RegExp(`value="${n}"`));
 const missing=render('StartingLevelControl',{...props,metadata:undefined});
 assert.doesNotMatch(missing,/value="[23]"/);
});
test('source loss retains visible selected level and provides retry and explicit downgrade',()=>{
 const html=render('StartingLevelControl',{draft:full,metadata:undefined,onChange:()=>{},onRetry:()=>{}});
 assert.match(html,/value="1"/);assert.match(html,/value="3"/);assert.match(html,/selected=""/);
 assert.match(html,/Yeniden dene/);assert.match(html,/yüklenemedi|kullanılamıyor/);
});
test('real level-three choice fieldsets show separate choices and honest pending effects',()=>{
 const html=render('StartingLevelChoices',{draft:full,metadata:meta,initialSpells:['Magic Missile','Shield'],onChange:()=>{}});
 assert.match(html,/<fieldset/);assert.match(html,/<legend/);
 for(const text of ['2. seviye','3. seviye','Quickened Spell','Twinned Spell','Aberrant Sorcery','Draconic Sorcery','Bu seviyedeki 1 özellik henüz oyunda tam işlemiyor.'])assert.ok(html.includes(text),text);
 assert.match(html,/type="checkbox"/);assert.match(html,/type="radio"/);
 assert.doesNotMatch(html,/value="Magic Missile"/);assert.doesNotMatch(html,/value="Shield"/);
 const two=render('StartingLevelChoices',{draft:{...full,startingLevel:2,level3Prepared:[],subclassId:''},metadata:meta,initialSpells:['Magic Missile','Shield'],onChange:()=>{}});
 assert.doesNotMatch(two,/type="radio"/);assert.ok(!two.includes('3. seviye'));
});
test('higher-level HP is deferred and all new choice inputs respect in-flight creation',()=>{
 assert.equal(render('StartingHitPoints',{level:1,hitPoints:8}),'<span>8</span>');
 assert.match(render('StartingHitPoints',{level:3,hitPoints:8}),/Oluşturulduğunda sunucu hesaplayacak/);
 const html=render('StartingLevelChoices',{draft:full,metadata:meta,initialSpells:['Magic Missile','Shield'],onChange:()=>{},disabled:true});
 for(const input of html.match(/<input[^>]*>/g)||[])assert.match(input,/disabled=""/);
 assert.ok((html.match(/<input[^>]*>/g)||[]).length>0);
});
test('pending effects notice is conditional and counts effects without rendering untrusted server text',()=>{
 assert.equal(render('ProgressionEffectsNotice',{}),'');assert.equal(render('ProgressionEffectsNotice',{effects:[]}),'');
 const html=render('ProgressionEffectsNotice',{effects:['Font not implemented','<script>test</script>']});
 assert.match(html,/Bu seviyedeki 2 özellik henüz oyunda tam işlemiyor\./);assert.doesNotMatch(html,/Font not implemented|&lt;script&gt;|<script>|<li/);
});

// Invoke the actual controlled presenter callbacks. This is not DOM/browser interaction evidence.
function nodes(element) {
 if(Array.isArray(element))return element.flatMap(nodes);
 if(!element || typeof element!=='object')return [];
 return [element,...nodes(element.props?.children)];
}
test('actual level and retry callbacks preserve explicit source-loss choices',()=>{
 let changed, retries=0;
 const tree=ui.StartingLevelControl({draft:full,metadata:undefined,onChange:value=>{changed=value;},onRetry:()=>{retries++;}});
 const select=nodes(tree).find(n=>n.type==='select');assert.ok(select);
 select.props.onChange({target:{value:'3'}});assert.equal(changed,undefined);
 select.props.onChange({target:{value:'1'}});assert.equal(changed,1);
 nodes(tree).find(n=>n.type==='button').props.onClick();assert.equal(retries,1);
});
test('actual checkbox and subclass callbacks emit controlled selections without mutating props',()=>{
 let changed;const draft=structuredClone(full), before=structuredClone(draft);
 const expanded={...meta,level_2:{...meta.level_2,metamagic_options:[...meta.level_2.metamagic_options,'Careful Spell']}};
 const tree=ui.StartingLevelChoices({draft,metadata:expanded,initialSpells:['Magic Missile','Shield'],onChange:value=>{changed=value;}});
 const inputs=nodes(tree).filter(n=>n.type==='input');
 inputs.find(n=>n.props.value==='Careful Spell').props.onChange({target:{checked:true}});
 assert.deepEqual(changed.metamagic,draft.metamagic,'third pick must not silently replace the existing two');
 inputs.find(n=>n.props.value==='Quickened Spell').props.onChange({target:{checked:false}});
 assert.deepEqual(changed.metamagic,['Twinned Spell']);
 inputs.find(n=>n.props.value==='draconic').props.onChange();assert.equal(changed.subclassId,'draconic');
 assert.deepEqual(draft,before);
});

test('stale initial choices can be explicitly removed without clearing unrelated higher choices',async()=>{
 const component=ui.StaleInitialSpellChoices;assert.equal(typeof component,'function','Missing stale-choice recovery presenter');
 const helper=await vite.ssrLoadModule('/src/lib/sorcerer-starting-creation.ts');
 const {updateLimitedSelection}=await vite.ssrLoadModule('/src/lib/character-catalog-normalizer.ts');
 const changedMeta=structuredClone(meta);
 for(const level of ['level_2','level_3'])changedMeta[level].prepared_spell_ids=[...changedMeta[level].prepared_spell_ids.filter(id=>id!=='Shield'),'Chaos Bolt'];
 let initial=['Magic Missile','Shield'];const draft=structuredClone(full),before=structuredClone(draft);
 assert.equal(helper.startingCreationFields('Sorcerer',draft,initial,changedMeta).ok,false);
 assert.deepEqual(updateLimitedSelection(initial,'Chaos Bolt',true,2),initial,'full count currently prevents replacement');
 const props={selectedSpells:initial,metadata:changedMeta,onRemove:id=>{initial=initial.filter(value=>value!==id);}};
 const html=render('StaleInitialSpellChoices',props);assert.match(html,/Shield/);assert.match(html,/Kaldır|kaldır/);
 const tree=component(props);nodes(tree).find(node=>node.type==='button').props.onClick();
 assert.deepEqual(initial,['Magic Missile']);initial=updateLimitedSelection(initial,'Chaos Bolt',true,2);
 assert.equal(helper.startingCreationFields('Sorcerer',draft,initial,changedMeta).ok,true);
 assert.deepEqual(draft,before);
 assert.equal(render('StaleInitialSpellChoices',{...props,metadata:undefined}),'','source loss must not classify every choice as stale');
});
