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
let renderActionEconomy;

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
  const economy = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
  mergeCombatHistory = history.mergeCombatHistory;
  renderActionEconomy = (state) => renderToStaticMarkup(React.createElement(economy.ActionEconomyPanel, {
    state, targetId: 'npc-test', sending: false, onCommand: () => {},
  }));
  renderCombatPanel = (state, entries = []) => {
    const queryClient = new QueryClient();
    return renderToStaticMarkup(
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(component.CombatPanel, { state, entries, sessionId: 'test-session' }),
      ),
    );
  };
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

test('action economy displays server resources without creating rolls or budgets', () => {
  const html = renderActionEconomy(makeState({ combat: {
    active: true, current_actor_id: 'player', action_economy: { actors: { player: {
      base_action_spent: true, additional_actions: [], bonus_action_spent: false,
      bonus_action_available: false, bonus_rules: [], reaction_available: true,
      movement_remaining: 17, speed_ft: 30, ready: null, opportunity: null,
      legal_actions: [{ kind: 'attack', legal: false, reason: 'spent' }],
    } } },
  } }));
  assert.match(html, /Action: kullanıldı/);
  assert.match(html, /Bonus: uygun yetenek yok/);
  assert.match(html, /Hareket: 17 ft/);
  assert.match(html, /tetikleyici gerekir/);
  assert.doesNotMatch(html, /d20|İSABET|ISKA/);
});

test('economy combat history restores nested server attack results once', () => {
  const event = { event_id: 'economy-server-event', turn_index: 7, result: {
    action: 'action_economy', economy_steps: [{ kind: 'attack', result: {
      action: 'attack', outcome: 'miss', attack_roll: 1, attack_bonus: 3,
      attack_total: 4, target_ac: 15, target_name: 'Gromm', damage: 0,
    } }],
  } };
  const entries = mergeCombatHistory([event, event], []);
  assert.equal(entries.length, 1);
  const html = renderCombatPanel(makeState(), entries);
  assert.match(html, /ISKA/);
  assert.match(html, /DOĞAL 1/);
});

function makeState(overrides = {}) {
  const { combat: combatOverrides = {}, ...stateOverrides } = overrides;
  return {
    character: {
      name: 'Arven',
      current_hp: 12,
      max_hp: 14,
      armor_class: 15,
    },
    player_combat_status: 'active',
    death_state: {
      mode: 'CHECKPOINT_ROLLBACK', status: 'conscious', successes: 0,
      failures: 0, terminal: false, last_death_save: null,
    },
    combat: {
      active: false,
      status: 'ended',
      round: 0,
      initiative_order: [],
      current_turn_index: 0,
      current_actor_id: null,
      turn_owner: null,
      participants: [],
      participant_records: [],
      target_id: null,
      end_reason: null,
      ...combatOverrides,
    },
    npcs: [{
      id: 'npc_bandit',
      name: 'Bandit',
      current_hp: 2,
      max_hp: 12,
      armor_class: 13,
      combat_status: 'active',
    }, {
      id: 'npc_wolf',
      name: 'Wolf',
      current_hp: 8,
      max_hp: 8,
      armor_class: 12,
      combat_status: 'active',
    }],
    ...stateOverrides,
  };
}

test('Aasimar ability controls expose uses and the selected Revelation form', () => {
  const state = makeState();
  state.character.species = 'Aasimar';
  state.character.level = 3;
  state.character.species_trait_state = {
    healing_hands_uses_remaining: 1,
    celestial_revelation_uses_remaining: 1,
    active_celestial_form: null,
    celestial_revelation_turns_remaining: 0,
  };

  const html = renderCombatPanel(state);
  assert.match(html, /data-testid="species-action-healing-hands"/);
  assert.match(html, /Göksel Tecelli biçimi/);
  assert.match(html, /data-testid="species-action-celestial-revelation"/);
});

