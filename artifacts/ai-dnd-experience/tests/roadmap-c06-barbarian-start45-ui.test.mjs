import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {emptyStartingDraft,changeStartingLevel} from '../src/lib/sorcerer-starting-creation.ts';

// Barbarian creation at selected starting levels 4 and 5. Source values: PHB PDF 51 (rows 4/5) via the server catalog.
// Behavioural tests only: real functions, real components called as functions, real screen code extracted by AST and run in vm.
const SKILLS=['Animal Handling','Athletics','Intimidation','Nature','Perception','Survival'];
const ABILITIES=['strength','constitution','intelligence','wisdom','charisma'];
const ASI=[...ABILITIES.map(a=>({feat:'Ability Score Improvement',increase:{[a]:2}})),
  ...ABILITIES.flatMap((a,i)=>ABILITIES.slice(i+1).map(b=>({feat:'Ability Score Improvement',increase:{[a]:1,[b]:1}})))];
const STR2={feat:'Ability Score Improvement',increase:{strength:2}};
const raw2=()=>({supported_starting_levels:[1,2],level_2:{choices:{},effects_supported:['Danger Sense: weapon/unarmed DEX saves only'],effects_pending:['Rage pending']}});
const raw3=()=>({...raw2(),supported_starting_levels:[1,2,3],level_3:{subclass_options:[{id:'berserker',name:'Path of the Berserker'}],primal_knowledge_skill_options:[...SKILLS],effects_supported:['Primal Knowledge: one additional class skill proficiency supported'],effects_pending:['Frenzy pending']}});
const raw4=()=>({...raw3(),supported_starting_levels:[1,2,3,4],level_4:{supported_asi_choices:structuredClone(ASI),effects_supported:['Selected level4 ordinary non-DEX Ability Score Improvement supported'],effects_pending:['Weapon Mastery pending','Higher-start equipment: normal starting gear only']}});
const raw5=()=>({...raw4(),supported_starting_levels:[1,2,3,4,5],level_5:{effects_supported:['Extra Attack: two attacks'],effects_pending:['Higher-start equipment: normal starting gear only','Fast Movement tracking pending']}});
const draftN=(level,extra={})=>({...emptyStartingDraft(),startingLevel:level,subclassId:'berserker',primalSkill:'Survival',...(level>=4?{level4Asi:structuredClone(STR2),level4ConConfirmed:true}:{}),...extra});

let helper={},ui={},vite,React,render;
before(async()=>{helper=await import('../src/lib/barbarian-starting-creation.ts');process.env.PORT||='4185';process.env.BASE_PATH||='/';const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});ui=await vite.ssrLoadModule('/src/components/barbarian-starting-creation.tsx');React=await import('react');render=(await import('react-dom/server')).renderToStaticMarkup;});
after(async()=>await vite?.close());
function fn(name){assert.equal(typeof helper[name],'function',name);return helper[name];}
function nodes(e){return Array.isArray(e)?e.flatMap(nodes):e&&typeof e==='object'?[e,...nodes(e.props?.children)]:[];}
const options=tree=>tree.filter(x=>x.type==='option').map(x=>x.props.value); // takes an already flattened node list

