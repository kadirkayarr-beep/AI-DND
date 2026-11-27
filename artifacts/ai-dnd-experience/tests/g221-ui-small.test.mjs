import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';
import ts from 'typescript';

process.env.PORT ||= '4183';
process.env.BASE_PATH ||= '/';

// G2.21: four small UI debts. D-153 accessible names, D-235 hands in the character panel,
// D-563 the legacy class-less level-up branch, D-282 the difficulty card shows the number.
let vite, React, render, panel, levelUp, skillCard;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  panel = await vite.ssrLoadModule('/src/components/character-panel.tsx');
  levelUp = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  skillCard = await vite.ssrLoadModule('/src/components/skill-check-result.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props) => renderToStaticMarkup(React.createElement(type, props));
});
after(async () => await vite?.close());

const fighter = { name: 'Arven', race: 'Human', class: 'Fighter', level: 1, current_hp: 12, max_hp: 12,
  armor_class: 18, proficiency_bonus: 2, xp: 0, strength: 17, dexterity: 13, constitution: 15,
  intelligence: 12, wisdom: 10, charisma: 8, proficient_skills: [], progression_effects_pending: [] };

function jsxName(node, ast) { return node.tagName.getText(ast); }
function attr(node, name) { return node.attributes.properties.find(p => ts.isJsxAttribute(p) && p.name.getText() === name); }

// D-153: every select and every +/- ability button has a non-empty accessible name.
test('every select and every point-buy button in the creation screen has an accessible name', async () => {
  const files = ['src/components/character-creation-screen.tsx', 'src/components/creation-steps/background-step.tsx',
    'src/components/creation-steps/equipment-step.tsx', 'src/components/creation-steps/species-step.tsx', 'src/components/creation-steps/class-step.tsx'];
  let checked = 0;
  const unnamed = [];
  for (const file of files) {
    const ast = ts.createSourceFile(file, await readFile(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const labelFor = new Set();
    (function collect(n) {
      if (ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n)) {
        if (jsxName(n, ast) === 'label') { const a = attr(n, 'htmlFor'); if (a?.initializer && ts.isStringLiteral(a.initializer)) labelFor.add(a.initializer.text); }
      }
      ts.forEachChild(n, collect);
    })(ast);
    (function visit(n, insideLabel) {
      const isEl = ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n);
      const tag = isEl ? jsxName(n, ast) : '';
      if (isEl && (tag === 'select' || (tag === 'button' && /cc-calc-btn/.test(attr(n, 'className')?.initializer?.getText() ?? '')))) {
        checked += 1;
        const label = attr(n, 'aria-label')?.initializer;
        const named = (label && label.getText().replace(/["'{}`\s]/g, '').length > 0)
          || !!attr(n, 'aria-labelledby')
          || (tag === 'select' && (insideLabel || labelFor.has(attr(n, 'id')?.initializer?.text)));
        if (!named) unnamed.push(`${file}:${ast.getLineAndCharacterOfPosition(n.getStart()).line + 1} <${tag}>`);
      }
      const opens = ts.isJsxElement(n) && jsxName(n.openingElement, ast) === 'label';
      ts.forEachChild(n, child => visit(child, insideLabel || opens));
    })(ast, false);
  }
  assert.ok(checked >= 12, `found the selects and buttons (${checked})`);
  assert.deepEqual(unnamed, []);
});

// D-235: the character panel names the main hand and the off hand; a creation shield is in the off hand.
test('the character panel shows the main hand and the off hand, shield included', () => {
  const html = render(panel.CharacterPanel, { character: fighter, inventory: ['Uzun Kılıç [item_1] (kuşanılmış) (ana el)', 'Kalkan [item_2] (kuşanılmış) (ikinci el)', 'Ip [item_3]'] });
  assert.match(html, /data-testid="text-character-main-hand"[^>]*>.*?Ana el<\/div><span>Uzun Kılıç</);
  assert.match(html, /data-testid="text-character-off-hand"[^>]*>.*?İkinci el<\/div><span>Kalkan</);
  assert.doesNotMatch(html, /\[item_|Ip</);
});
test('an empty hand reads as empty and the inventory panel still hides the hand marker', () => {
  const html = render(panel.CharacterPanel, { character: fighter, inventory: ['Ip [item_3]'] });
  assert.match(html, /Ana el<\/div><span>boş</);
  assert.match(html, /İkinci el<\/div><span>boş</);
  const inv = render(panel.InventoryPanel, { items: ['Kalkan [item_2] (kuşanılmış) (ikinci el)'] });
  assert.match(inv, /Kalkan/); assert.match(inv, /kuşanılmış/);
  assert.doesNotMatch(inv, /ikinci el|\[item_/);
});

// D-563: a preview with no class name draws no Sorcerer controls any more.
const sorcererPreview = { session_id: 's', campaign_id: 'c', revision: 7, status: 'ready', reason: null, target_level: 4,
  choices_required: { cantrips: 1, prepared_spells: 1, asi: 1 }, cantrip_ids: ['Light'], prepared_spell_ids: ['Web'], supported_asi_choices: [] };
test('a level-up preview without class_name draws no Sorcerer controls', () => {
  const props = { draft: { cantrip: '', preparedSpell: '', confirmed: false }, onChange() {}, onConfirm() {}, onCancel() {} };
  const legacy = render(levelUp.LevelUpChoices, { preview: sorcererPreview, ...props });
  assert.doesNotMatch(legacy, /level-up-choices|level-up-cantrip/);
  assert.match(legacy, /henüz desteklenmiyor/);
  const named = render(levelUp.LevelUpChoices, { preview: { ...sorcererPreview, class_name: 'Sorcerer' }, ...props });
  assert.match(named, /data-testid="level-up-choices"/);
});
test('the legacy class-less branch is gone from the source', async () => {
  const source = await readFile('src/components/level-up-controls.tsx', 'utf8');
  assert.doesNotMatch(source, /retainedSorcerer|class_name == null|class_name \?\? 'Sorcerer'/);
});
test('every browser fixture that serves a level-up preview names its class', async () => {
  for (const fixture of ['c06-level4-fixture', 'play-screen-fixture']) {
    const source = await readFile(`tests/${fixture}/main.tsx`, 'utf8');
    const at = source.indexOf('target_level');
    assert.match(source.slice(source.lastIndexOf('=>', at), at), /class_name:/, fixture);
  }
});

// D-282: the difficulty row names the label and the number (Kadir, 2026-11-16).
test('the difficulty row reads label and DC together', () => {
  const result = { skill: 'Athletics', ability: 'strength', difficulty: 'hard', dc: 18, outcome: 'success', d20: 15, total: 19, proficient: true, ability_modifier: 3, proficiency_modifier: 2, total_modifier: 5 };
  assert.match(render(skillCard.SkillCheckResultCard, { result }), /<dt>Zorluk<\/dt><dd>Zor, DC 18<\/dd>/);
});