test('Goliath ancestry controls and combat log render the server species effect', () => {
  const state = makeState();
  state.character.species = 'Goliath';
  state.character.level = 5;
  state.character.giant_ancestry = 'fire';
  state.character.species_trait_state = {
    giant_ancestry_uses_remaining: 1,
    giant_ancestry_armed: false,
    large_form_uses_remaining: 1,
    large_form_turns_remaining: 0,
  };
  const entry = {
    id: 'species-attack',
    turnIndex: 1,
    result: {
      action: 'attack',
      outcome: 'hit',
      success: true,
      damage: 8,
      target_name: 'Target',
      species_effects: [{
        trait: 'fire_giant_ancestry',
        damage: 6,
        damage_type: 'fire',
      }],
    },
  };

  const html = renderCombatPanel(state, [entry]);
  assert.match(html, /data-testid="species-action-arm-giant-ancestry"/);
  assert.match(html, /data-testid="species-action-large-form"/);
  assert.match(html, /Ateş Devi kökeni: 6 ateş hasarı/);
});

test('Orc panel presents Adrenaline Rush and Relentless Endurance state', () => {
  const state = makeState();
  state.character.species = 'Orc';
  state.character.species_trait_state = {
    adrenaline_rush_uses_remaining: 2,
    temporary_hit_points: 0,
    relentless_endurance_available: true,
  };

  const html = renderCombatPanel(state);
  assert.match(html, /data-testid="species-action-adrenaline-rush"/);
  assert.match(html, /Amansız Dayanıklılık/);
});

const combatantRecords = {
  player: {
    id: 'player',
    kind: 'player',
    name: 'Arven',
    current_hp: 12,
    max_hp: 14,
    armor_class: 15,
    status: 'active',
    primary_action_available: true,
  },
  npc_bandit: {
    id: 'npc_bandit',
    kind: 'npc',
    name: 'Bandit',
    current_hp: 2,
    max_hp: 12,
    armor_class: 13,
    status: 'active',
    primary_action_available: true,
  },
  npc_wolf: {
    id: 'npc_wolf',
    kind: 'npc',
    name: 'Wolf',
    current_hp: 8,
    max_hp: 8,
    armor_class: 12,
    status: 'active',
    primary_action_available: true,
  },
};

function activeCombat(overrides = {}) {
  const combat = {
    active: true,
    status: 'active',
    round: 1,
    initiative_order: ['player', 'npc_bandit'],
    current_turn_index: 0,
    current_actor_id: 'player',
    turn_owner: 'player',
    participants: ['player', 'npc_bandit'],
    participant_records: [],
    target_id: 'npc_bandit',
    end_reason: null,
    ...overrides,
  };
  const customRecords = new Map(
    (overrides.participant_records ?? []).map((record) => [record.id, record]),
  );
  combat.turn_owner = combat.current_actor_id;
  combat.participant_records = combat.participants.map((id) => ({
    ...combatantRecords[id],
    ...customRecords.get(id),
    is_current_actor: id === combat.current_actor_id,
  }));
  return combat;
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
  enemy_actions: [
    {
      action: 'enemy_attack',
      actor: 'npc_bandit',
      actor_name: 'Bandit',
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
    {
      action: 'enemy_attack',
      actor: 'npc_wolf',
      actor_name: 'Wolf',
      success: true,
      outcome: 'hit',
      target_id: 'player',
      target_name: 'Arven',
      weapon: 'Bite',
      attack_roll: 15,
      attack_bonus: 3,
      attack_total: 18,
      target_ac: 15,
      critical: false,
      damage: 4,
      target_hp_before: 12,
      target_hp_after: 8,
      target_status: 'active',
    },
  ],
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
    const abilityLabels = { strength: 'KUV', dexterity: 'ÇEV', constitution: 'DAY', intelligence: 'ZEK', wisdom: 'BİL', charisma: 'KAR' };
    assert.ok(html.includes(`<dt>${abilityLabels[ability]}</dt>`));
    assert.ok(html.includes('<dt>Yeterlilik</dt>'));
    assert.ok(html.includes('<dt>Toplam</dt>'));
    assert.ok(html.includes('>13<'));
    assert.ok(html.includes('Orta · DC 15'));
    assert.ok(!html.includes('<dt>PROF</dt>'));
    assert.ok(!html.includes('<dt>TOTAL</dt>'));
    assert.ok(!html.includes('<dt>STR</dt>'));
  }
});

