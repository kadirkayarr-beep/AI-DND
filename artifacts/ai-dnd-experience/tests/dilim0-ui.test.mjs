// Dilim 0 (UI tour): pure helpers and components rendered from the real modules.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

process.env.PORT ||= '4191';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite, React, render;
let coins, purse, notice, panel;            // Görev 4
let history, transcript, lastTurn, banner, resumeMode;  // Görev 5
let counter, questUi;                       // Görev 6
let panels;                                 // Görev 7
let economy, terms, rogueUi;                // Görev 8, 10
let strip;                                  // Görev 9
let display, inv, sorcerer;                 // Görev 11

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  coins = await vite.ssrLoadModule('/src/lib/coins.ts');
  purse = await vite.ssrLoadModule('/src/lib/starting-purse.ts');
  notice = await vite.ssrLoadModule('/src/components/starting-equipment-notice.tsx');
  panel = await vite.ssrLoadModule('/src/components/character-panel.tsx');
  history = await vite.ssrLoadModule('/src/lib/transcript-history.ts');
  transcript = await vite.ssrLoadModule('/src/components/campaign-transcript.tsx');
  lastTurn = await vite.ssrLoadModule('/src/components/last-turn-bar.tsx');
  banner = await vite.ssrLoadModule('/src/components/notice-banner.tsx');
  resumeMode = await vite.ssrLoadModule('/src/lib/resume-mode.ts');
  counter = await vite.ssrLoadModule('/src/lib/quest-counter.ts');
  questUi = await vite.ssrLoadModule('/src/components/quest-journal-section.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props) => renderToStaticMarkup(React.createElement(type, props));
});
after(async () => { await vite?.close(); });

/** Visible text only: drops title="…" attributes so the English hover names are not counted. */
const stripTitles = (html) => html.replace(/\stitle="[^"]*"/g, '');
/** Same as makeState in tests/combat-panel.test.mjs:89-134. */
function makeState(overrides = {}) {
  const { combat: combatOverrides = {}, ...stateOverrides } = overrides;
  return {
    character: { name: 'Arven', current_hp: 12, max_hp: 14, armor_class: 15 },
    player_combat_status: 'active',
    death_state: { mode: 'CHECKPOINT_ROLLBACK', status: 'conscious', successes: 0, failures: 0, terminal: false, last_death_save: null },
    combat: { active: false, status: 'ended', round: 0, initiative_order: [], current_turn_index: 0, current_actor_id: null,
      turn_owner: null, participants: [], participant_records: [], target_id: null, end_reason: null, ...combatOverrides },
    npcs: [{ id: 'npc_bandit', name: 'Bandit', current_hp: 2, max_hp: 12, armor_class: 13, combat_status: 'active' },
      { id: 'npc_wolf', name: 'Wolf', current_hp: 8, max_hp: 8, armor_class: 12, combat_status: 'active' }],
    ...stateOverrides,
  };
}
/** A player turn with every resource ready (shape of tests/combat-panel.test.mjs:59-66). */
const playerTurnState = makeState({ combat: { active: true, status: 'active', round: 1, current_actor_id: 'player',
  action_economy: { actors: { player: {
    base_action_spent: false, additional_actions: [], bonus_action_spent: false, bonus_action_available: false,
    bonus_rules: [], reaction_available: true, movement_remaining: 30, speed_ft: 30, ready: null, opportunity: null,
    legal_actions: [{ kind: 'attack', legal: true }, { kind: 'dash', legal: true }, { kind: 'ready', legal: true }],
  } } } } });

const fighter = { name: 'Kadir', race: 'Human', class: 'Fighter', level: 1, current_hp: 12, max_hp: 12,
  armor_class: 16, proficiency_bonus: 2, xp: 0, strength: 17, dexterity: 13, constitution: 15,
  intelligence: 12, wisdom: 10, charisma: 8, proficient_skills: [], progression_effects_pending: [] };