test('reader serves 4 and 5 only with valid detached blocks and keeps the verified prefix otherwise',()=>{
  const read=fn('readBarbarianStartingCreationOptions');
  const five=read(raw5());
  assert.deepEqual(five.supported_starting_levels,[1,2,3,4,5]);
  assert.deepEqual(five.level_4,raw5().level_4);assert.deepEqual(five.level_5,raw5().level_5);
  assert.deepEqual(read(raw4()).supported_starting_levels,[1,2,3,4]);assert.equal('level_5' in read(raw4()),false);
  five.level_4.supported_asi_choices.pop();five.level_4.effects_pending.push('forged');
  assert.equal(raw5().level_4.supported_asi_choices.length,15);  // detached copy
  const badFour=[l=>{l.supported_asi_choices=[];},l=>{l.supported_asi_choices=[{feat:'Ability Score Improvement',increase:{dexterity:2}}];},
    l=>{l.supported_asi_choices=[STR2,STR2];},l=>{l.supported_asi_choices=[{feat:'Tough',increase:{strength:2}}];},
    l=>{l.supported_asi_choices=[{feat:'Ability Score Improvement',increase:{strength:3}}];},l=>{l.effects_supported=[1];},l=>{l.effects_pending='x';},
    l=>{delete l.supported_asi_choices;},l=>{l.extra=true;}];
  for(const mutate of badFour){const v=raw5();mutate(v.level_4);const r=read(v);assert.deepEqual(r.supported_starting_levels,[1,2,3],JSON.stringify(v.level_4));assert.equal('level_4' in r,false);assert.equal('level_5' in r,false);}
  const noFour=raw5();delete noFour.level_4;assert.deepEqual(read(noFour).supported_starting_levels,[1,2,3]);
  const badFive=[l=>{l.effects_supported=[];l.effects_pending=[2];},l=>{l.effects_pending='x';},l=>{l.extra=1;}];
  for(const mutate of badFive){const v=raw5();mutate(v.level_5);const r=read(v);assert.deepEqual(r.supported_starting_levels,[1,2,3,4]);assert.deepEqual(r.level_4,raw5().level_4);assert.equal('level_5' in r,false);}
  const noFive=raw5();delete noFive.level_5;assert.deepEqual(read(noFive).supported_starting_levels,[1,2,3,4]);
  // A broken level 3 hides everything above it; the claimed level list alone grants nothing.
  const noThree=raw5();delete noThree.level_3;const r=read(noThree);assert.deepEqual(r.supported_starting_levels,[1,2]);assert.equal('level_4' in r,false);
  const onlyClaimed={...raw5(),supported_starting_levels:[1,2,3]};assert.deepEqual(read(onlyClaimed).supported_starting_levels,[1,2,3]);assert.equal('level_4' in read(onlyClaimed),false);
  // A level list that is not the exact prefix 1..n (n=2..5) is not a catalog at all.
  for(const levels of [[1,2,3,5],[1,3,4,5],[1,2,3,4,5,6],[2,3,4,5],[1,2,3,4,'5'],[1,2,3,4,4],[1],[]])assert.equal(read({...raw5(),supported_starting_levels:levels}),undefined,JSON.stringify(levels));
  assert.deepEqual(read(raw2()),raw2());assert.deepEqual(read(raw3()).supported_starting_levels,[1,2,3]);
});

test('request builder: exact start-4 and start-5 bundles, parsed by the generated Zod body',async()=>{
  const build=fn('barbarianStartingCreationFields'),read=fn('readBarbarianStartingCreationOptions'),meta=read(raw5());
  const {CreateCampaignBody}=await import('../../../lib/api-zod/src/generated/api.ts');
  for(const level of [4,5]){
    const draft=draftN(level),before=structuredClone(draft),result=build(draft,meta);
    const expected={'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'},'4':{asi:STR2},...(level===5?{'5':{}}:{})};
    assert.deepEqual(result,{ok:true,fields:{starting_level:level,level_choices:expected}});
    assert.deepEqual(draft,before);
    result.fields.level_choices['4'].asi.increase.strength=99;assert.equal(draft.level4Asi.increase.strength,2); // never aliases the draft
    const parsed=CreateCampaignBody.parse({character:{mode:'custom',class:'Barbarian',...build(draft,meta).fields}});
    assert.deepEqual(parsed.character.level_choices,expected);
  }
});

