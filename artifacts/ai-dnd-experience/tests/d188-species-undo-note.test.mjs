import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';

// D-188 (owner decision a): a species action stays outside Geri Al, like a level-up. The panel says so before any action runs.
let species, vite, render;
before(async () => {
  process.env.PORT ||= '4192'; process.env.BASE_PATH ||= '/';
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

const state = (race) => ({
  character: { name: 'Arven', race, species: race, level: 5, max_hp: 30, current_hp: 30, species_trait_state: null },
  combat: { active: false, current_actor_id: null, participant_records: [], action_economy: null },
});

for (const race of ['Dragonborn', 'Aasimar', 'Goliath', 'Orc', 'Human']) {
  test(`${race} panel says species actions cannot be undone`, () => {
    const html = render(state(race));
    assert.match(html, /data-testid="species-undo-note"/);
    assert.match(html, /Bu eylemler geri alınamaz/);
    assert.match(html, /önceki turun Geri Al/);
  });
}
