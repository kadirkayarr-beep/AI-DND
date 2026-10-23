import assert from 'node:assert/strict';
import {test} from 'node:test';
import ts from 'typescript';
import {readFile} from 'node:fs/promises';
import {CreateCampaignResponse,GetCampaignResponse,ResumeCampaignResponse} from '../../../lib/api-zod/src/generated/api.ts';

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
  const [spec,client,source]=await Promise.all([
    readFile(new URL('../../../lib/api-spec/openapi.yaml',import.meta.url),'utf8'),
    readFile(new URL('../../../lib/api-client-react/src/generated/api.schemas.ts',import.meta.url),'utf8'),
    readFile(new URL('../src/pages/game-browser.tsx',import.meta.url),'utf8')
  ]);
  const block=client.match(/export interface CampaignHistoryEntry \{([^}]+)\}/);
  assert.ok(block,'generated interface exists');
  assert.match(block[1],/skill_check_result\?: SkillCheckResult;/);
  const specBlock=spec.match(/    CampaignHistoryEntry:\s*\n([\s\S]*?)    CampaignDetail:/);
  assert.ok(specBlock,'authoritative OpenAPI schema exists');
  assert.match(specBlock[1],/skill_check_result:\s*\n\s+\$ref: "#\/components\/schemas\/SkillCheckResult"/);
  assert.match(specBlock[1],/required: \[player_message, narration, created_at\]/);
  assert.doesNotMatch(source,/HistoryWithSkillResult| as CampaignHistoryEntry & /,'no cast masks drift');
  const ast=ts.createSourceFile('game-browser.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const owners=new Map();
  const visit=node=>{
    if(ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)
        && ['undoLastTurn','handleResume','submitTurn'].includes(node.name.text)){
      owners.set(node.name.text,node.getText(ast));
    }
    ts.forEachChild(node,visit);
  };
  visit(ast);
  for(const owner of ['undoLastTurn','handleResume','submitTurn']){
    assert.ok(owners.has(owner),owner+' exists');
    assert.equal(owners.get(owner).match(/skillCheckResult: entry\.skill_check_result/g)?.length,1,
      owner+' preserves exactly one generated history skill field');
  }
  assert.equal(source.match(/skillCheckResult: entry\.skill_check_result/g)?.length,3,
    'undo, resume and real turn reconciliation all preserve the skill field');
});
