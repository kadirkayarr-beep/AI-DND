import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { after, before, test } from 'node:test';
import ts from 'typescript';
import { startingCreationPayload } from '../src/lib/starting-creation-payload.ts';
import { emptyStartingDraft } from '../src/lib/sorcerer-starting-creation.ts';

process.env.PORT ||= '4182';
process.env.BASE_PATH ||= '/';

// D-564 / D-559 / D-573 / D-560: the character creation screen is split, its payload no longer carries the legacy race key,
// and the hidden test-only block is gone: the class ids are read from the visible class cards instead.
const catalog = {
  races: { Human: { name_tr: 'Insan', speed: '9 metre', darkvision: 'Yok', traits: [] } },
  classes: {
    Fighter: { name_tr: 'Savasci (Fighter)', hit_die: 10, primary_ability: 'strength', skill_count: 2, skill_options: ['Athletics'], features: [], is_spellcaster: false },
    Wizard: { name_tr: 'Buyucu (Wizard)', hit_die: 6, primary_ability: 'intelligence', skill_count: 2, skill_options: ['Arcana'], features: [], is_spellcaster: true, cantrips_count: 3, spells_count: 6 },
  },
  backgrounds: {}, skills: {}, alignments: [], languages: [], equipment_rules: {},
};
let vite, source, component, React, render;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  component = await vite.ssrLoadModule('/src/components/character-creation-screen.tsx');
  React = await import('react');
  render = (await import('react-dom/server')).renderToStaticMarkup;
  source = await readFile('src/components/character-creation-screen.tsx', 'utf8');
});
after(async () => await vite?.close());

function submitFunction() {
  const ast = ts.createSourceFile('screen.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let found;
  (function visit(n) { if (ts.isVariableDeclaration(n) && n.name.getText(ast) === 'handleSubmit') found = n; ts.forEachChild(n, visit); })(ast);
  assert.ok(found, 'handleSubmit');
  return found.initializer.getText(ast);
}

test('the submitted character request has no legacy race key and still names class and species', () => {
  const sent = [];
  const env = { startingCreationPayload, startingSources: {}, isFormValid: true, selectedSetting: { setting_id: 's' }, selectedRegion: { region_pack_id: 'p', region_id: 'r' },
    selectedLocation: { entity_id: 'l' }, creating: false, characterClass: 'Fighter', startingDraft: emptyStartingDraft(), name: 'Carius', species: 'Human', giantAncestry: '',
    background: 'Soldier', alignment: 'Neutral', abilityMethod: 'standard_array', baseScores: { strength: 15 }, calculatedBackgroundBonuses: {}, derivedStats: { allSkills: [] },
    selectedExpertiseSkills: [], selectedSpeciesSkills: [], artisanTool: 'Smiths Tools', backgroundData: { tool: 'Gaming Set', origin_feat: 'Savage Attacker' }, speciesBonusFeat: '',
    fightingStyle: 'Defense', equipmentPackage: 'A', classData: { equipment_packages: [{ id: 'A', items: ['Longsword'] }] }, backgroundEquipmentOption: 'A',
    selectedLanguages: ['Dwarvish', 'Elvish'], selectedCantrips: [], selectedSpells: [], origin: '', appearance: '', personality: '', backstory: '', deathMode: 'NORMAL',
    onCreate: (...args) => sent.push(args) };
  vm.runInNewContext(ts.transpileModule(`globalThis.submit=(${submitFunction()});`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, env);
  env.submit({ preventDefault() {} });
  assert.equal(sent.length, 1);
  const request = sent[0][0];
  assert.equal('race' in request, false);
  assert.equal(request.class, 'Fighter');
  assert.equal(request.species, 'Human');
  assert.deepEqual(request.equipment_choices, ['Longsword']);
});

test('class ids are readable from the visible class cards and no hidden legacy test block remains', () => {
  const html = render(React.createElement(component.CharacterCreationScreen, { catalog, startOptions: { settings: [] }, loadingOptions: false, loadingStartOptions: false,
    optionsError: null, startOptionsError: null, creating: false, notice: null, initialStep: 'class', onBack() {}, onCreate() {}, onRetryOptions() {}, onRetryStartOptions() {} }));
  assert.match(html, /data-class-key="Fighter"/);
  assert.match(html, /data-class-key="Wizard"/);
  assert.doesNotMatch(html, /select-character-race|select-character-class|button-mode-custom/);
  assert.doesNotMatch(source, /Hidden legacy test targets/);
});

test('the screen asks one dispatcher for the starting bundle instead of one branch per class', () => {
  assert.doesNotMatch(source, /(fighter|rogue|monk|paladin|barbarian)StartingCreationFields\(/);
  assert.equal((source.match(/startingCreationPayload\(/g) ?? []).length, 2, 'one call for step validation, one for submit');
});

// D-560 (partial): the species, class, background and equipment steps are their own components; the screen only mounts them.
test('four steps are separate step components and the screen keeps no inline copy of them', async () => {
  for (const [file, name] of [['species', 'SpeciesStep'], ['class', 'ClassStep'], ['background', 'BackgroundStep'], ['equipment', 'EquipmentStep']]) {
    const stepSource = await readFile(`src/components/creation-steps/${file}-step.tsx`, 'utf8');
    assert.match(stepSource, new RegExp('export function ' + name + '[(]'));
    assert.match(source, new RegExp(`<${name} `), `${name} is mounted by the screen`);
  }
  assert.doesNotMatch(source, /data-class-key=|cc-cards-grid cc-portrait-grid/, 'class cards are not inline in the screen');
  assert.ok(source.split('\n').length < 2200, 'the screen shrank below 2200 lines');
});
