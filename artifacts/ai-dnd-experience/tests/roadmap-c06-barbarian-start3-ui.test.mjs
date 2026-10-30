import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {emptyStartingDraft,changeStartingLevel} from '../src/lib/sorcerer-starting-creation.ts';

const SKILLS=['Animal Handling','Athletics','Intimidation','Nature','Perception','Survival'];
const raw2=()=>({supported_starting_levels:[1,2],level_2:{choices:{},effects_supported:['Danger Sense: weapon/unarmed DEX saves only'],effects_pending:['Rage pending']}});
const raw3=()=>({...raw2(),supported_starting_levels:[1,2,3],level_3:{subclass_options:[{id:'berserker',name:'Path of the Berserker'}],primal_knowledge_skill_options:[...SKILLS],effects_supported:['Primal Knowledge: one additional class skill proficiency supported'],effects_pending:['Frenzy pending']}});
const draft3=(extra={})=>({...emptyStartingDraft(),startingLevel:3,subclassId:'berserker',primalSkill:'Survival',...extra});

let helper={},ui={},vite,React,render;
before(async()=>{helper=await import('../src/lib/barbarian-starting-creation.ts');process.env.PORT||='4185';process.env.BASE_PATH||='/';const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});ui=await vite.ssrLoadModule('/src/components/barbarian-starting-creation.tsx');React=await import('react');render=(await import('react-dom/server')).renderToStaticMarkup;});
after(async()=>await vite?.close());
function fn(name){assert.equal(typeof helper[name],'function',name);return helper[name];}
function nodes(e){return Array.isArray(e)?e.flatMap(nodes):e&&typeof e==='object'?[e,...nodes(e.props?.children)]:[];}

test('reader serves start 3 only with a valid detached level_3 block, otherwise keeps verified 1/2',()=>{
  const read=fn('readBarbarianStartingCreationOptions'),source=raw3(),meta=read(source);
  assert.deepEqual(meta.supported_starting_levels,[1,2,3]);
  assert.deepEqual(meta.level_3,source.level_3);
  meta.level_3.primal_knowledge_skill_options.push('forged');meta.level_3.subclass_options[0].id='forged';
  assert.equal(source.level_3.primal_knowledge_skill_options.length,6);assert.equal(source.level_3.subclass_options[0].id,'berserker');
  const bad=(patch)=>{const v=raw3();patch(v.level_3);return read(v);};
  for(const mutate of [l=>{l.subclass_options=[];},l=>{l.subclass_options.push({id:'wild_heart',name:'x'});},l=>{l.subclass_options[0].id='wild_heart';},
    l=>{l.primal_knowledge_skill_options=SKILLS.slice(1);},l=>{l.primal_knowledge_skill_options=[...SKILLS.slice(1),'Arcana'];},
    l=>{l.primal_knowledge_skill_options=[...SKILLS.slice(1),'Athletics'];},
    l=>{l.effects_supported=[1];},l=>{l.effects_pending='x';}]){
    const result=bad(mutate);assert.deepEqual(result.supported_starting_levels,[1,2]);assert.equal('level_3' in result,false);
  }
  const noBlock=raw3();delete noBlock.level_3;const result=read(noBlock);assert.deepEqual(result.supported_starting_levels,[1,2]);assert.equal('level_3' in result,false);
  assert.deepEqual(read(raw2()),raw2());
  const twoEntries=read({...raw3(),supported_starting_levels:[1,2]});assert.deepEqual(twoEntries.supported_starting_levels,[1,2]);assert.equal('level_3' in twoEntries,false);
});