const catalog = { classes: { Fighter: { equipment_packages: [{ id: 'C', coin_gp: 10, coin_items: ['10 Altın'] }] } },
  backgrounds: { Soldier: { coin_gp: 14, coin_items: ['14 Altın'] }, Artisan: { coin_gp: 32, coin_items: ['32 GP'] } },
  equipment_rules: { background_option_b_gp: 50 } };

test('coinText shows gold, silver and copper like the counter', () => {
  assert.equal(coins.coinText(6000), '60 altın 0 gümüş 0 bakır');
  assert.equal(coins.coinText(5741), '57 altın 4 gümüş 1 bakır');
  assert.equal(coins.coinText(-1), '—');
});
test('the starting purse adds the class package and the background', () => {
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Soldier', 'B'), { classGp: 10, backgroundGp: 50, totalGp: 60 });
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Soldier', 'A'), { classGp: 10, backgroundGp: 14, totalGp: 24 });
  assert.deepEqual(purse.startingPurse(catalog, 'Fighter', 'C', 'Artisan', 'A'), { classGp: 10, backgroundGp: 32, totalGp: 42 });
  assert.equal(purse.startingPurse({ classes: {} }, 'Fighter', 'C', 'Soldier', 'B'), null);
});
test('the notice says one sentence for every class', () => {
  const html = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Soldier', backgroundOption: 'B', backgroundData: catalog.backgrounds.Soldier, catalog });
  assert.match(html, /Başlangıç kesesi: sınıf paketi 10 altın \+ geçmiş 50 altın = 60 altın\./);
  assert.doesNotMatch(html, /sunucu|cüzdan|servet|GP/);
  const optionA = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Soldier', backgroundOption: 'A', backgroundData: catalog.backgrounds.Soldier, catalog });
  assert.match(optionA, /sınıf paketi 10 altın \+ geçmiş 14 altın = 24 altın\./);
  // A sourced background A (decision 40): its "32 GP" is the purse line, never a good.
  const sourcedA = render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes,
    equipmentPackage: 'C', background: 'Artisan', backgroundOption: 'A', backgroundData: catalog.backgrounds.Artisan, catalog });
  assert.match(sourcedA, /sınıf paketi 10 altın \+ geçmiş 32 altın = 42 altın\./);
  assert.doesNotMatch(sourcedA, /GP/);
  // The welcome call site knows neither package nor background: nothing is drawn, no amount is guessed.
  assert.equal(render(notice.StartingEquipmentNotice, { characterClass: 'Fighter', classes: catalog.classes, catalog }), '');
});
test('the character panel shows the purse from the wallet', () => {
  const html = render(panel.CharacterPanel, { character: fighter, walletTotalCp: 6000 });
  assert.match(html, /data-testid="text-character-purse"[^>]*>Kese: 60 altın 0 gümüş 0 bakır</);
  assert.doesNotMatch(render(panel.CharacterPanel, { character: fighter, walletTotalCp: null }), /text-character-purse/);
});
test('the package list shows goods only; coin is the purse line; an old catalog keeps its list', () => {
  const pack = { id: 'C', items: ['Ağır Tatar Yayı & 20 Ok', '10 Altın', 'Macera Çantası'], coin_items: ['10 Altın'] };
  assert.deepEqual(purse.packageGoods(pack), ['Ağır Tatar Yayı & 20 Ok', 'Macera Çantası']);
  assert.deepEqual(purse.packageGoods({ id: 'A', items: ['Zırh', '10 Altın'] }), ['Zırh', '10 Altın']);
  assert.deepEqual(purse.packageGoods({ id: 'B', items: ['75 GP'], coin_items: ['75 GP'] }), []);
  assert.deepEqual(purse.packageGoods(null), []);
});