test('request builder refuses every incomplete, stale or foreign start-4/5 draft',()=>{
  const build=fn('barbarianStartingCreationFields'),read=fn('readBarbarianStartingCreationOptions'),meta=read(raw5());
  for(const level of [4,5]){
    const bad={noAsi:{level4Asi:undefined},unconfirmed:{level4ConConfirmed:false},unconfirmedUndefined:{level4ConConfirmed:undefined},
      dexterity:{level4Asi:{feat:'Ability Score Improvement',increase:{dexterity:2}}},wrongFeat:{level4Asi:{feat:'Tough',increase:{strength:2}}},
      three:{level4Asi:{feat:'Ability Score Improvement',increase:{strength:3}}},extraKey:{level4Asi:{...STR2,extra:1}},
      noSkill:{primalSkill:undefined},noSubclass:{subclassId:''},arcana:{primalSkill:'Arcana'},wild:{subclassId:'wild_heart'},
      sorcPrepared2:{level2Prepared:['Shield']},sorcMeta:{metamagic:['Quickened Spell']},sorcPrepared3:{level3Prepared:['Web']},
      sorcPrepared4:{level4Prepared:['Fog Cloud']},sorcCantrips:{level4Cantrips:['Shocking Grasp']},sorcPrepared5:{level5Prepared:['Silent Image']}};
    for(const [name,extra] of Object.entries(bad))assert.equal(build(draftN(level,extra),meta).ok,false,`${level} ${name}`);
    assert.equal(build(draftN(level),undefined).ok,false);
    assert.equal(build(draftN(level),read(raw3())).ok,false,'catalog without level 4');
    assert.equal(build(draftN(level),read(raw2())).ok,false);
    assert.equal(build(draftN(level),meta,['Survival']).ok,false,'owned Primal Knowledge skill');
    assert.equal(build(draftN(level),meta,['Athletics','Perception']).ok,true);
  }
  assert.equal(build(draftN(5),read(raw4())).ok,false,'catalog without level 5');
  assert.equal(build(draftN(4),read(raw4())).ok,true);
  assert.equal(build({...draftN(5),startingLevel:6},meta).ok,false);
  // Level-4 choices never leak below level 4.
  for(const level of [1,2,3]){
    for(const extra of [{level4Asi:structuredClone(STR2)},{level4ConConfirmed:true}])
      assert.equal(build({...emptyStartingDraft(),startingLevel:level,...(level===3?{subclassId:'berserker',primalSkill:'Survival'}:{}),...extra},meta).ok,false,`${level} ${JSON.stringify(extra)}`);
  }
  // The server's level-4 choice family is the only source: a family that lost the pick refuses it.
  const narrowed=raw5();narrowed.level_4.supported_asi_choices=ASI.filter(c=>!('strength' in c.increase));
  assert.equal(build(draftN(4),read(narrowed)).ok,false);
  assert.deepEqual(build({...emptyStartingDraft(),startingLevel:3,subclassId:'berserker',primalSkill:'Survival'},meta),
    {ok:true,fields:{starting_level:3,level_choices:{'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'}}}});
});

test('draft level changes keep the Barbarian picks through 3-5 and clear them below',()=>{
  const four=draftN(4);
  const five=changeStartingLevel(four,5);
  assert.equal(five.primalSkill,'Survival');assert.equal(five.subclassId,'berserker');assert.deepEqual(five.level4Asi,STR2);assert.equal(five.level4ConConfirmed,true);
  const three=changeStartingLevel(five,3);
  assert.equal(three.primalSkill,'Survival');assert.equal(three.level4Asi,undefined);assert.equal(three.level4ConConfirmed,false);
  const two=changeStartingLevel(three,2);assert.equal(two.primalSkill,undefined);assert.equal(two.subclassId,'');
  assert.equal(changeStartingLevel(four,1).primalSkill,undefined);
  assert.equal(changeStartingLevel({...emptyStartingDraft(),startingLevel:3,subclassId:'berserker'},4).primalSkill,undefined);
  assert.equal(changeStartingLevel({...emptyStartingDraft(),startingLevel:2},3).primalSkill,undefined);
});

test('pruning clears a stale, owned or no-longer-offered pick at 4 and 5 and keeps an unchanged draft by identity',()=>{
  const prune=fn('pruneBarbarianDraft'),read=fn('readBarbarianStartingCreationOptions'),meta=read(raw5());
  for(const level of [4,5]){
    const keep=draftN(level);assert.equal(prune(keep,meta,['Athletics']),keep,`identity ${level}`);
    const owned=prune(draftN(level),meta,['Survival']);assert.equal(owned.primalSkill,undefined);assert.equal(owned.subclassId,'berserker');assert.deepEqual(owned.level4Asi,STR2);
    const stale=prune(draftN(level,{level4Asi:{feat:'Ability Score Improvement',increase:{dexterity:2}}}),meta,[]);
    assert.equal(stale.level4Asi,undefined);assert.equal(stale.level4ConConfirmed,false);assert.equal(stale.primalSkill,'Survival');
    const narrowed=raw5();narrowed.level_4.supported_asi_choices=ASI.filter(c=>!('strength' in c.increase));
    const dropped=prune(draftN(level),read(narrowed),[]);assert.equal(dropped.level4Asi,undefined);assert.equal(dropped.level4ConConfirmed,false);
    const lost=prune(draftN(level),read(raw3()),[]);assert.equal(lost.level4Asi,undefined);assert.equal(lost.level4ConConfirmed,false);
    const noMeta=prune(draftN(level),undefined,[]);assert.equal(noMeta.primalSkill,undefined);assert.equal(noMeta.level4Asi,undefined);
  }
  const unconfirmed=draftN(4,{level4ConConfirmed:false});assert.equal(prune(unconfirmed,meta,[]),unconfirmed);
  const three=draftN(3);assert.equal(prune(three,meta,['Athletics']),three);
  const two={...emptyStartingDraft(),startingLevel:2};assert.equal(prune(two,meta,[]),two);
});

