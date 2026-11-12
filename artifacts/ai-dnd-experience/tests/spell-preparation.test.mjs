import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';

// UI slice 3, S1 + S3: the Hazırlık (spell preparation) screen and its read-only status rows.
process.env.PORT ||= '4191';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;
let lib, names, screen, panel, React, render, vite;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  lib = await vite.ssrLoadModule('/src/lib/spell-preparation.ts');
  names = await vite.ssrLoadModule('/src/lib/spell-names.ts');
  screen = await vite.ssrLoadModule('/src/components/spell-preparation-screen.tsx');
  panel = await vite.ssrLoadModule('/src/components/spellcasting-panel.tsx');
  React = await import('react');
  render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });

const view = (extra = {}) => ({ session_id: 's', supported: true, blocked_reason: null, class_name: 'Wizard', open: true, reason: 'long_rest', limit: 3,
  candidates: ['Magic Missile', 'Shield', 'Sleep', 'Misty Step'], prepared: ['Magic Missile'], spellbook: ['Magic Missile', 'Shield', 'Sleep', 'Misty Step'], ...extra });
const plainLabel = id => `<${id}>`;

test('window reason is plain Turkish for every engine reason, closed, combat and blocked', () => {
  const text = (extra, combat = false) => lib.windowReasonText(view(extra), combat);
  assert.match(text({ reason: 'creation' }), /yeni yaratıldı.*ilk kaydettiğin listeye kadar/);
  assert.match(text({ reason: 'migration' }), /Eski kaydın.*bir kez seç/);
  assert.match(text({ reason: 'long_rest' }), /Uzun dinlenmeyi bitirdin.*değiştirebilirsin/);
  assert.match(text({ reason: 'level_up' }), /yalnız büyü ekleyebilirsin.*uzun dinlenme gerekir/);
  assert.match(text({ open: false, reason: null }), /kapalı\. Uzun dinlenmeyi bitirince ya da yeni bir seviyeye/);
  assert.match(text({ open: false, reason: 'creation' }, true), /Çatışma sürerken büyü hazırlanamaz/);
  assert.match(text({ supported: false, blocked_reason: 'spellbook_missing', open: false }), /Büyü kitabın kayıtta yok/);
  assert.match(text({ supported: false, blocked_reason: 'not_preparing_class', open: false }), /Bu sınıf büyü hazırlamaz/);
  for (const reason of ['creation', 'migration', 'long_rest', 'level_up']) assert.doesNotMatch(text({ reason }), /creation|migration|long_rest|level_up/);
});

test('toggling keeps the cap, never adds a non-candidate and does nothing in a closed window', () => {
  const v = view({ limit: 2 });
  assert.deepEqual(lib.toggleSpell(v, ['Magic Missile'], 'Shield'), ['Magic Missile', 'Shield']);
  assert.deepEqual(lib.toggleSpell(v, ['Magic Missile', 'Shield'], 'Sleep'), ['Magic Missile', 'Shield'], 'cap reached');
  assert.deepEqual(lib.toggleSpell(v, ['Magic Missile', 'Shield'], 'Magic Missile'), ['Shield'], 'long rest may remove');
  assert.deepEqual(lib.toggleSpell(v, [], 'Fireball'), [], 'not a candidate');
  assert.deepEqual(lib.toggleSpell(view({ open: false }), ['Magic Missile'], 'Shield'), ['Magic Missile']);
  assert.deepEqual(lib.toggleSpell(view({ supported: false }), [], 'Shield'), []);
});