// Görev 5 (52, EK 6/6, 22, R, EK 5 T17): the undo is shown from the server's receipt-backed flags.
const undoHistory = [{ player_message: 'bira', narration: 'n1', created_at: 't', undone: true },
  { player_message: '↶ Son turu geri al', narration: 'Son tur geri alındı; o turda olanlar yaşanmamış sayılıyor.', created_at: 't', undo_note: true }];
test('history becomes entries with the undo flags', () => {
  const entries = history.historyToEntries(undoHistory, { opening: 'açılış' });
  assert.deepEqual(entries.map(x => [x.kind, !!x.undone, !!x.undoNote]),
    [['narration', false, false], ['player', true, false], ['narration', true, false], ['player', false, true], ['narration', false, true]]);
  assert.equal(history.historyToEntries(undoHistory).length, 4);  // no opening, no extra entry
  const moded = history.historyToEntries(undoHistory, { lastPlayerMode: 'say' });
  assert.deepEqual(moded.filter(x => x.kind === 'player').map(x => x.mode), [undefined, 'say']);  // only the last player entry
});
test('an undone turn is faded and labelled, the undo row reads as a sentence', () => {
  const html = render(transcript.Transcript, { entries: history.historyToEntries(undoHistory),
    scrollRef: { current: null }, onScroll() {}, newResponseEntryIndex: null, onJumpToNewResponse() {} });
  assert.equal((html.match(/class="(player-entry|story-entry) transcript-undone"/g) ?? []).length, 2);
  assert.match(html, /data-testid="transcript-undone-0">Geri alındı</);
  assert.match(html, /data-testid="transcript-undone-1">Geri alındı</);
  assert.doesNotMatch(html, /transcript-undone-2/);
  assert.match(html, /Geri aldın/); assert.match(html, /Son turu geri aldın\./);
  assert.doesNotMatch(html, /↶/);
});
test('an unverifiable undo says so and a typed marker stays the player\'s words', () => {
  // decisions 36-37: only a receipt-verified row reads as an undo
  const html = render(transcript.Transcript, { entries: history.historyToEntries([
    { player_message: '↶ Son turu geri al', narration: 'Son tur geri alındı; o turda olanlar yaşanmamış sayılıyor.', created_at: 't',
      undo_note: true, undo_target_unknown: true },
    { player_message: '↶ Son turu geri al', narration: 'Barmen omuz silker.', created_at: 't2' }]),
    scrollRef: { current: null }, onScroll() {}, newResponseEntryIndex: null, onJumpToNewResponse() {} });
  assert.match(html, /data-testid="transcript-undo-unknown-0">Hangi turun geri alındığı bu kayıtta artık doğrulanamıyor\.</);
  assert.equal((html.match(/Son turu geri aldın\./g) ?? []).length, 1);          // only the verified row
  assert.match(html, /data-testid="transcript-player-2"[\s\S]*?↶ Son turu geri al/); // the typed row shows as typed
  assert.doesNotMatch(html, /transcript-undone-/);
});
test('right after an undo the bar says why there is no second undo', () => {
  const base = { summary: null, recoveringUndo: false, busy: false, onUndo() {}, combatActive: false };
  const once = render(lastTurn.LastTurnBar, { ...base, canUndo: false, justUndone: true });
  assert.match(once, /data-testid="text-undo-once">Yalnız son tur geri alınır; yeni bir tur oynayınca Geri al yeniden açılır\.</);
  assert.doesNotMatch(once, /button-undo-last-turn/);
  assert.doesNotMatch(render(lastTurn.LastTurnBar, { ...base, canUndo: true, justUndone: false }), /text-undo-once/);
});
test('a resumed game keeps an open conversation in Söyle', async () => {
  // before(): resumeMode = /src/lib/resume-mode.ts (decision 39b)
  assert.deepEqual(resumeMode.resumeComposerMode({ conversation: { active: true, interlocutor: { id: 'barman', name: 'Marek' } } }),
    { mode: 'say', targetId: 'barman' });
  assert.deepEqual(resumeMode.resumeComposerMode({ conversation: { active: false, interlocutor: null } }), { mode: 'do', targetId: '' });
  assert.deepEqual(resumeMode.resumeComposerMode({}), { mode: 'do', targetId: '' });
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(source, /resumeComposerMode\(resumed\.state\)/);
  assert.match(source, /justUndone=\{undoneJustNow\}/);
});
test('the undo button says Geri al and explains itself in a fight', () => {
  const base = { summary: null, recoveringUndo: false, busy: false, onUndo() {}, justUndone: false };
  const idle = render(lastTurn.LastTurnBar, { ...base, canUndo: true, combatActive: false });
  assert.match(idle, /data-testid="button-undo-last-turn"[\s\S]*?Geri al<\/button>/);
  assert.match(idle, /aria-label="Son turu geri al"/);
  assert.doesNotMatch(idle, /text-undo-combat/);
  const fight = render(lastTurn.LastTurnBar, { ...base, canUndo: false, combatActive: true });
  assert.match(fight, /data-testid="text-undo-combat">Savaş sürerken son tur geri alınamaz\.</);
  assert.doesNotMatch(fight, /button-undo-last-turn/);
  assert.equal(render(lastTurn.LastTurnBar, { ...base, canUndo: false, combatActive: false }), '');
});
test('a success notice carries a check, not a warning', () => {
  const ok = render(banner.NoticeBanner, { notice: { tone: 'success', title: 'Geri alındı', detail: 'Son tur geri alındı.' } });
  assert.match(ok, /data-testid="notice-icon-success"/); assert.doesNotMatch(ok, /notice-icon-warning/);
  const bad = render(banner.NoticeBanner, { notice: { tone: 'error', title: 'Olmadı', detail: 'Bağlantı koptu.' } });
  assert.match(bad, /data-testid="notice-icon-warning"/); assert.doesNotMatch(bad, /notice-icon-success/);
});
test('the play screen maps history through one helper', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.equal((source.match(/historyToEntries\(/g) ?? []).length, 4);
  assert.doesNotMatch(source, /history\.flatMap\(\(entry/);
  assert.match(source, /combatActive=\{Boolean\(visibleLastTurn\) && state\.combat\.active\}/);
});
test('the local transcript cache gives the undo flags back, and only true ones', async () => {
  // A campaignless session restores its story from the local cache (game-browser.tsx restore effect, run as written).
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const browser = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
  const effect = browser.body.statements.find(n => ts.isExpressionStatement(n) && n.getText(ast).startsWith('useEffect(')
    && n.getText(ast).includes('setEntries(restored)'));
  const js = ts.transpileModule('globalThis.restore = ' + effect.expression.arguments[0].getText(ast) + ';',
    { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  const cached = [{ kind: 'player', text: 'bira', undone: true }, { kind: 'narration', text: 'n1', undone: true },
    { kind: 'player', text: '↶ Son turu geri al', undoNote: true, undoTargetUnknown: true }, { kind: 'narration', text: 'n2', undoNote: 'yes' }];
  const shown = [];
  const ctx = { sessionId: 'local-session', campaignId: '', TRANSCRIPT_KEY: 'ai-dnd-transcript-', JSON,
    window: { localStorage: { getItem: () => JSON.stringify(cached) } },
    setEntries: v => shown.push(v), setCombatEndNotice() {}, setCombatTargetId() {} };
  vm.runInNewContext(js, ctx);
  ctx.restore();
  assert.deepEqual(JSON.parse(JSON.stringify(shown.at(-1))), [{ kind: 'player', text: 'bira', undone: true },
    { kind: 'narration', text: 'n1', undone: true }, { kind: 'player', text: '↶ Son turu geri al', undoNote: true, undoTargetUnknown: true },
    { kind: 'narration', text: 'n2' }]);
});

// before(): counter = /src/lib/quest-counter.ts, questUi = /src/components/quest-journal-section.tsx
const noAdventures = { rumors: [], active: [], completed: [], failed: [], timeline: [] };
const questProps = { quests: [], offers: [], knownNpcs: [], onAccept() {}, onCancel() {},
  acceptPending: false, cancelPending: false, hasError: false };
test('the counter counts running quests and running adventures, not finished ones', () => {
  assert.equal(counter.runningQuestCount({ quests: [{ status: 'accepted' }, { status: 'completed' }, { status: 'cancelled' }],
    campaign_adventures: { active: [{ title: 'Teslimat' }] } }), 2);
  assert.equal(counter.runningQuestCount({ quests: [], campaign_adventures: null }), 0);
  assert.equal(counter.runningQuestCount({ quests: [{ status: 'active' }] }), 1);
});
test('the quest section never says no quests while an adventure runs', () => {
  const running = render(questUi.QuestJournalSection, { ...questProps, adventures: { ...noAdventures,
    active: [{ title: 'Teslimat', summary: "İade takımını Tuna'ya götür.", objectives: [] }] } });
  assert.doesNotMatch(running, /empty-journal-quests/);
  assert.match(running, /<span class="character-badge">01<\/span>/);
  const empty = render(questUi.QuestJournalSection, { ...questProps, adventures: noAdventures });
  assert.match(empty, /data-testid="empty-journal-quests"[^>]*>\s*Henüz kayıtlı görev yok\./);
  assert.match(empty, /<span class="character-badge">00<\/span>/);
});
test('the rail summary says Süren görevler from the same count', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(source, /Süren görevler \{runningQuestCount\(state\)\}/);
  assert.doesNotMatch(source, /Görevler \{state\.quests\?\.length/);
});

// Görev 7: additions preserve all existing tests and setup unchanged.
test('the counter shows outside a fight only', async () => {
  const panels = await vite.ssrLoadModule('/src/lib/play-panels.ts');
  assert.equal(panels.showsCounter({ combat: { active: false } }, 'c1'), true);
  assert.equal(panels.showsCounter({ combat: { active: true } }, 'c1'), false);
  assert.equal(panels.showsCounter({ combat: { active: false } }, ''), false);
  assert.equal(panels.showsCounter({ combat: null }, 'c1'), true);
  assert.equal(panels.showsCounter({}, 'c1'), true);
});
test('the play screen draws the counter through showsCounter and folds the offer form', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(source, /showsCounter\(state, campaignId\) && <ShopControls/);
  assert.match(source, /economic-prepare-drawer[\s\S]{0,200}Para ver ya da teklif hazırla/);
  assert.match(source, /!state\.combat\.active && <details className="economic-prepare-drawer"/);
  assert.doesNotMatch(source, /<details[^>]*economic-prepare-drawer[^>]*\sopen/);
});

const stripCombat = { active: true, round: 2, participant_records: [
  { id: 'npc1', kind: 'npc', name: 'Haydut', current_hp: 7, max_hp: 11, armor_class: 12, status: 'active', primary_action_available: true, is_current_actor: true },
  { id: 'player', kind: 'player', name: 'Kadir', current_hp: 6, max_hp: 9, armor_class: 16, status: 'active', primary_action_available: true, is_current_actor: false }] };
test('the strip shows the round and every side hit points, player first', async () => {
  const strip = await vite.ssrLoadModule('/src/components/combat-status-strip.tsx');
  const html = render(strip.CombatStatusStrip, { combat: stripCombat });
  assert.match(html, /Çatışma · Tur 2/);
  assert.ok(html.indexOf('Kadir') < html.indexOf('Haydut'));
  assert.match(html, /Haydut · Can 7\/11 · Ayakta/); assert.match(html, /sırada/);
  assert.equal(render(strip.CombatStatusStrip, { combat: { ...stripCombat, active: false } }), '');
});
test('the start notice comes from combat_started and the generic end is said once', async () => {
  const strip = await vite.ssrLoadModule('/src/components/combat-status-strip.tsx');
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(source, /combat_started === true/);
  assert.match(source, /<CombatTransitionBanner kind="start"/);
  assert.match(source, /<CombatTransitionBanner kind="end"/);
  const start = render(strip.CombatTransitionBanner, { kind: 'start', text: 'Sıra: Haydut' });
  assert.match(start, /data-testid="status-combat-started"/); assert.match(start, /role="status"/);
  assert.match(start, /<strong>ÇATIŞMA BAŞLADI<\/strong><span>Sıra: Haydut<\/span>/);
  const generic = render(strip.CombatTransitionBanner, { kind: 'end', text: 'Çatışma sona erdi.' });
  assert.match(generic, /data-testid="status-combat-ended"/); assert.match(generic, /<strong>ÇATIŞMA SONA ERDİ<\/strong>/);
  assert.doesNotMatch(generic, /Çatışma sona erdi\./);
  const won = render(strip.CombatTransitionBanner, { kind: 'end', text: 'Rakip etkisiz hale getirildi.' });
  assert.match(won, /<span>Rakip etkisiz hale getirildi\.<\/span>/);
});
test('the strip reuses the combat panel status words', async () => {
  const strip = await vite.ssrLoadModule('/src/components/combat-status-strip.tsx');
  const source = await readFile('src/components/combat-panel.tsx', 'utf8');
  assert.match(source, /export function combatStatusLabel/);
  const html = render(strip.CombatStatusStrip, { combat: { ...stripCombat, participant_records: [
    { ...stripCombat.participant_records[0], status: 'unconscious', current_hp: 0 }, stripCombat.participant_records[1]] } });
  assert.match(html, /Haydut · Can 0\/11 · Bilinçsiz/);
});

test('combat start notices clear on later turns and context changes, and ignore stale results', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const browser = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
  const reset = browser.body.statements.find(n => ts.isExpressionStatement(n) && n.getText(ast).startsWith('useEffect(')
    && n.expression.arguments[0].getText(ast).trim() === '() => {\n    setCombatStartNotice(null);\n  }');
  assert.ok(reset, 'transient combat notice has its own context reset');
  assert.equal(reset.expression.arguments[1].getText(ast), '[sessionId, campaignId]');
  const resets = [];
  vm.runInNewContext(ts.transpileModule('(' + reset.expression.arguments[0].getText(ast) + ')();', {}).outputText,
    { setCombatStartNotice: value => resets.push(value) });
  assert.deepEqual(resets, [null]);
  let resultBranch;
  function visit(node) {
    if (ts.isIfStatement(node) && node.expression.getText(ast) === 'stillVisible'
      && node.thenStatement.getText(ast).includes('combatResult?.combat_started === true')) resultBranch = node;
    ts.forEachChild(node, visit);
  }
  visit(browser);
  assert.ok(resultBranch, 'notice update is guarded against stale responses');
  const js = ts.transpileModule(resultBranch.getText(ast), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const [visible, combatResult, expected] of [[true, { combat_started: true }, ['Sıra: Haydut']],
    [true, { combat_started: false }, [null]], [true, undefined, [null]], [false, { combat_started: true }, []]]) {
    const shown = [];
    vm.runInNewContext(js, { stillVisible: visible, combatResult, result: { state: { combat: stripCombat } },
      setCombatStartNotice: value => shown.push(value) });
    assert.deepEqual(shown, expected);
  }
});

test('accepted current server recovery clears an old combat start banner without replaying it', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let reconcile;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'reconcileFromServer') reconcile = node.initializer;
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.ok(reconcile);
  const js = ts.transpileModule('globalThis.recover = ' + reconcile.getText(ast) + ';',
    { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const [current, accepted] of [[true, true], [false, true], [true, false]]) {
    const shown = [];
    const ctx = { sessionId: 'synthetic', campaignId: '', getGetGameSessionStateQueryKey: () => [], nextRevision: () => 1,
      reconcileState: async () => ({ state: { combat: stripCombat }, history: null, combat_history: null }),
      queryClient: { invalidateQueries() {} }, operation: { isCurrent: () => current },
      ReconciliationError: Error, applyGameState: () => accepted, getGetCampaignsQueryKey: () => [],
      setCombatStartNotice: value => shown.push(value) };
    vm.runInNewContext(js, ctx);
    if (current && accepted) await ctx.recover(); else await assert.rejects(ctx.recover());
    assert.deepEqual(shown, current && accepted ? [null] : []);
  }
});

test('the play shell never caps the story below a readable height', async () => {
  const css = await readFile('src/index.css', 'utf8') + await readFile('src/components/unwritten-play.css', 'utf8');
  assert.doesNotMatch(css, /\.play-shell \.transcript-scroll \{[^}]*max-height:\s*(18|30)dvh/);
  assert.match(css, /\.play-shell \.transcript-scroll \{[^}]*min-height:\s*max\(220px,\s*38dvh\)/);
});
test('long combat rows fold without hiding primary actions or changing availability', async () => {
  const economy = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
  const html = render(economy.ActionEconomyPanel, { state: playerTurnState, targetId: 'npc_bandit', sending: false, onCommand() {} });
  const start = html.indexOf('data-testid="combat-more-actions"');
  assert.ok(start > 0);
  const end = html.indexOf('</details>', start);
  assert.ok(end > start);
  const inside = html.slice(start, end), outside = html.slice(0,start) + html.slice(end);
  assert.match(inside, /<summary>Diğer eylemler<\/summary>/);
  assert.match(inside, />Hareket et</); assert.match(inside, /Hazırlan/);
  assert.match(inside, /aria-label="Hareket mesafesi"/);
  assert.match(outside, />Saldır · /); assert.match(outside, />Turu bitir</); assert.match(outside, />Koş/);
  assert.doesNotMatch(outside, />Hareket et</);
  assert.doesNotMatch(html, /<details[^>]*data-testid="combat-more-actions"[^>]*\sopen/);
  const busy = render(economy.ActionEconomyPanel, { state: playerTurnState, targetId: 'npc_bandit', sending: true, onCommand() {} });
  assert.match(busy, /disabled=""[^>]*>Hareket et</);
  assert.match(busy, /disabled=""[^>]*>Hazırlan/);
});

test('combat terms, accessible labels and sent sentences are Turkish without changing typed commands', async () => {
  const terms = await vite.ssrLoadModule('/src/lib/tr-terms.ts');
  const economy = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
  assert.deepEqual(terms.SENT, { attack: 'Saldırıyorum.', continue_attack: 'Aynı saldırı eyleminde bir saldırı daha yapıyorum.',
    dash: 'Koşuyorum.', ready: 'Hazırlanıp bekliyorum.', react: 'Hazırladığım tepkiyi kullanıyorum.', decline_reaction: 'Tepki fırsatını geçiyorum.' });
  assert.equal(terms.moveSentence(30), '30 fit hareket ediyorum.');
  assert.equal(terms.abilitySentence('Büyük Biçim'), 'Büyük Biçim kullanıyorum.');
  const html = render(economy.ActionEconomyPanel, { state: playerTurnState, targetId: 'npc_bandit', sending: false, onCommand() {} });
  for (const word of [/Action\b/, /Reaction\b/, /\bReady\b/, /\bDash\b/, /\bft\b/]) assert.doesNotMatch(stripTitles(html), word);
  assert.match(html, /Hareket: 30 fit · Hız: 30 fit/); assert.match(html, /title="Dash"/);
  for (const label of ['Hazırlık tetikleyicisi', 'Tetikleyen', 'Hazırlık yanıtı', 'Hareket mesafesi']) assert.ok(html.includes(`aria-label="${label}"`));
  const source = await readFile('src/components/action-economy-panel.tsx', 'utf8');
  assert.match(source, /send\(SENT\.dash, \{ kind: 'dash' \}\)/);
  assert.match(source, /send\(moveSentence\(distanceValue\), \{ kind: 'move', distance_ft: distanceValue \}\)/);
  assert.match(source, /send\(SENT\.react, \{ kind: 'react', opportunity_id: /);
  assert.match(source, /send\(SENT\.decline_reaction, \{ kind: 'decline_reaction', opportunity_id: /);
  for (const old of ['Saldırı Action kullanıyorum.', 'Attack Action içindeki', 'Dash Action kullanıyorum.', 'Ready Action hazırlıyorum.',
    'Ready Reaction kullanıyorum.', 'Ready Reaction fırsatını atlıyorum.', 'Bonus Action kullanıyorum.', 'feet hareket ediyorum']) assert.ok(!source.includes(old), old);
});
test('combat glossary keeps original hover names and translated visible names', async () => {
  const terms = await vite.ssrLoadModule('/src/lib/tr-terms.ts');
  for (const [key, value] of Object.entries(terms.TR_TERMS)) {
    assert.equal(terms.term(key), value.tr); assert.equal(terms.termTitle(key), value.en);
    assert.notEqual(value.tr, value.en);
  }
  assert.equal(terms.term('second_wind'), 'İkinci Nefes');
  assert.equal(terms.term('sneak_attack'), 'Gizli Saldırı');
  assert.equal(terms.feetText(5), '5 fit');
});

test('all action costs and distances preserve their original hover names', async () => {
  const economy = await vite.ssrLoadModule('/src/components/action-economy-panel.tsx');
  const state = structuredClone(playerTurnState);
  state.combat.action_economy.actors.player.bonus_rules = ['adrenaline_rush'];
  const html = render(economy.ActionEconomyPanel, { state, targetId: 'npc_bandit', sending: false, onCommand() {} });
  assert.match(html, /title="Speed \/ feet"/);
  assert.match(html, /<label title="feet">Mesafe \(fit\)/);
  assert.match(html, /title="Attack \/ Action"/);
  assert.match(html, /title="Bonus Action \/ Dash"/);
});

test('rage status and confirmation preserve original hover names', async () => {
  const rage = await vite.ssrLoadModule('/src/components/rage-controls.tsx');
  const value = { uses_remaining: 1, max_uses: 2, active: true, remaining_seconds: 6, activate: { available: false, reason: 'active' }, extend: { available: true, reason: null } };
  const html = render(rage.RageControl, { rage: value, confirmed: true, blocked: false, onChange() {}, onCommand() {} });
  assert.match(html, /<p[^>]*title="Rage"[^>]*data-testid="rage-active"|<p[^>]*data-testid="rage-active"[^>]*title="Rage"/);
  assert.match(html, /<button[^>]*title="Rage \/ Bonus Action"/);
  assert.match(html, /<label title="Rage \/ Bonus Action"/);
});

test('monk second strike and action costs use the shared Turkish glossary', async () => {
  const monk = await vite.ssrLoadModule('/src/components/monk-controls.tsx');
  const yes = { available: true, reason: null };
  const value = { martial_arts_die: 8, martial_arts_ready: true, movement_bonus_ft: 10, save_dc: 13, focus: { points_remaining: 3, max_points: 5 }, martial_arts_strike: yes, flurry_of_blows: yes, flurry_strikes_remaining: 1, patient_defense: yes, step_of_the_wind: yes, uncanny_metabolism: yes, stunning_strike: yes, deflect_mode: 'reduce', open_hand_techniques: ['push'] };
  const html = render(monk.MonkControl, { monk: value, targetId: 'npc', blocked: false, attackEnabled: true, continueEnabled: true, technique: '', onTechniqueChange() {}, onCommand() {} });
  assert.doesNotMatch(stripTitles(html), /Flurry| · Bonus(?:<| ·)/);
  assert.match(html, /title="Flurry of Blows"/);
  assert.match(html, /title="Bonus Action">Bonus eylem/);
});