test('level control offers 4 and 5 only when the validated blocks exist, and never downgrades silently',()=>{
  const read=fn('readBarbarianStartingCreationOptions');
  let level;const props=(metadata,startingLevel=1)=>({draft:{...emptyStartingDraft(),startingLevel},metadata,onChange:n=>level=n,onRetry:()=>{}});
  let tree=nodes(ui.BarbarianStartingLevelControl(props(read(raw5()))));
  assert.deepEqual(options(tree),[1,2,3,4,5]);
  for(const wanted of [4,5]){level=undefined;tree.find(n=>n.type==='select').props.onChange({target:{value:String(wanted)}});assert.equal(level,wanted);}
  tree=nodes(ui.BarbarianStartingLevelControl(props(read(raw4()))));assert.deepEqual(options(tree),[1,2,3,4]);
  level=undefined;tree.find(n=>n.type==='select').props.onChange({target:{value:'5'}});assert.equal(level,undefined);
  tree=nodes(ui.BarbarianStartingLevelControl(props(read(raw3()))));level=undefined;tree.find(n=>n.type==='select').props.onChange({target:{value:'4'}});assert.equal(level,undefined);
  level=undefined;tree=nodes(ui.BarbarianStartingLevelControl(props(undefined,5)));
  assert.equal(tree.find(n=>n.type==='option'&&n.props.value===5).props.disabled,true);
});

test('choices component: ASI picker and explicit confirmation appear from level 4, confirmation resets on a new pick',()=>{
  const meta=fn('readBarbarianStartingCreationOptions')(raw5());let next;
  const base={metadata:meta,ownedSkills:['Athletics','Perception'],onChange:d=>next=d};
  const three=nodes(ui.BarbarianStartingChoices({...base,draft:{...emptyStartingDraft(),startingLevel:3}}));
  assert.equal(three.some(n=>n.props?.testId==='barbarian-asi-choice'),false);
  assert.equal(three.some(n=>n.props?.['data-testid']==='barbarian-asi-confirm'),false);
  for(const level of [4,5]){
    next=undefined;
    const draft=draftN(level,{level4Asi:undefined,level4ConConfirmed:false});
    const tree=nodes(ui.BarbarianStartingChoices({...base,draft}));
    const picker=tree.find(n=>n.props?.testId==='barbarian-asi-choice'),confirm=tree.find(n=>n.props?.['data-testid']==='barbarian-asi-confirm');
    assert.ok(picker&&confirm,`level ${level}`);
    assert.equal(picker.props.choices.length,15);
    assert.equal(confirm.props.disabled,true,'cannot confirm before choosing');
    picker.props.onChange(STR2);assert.deepEqual(next.level4Asi,STR2);assert.equal(next.level4ConConfirmed,false);assert.equal(draft.level4Asi,undefined);
    const chosen=nodes(ui.BarbarianStartingChoices({...base,draft:{...draft,level4Asi:STR2}}));
    const enabled=chosen.find(n=>n.props?.['data-testid']==='barbarian-asi-confirm');assert.equal(enabled.props.disabled,false);
    next=undefined;enabled.props.onChange({target:{checked:true}});assert.equal(next.level4ConConfirmed,true);assert.deepEqual(next.level4Asi,STR2);
    const confirmed=nodes(ui.BarbarianStartingChoices({...base,draft:{...draft,level4Asi:STR2,level4ConConfirmed:true}}));
    next=undefined;confirmed.find(n=>n.props?.testId==='barbarian-asi-choice').props.onChange({feat:'Ability Score Improvement',increase:{wisdom:2}});
    assert.equal(next.level4ConConfirmed,false);
    next=undefined;confirmed.find(n=>n.props?.testId==='barbarian-asi-choice').props.onChange(undefined);assert.equal(next.level4Asi,undefined);assert.equal(next.level4ConConfirmed,false);
  }
});