test('a level step window only grows the list: earlier spells are locked and a list without them is not sent', () => {
  const v = view({ reason: 'level_up', limit: 3, prepared: ['Magic Missile'] });
  assert.deepEqual([...lib.lockedSpells(v)], ['Magic Missile']);
  assert.deepEqual(lib.toggleSpell(v, ['Magic Missile', 'Shield'], 'Magic Missile'), ['Magic Missile', 'Shield']);
  assert.deepEqual(lib.toggleSpell(v, ['Magic Missile', 'Shield'], 'Shield'), ['Magic Missile']);
  assert.equal(lib.prepareRequest(v, ['Shield']), null);
  assert.deepEqual(lib.prepareRequest(v, ['Magic Missile', 'Shield']), { prepared: ['Magic Missile', 'Shield'] });
  assert.equal(lib.lockedSpells(view({ reason: 'long_rest' })).size, 0);
  assert.equal(lib.lockedSpells(view({ reason: 'level_up', open: false })).size, 0);
});

test('the request is exactly the player list, or null when closed, over the cap, repeated or unknown', () => {
  assert.deepEqual(lib.prepareRequest(view(), ['Shield', 'Magic Missile']), { prepared: ['Shield', 'Magic Missile'] });
  assert.deepEqual(lib.prepareRequest(view(), []), { prepared: [] }, 'an explicit empty list is a list');
  assert.equal(lib.prepareRequest(view({ open: false }), ['Shield']), null);
  assert.equal(lib.prepareRequest(view({ limit: 1 }), ['Shield', 'Sleep']), null);
  assert.equal(lib.prepareRequest(view(), ['Shield', 'Shield']), null);
  assert.equal(lib.prepareRequest(view(), ['Fireball']), null);
  assert.equal(lib.prepareRequest(view({ supported: false }), []), null);
});

test('results and dropped names are our Turkish sentences with display names, never the server message', () => {
  const ok = { status: 'prepared', prepared: ['Magic Missile', 'Shield'], dropped: [], limit: 3, excess: 0, open: false, message: 'Hazırlanan büyüler: Magic Missile, Shield.' };
  assert.equal(lib.resultText(ok, plainLabel), 'Hazırlanan büyüler: <Magic Missile>, <Shield>. 1 boş yerin kaldı.');
  assert.equal(lib.resultText({ ...ok, limit: 2 }, plainLabel), 'Hazırlanan büyüler: <Magic Missile>, <Shield>.');
  assert.equal(lib.resultText({ ...ok, prepared: [] }, plainLabel), 'Hazırlanan büyüler: yok. 3 boş yerin kaldı.');
  assert.match(lib.resultText({ ...ok, status: 'too_many', limit: 2, excess: 1 }, plainLabel), /En çok 2 büyü.*1 fazlası var.*kaydedilmedi/);
  assert.equal(lib.droppedText([], plainLabel), null);
  assert.equal(lib.droppedText([{ spell_id: 'Fire Bolt', reason: 'cantrip' }, { spell_id: 'Wish', reason: 'not_in_spellbook' }, { spell_id: 'Aid', reason: 'not_on_class_list' }, { spell_id: 'Sleep', reason: 'duplicate' }], plainLabel),
    'Listeye alınmayanlar: <Fire Bolt> (hile (cantrip) hazırlanmaz), <Wish> (büyü kitabında yok), <Aid> (sınıf listesinde yok), <Sleep> (iki kez seçildi).');
});

test('every engine refusal code has its own Turkish text; 5xx and network errors are not refusals', () => {
  const err = (status, code) => ({ status, data: { detail: code ? { code, message: 'English or engine text' } : [{ msg: 'x' }] } });
  const codes = { prepare_window_closed: /penceresi kapalı/, prepare_spellbook_missing: /Büyü kitabın kayıtta yok/, prepare_not_supported: /büyü hazırlamaz/,
    prepare_unavailable: /okunamadı/, prepare_level_up_additive_only: /yalnız büyü ekleyebilirsin/, action_id_conflict: /işlem kimliği/ };
  for (const [code, pattern] of Object.entries(codes)) {
    const text = lib.prepareRefusalText(err(409, code));
    assert.match(text, pattern, code);
    assert.match(text, /kaydedilmedi/, code);
    assert.doesNotMatch(text, /English|engine/, code);
    assert.equal(lib.isPrepareRefusal(err(409, code)), true);
  }
  assert.match(lib.prepareRefusalText(err(422)), /geçersiz sayıldı/);
  assert.match(lib.prepareRefusalText(err(409, 'campaign_stale')), /kaydedilmedi/);
  assert.equal(lib.isPrepareRefusal(err(500, 'x')), false);
  assert.equal(lib.isPrepareRefusal(new TypeError('Failed to fetch')), false);
});

