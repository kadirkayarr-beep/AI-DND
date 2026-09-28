import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let renderCombatPanel;
let renderSkillCheckResult;
let renderQuestJournalSection;
let mergeCombatHistory;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  const component = await vite.ssrLoadModule('/src/components/combat-panel.tsx');
  const history = await vite.ssrLoadModule('/src/lib/combat-history.ts');
  const skillResult = await vite.ssrLoadModule('/src/components/skill-check-result.tsx');
  const questJournal = await vite.ssrLoadModule('/src/components/quest-journal-section.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  mergeCombatHistory = history.mergeCombatHistory;
  renderCombatPanel = (state, entries = []) => renderToStaticMarkup(
    React.createElement(component.CombatPanel, { state, entries }),
  );
  renderSkillCheckResult = (result) => renderToStaticMarkup(
    React.createElement(skillResult.SkillCheckResultCard, { result }),
  );
  renderQuestJournalSection = (props) => renderToStaticMarkup(
    React.createElement(questJournal.QuestJournalSection, props),
  );
});

after(async () => {
  await vite?.close();
});

function makeState(overrides = {}) {
  return {
    character: {
      name: 'Arven',
      current_hp: 12,
      max_hp: 14,
      armor_class: 15,
    },
    player_combat_status: 'active',
    combat: {
      active: false,
      round: 0,
      initiative_order: [],
      current_turn_index: 0,
      target_id: null,
    },
    npcs: [{
      id: 'npc_bandit',
      name: 'Bandit',
      current_hp: 2,
      max_hp: 12,
      armor_class: 13,
      combat_status: 'active',
    }],
    ...overrides,
  };
}

const criticalExchange = {
  action: 'attack',
  success: true,
  outcome: 'critical_hit',
  target_id: 'npc_bandit',
  target_name: 'Bandit',
  weapon: 'Longsword',
  attack_roll: 20,
  attack_bonus: 4,
  attack_total: 24,
  target_ac: 13,
  critical: true,
  damage: 7,
  target_hp_before: 9,
  target_hp_after: 2,
  target_status: 'active',
  combat_started: true,
  combat_ended: false,
  enemy_action: {
    action: 'enemy_attack',
    success: false,
    outcome: 'miss',
    target_id: 'player',
    target_name: 'Arven',
    weapon: 'Dagger',
    attack_roll: 1,
    attack_bonus: 2,
    attack_total: 3,
    target_ac: 15,
    critical: false,
    damage: 0,
    target_hp_before: 12,
    target_hp_after: 12,
    target_status: 'active',
  },
};