test('summary and scope: level 4 and 5 text lists the server effects, the ASI pick and the equipment limit',()=>{
  const meta=fn('readBarbarianStartingCreationOptions')(raw5());assert.equal(typeof ui.BarbarianStartingSummary,'function');
  const four=render(React.createElement(ui.BarbarianStartingScope,{metadata:meta,level:4}));
  assert.match(four,/seviyesi 4/);assert.match(four,/Weapon Mastery pending/);assert.match(four,/Selected level4 ordinary/);assert.match(four,/Normal başlangıç ekipmanı korunur/);
  const five=render(React.createElement(ui.BarbarianStartingScope,{metadata:meta,level:5}));
  assert.match(five,/seviyesi 5/);assert.match(five,/Extra Attack: two attacks/);assert.match(five,/Fast Movement tracking pending/);assert.doesNotMatch(five,/Metamagic|Sorcerer/);
  assert.match(render(React.createElement(ui.BarbarianStartingScope,{metadata:fn('readBarbarianStartingCreationOptions')(raw3()),level:4})),/doğrulanamadı/);
  const summary=render(React.createElement(ui.BarbarianStartingSummary,{draft:draftN(5),metadata:meta}));
  assert.match(summary,/Path of the Berserker/);assert.match(summary,/Survival/);assert.match(summary,/strength \+2/);assert.match(summary,/seviyesi 5/);
  const three=render(React.createElement(ui.BarbarianStartingSummary,{draft:draftN(3),metadata:meta}));assert.doesNotMatch(three,/Ability Score Improvement/);
  assert.equal(render(React.createElement(ui.BarbarianStartingSummary,{draft:draftN(1),metadata:meta})),'');
});