test('spell names: Turkish where a catalog has one, else the English id; server catalog first', () => {
  assert.match(names.spellLabel('Magic Missile'), /^\S.* \(Magic Missile\)$/);
  assert.doesNotMatch(names.spellLabel('Magic Missile'), /^Magic Missile/);
  assert.equal(names.spellLabel('Misty Step'), 'Misty Step', 'level-2 spells have no Turkish name yet (D-043)');
  const server = { spells_catalog: { Cleric: { spells_level_1: [{ id: 'Bless', name_tr: 'Kutsama (Bless)' }] } } };
  assert.equal(names.spellLabel('Bless', server), 'Kutsama (Bless)');
  assert.equal(names.spellLabel('Bless', { spells_catalog: { Cleric: { spells_level_1: [{ id: 'Bless', name_tr: 'Takdis' }] } } }), 'Takdis (Bless)');
  assert.equal(names.spellLabel('Unknown Spell', server), 'Unknown Spell');
});

test('only Wizard and Cleric with a spell state get the screen', () => {
  assert.equal(lib.preparesSpells({ character: { class: 'Wizard' }, spellcasting: { prepared: [] } }), true);
  assert.equal(lib.preparesSpells({ character: { class: 'Cleric' }, spellcasting: { prepared: [] } }), true);
  assert.equal(lib.preparesSpells({ character: { class: 'Sorcerer' }, spellcasting: { prepared: [] } }), false);
  assert.equal(lib.preparesSpells({ character: { class: 'Wizard' }, spellcasting: null }), false);
  assert.equal(lib.preparesSpells(null), false);
});

const panelProps = (extra = {}) => ({ view: view(), draft: ['Magic Missile'], combatActive: false, expanded: true, sending: false, disabled: false, feedback: null,
  onToggle() {}, onSave() {}, onExpand() {}, onReset() {}, ...extra });
const screenHtml = extra => render(React.createElement(screen.SpellPreparationPanel, panelProps(extra)));

test('open window renders a keyboard-usable checklist with count, cap and Turkish names', () => {
  const html = screenHtml();
  assert.match(html, /data-testid="spell-preparation"/);
  assert.match(html, /<h2[^>]*>Büyü hazırlığı<\/h2>/);
  assert.match(html, /aria-expanded="true"/);
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, 4);
  assert.match(html, /data-testid="spell-prepare-count"[^>]*>1 \/ 3 hazır</);
  assert.match(html, /\(Magic Missile\)/);
  assert.match(html, />Misty Step</);
  assert.match(html, /Uzun dinlenmeyi bitirdin/);
  assert.match(html, /data-testid="button-save-prepared"/);
  assert.doesNotMatch(html, /data-testid="button-save-prepared"[^>]*disabled/);
  assert.doesNotMatch(html, /long_rest|level_up|creation/);
});

test('at the cap unchecked boxes are disabled and the reason is said', () => {
  const html = screenHtml({ view: view({ limit: 1 }) });
  assert.match(html, /Sınıra ulaştın/);
  const boxes = html.match(/<input[^>]*type="checkbox"[^>]*>/g);
  assert.equal(boxes.filter(box => /disabled/.test(box)).length, 3);
  assert.equal(boxes.filter(box => /checked/.test(box)).length, 1);
});

test('level step window: earlier spells are checked, locked and explained', () => {
  const html = screenHtml({ view: view({ reason: 'level_up', prepared: ['Magic Missile'] }), draft: ['Magic Missile'] });
  const locked = html.match(/<input[^>]*value="Magic Missile"[^>]*>/)[0];
  assert.match(locked, /checked/);
  assert.match(locked, /disabled/);
  assert.match(html, /önceki hazırlık · uzun dinlenmede değişir/);
  assert.match(html, /yalnız büyü ekleyebilirsin/);
});

