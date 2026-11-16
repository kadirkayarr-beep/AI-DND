// Render check, the same SSR pattern as tests/economic-card.test.mjs:11-18 (vite.ssrLoadModule + renderToStaticMarkup).
import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';
process.env.PORT ||= '4189';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let vite, ui, React, render;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/quest-journal-section.tsx');
  React = await import('react');
  render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });
const base = { quests: [], offers: [], knownNpcs: [], adventures: undefined, onAccept() {}, onCancel() {},
               acceptPending: false, cancelPending: false, hasError: false, commandNotice: null };
const row = (title, extra = {}) => ({ quest_id: title, title, summary: 's', giver: null, recipient: null, place: null,
                                      status: 'active', objectives: [], result: null, promised_cp: null, record_kind: 'dynamic', raw_status: 'ACTIVE', ...extra });
const log = (trails) => ({ active_count: 1, active: [row('Teslimat: Revomar İskelesi')], offered: [], let_go: [], rumors: [],
                           done: [row('Kayıp mektup', { status: 'done', raw_status: 'COMPLETED', result: '12 bakır ödendi' })], trails });
test('the journal shows trails with where, source and followed', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([
    { id: 't1', what: 'Tuna bir sorundan söz etti', where: 'Revomar İskelesi', who: 'Tuna', source: 'teslim', followed: false },
    { id: 't2', what: 'Mühürlü mektup', where: 'Değirmen', who: null, source: 'mektup', followed: true }]) }));
  assert.match(html, /İzler/);
  assert.match(html, /Tuna bir sorundan söz etti/);
  assert.match(html, /→ Revomar İskelesi/);
  assert.match(html, /teslimden/);
  assert.match(html, /mektuptan/);
  assert.equal((html.match(/izlendi/g) || []).length, 1);          // only the followed trail is marked
  assert.doesNotMatch(html, /Henüz bir iz yok\./);
});
test('a job heard of in the street shows as heard by ear, not the raw source word', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([
    { id: 'duyulan:a1b2c3d4e5f6', what: 'İskelede yardımcı aranıyor', where: 'Revomar İskelesi', who: null,
      source: 'duyulan', followed: false }]) }));
  assert.match(html, /kulaktan/);
  assert.doesNotMatch(html, /· duyulan</);
});
test('no trails shows the empty state under the heading', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([]) }));
  assert.match(html, /İzler/);
  assert.match(html, /Henüz bir iz yok\./);
});
test('D-136: an offered dynamic job has an accept button in its row and no cancel button yet', () => {
  const offered = row('İskele teslimatı', { quest_id: 'dyn.q1', status: 'offered', raw_status: 'DISCOVERED', objectives: ['Paketi al'] });
  const accepted = [];
  const tree = React.createElement(ui.QuestJournalSection, { ...base, onAccept: (id) => accepted.push(id),
    questLog: { ...log([]), offered: [offered] } });
  const html = render(tree);
  assert.match(html, /data-testid="journal-quest-offered-dyn\.q1"/);
  assert.match(html, /İskele teslimatı/);
  assert.match(html, /Paketi al/);
  assert.match(html, /data-testid="button-accept-quest-dyn\.q1"[^>]*>Kabul et</);
  assert.doesNotMatch(html, /button-cancel-quest-dyn\.q1/);         // cancel waits for ORTA-29 (D-134) to merge
  // the row's button calls onAccept with the job id: find the element and press it
  const find = (node) => {
    if (!node || typeof node !== 'object') return null;
    if (Array.isArray(node)) { for (const child of node) { const hit = find(child); if (hit) return hit; } return null; }
    if (typeof node.type === 'function') return find(node.type(node.props));
    if (node.props?.['data-testid'] === 'button-accept-quest-dyn.q1') return node;
    return find(node.props?.children);
  };
  const button = find(tree);
  assert.ok(button, 'accept button element');
  button.props.onClick();
  assert.deepEqual(accepted, ['dyn.q1']);
});
test('D-136: an offered dynamic job alone is not the empty journal', () => {
  const offered = row('Tek teklif', { quest_id: 'dyn.q2', status: 'offered', raw_status: 'DISCOVERED' });
  const html = render(React.createElement(ui.QuestJournalSection, { ...base,
    questLog: { active_count: 0, active: [], offered: [offered], done: [], let_go: [], rumors: [], trails: [] } }));
  assert.doesNotMatch(html, /Henüz kayıtlı görev yok\./);
  assert.match(html, /button-accept-quest-dyn\.q2/);
});
test('a done job shows the engine result and the badge counts quest_log', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([]) }));
  assert.match(html, /Kayıp mektup: 12 bakır ödendi/);
  assert.match(html, /Süren maceralar/);
  assert.match(html, /Teslimat: Revomar İskelesi/);
  assert.match(html, />01</);                                          // the badge reads active_count, not quests.length (0)
});
test('D-232: an offered and a running job card show the promised pay', () => {
  const offered = row('Teslimat: Fezlok Karakolu', { quest_id: 'dyn.q2', status: 'offered', raw_status: 'DISCOVERED', promised_cp: 14 });
  const running = row('Kayıp mektup', { quest_id: 'dyn.q3', promised_cp: 9 });
  const html = render(React.createElement(ui.QuestJournalSection, { ...base,
    questLog: { ...log([]), offered: [offered], active: [running] } }));
  assert.match(html, /Vaat edilen ücret: 14 bakır/);
  assert.match(html, /Vaat edilen ücret: 9 bakır/);
});
test('D-232: a job without terms shows no pay line', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([]) }));
  assert.doesNotMatch(html, /Vaat edilen ücret/);
});