async function screen(){
  const ts=await import('typescript'),vm=await import('node:vm');
  const source=await readFile('src/components/character-creation-screen.tsx','utf8');
  const ast=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const evaluate=(code,env)=>{vm.runInNewContext(ts.transpileModule(`globalThis.__r=(${code});`,{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,env);return env.__r;};
  const declaration=name=>{let d;(function visit(n){if(ts.isVariableDeclaration(n)&&n.name.getText(ast)===name)d=n;ts.forEachChild(n,visit);})(ast);assert.ok(d,name);return d.initializer.getText(ast);};
  // The `&&` guard chain in front of a JSX element, evaluated as the screen itself would.
  const guards=tag=>{const found=[];(function visit(n){
    if((ts.isJsxSelfClosingElement(n)||ts.isJsxOpeningElement(n))&&n.tagName.getText(ast)===tag){
      let node=ts.isJsxOpeningElement(n)?n.parent:n;const conditions=[];
      while(node.parent&&ts.isBinaryExpression(node.parent)&&node.parent.operatorToken.kind===ts.SyntaxKind.AmpersandAmpersandToken&&node.parent.right===node){conditions.unshift(node.parent.left.getText(ast));node=node.parent;}
      found.push(conditions.length?conditions.map(c=>`(${c})`).join(' && '):'true');}
    ts.forEachChild(n,visit);})(ast);return found;};
  return {ts,vm,ast,evaluate,declaration,guards};
}

test('real screen: the class step opens for Barbarian 4 and 5 only when the live catalog advertises them',async()=>{
  const {evaluate,declaration}=await screen(),read=fn('readBarbarianStartingCreationOptions');
  const stepValid=declaration('isStepValid');
  const run=(metadata,startingLevel,characterClass='Barbarian')=>evaluate(stepValid,{characterClass,startingDraft:{...emptyStartingDraft(),startingLevel},barbarianStartingMetadata:metadata,startingMetadata:undefined,Boolean})('class');
  for(const level of [1,2,3,4,5])assert.equal(run(read(raw5()),level),true,`level ${level} advertised`);
  assert.equal(run(read(raw4()),5),false);assert.equal(run(read(raw3()),4),false);assert.equal(run(read(raw2()),3),false);
  assert.equal(run(undefined,4),false);assert.equal(run(undefined,1),true);
  assert.equal(run(read(raw5()),6),false);
  assert.equal(run(read(raw5()),4,'Fighter'),false);
});

test('real screen: choices and summary render for Barbarian 3-5 only',async()=>{
  const {evaluate,guards}=await screen();
  for(const tag of ['BarbarianStartingChoices','BarbarianStartingSummary']){
    const found=guards(tag);assert.equal(found.length,1,tag);
    const visible=(characterClass,startingLevel)=>evaluate(found[0],{characterClass,startingDraft:{startingLevel}});
    const expected=tag==='BarbarianStartingChoices'?[false,false,true,true,true]:[false,true,true,true,true];
    [1,2,3,4,5].forEach((level,i)=>assert.equal(Boolean(visible('Barbarian',level)),expected[i],`${tag} ${level}`));
    for(const other of ['Sorcerer','Fighter'])for(const level of [3,4,5])assert.equal(Boolean(visible(other,level)),false,`${tag} ${other}`);
  }
});

test('real screen: wizard submit sends the start-4 and start-5 bundles, never an unconfirmed, owned or caster pick',async()=>{
  const {evaluate,declaration}=await screen(),read=fn('readBarbarianStartingCreationOptions');
  const submit=declaration('handleSubmit');
  const sent=[];
  const make=(level,extra={},skills=[])=>({isFormValid:true,selectedSetting:{setting_id:'setting'},selectedRegion:{region_pack_id:'pack',region_id:'region'},selectedLocation:{entity_id:'place'},creating:false,characterClass:'Barbarian',
    startingDraft:draftN(level,extra),barbarianStartingMetadata:read(raw5()),barbarianStartingCreationFields:helper.barbarianStartingCreationFields,
    name:'Barb',species:'Human',background:'Soldier',alignment:'Neutral',abilityMethod:'standard_array',baseScores:{constitution:14},calculatedBackgroundBonuses:{},derivedStats:{allSkills:skills},
    selectedExpertiseSkills:[],selectedSpeciesSkills:[],backgroundData:{tool:'Gaming Set',origin_feat:'Savage Attacker'},speciesBonusFeat:'',equipmentPackage:'A',
    classData:{equipment_packages:[{id:'A',items:['Greataxe']}]},backgroundEquipmentOption:'A',selectedLanguages:['Dwarvish','Elvish'],selectedCantrips:[],selectedSpells:[],
    origin:'',appearance:'',personality:'',backstory:'',deathMode:'NORMAL',onCreate:(...args)=>sent.push(args)});
  const go=env=>{evaluate(submit,env)({preventDefault(){}});};
  for(const level of [4,5]){
    sent.length=0;go(make(level));
    assert.equal(sent.length,1,`level ${level}`);assert.equal(sent[0][0].starting_level,level);
    assert.deepEqual(sent[0][0].level_choices,{'2':{},'3':{subclass_id:'berserker',primal_knowledge_skill:'Survival'},'4':{asi:STR2},...(level===5?{'5':{}}:{})});
    for(const [extra,skills] of [[{level4ConConfirmed:false},[]],[{level4Asi:undefined},[]],[{level4Prepared:['Fog Cloud']},[]],[{level5Prepared:['Silent Image']},[]],[{},['Survival']]]){
      sent.length=0;go(make(level,extra,skills));assert.equal(sent.length,0,`${level} ${JSON.stringify(extra)} ${skills}`);
    }
  }
});

test('real screen: the Barbarian prune effect clears a stale ASI and the shared Sorcerer effect never touches it',async()=>{
  const {ts,vm,ast,evaluate}=await screen(),read=fn('readBarbarianStartingCreationOptions');
  const effects=[];(function visit(n){if(ts.isCallExpression(n)&&n.expression.getText(ast)==='useEffect')effects.push(n);ts.forEachChild(n,visit);})(ast);
  const barbarian=effects.filter(n=>n.arguments[0].getText(ast).includes('pruneBarbarianDraft('));assert.equal(barbarian.length,1);
  const shared=effects.filter(n=>n.arguments[0].getText(ast).includes('pruneStartingDraft('));assert.equal(shared.length,1);
  const {pruneStartingDraft}=await import('../src/lib/sorcerer-starting-creation.ts');
  const run=(effect,characterClass,draft,metadata)=>{let result=draft;
    evaluate(effect.arguments[0].getText(ast),{characterClass,pruneBarbarianDraft:helper.pruneBarbarianDraft,pruneStartingDraft,barbarianStartingMetadata:metadata,derivedStats:{allSkills:['Athletics']},
      selectedSpells:[],selectedCantrips:[],startingMetadata:{level_2:{prepared_spell_ids:[],metamagic_options:[]},level_3:{prepared_spell_ids:[],subclass_options:[{id:'aberrant',name:'A'}]}},setStartingDraft:update=>{result=update(result);}})();
    return result;};
  const narrowed=raw5();narrowed.level_4.supported_asi_choices=ASI.filter(c=>!('strength' in c.increase));
  const cleared=run(barbarian[0],'Barbarian',draftN(5),read(narrowed));assert.equal(cleared.level4Asi,undefined);assert.equal(cleared.level4ConConfirmed,false);assert.equal(cleared.primalSkill,'Survival');
  const keep=draftN(5);assert.equal(run(barbarian[0],'Barbarian',keep,read(raw5())),keep);
  assert.equal(run(barbarian[0],'Sorcerer',keep,read(narrowed)),keep);
  assert.equal(run(shared[0],'Barbarian',keep,read(raw5())),keep);
  void vm;
});
