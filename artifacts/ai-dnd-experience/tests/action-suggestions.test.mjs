import assert from 'node:assert/strict';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let getContextualActionSuggestions;
let getTurnInteractionMetadata;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  const module = await vite.ssrLoadModule('/src/lib/action-suggestions.ts');
  getContextualActionSuggestions = module.getContextualActionSuggestions;
  getTurnInteractionMetadata = module.getTurnInteractionMetadata;
});

after(async () => {
  await vite?.close();
});

function makeState(overrides = {}) {
  const { combat = {}, ...stateOverrides } = overrides;
  return {
    location: 'tavern',
    scene: {
      npcs: [{ id: 'npc_001', name: 'Gromm', role: 'Barmen' }],
    },
    inventory: ['Kılıç'],
    combat: {
      active: false,
      current_actor_id: null,
      participant_records: [],
      ...combat,
    },
    ...stateOverrides,
  };
}

test('suggestions come from the current scene, with no generic filler', () => {
  const suggestions = getContextualActionSuggestions(makeState({
    scene: {
      npcs: [{ id: 'npc_001', name: 'Gromm', role: 'Barmen' }],
    },
    npcs: [{ id: 'npc_002', name: 'Lyra', location: 'forest' }],
  }));
  const messages = suggestions.map((suggestion) => suggestion.message);

  assert.ok(messages.includes('Gromm ile konuşmak istiyorum.'));
  assert.ok(!messages.includes('Çevreyi gözlemliyorum.'));
  assert.ok(!messages.includes('Envanterimde neler var?'));
  assert.ok(!messages.some((message) => message.includes('Lyra')));
  assert.ok(!messages.some((message) => message.includes('saldırıyorum')));
  assert.equal(suggestions.find((item) => item.id === 'talk-npc_001')?.mode, 'say');
  assert.equal(suggestions.find((item) => item.id === 'talk-npc_001')?.targetId, 'npc_001');
});

test('the person being spoken to, a place just named and a door in reach lead the list', () => {
  const state = makeState({
    location: 'city',
    conversation: { active: true, interlocutor: { id: 'npc_001', name: 'Gromm' } },
    scene: { npcs: [{ id: 'npc_001', name: 'Gromm' }, { id: 'npc_002', name: 'Lyra' }] },
    locations: {
      city: { id: 'city', name: 'Kent' },
      inn: { id: 'inn', name: 'Neris Hanı' },
      far: { id: 'far', name: 'Uzak Liman' },
    },
    doors: [
      { id: 'd1', name: 'Depo Kapısı', location: 'city', open: false, locked: true, broken: false },
      { id: 'd2', name: 'Başka Kapı', location: 'inn', open: false, locked: false, broken: false },
    ],
  });
  const suggestions = getContextualActionSuggestions(state, 'Gromm: “Yakınlarda Neris Hanı var.”');
  const ids = suggestions.map((suggestion) => suggestion.id);

  assert.deepEqual(ids, ['ask-npc_001', 'place-inn', 'door-d1', 'talk-npc_002']);
  assert.equal(suggestions[0].mode, 'say');
  assert.equal(suggestions[0].targetId, 'npc_001');
  assert.ok(suggestions[1].message.includes('Neris Hanı'));
  assert.equal(suggestions[1].mode, 'do');
  assert.equal(suggestions[2].mode, 'do');
  assert.ok(suggestions.length <= 4);
});

test('a suggestion never says what the player has not learned about a door', () => {
  const closed = { id: 'd1', name: 'Depo Kapısı', location: 'tavern', open: false, broken: false };
  const text = (door) => JSON.stringify(
    getContextualActionSuggestions(makeState({ doors: [door] })).filter((item) => item.id === 'door-d1')
      .map(({ label, message }) => [label, message]),
  );
  assert.equal(text({ ...closed, locked: true }), text({ ...closed, locked: false }));
  assert.ok(!/kilit/i.test(text({ ...closed, locked: true })));
  assert.ok(!getContextualActionSuggestions(makeState({
    doors: [{ ...closed, open: true, locked: false }],
  })).some((item) => item.id === 'door-d1'));
});