test('active panel displays only canonical HP, AC, round, target, and initiative order', () => {
  const state = makeState({
    combat: activeCombat({
      round: 2,
      initiative_order: ['npc_bandit', 'player'],
      current_turn_index: 0,
      current_actor_id: 'npc_bandit',
      participants: ['player', 'npc_bandit'],
      target_id: 'npc_bandit',
    }),
  });
  const html = renderCombatPanel(state);

  assert.match(html, /data-testid="combat-player-hp"[^>]*>[\s\S]*?12 \/ 14/);
  assert.match(html, /data-testid="combat-player-ac"[^>]*>[\s\S]*?15/);
  assert.match(html, /data-testid="combat-opponent-npc_bandit-name">Bandit/);
  assert.match(html, /data-testid="combat-opponent-npc_bandit-hp"[^>]*>[\s\S]*?2 \/ 12/);
  assert.match(html, /data-testid="combat-opponent-npc_bandit-ac"[^>]*>[\s\S]*?13/);
  assert.match(html, /data-testid="combat-round">Tur 2/);
  assert.match(html, /data-testid="combat-initiative-0"[^>]*>[\s\S]*?Bandit/);
  assert.match(html, /data-testid="combat-initiative-1"[^>]*>[\s\S]*?Arven/);
  assert.match(html, /Sıra: Bandit/);
  assert.doesNotMatch(html, /Sıra indeksi/);
  assert.doesNotMatch(html, /Atış toplamı: \d+/);
});

test('structured critical and multi-enemy results show returned rolls, modifiers, and damage', () => {
  const state = makeState({
    combat: activeCombat({
      round: 1,
      initiative_order: ['player', 'npc_bandit', 'npc_wolf'],
      current_turn_index: 0,
      participants: ['player', 'npc_bandit', 'npc_wolf'],
      target_id: 'npc_bandit',
    }),
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
  assert.match(html, /data-testid="combat-entry-6-enemy-0-enemy-roll">[\s\S]*?<strong>1<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-enemy-0-enemy-total">[\s\S]*?<strong>3<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-enemy-1-enemy-roll">[\s\S]*?<strong>15<\/strong>/);
  assert.match(html, /data-testid="combat-entry-6-enemy-1-enemy-total">[\s\S]*?<strong>18<\/strong>/);
  assert.match(html, /Bandit/);
  assert.match(html, /Wolf/);
  assert.match(html, /ISKA/);
  assert.match(html, /DOĞAL 1/);
  assert.match(html, /data-testid="combat-entry-6-enemy-1-enemy-damage"[^>]*>[\s\S]*?4/);
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
    combat: activeCombat({
      round: 3,
      initiative_order: ['player', 'npc_bandit'],
      current_turn_index: 0,
      target_id: 'npc_bandit',
    }),
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
  assert.doesNotMatch(html, /visit_location/);
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
  assert.match(html, /Visit the forest twice/);
  assert.doesNotMatch(html, /1\/2/);
  assert.match(html, /data-testid="quest-command-outcome"/);
  assert.match(html, /Görev kabul edildi/);
  assert.match(html, /data-testid="button-cancel-accepted-quest-quest\.forest"/);
  assert.match(html, /Görevi iptal et/);
});

test('campaign adventures show rumor, clue, and outcome labels without internal ids', () => {
  const html = renderQuestJournalSection({
    quests: [],
    offers: [],
    knownNpcs: [],
    onAccept() {},
    onCancel() {},
    acceptPending: false,
    cancelPending: false,
    hasError: false,
    adventures: {
      rumors: [
        { label: 'Söylenti', text: 'Depoda bir ses duyulmuş.' },
        { label: 'İpucu', text: 'Bir iz bul.' },
      ],
      active: [{ title: 'Kayıp kişi', summary: 'Bir muhafız kayıp.', objectives: ['Söylentiyi dinle'] }],
      completed: [{ title: 'Kayıp kişi', summary: 'Ulaşıldı.', label: 'Doğrulandı', objectives: [] }],
      failed: [{ title: 'Eski iz', summary: 'Süre doldu.', objectives: [] }],
      timeline: ['Marek kayıp muhafız hakkında konuştu.'],
      affordances: ['İz ara'],
    },
  });
  assert.match(html, /Söylenti/);
  assert.match(html, /İpucu/);
  assert.match(html, /Depoda bir ses duyulmuş/);
  assert.match(html, /Söylentiyi dinle/);
  assert.match(html, /Doğrulandı/);
  assert.match(html, /Sonuçsuz/);
  assert.doesNotMatch(html, /MISSING_PERSON|template_version|objective_id|opportunity:/);
});