// D-144 (ORTA-14): the creation screen's Armor Class is a draft-only number. At a start where the server's level
// steps can move it (the level 4 Ability Score Improvement; a Paladin's level 2 Defense style), the screen must not
// show the pre-step value as if it were the saved one.
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
let vite,ui,React,render;
before(async()=>{process.env.PORT||='4184';process.env.BASE_PATH||='/';const {createServer}=await import('vite');vite=await createServer({configFile:path.join(process.cwd(),'vite.config.ts'),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});ui=await vite.ssrLoadModule('/src/components/sorcerer-starting-creation.tsx');React=await import('react');render=(await import('react-dom/server')).renderToStaticMarkup;});
after(async()=>await vite?.close());

const DEFERRED=/sunucu hesaplayacak/;
// [class, starting level, deferred?]
const CASES=[
  ['Fighter',1,false],['Fighter',2,false],['Fighter',3,false],['Fighter',4,true],['Fighter',5,true],
  ['Rogue',3,false],['Rogue',4,true],['Monk',3,false],['Monk',4,true],['Barbarian',3,false],['Barbarian',4,true],
  ['Sorcerer',3,false],['Sorcerer',4,true],
  ['Paladin',1,false],['Paladin',2,true],['Paladin',3,true],['Paladin',5,true],
];

test('StartingArmorClass defers exactly where a level step can change the saved Armor Class',()=>{
  assert.equal(typeof ui.StartingArmorClass,'function');
  for(const [characterClass,level,deferred] of CASES){
    const html=render(React.createElement(ui.StartingArmorClass,{level,characterClass,armorClass:17}));
    if(deferred){assert.match(html,DEFERRED,`${characterClass} ${level}`);assert.ok(!html.includes('17'),`${characterClass} ${level} shows a stale number`);}
    else{assert.doesNotMatch(html,DEFERRED,`${characterClass} ${level}`);assert.ok(html.includes('17'),`${characterClass} ${level}`);}
  }
});

test('every Armor Class the creation screen shows goes through StartingArmorClass',async()=>{
  const source=await readFile('src/components/character-creation-screen.tsx','utf8');
  const ast=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const reads=[];
  function visit(n){if(ts.isPropertyAccessExpression(n)&&n.getText(ast)==='derivedStats.ac')reads.push(n);ts.forEachChild(n,visit);}
  visit(ast);
  assert.equal(reads.length,2,'vitals box and final summary note');
  for(const read of reads){
    let n=read.parent;
    while(n&&!(ts.isJsxSelfClosingElement(n)&&n.tagName.getText(ast)==='StartingArmorClass'))n=n.parent;
    assert.ok(n,`derivedStats.ac shown outside StartingArmorClass: ${read.parent.getText(ast)}`);
    const code=ts.transpileModule(`globalThis.element=(${n.getText(ast)});`,{compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
    for(const [characterClass,level,deferred] of CASES){
      const env={React,StartingArmorClass:ui.StartingArmorClass,characterClass,startingDraft:{startingLevel:level},derivedStats:{ac:17}};
      vm.runInNewContext(code,env);
      const html=render(env.element);
      if(deferred)assert.match(html,DEFERRED,`${characterClass} ${level}`);
      else assert.ok(html.includes('17')&&!DEFERRED.test(html),`${characterClass} ${level}`);
    }
  }
});