test('inactive combat renders without invented round, target, or roll data', () => {
  const html = renderCombatPanel(makeState());

  assert.match(html, /data-testid="combat-idle-state"/);
  assert.match(html, /Çatışma yok/);
  assert.doesNotMatch(html, /data-testid="combat-round"/);
  assert.doesNotMatch(html, /data-testid="combat-opponent"/);
  assert.doesNotMatch(html, /data-testid="combat-entry-/);
});

test('the existing skill result card renders all four newly routed skills', () => {
  const cases = [
    ['Persuasion', 'charisma'],
    ['Deception', 'charisma'],
    ['Acrobatics', 'dexterity'],
    ['Survival', 'wisdom'],
  ];

  for (const [skill, ability] of cases) {
    const result = {
      skill,
      ability,
      d20: 12,
      proficient: false,
      ability_modifier: 1,
      proficiency_modifier: 0,
      total_modifier: 1,
      total: 13,
      difficulty: 'medium',
      dc: 15,
      outcome: 'failure',
    };
    const html = renderSkillCheckResult(result);

    assert.match(html, /data-testid="skill-check-result"/);
    assert.ok(html.includes(skill), `accessible label should include ${skill}`);
    assert.ok(html.includes(skill.toLocaleUpperCase('tr-TR')), `card should display ${skill}`);
  }
});

test('active panel displays only canonical HP, AC, round, target, and initiative order', () => {
  const state = makeState({
    combat: {
      active: true,
      round: 2,
      initiative_order: ['npc_bandit', 'player'],
      current_turn_index: 0,
      target_id: 'npc_bandit',
    },
  });
  const html = renderCombatPanel(state);

  assert.match(html, /data-testid="combat-player-hp"[^>]*>[\s\S]*?12 \/ 14/);
  assert.match(html, /data-testid="combat-player-ac"[^>]*>[\s\S]*?15/);
  assert.match(html, /data-testid="combat-opponent-name">Bandit/);
  assert.match(html, /data-testid="combat-opponent-hp"[^>]*>[\s\S]*?2 \/ 12/);
  assert.match(html, /data-testid="combat-opponent-ac"[^>]*>[\s\S]*?13/);
  assert.match(html, /data-testid="combat-round">Tur 2/);
  assert.match(html, /data-testid="combat-initiative-0"[^>]*>[\s\S]*?Bandit/);
  assert.match(html, /data-testid="combat-initiative-1"[^>]*>[\s\S]*?Arven/);
  assert.doesNotMatch(html, /Sıra indeksi/);
  assert.doesNotMatch(html, /Atış toplamı: \d+/);
});

test('structured critical and retaliation results show returned rolls, modifiers, and damage', () => {
  const state = makeState({
    combat: {
      active: true,
      round: 1,
      initiative_order: ['player', 'npc_bandit'],
      current_turn_index: 0,
      target_id: 'npc_bandit',
    },
  });
  const html = renderCombatPanel(state, [{ id: '6', turnIndex: 6, result: criticalExchange }]);

  assert.match(html, /data-testid="combat-entry-6-roll">[\s\S]*?<strong>20<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-bonus">[\s\S]*?<strong>4<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-total">[\s\S]*?<strong>24<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-target-ac">[\s\S]*?<strong>13<\/strong>/);
  assert.match(html, /KRİTİK/);
  assert.match(html, /İSABET/);
  assert.match(html, /DOĞAL 20/);
  assert.match(html, /data-testid="combat-entry-6-damage"[^>]*>[\s\S]*?7/);
  assert.match(html, /data-testid="combat-entry-6-enemy-roll">[\s\S]*?<strong>1<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-enemy-total">[\s\S]*?<strong>3<\/strong>/);
  assert.match(html, /ISKA/);
  assert.match(html, /DOĞAL 1/);
  assert.match(html, /data-testid="combat-log-entry-6-started"/);
  assert.doesNotMatch(html, /critical_hit/);
});

test('ended state follows Python result while active canonical state takes precedence', () => {
  const endedEntry = {
    id: '7',
    turnIndex: 7,
    result: {
      ...criticalExchange,
      combat_started: false,
      combat_ended: true,
      end_reason: 'target_defeated',
    },
  };
  const endedHtml = renderCombatPanel(makeState(), [endedEntry]);
  assert.match(endedHtml, /data-testid="combat-ended-state"/);
  assert.match(endedHtml, /Rakip etkisiz hale getirildi/);
  assert.match(endedHtml, /data-testid="combat-log-entry-7-ended"/);

  const activeHtml = renderCombatPanel(makeState({
    combat: {
      active: true,
      round: 3,
      initiative_order: ['player', 'npc_bandit'],
      current_turn_index: 0,
      target_id: 'npc_bandit',
    },
  }), [endedEntry]);
  assert.match(activeHtml, /data-testid="combat-player"/);
  assert.doesNotMatch(activeHtml, /data-testid="combat-ended-state"/);
});

test('resumed combat history renders returned cards once per stable event ID', () => {
  const event = {
    event_id: '00000000-0000-4000-8000-000000000006',
    turn_index: 6,
    result: criticalExchange,
  };
  const restored = mergeCombatHistory([event, event, null, {
    event_id: '',
    turn_index: 7,
    result: criticalExchange,
  }]);
  const html = renderCombatPanel(makeState(), restored);

  assert.equal(restored.length, 1);
  assert.equal(restored[0].id, event.event_id);
  assert.match(html, /data-testid="combat-log-entry-00000000-0000-4000-8000-000000000006"/);
  assert.match(html, /data-testid="combat-entry-00000000-0000-4000-8000-000000000006-roll">[\s\S]*?<strong>20<\/strong>/);

  const appended = mergeCombatHistory([event], restored);
  assert.equal(appended.length, 1);
  assert.equal(appended[0].turnIndex, 6);
});

test('result animation is brief and disabled for reduced motion', async () => {
  const css = await readFile(
    path.join(process.cwd(), 'src/components/combat-panel.css'),
    'utf8',
  );
  assert.match(css, /@keyframes combat-result-reveal/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /\.combat-result-die \{ animation: none; \}/);
});

test('quest journal remains empty and shows no commands without server offers', () => {
  const html = renderQuestJournalSection({
    quests: [],
    offers: [],
    knownNpcs: [],
    onAccept() {},
    onCancel() {},
    acceptPending: false,
    cancelPending: false,
    hasError: false,
  });

  assert.match(html, /data-testid="empty-journal-quests"/);
  assert.doesNotMatch(html, /button-accept-quest-/);
  assert.doesNotMatch(html, /button-cancel-quest-/);
});

test('quest offers render server-owned giver, objectives, and both quest-ID commands', () => {
  const html = renderQuestJournalSection({
    quests: [],
    offers: [{
      quest_id: 'quest.forest',
      title: 'The Forest Path',
      description: 'Reach the forest.',
      giver_npc_id: 'npc_mira',
      objectives: [{
        objective_id: 'visit-forest',
        description: 'Visit the forest twice.',
        kind: 'visit_location',
        target: 'forest',
        required_count: 2,
      }],
    }],
    knownNpcs: [{ npc_id: 'npc_mira', name: 'Mira' }],
    onAccept() {},
    onCancel() {},
    acceptPending: false,
    cancelPending: false,
    hasError: false,
  });

  assert.match(html, /The Forest Path/);
  assert.match(html, /Reach the forest/);
  assert.match(html, /Görevi veren: Mira/);
  assert.match(html, /Visit the forest twice/);
  assert.match(html, /visit_location · forest · 2/);
  assert.match(html, /data-testid="button-accept-quest-quest\.forest"/);
  assert.match(html, /data-testid="button-cancel-quest-quest\.forest"/);
  assert.equal((html.match(/data-quest-id="quest\.forest"/g) ?? []).length, 2);
});

test('accepted quest progress and cancellation use canonical returned state', () => {
  const html = renderQuestJournalSection({
    quests: [{
      quest_id: 'quest.forest',
      title: 'The Forest Path',
      description: 'Reach the forest.',
      status: 'accepted',
      giver_npc_id: 'npc_mira',
      objectives: [{
        objective_id: 'visit-forest',
        description: 'Visit the forest twice.',
        status: 'active',
        progress: 1,
        required_count: 2,
      }],
    }],
    offers: [],
    knownNpcs: [{ npc_id: 'npc_mira', name: 'Mira' }],
    onAccept() {},
    onCancel() {},
    acceptPending: false,
    cancelPending: false,
    hasError: false,
    commandNotice: 'Görev kabul edildi.',
  });

  assert.match(html, /Sürüyor/);
  assert.match(html, /1\/2/);
  assert.match(html, /data-testid="quest-command-outcome"/);
  assert.match(html, /Görev kabul edildi/);
  assert.match(html, /data-testid="button-cancel-accepted-quest-quest\.forest"/);
  assert.match(html, /Görevi iptal et/);
});