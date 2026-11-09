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
                                      status: 'active', objectives: [], result: null, record_kind: 'dynamic', raw_status: 'ACTIVE', ...extra });
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
test('a done job shows the engine result and the badge counts quest_log', () => {
  const html = render(React.createElement(ui.QuestJournalSection, { ...base, questLog: log([]) }));
  assert.match(html, /Kayıp mektup: 12 bakır ödendi/);
  assert.match(html, /Süren maceralar/);
  assert.match(html, /Teslimat: Revomar İskelesi/);
  assert.match(html, />01</);                                          // the badge reads active_count, not quests.length (0)
});