test('request builder: exact start-3 bundle, parsed by the generated Zod body, never trusts a typed cast',async()=>{
  const build=fn('barbarianStartingCreationFields'),read=fn('readBarbarianStartingCreationOptions'),meta=read(raw3()),draft=draft3(),before=structuredClone(draft);
  const result=build(draft,meta);
  assert.deepEqual(result,{ok:true,fields:{starting_level:3,level_choices:{'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'}}}});
  assert.deepEqual(draft,before);
  const {CreateCampaignBody}=await import('../../../lib/api-zod/src/generated/api.ts');
  assert.deepEqual(CreateCampaignBody.parse({character:{mode:'custom',class:'Barbarian',...result.fields}}).character.level_choices,result.fields.level_choices);
  for(const bad of [{primalSkill:undefined},{primalSkill:''},{primalSkill:'Arcana'},{subclassId:''},{subclassId:'wild_heart'}])assert.equal(build(draft3(bad),meta).ok,false,JSON.stringify(bad));
  assert.equal(build(draft3(),read(raw2())).ok,false);
  assert.equal(build(draft3(),undefined).ok,false);
  for(const extra of [{level2Prepared:['Shield']},{metamagic:['Quickened Spell']},{level3Prepared:['Web']},{level4Prepared:['Fog Cloud']},{level4ConConfirmed:true},{level5Prepared:['Silent Image']}])assert.equal(build(draft3(extra),meta).ok,false);
  for(const level of [1,2])for(const extra of [{subclassId:'berserker'},{primalSkill:'Survival'}]){
    assert.equal(build({...emptyStartingDraft(),startingLevel:level,...extra},meta).ok,false,`${level} ${JSON.stringify(extra)}`);
  }
  assert.deepEqual(build({...emptyStartingDraft(),startingLevel:2},meta),{ok:true,fields:{starting_level:2,level_choices:{'2':{}}}});
  assert.deepEqual(build(emptyStartingDraft(),meta),{ok:true,fields:{}});
});

test('builder independently refuses a Primal Knowledge skill the character already owns',()=>{
  const build=fn('barbarianStartingCreationFields'),meta=fn('readBarbarianStartingCreationOptions')(raw3());
  assert.equal(build(draft3(),meta,['Survival']).ok,false);
  assert.equal(build(draft3(),meta,['Athletics','Perception']).ok,true);
  assert.equal(build(draft3(),meta,[]).ok,true);
  assert.equal(build(draft3(),meta).ok,true);
  assert.equal(build({...emptyStartingDraft(),startingLevel:2},meta,['Survival']).ok,true);
});

test('actual wizard submit sends the start-3 bundle but never an owned skill',async()=>{
  const ts=await import('typescript'),vm=await import('node:vm');
  const source=await readFile('src/components/character-creation-screen.tsx','utf8');
  const ast=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let declaration;(function visit(n){if(ts.isVariableDeclaration(n)&&n.name.getText(ast)==='handleSubmit')declaration=n;ts.forEachChild(n,visit);})(ast);
  assert.ok(declaration);
  const sent=[];
  const env={isFormValid:true,selectedSetting:{setting_id:'setting'},selectedRegion:{region_pack_id:'pack',region_id:'region'},selectedLocation:{entity_id:'place'},creating:false,characterClass:'Barbarian',
    startingDraft:draft3(),barbarianStartingMetadata:fn('readBarbarianStartingCreationOptions')(raw3()),barbarianStartingCreationFields:helper.barbarianStartingCreationFields,
    name:'Barb',species:'Human',background:'Soldier',alignment:'Neutral',abilityMethod:'standard_array',baseScores:{constitution:14},calculatedBackgroundBonuses:{},derivedStats:{allSkills:[]},
    selectedExpertiseSkills:[],selectedSpeciesSkills:[],backgroundData:{tool:'Gaming Set',origin_feat:'Savage Attacker'},speciesBonusFeat:'',equipmentPackage:'A',
    classData:{equipment_packages:[{id:'A',items:['Greataxe']}]},backgroundEquipmentOption:'A',selectedLanguages:['Dwarvish','Elvish'],selectedCantrips:[],selectedSpells:[],
    origin:'',appearance:'',personality:'',backstory:'',deathMode:'NORMAL',onCreate:(...args)=>sent.push(args)};
  vm.runInNewContext(ts.transpileModule(`globalThis.submit=(${declaration.initializer.getText(ast)});`,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,env);
  env.submit({preventDefault(){}});
  assert.equal(sent.length,1);assert.equal(sent[0][0].starting_level,3);
  assert.deepEqual(sent[0][0].level_choices,{'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'}});
  env.derivedStats={allSkills:['Survival']};env.submit({preventDefault(){}});
  assert.equal(sent.length,1);
});

