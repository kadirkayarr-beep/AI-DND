import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import path from 'node:path';

process.env.PORT ||= '4183';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, render, label;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  const { ExplorationControls } = await vite.ssrLoadModule('/src/components/exploration-controls.tsx');
  label = (await vite.ssrLoadModule('/src/lib/exploration-input.ts')).explorationInputLabel;
  const { createElement } = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (state, disabled = false) => renderToStaticMarkup(createElement(ExplorationControls,
    { state, disabled, onCommand() {} }));
});
after(async () => { await vite?.close(); });

const exploration = {
  catalog_id: 'catalog-authority', pace: 'normal', weather: 'fog',
  routes: [{ id: 'route-secret-id', origin: 'camp', destination: 'entry', name: 'Taş Eşik',
    distance_miles: 6, duration_seconds: 7200, blocked: false }],
  exits: [
    { id: 'exit-a', destination: 'hall', name: 'Sessiz Salon', state: 'locked', door_id: 'door-a' },
    { id: 'exit-b', destination: 'vault', name: 'Eski Mahzen', state: 'closed', door_id: 'door-b' },
  ],
  obstacles: [{ id: 'trap-source', name: 'Gerili Tel', state: 'detected' }],
  discoveries: [{ id: 'secret-source', name: 'Gizli Geçit', text: 'Doğrulanmış bulgu.' }],
  actions: [{ label: 'Kaldıracı çek', message: '/explore interact private-id' }],
};
test('adventure is an opt-in possibility, never existing campaign history', () => {
  const html = render({ exploration: null, journey: null });
  assert.match(html, /Taş Patika/);
  assert.match(html, /bir parçası değil/);
  assert.doesNotMatch(html, /\/explore|private-id/);
});
test('renders verified distances, durations, exits, weather and lifecycle states only', () => {
  const html = render({ exploration, journey: null });
  for (const text of ['Taş Eşik', '6 mil', '2 sa', 'Sessiz Salon', 'Eski Mahzen',
    'kilitli', 'kapalı', 'Sisli', 'Gerili Tel', 'fark edildi', 'Doğrulanmış bulgu.', 'Kaldıracı çek']) {
    assert.ok(html.includes(text), text);
  }
  for (const hidden of ['route-secret-id', 'secret-source', 'private-id', '/explore', '/travel']) {
    assert.ok(!html.replace(/<[^>]*>/g, '').includes(hidden), hidden);
  }
});
test('stopped, travelling and interrupted journeys disable pace changes', () => {
  for (const status of ['TRAVELLING', 'STOPPED', 'INTERRUPTED']) {
    const html = render({ exploration, journey: { status } });
    for (const pace of ['slow', 'normal', 'fast']) {
      assert.match(html, new RegExp(`data-testid="button-pace-${pace}"[^>]*disabled|disabled[^>]*data-testid="button-pace-${pace}"`));
    }
  }
});
test('renders supplied commands as readable intentions without claiming success', () => {
  assert.equal(label('/explore door secret-id unlock'), 'Seçtiğim kapının kilidini açmayı deniyorum.');
  assert.equal(label('/travel continue'), 'Yolculuğa devam ediyorum.');
  assert.equal(label('Burası neresi?'), 'Burası neresi?');
  assert.doesNotMatch(label('/explore trap private-id disarm'), /private-id|\/explore/);
});