test('closed window and blocked save show no editable controls and the reason', () => {
  for (const [extra, pattern] of [[{ open: false, reason: null }, /penceresi kapalı/], [{ supported: false, blocked_reason: 'spellbook_missing', open: false }, /Büyü kitabın kayıtta yok/]]) {
    const html = screenHtml({ view: view(extra) });
    assert.match(html, pattern);
    assert.doesNotMatch(html, /type="checkbox"|button-save-prepared/);
  }
  assert.match(screenHtml({ view: view({ open: false }), combatActive: true }), /Çatışma sürerken/);
});

test('collapsed card keeps only the header and the status rows', () => {
  const html = screenHtml({ expanded: false });
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /type="checkbox"/);
  assert.match(html, /data-testid="spell-status-rows"/);
});

test('sending disables the form; feedback is announced', () => {
  const html = screenHtml({ sending: true, feedback: { tone: 'error', text: 'Listen kaydedilmedi.' } });
  assert.match(html, /<fieldset[^>]*disabled/);
  assert.match(html, /role="alert"[^>]*>Listen kaydedilmedi\.</);
  assert.match(screenHtml({ feedback: { tone: 'success', text: 'Tamam.' } }), /role="status"[^>]*>Tamam\.</);
});

// S3: read-only status rows.
const rows = extra => render(React.createElement(panel.SpellStatusRows, { view: view(), combatActive: false, label: id => names.spellLabel(id), ...extra }));
test('status rows show window, prepared count and the Wizard spellbook, read-only', () => {
  const html = rows();
  assert.match(html, /data-testid="spell-window-row"[^>]*>Açık · uzun dinlenme</);
  assert.match(html, /data-testid="spell-prepared-count-row"[^>]*>1 \/ 3</);
  assert.match(html, /data-testid="spell-spellbook-row"/);
  assert.match(html, /4 büyü/);
  assert.match(html, /\(Magic Missile\)/);
  assert.doesNotMatch(html, /<button|<input|<select/);
  assert.match(rows({ view: view({ reason: 'level_up' }) }), /Açık · yeni seviye/);
  assert.match(rows({ view: view({ open: false, reason: null }) }), /spell-window-row"[^>]*>Kapalı</);
  assert.match(rows({ view: view({ open: false }), combatActive: true }), /Kapalı · çatışma/);
  const cleric = rows({ view: view({ class_name: 'Cleric', spellbook: null }) });
  assert.doesNotMatch(cleric, /spell-spellbook-row/);
  assert.doesNotMatch(cleric, /Konsantrasyon/, 'not projected by the engine yet (debt row)');
});

test('the screen is mounted once in the play page, gated to preparing classes, and stays outside save/money code', async () => {
  const page = readGameBrowserSource();
  assert.equal((page.match(/<SpellPreparationControls /g) ?? []).length, 1);
  assert.match(page, /preparesSpells\(state\) && <SpellPreparationControls key=\{`\$\{currentAccountOwner\(\) \?\? LOCAL_OWNER\}:\$\{campaignId\}:\$\{sessionId\}`\} state=\{state\} sessionId=\{sessionId\} campaignId=\{campaignId\} catalog=\{characterCatalogQuery\.data\}\s+disabled=\{turnSending \|\| undoBusy \|\| Boolean\(blockingMutation\(\)\)\} \/>/);
  const source = await readFile('src/components/spell-preparation-screen.tsx', 'utf8');
  assert.match(source, /prepareGameSessionSpells\(sessionId, \{ \.\.\.body, action_id: actionId \}/);
  assert.match(source, /getGameSessionSpellPreparation\(sessionId/);
  assert.doesNotMatch(source, /economic|wallet|shop|coins|applyGameSessionLevelUp|submitTurn|localStorage/i);
  assert.match(source, /readPending\(/, 'an unresolved play move blocks the save');
  assert.match(source, /applyGameState\(/);
});