test('combat suggestions require the player turn and a live target', () => {
  const combat = {
    active: true,
    current_actor_id: 'player',
    participant_records: [
      {
        id: 'npc_001',
        kind: 'npc',
        name: 'Gromm',
        status: 'active',
        current_hp: 20,
      },
      {
        id: 'npc_002',
        kind: 'npc',
        name: 'Lyra',
        status: 'defeated',
        current_hp: 0,
      },
    ],
  };
  const suggestions = getContextualActionSuggestions(makeState({ combat }));
  const attackSuggestions = suggestions.filter((suggestion) =>
    suggestion.id.startsWith('attack-'),
  );

  assert.deepEqual(attackSuggestions.map((suggestion) => suggestion.id), ['attack-npc_001']);
  assert.ok(attackSuggestions[0].message.includes('Gromm'));
  assert.ok(!attackSuggestions[0].message.includes('Lyra'));

  assert.equal(attackSuggestions[0].mode, 'do');
  assert.equal(attackSuggestions[0].targetId, 'npc_001');

  const enemyTurn = getContextualActionSuggestions(makeState({
    combat: { ...combat, current_actor_id: 'npc_001' },
  }));
  assert.ok(!enemyTurn.some((suggestion) => suggestion.id.startsWith('attack-')));

  const axe = getContextualActionSuggestions(makeState({
    inventory: ['Balta'],
    combat,
  }));
  assert.ok(axe.some((suggestion) => suggestion.id === 'attack-npc_001'));
  assert.ok(!axe.some((suggestion) => suggestion.message.includes('kılıç')));
});

test('empty scenes offer a grounded presence question rather than an invented target', () => {
  const suggestions = getContextualActionSuggestions(makeState({
    scene: { npcs: [] },
    inventory: [],
  }));

  assert.ok(suggestions.some((suggestion) => suggestion.id === 'presence'));
  assert.ok(!suggestions.some((suggestion) => suggestion.id.startsWith('attack-')));
  assert.equal(suggestions.find((suggestion) => suggestion.id === 'presence')?.mode, 'ask_dm');
});

test('conversation mode uses only a target in the current scene', () => {
  const state = makeState();
  assert.deepEqual(getTurnInteractionMetadata(state, 'say', 'npc_001', 'npc_combat'), {
    interaction_mode: 'say', target_id: 'npc_001',
  });
  for (const target of ['', 'npc_previous_scene']) {
    assert.deepEqual(getTurnInteractionMetadata(state, 'say', target, 'npc_combat'), {
      interaction_mode: 'say', target_id: null,
    });
  }
});

test('narrator questions and world actions do not carry a conversation target', () => {
  for (const mode of ['ask_dm', 'do']) {
    assert.deepEqual(getTurnInteractionMetadata(makeState(), mode, 'npc_001', 'npc_combat'), {
      interaction_mode: mode, target_id: null,
    });
  }
});

test('active combat and structured actions keep the existing action route', () => {
  const state = makeState({ combat: { active: true } });
  for (const mode of ['say', 'ask_dm', 'do']) {
    assert.deepEqual(getTurnInteractionMetadata(state, mode, 'npc_001', 'npc_enemy'), {
      interaction_mode: 'do', target_id: 'npc_enemy',
    });
  }
  assert.deepEqual(getTurnInteractionMetadata(makeState(), 'say', 'npc_001', '', true), {
    interaction_mode: 'do', target_id: null,
  });
});

test('suggestions live beside the composer in a closed control, not in the drawer', async () => {
  const { readFile } = await import('node:fs/promises');
  const page = readGameBrowserSource();
  const ideas = page.match(/<details className="scene-ideas"[^>]*>/)?.[0];
  assert.ok(ideas, 'scene ideas control exists');
  assert.ok(!/\bopen\b/.test(ideas), 'closed by default');
  const drawer = page.slice(page.indexOf('function ExperimentalWorldControls'), page.indexOf('function WorldTabs'));
  assert.ok(!drawer.includes('getContextualActionSuggestions'));
  assert.ok(page.indexOf('<SceneIdeas') < page.indexOf('data-testid="button-open-composer"'));
});
