import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

process.env.PORT ||= '4180';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, helpers, renderContext, renderDate, renderLibrary, renderAdventure, renderTranscript;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  helpers = await vite.ssrLoadModule('/src/lib/campaign-presentation.ts');
  const { CampaignContextPanel, CampaignDate } = await vite.ssrLoadModule('/src/components/campaign-context-panel.tsx');
  const { CampaignLibrary } = await vite.ssrLoadModule('/src/components/campaign-library.tsx');
  const { AdventureJournalSection } = await vite.ssrLoadModule('/src/components/adventure-journal-section.tsx');
  const { Transcript } = await vite.ssrLoadModule('/src/components/campaign-transcript.tsx');
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  renderContext = (state) => renderToStaticMarkup(React.createElement(CampaignContextPanel, { state }));
  renderDate = (state) => renderToStaticMarkup(React.createElement(CampaignDate, { state }));
  renderAdventure = (adventure) => renderToStaticMarkup(React.createElement(AdventureJournalSection, { adventure }));
  renderTranscript = (entries) => renderToStaticMarkup(React.createElement(Transcript, {
    entries, scrollRef: React.createRef(), onScroll: () => {},
  }));
  renderLibrary = (campaigns) => renderToStaticMarkup(React.createElement(QueryClientProvider, { client: new QueryClient() },
    React.createElement(CampaignLibrary, { campaigns, loading: false, resuming: false, resumingCampaignId: null, notice: null })));
});
after(async () => { await vite?.close(); });
test('adventure journal only renders returned thread/commitment/plan state, without authoring controls', () => {
  assert.equal(renderAdventure(undefined), '');
  assert.equal(renderAdventure({ threads: [], commitments: [], plan: null }), '');
  const projection = {
    threads: [{ thread_id: 'thread:1', title: 'Kendi hedefim', status: 'reframed',
      objectives: [{ objective_id: 'objective:1', description: 'Bir iz bul', optional: true, status: 'completed' }] }],
    commitments: [{ commitment_id: 'commitment:1', quote: 'Söz veriyorum', status: 'open' }],
    plan: { status: 'paused', cursor: 0, steps: [{ quote: 'Dışarı çık', precondition: 'Tehlike geçince' }] },
  };
  const untouched = structuredClone(projection);
  const html = renderAdventure(projection);
  assert.match(html, /Kendi hedefim/);
  assert.match(html, /Yönü değişti/);
  assert.match(html, /Tamamlandı/);
  assert.match(html, /Henüz yerine gelmedi/);
  assert.match(html, /planın bekliyor/);
  assert.doesNotMatch(html, /<button|<input|QUEST ACCEPTED|canonical|Python/);
  assert.deepEqual(projection, untouched);
  assert.match(renderAdventure({ ...projection, threads: [{ ...projection.threads[0], status: 'succeeded' }] }), /Sonuca ulaştı/);
});
function state() {
  return { location: 'here', locations: {
    here: { id: 'here', name: 'Kuzgun Hanı', description: 'Taş duvarlar.', type: 'tavern' },
    remote: { id: 'remote', name: 'Uzak kale', description: 'Gösterilmemeli.' },
  }, campaign_time: { day: 2, month: 'Mirtul', year: 1507, hour: 10, minute: 3, detail: 'Takvim ayrıntısı' },
  scene: { id: 'scene-id', location_id: 'here', npcs: [{ id: 'near', name: 'Sema', role: 'Hancı' }], features: [{ id: 'table', name: 'Masa' }] },
  npcs: [{ id: 'remote-npc', name: 'Uzak kişi', location: 'remote' }, { id: 'hidden', name: 'Sahnede gösterilmemiş kişi', location: 'here' }],
  features: [{ id: 'remote-feature', location: 'remote' }, { id: 'local-feature', location: 'here' }],
  doors: [{ id: 'local-door', location: 'here' }, { id: 'remote-door', location: 'remote' }],
  quests: [], known_scheduled_events: [], player_combat_status: 'active', death_state: { stable: false },
  combat: { active: false, round: 0, participant_records: [] } };
}
test('calendar renders changed authoritative year/day/time, never a fixed era', () => {
  const data = state();
  assert.equal(helpers.campaignDateLabel(data.campaign_time), '2 Mirtul 1507 DR · 10:03');
  assert.match(renderDate(data), /1507 DR/);
  data.campaign_time.year = 1512;
  assert.match(renderDate(data), /1512 DR/);
  assert.doesNotMatch(renderDate(data), /1501|1492/);
});
test('missing campaign time supplies no invented date or browser clock', () => {
  assert.equal(helpers.campaignDateLabel(null), null);
  assert.equal(renderDate({ campaign_time: null }), '');
});
test('canonical catalog names resolve identifiers; unknown legacy identifiers never become guessed locations', () => {
  const catalog = { settings: [{ regions: [{ starting_locations: [{ entity_id: 'fr:city:neverwinter', name: 'Neverwinter' }] }] }] };
  assert.equal(helpers.campaignLocationLabel('fr:city:neverwinter', catalog), 'Neverwinter');
  const unknown = helpers.campaignLocationLabel('location_001', catalog);
  assert.doesNotMatch(unknown, /location_001|Neverwinter/);
  assert.equal(helpers.classLabel('Sorcerer'), 'Büyücü');
  assert.equal(helpers.speciesLabel('Human'), 'İnsan');
});
test('valid scene membership takes priority over same-location global candidates', () => {
  const result = helpers.currentSceneContext(state());
  assert.deepEqual(result.people.map(p => p.id), ['near']);
  assert.deepEqual(result.features.map(p => p.id), ['table']);
  assert.deepEqual(result.doors.map(p => p.id), ['local-door']);
});
test('absent or stale scene falls back only to exact canonical location membership', () => {
  const data = state(); data.scene.location_id = 'remote';
  const result = helpers.currentSceneContext(data);
  assert.equal(result.scene, null);
  assert.deepEqual(result.people.map(p => p.id), ['hidden']);
  assert.deepEqual(result.features.map(p => p.id), ['local-feature']);
});
test('world panel excludes unrelated locations and NPCs without changing state', () => {
  const data = state(); const before = JSON.stringify(data);
  const html = renderContext(data);
  assert.match(html, /Kuzgun Hanı|Sema/);
  assert.doesNotMatch(html, /Uzak kale|Uzak kişi|Sahnede gösterilmemiş kişi/);
  assert.equal(JSON.stringify(data), before);
});
test('sanitized same-campaign P01 history renders both narrations with canonical location and clock', async () => {
  const capture = JSON.parse(await readFile(new URL(
    '../../../.local/evidence/F03/20261010T192142Z/P01/field-paths.json',
    import.meta.url,
  ), 'utf8'));
  assert.equal(capture.phase, 'F03-P01');
  assert.equal(capture.gate, 'PASS');
  assert.equal(capture.constraints.campaigns_created, 1);
  assert.equal(capture.constraints.accepted_turns, 2);
  assert.ok(capture.source.campaign_id_sha256);

  const saved = capture.steps.find((step) =>
    step.name === 'read_only_saved_campaign_history_get' && step.history_length === 2);
  const turns = capture.steps.filter((step) => step.name === 'native_turn');
  assert.ok(saved);
  assert.equal(turns.length, 2);
  const history = saved.response_sanitized.history;
  const stateSnapshot = saved.response_sanitized.state;
  const lastTurnNarration = turns.at(-1).response_sanitized.narration;
  assert.equal(history.at(-1).narration, lastTurnNarration);
  assert.equal(stateSnapshot.location, 'fr:city:neverwinter');
  assert.equal(stateSnapshot.locations[stateSnapshot.location].name, 'Neverwinter');
  assert.deepEqual(
    [stateSnapshot.campaign_time.day, stateSnapshot.campaign_time.month,
      stateSnapshot.campaign_time.year, stateSnapshot.campaign_time.hour,
      stateSnapshot.campaign_time.minute],
    [1, 'Mirtul', 1501, 9, 0],
  );

  const entries = history.flatMap((entry) => [
    { kind: 'player', text: entry.player_message },
    { kind: 'narration', text: entry.narration },
  ]);
  const transcriptHtml = renderTranscript(entries);
  for (const entry of history) assert.ok(transcriptHtml.includes(entry.narration));
  assert.match(transcriptHtml, /data-testid="transcript-narration-1"/);
  assert.match(transcriptHtml, /data-testid="transcript-narration-3"/);
  assert.match(transcriptHtml, /aria-label="Hikâye akışı"/);
  assert.match(renderTranscript([]), /data-testid="empty-transcript"/);

  const contextHtml = renderContext(stateSnapshot);
  assert.match(contextHtml, /Neverwinter/);
  assert.match(contextHtml, /1 Mirtul 1501 DR · 09:00/);
});
test('only accepted quests, actual combat actor and canonical condition are presented', () => {
  const data = state();
  data.quests = [{ quest_id: 'a', title: 'Etkin görev', description: 'Yol', status: 'accepted', objectives: [] },
    { quest_id: 'b', title: 'Bitmiş görev', description: '', status: 'completed', objectives: [] }];
  data.combat = { active: true, round: 4, current_actor_id: 'n', participant_records: [{ id: 'n', name: 'Muhafız' }] };
  data.player_combat_status = 'unconscious'; data.death_state.stable = true;
  const html = renderContext(data);
  assert.match(html, /Etkin görev/); assert.doesNotMatch(html, /Bitmiş görev/);
  assert.match(html, /Raunt 4/); assert.match(html, /Sıra: Muhafız/); assert.match(html, /Durumun dengelendi/);
});
test('technical ability text is neutralized without inventing a successful effect', () => {
  assert.equal(helpers.playerAbilityMessage('Python API receipt rollback'), 'Yeteneğin değerlendirildi.');
  assert.equal(helpers.playerAbilityMessage('Şifa Veren Eller 4 can iyileştirdi.'), 'Şifa Veren Eller 4 can iyileştirdi.');
});
test('library empty and populated surfaces use player language and preserve deletion controls', () => {
  const html = renderLibrary([{ campaign_id: 'test-only', name: 'Test macerası', character_name: 'Arven', character_race: 'Human', character_class: 'Sorcerer', location: 'fr:city:neverwinter', last_played_at: '2026-10-04T12:00:00Z' }]);
  assert.doesNotMatch(html + renderLibrary([]), /\bsunucu\b|\bbackend\b|\bAPI\b|\bQwen\b/i);
  assert.match(html, /button-delete-test-only/);
  assert.match(html, /İnsan Büyücü/);
  assert.doesNotMatch(html, /fr:city:neverwinter/);
});
test('presentation sources contain no fixed date, client clock, gameplay commands or spell reconstruction', async () => {
  const helper = await readFile('src/lib/campaign-presentation.ts', 'utf8');
  assert.doesNotMatch(helper, /Date\.now|new Date|fetch\(|useState|localStorage/);
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.doesNotMatch(page, /\b(?:1492|1501)\s*DR/);
  const panel = await readFile('src/components/campaign-context-panel.tsx', 'utf8');
  assert.doesNotMatch(panel, /mutate|fetch\(|useState|localStorage|spellcasting_v1/);
});