test('draft level changes never carry the Primal Knowledge pick below level 3 and reset on level 1',()=>{
  const down=changeStartingLevel(draft3(),2);assert.equal(down.primalSkill,undefined);assert.equal(down.subclassId,'');
  assert.equal(changeStartingLevel(draft3(),1).primalSkill,undefined);
  assert.equal(changeStartingLevel({...emptyStartingDraft(),startingLevel:2},3).primalSkill,undefined);
  assert.equal(changeStartingLevel(draft3(),3).primalSkill,'Survival');
});

test('pruning clears a stale or owned Primal Knowledge skill and keeps an unchanged draft by identity',()=>{
  const prune=fn('pruneBarbarianDraft'),read=fn('readBarbarianStartingCreationOptions'),meta=read(raw3());
  const keep=draft3();assert.equal(prune(keep,meta,['Athletics']),keep);
  assert.equal(prune(draft3(),meta,['Survival']).primalSkill,undefined);
  assert.equal(prune(draft3(),meta,['Survival']).subclassId,'berserker');
  assert.equal(prune(draft3({primalSkill:'Arcana'}),meta,[]).primalSkill,undefined);
  assert.equal(prune(draft3({subclassId:'wild_heart'}),meta,[]).subclassId,'');
  const lost=prune(draft3(),read(raw2()),[]);assert.equal(lost.primalSkill,undefined);assert.equal(lost.subclassId,'');
  const two={...emptyStartingDraft(),startingLevel:2};assert.equal(prune(two,meta,[]),two);
});

test('level control offers 3 only when the validated server block exists, and never downgrades silently',()=>{
  const read=fn('readBarbarianStartingCreationOptions'),meta3=read(raw3()),meta2=read(raw2());
  let level;const props=(metadata,startingLevel=1)=>({draft:{...emptyStartingDraft(),startingLevel},metadata,onChange:n=>level=n,onRetry:()=>{}});
  let tree=nodes(ui.BarbarianStartingLevelControl(props(meta3)));
  assert.deepEqual(tree.filter(n=>n.type==='option').map(n=>n.props.value),[1,2,3]);
  tree.find(n=>n.type==='select').props.onChange({target:{value:'3'}});assert.equal(level,3);
  level=undefined;tree=nodes(ui.BarbarianStartingLevelControl(props(meta2)));
  assert.deepEqual(tree.filter(n=>n.type==='option').map(n=>n.props.value),[1,2]);
  tree.find(n=>n.type==='select').props.onChange({target:{value:'3'}});assert.equal(level,undefined);
  tree.find(n=>n.type==='select').props.onChange({target:{value:'2'}});assert.equal(level,2);
  level=undefined;tree=nodes(ui.BarbarianStartingLevelControl(props(undefined,3)));
  assert.equal(tree.find(n=>n.type==='option'&&n.props.value===3).props.disabled,true);
});

