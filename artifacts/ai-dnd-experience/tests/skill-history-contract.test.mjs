import assert from 'node:assert/strict';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import {test} from 'node:test';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {readFile} from 'node:fs/promises';
import {CreateCampaignResponse,GetCampaignResponse,ResumeCampaignResponse} from '../../../lib/api-zod/src/generated/api.ts';

// Reuse api-spec's installed Orval YAML parser; no new dependency or install.
const codegenRequire = createRequire(new URL('../../../lib/api-spec/package.json', import.meta.url));
const {load: parseYaml} = createRequire(codegenRequire.resolve('orval'))('js-yaml');

const specimen = {
  player_message:'Test için gizlenmeye çalışıyorum.',
  narration:'Gizlenme girişimin başarısız olur.',
  created_at:new Date('2026-10-15T12:00:00Z'),
};
const result={
  skill:'Stealth',ability:'dexterity',d20:2,
  proficient:true,expertise:true,ability_modifier:4,
  proficiency_modifier:4,total_modifier:8,total:10,
  difficulty:'medium',dc:15,outcome:'failure',
};

test('generated Create/Get/Resume campaign history accepts absent legacy skill result and rejects malformed values',()=>{
  for(const [kind,response] of Object.entries({Create:CreateCampaignResponse,Get:GetCampaignResponse,Resume:ResumeCampaignResponse})){
    const entrySchema=response.shape.history.element;
    const old=entrySchema.parse(specimen);
    assert.equal(Object.hasOwn(old,'skill_check_result'),false,kind+' legacy unchanged');
    const current=entrySchema.parse({...specimen,skill_check_result:result});
    assert.deepEqual(current.skill_check_result,result,kind+' typed skill carried');
    assert.equal(entrySchema.safeParse({...specimen,skill_check_result:{...result,d20:22}}).success,false,kind+' invalid roll');
    assert.equal(entrySchema.safeParse({...specimen,skill_check_result:{...result,outcome:'invented'}}).success,false,kind+' invalid outcome');
  }
});

test('public generated interface, OpenAPI and game upper flow agree without a narrowing cast',async()=>{
  const [spec,client,source,helper]=await Promise.all([
    readFile(new URL('../../../lib/api-spec/openapi.yaml',import.meta.url),'utf8'),
    readFile(new URL('../../../lib/api-client-react/src/generated/api.schemas.ts',import.meta.url),'utf8'),
    readGameBrowserSource(),
    readFile(new URL('../src/lib/transcript-history.ts',import.meta.url),'utf8')
  ]);
  const block=client.match(/export interface CampaignHistoryEntry \{([^}]+)\}/);
  assert.ok(block,'generated interface exists');
  assert.match(block[1],/skill_check_result\?: SkillCheckResult;/);
  const historySchema = parseYaml(spec).components.schemas.CampaignHistoryEntry;
  assert.ok(historySchema, 'authoritative OpenAPI schema exists');
  assert.equal(historySchema.properties.skill_check_result.$ref, '#/components/schemas/SkillCheckResult');
  assert.deepEqual(historySchema.required, ['player_message', 'narration', 'created_at']);
  assert.doesNotMatch(source,/HistoryWithSkillResult| as CampaignHistoryEntry & /,'no cast masks drift');
  const ast=ts.createSourceFile('game-browser.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const owners=new Map();
  const visit=node=>{
    if(ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)
        && ['undoLastTurn','handleResume','submitTurn','serverRecovery'].includes(node.name.text)){
      owners.set(node.name.text,node.getText(ast));
    }
    ts.forEachChild(node,visit);
  };
  visit(ast);
  // Dilim 0 Görev 5: the four history mappings are one helper (historyToEntries); it carries the skill field once.
  for(const owner of ['undoLastTurn','handleResume','submitTurn','serverRecovery']){
    assert.ok(owners.has(owner),owner+' exists');
    assert.equal(owners.get(owner).match(/historyToEntries\(/g)?.length,1,
      owner+' maps the generated history through exactly one historyToEntries call');
  }
  assert.equal(source.match(/historyToEntries\(/g)?.length,4,
    'undo, resume, real turn reconciliation and server-proven recovery all map history through the helper');
  assert.equal(source.match(/entry\.skill_check_result/g),null,'the play screen maps no history skill field of its own');
  assert.equal(helper.match(/skillCheckResult: entry\.skill_check_result/g)?.length,1,
    'the helper preserves exactly one generated history skill field');
});
