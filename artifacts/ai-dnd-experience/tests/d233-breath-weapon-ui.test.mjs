import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';

// D-233: a Dragonborn chooses the dragon once out of combat, and in a fight the panel sends breath_weapon with a shape
// and a target; the server owns the save, the damage and the uses (the panel only shows the uses it is told).
let species, vite, render;
before(async () => {
  process.env.PORT ||= '4191'; process.env.BASE_PATH ||= '/';
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  species = await vite.ssrLoadModule('/src/components/species-trait-controls.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
  render = (state) => renderToStaticMarkup(React.createElement(QueryClientProvider, { client: new QueryClient() },
    React.createElement(species.SpeciesTraitControls, { state, sessionId: 'synthetic' })));
});
after(async () => await vite?.close());

const record = (id, kind, name, status = 'active') => ({ id, kind, name, status, current_hp: 10, max_hp: 10, armor_class: 12, primary_action_available: true, is_current_actor: id === 'player' });

function state({ ancestry = 'red', uses = 2, active = true, actor = 'player' } = {}) {
  return {
    character: { name: 'Arven', race: 'Dragonborn', species: 'Dragonborn', level: 5, max_hp: 30, current_hp: 30,
      draconic_ancestry: ancestry, breath_weapon_uses_remaining: uses, species_trait_state: null },
    combat: { active, current_actor_id: actor, participant_records: active
      ? [record('player', 'player', 'Arven'), record('npc-a', 'npc', 'Haydut'), record('npc-b', 'npc', 'Düşmüş', 'dead')] : [] },
  };
}

test('breath targets are the fight\'s other active creatures', () => {
  assert.deepEqual(species.breathTargets(state()), [{ id: 'npc-a', name: 'Haydut' }]);
  assert.deepEqual(species.breathTargets(state({ active: false })), []);
});

test('in a fight the chosen dragon, the uses and the breath controls show', () => {
  const html = render(state());
  assert.match(html, /Ejderha Soyu: Kızıl Ejderha · ateş · Nefes Silahı · 2 kullanım/);
  assert.match(html, /15 fit koni/); assert.match(html, /30 fit hat/); assert.match(html, /Haydut/);
  assert.doesNotMatch(html, /Düşmüş/);
  assert.doesNotMatch(html, /data-testid="species-action-breath-weapon"[^>]*disabled/);
});

test('no uses left or not the player\'s turn: the breath button is off', () => {
  assert.match(render(state({ uses: 0 })), /data-testid="species-action-breath-weapon"[^>]*disabled/);
  assert.match(render(state({ actor: 'npc-a' })), /data-testid="species-action-breath-weapon"[^>]*disabled/);
});

test('before the choice the dragon is chosen out of combat only', () => {
  const calm = render(state({ ancestry: null, active: false }));
  assert.match(calm, /species-action-choose-draconic-ancestry/);
  assert.doesNotMatch(calm, /data-testid="species-action-choose-draconic-ancestry"[^>]*disabled/);
  assert.doesNotMatch(calm, /species-action-breath-weapon/);
  assert.match(render(state({ ancestry: null })), /data-testid="species-action-choose-draconic-ancestry"[^>]*disabled/);
});