test('choices component: explicit subclass and skill selects, owned skills excluded, callbacks return new drafts',()=>{
  assert.equal(typeof ui.BarbarianStartingChoices,'function');
  const meta=fn('readBarbarianStartingCreationOptions')(raw3());let next;
  const draft={...emptyStartingDraft(),startingLevel:3};
  const props={draft,metadata:meta,ownedSkills:['Athletics','Perception'],onChange:d=>next=d};
  const tree=nodes(ui.BarbarianStartingChoices(props));
  const subclass=tree.find(n=>n.props?.['data-testid']==='barbarian-subclass'),skill=tree.find(n=>n.props?.['data-testid']==='barbarian-primal-skill');
  assert.ok(subclass&&skill);
  assert.equal(subclass.props.value,'');assert.equal(skill.props.value,'');
  assert.deepEqual(nodes(skill).filter(n=>n.type==='option').map(n=>n.props.value),['','Animal Handling','Intimidation','Nature','Survival']);
  assert.deepEqual(nodes(subclass).filter(n=>n.type==='option').map(n=>n.props.value),['','berserker']);
  skill.props.onChange({target:{value:'Survival'}});assert.equal(next.primalSkill,'Survival');assert.equal(draft.primalSkill,undefined);
  subclass.props.onChange({target:{value:'berserker'}});assert.equal(next.subclassId,'berserker');
  next=undefined;skill.props.onChange({target:{value:'Athletics'}});assert.equal(next,undefined); // an owned pick is refused
});

test('scope text for level 3 lists the supported and pending effects and claims no full class',()=>{
  const meta=fn('readBarbarianStartingCreationOptions')(raw3());
  const html=render(React.createElement(ui.BarbarianStartingScope,{metadata:meta,level:3}));
  assert.match(html,/Primal Knowledge/);assert.match(html,/Frenzy pending/);assert.doesNotMatch(html,/Metamagic|Sorcerer/);
  assert.match(render(React.createElement(ui.BarbarianStartingScope,{metadata:meta})),/seviyesi 2/);
});

test('the screen\'s real shared prune effect leaves a Barbarian start-3 pick alone and still prunes a Sorcerer',async()=>{
  const ts=await import('typescript'),vm=await import('node:vm');
  const source=await readFile('src/components/character-creation-screen.tsx','utf8');
  const ast=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const effects=[];(function visit(n){if(ts.isCallExpression(n)&&n.expression.getText(ast)==='useEffect')effects.push(n);ts.forEachChild(n,visit);})(ast);
  const shared=effects.filter(n=>n.arguments[0].getText(ast).includes('pruneStartingDraft('));
  assert.equal(shared.length,1);
  const {pruneStartingDraft}=await import('../src/lib/sorcerer-starting-creation.ts');
  const sorcererMeta={level_2:{prepared_spell_ids:[],metamagic_options:[]},level_3:{prepared_spell_ids:[],subclass_options:[{id:'aberrant',name:'Aberrant'}]}};
  const run=(characterClass,draft)=>{
    let result=draft;
    const env={characterClass,pruneStartingDraft,selectedSpells:[],selectedCantrips:[],startingMetadata:sorcererMeta,setStartingDraft:update=>{result=update(result);}};
    vm.runInNewContext(ts.transpileModule(`globalThis.effect=(${shared[0].arguments[0].getText(ast)});`,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,env);
    env.effect();return result;
  };
  const barbarian=draft3();assert.equal(run('Barbarian',barbarian),barbarian);
  assert.equal(run('Barbarian',barbarian).subclassId,'berserker');
  const sorcerer={...emptyStartingDraft(),startingLevel:3,subclassId:'berserker'};
  assert.equal(run('Sorcerer',sorcerer).subclassId,'');
});

test('wizard wiring: the start components are imported and used (the guards themselves are behavioural tests in roadmap-c06-barbarian-start45-ui)',async()=>{
  // Superseded: the old guard text ([2, 3].includes / === 3) was a source regex. Start 3 reachability, the choices guard and the
  // summary guard are now evaluated from the real screen AST for levels 1-5 in roadmap-c06-barbarian-start45-ui.test.mjs.
  const source=await readFile('src/components/character-creation-screen.tsx','utf8');
  assert.match(source,/BarbarianStartingChoices/);
  assert.match(source,/pruneBarbarianDraft/);
  assert.match(source,/BarbarianStartingSummary/);
});
