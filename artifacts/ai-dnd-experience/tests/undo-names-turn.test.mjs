// Görev 26: the undo confirmation says which turn is undone and how the purse comes back. Text only.
import assert from 'node:assert/strict';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4193';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite, lastTurn;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  lastTurn = await vite.ssrLoadModule('/src/components/last-turn-bar.tsx');
});
after(async () => { await vite?.close(); });

test('the confirmation names the turn and the coins that come back', () => {
  assert.equal(lastTurn.undoConfirmText('bira istiyorum', 4), '“bira istiyorum” ve sonuçları geri alınacak; kesene 4 bakır geri döner.');
  assert.equal(lastTurn.undoConfirmText("Marek'e bahşiş: 4 bakır ödendi.", 4),
    "“Marek'e bahşiş: 4 bakır ödendi” ve sonuçları geri alınacak; kesene 4 bakır geri döner.");
  assert.equal(lastTurn.undoConfirmText('kılıcı satıyorum', -7), '“kılıcı satıyorum” ve sonuçları geri alınacak; kesenden 7 bakır geri gider.');
  assert.equal(lastTurn.undoConfirmText('etrafa bakıyorum', 0), '“etrafa bakıyorum” ve sonuçları geri alınacak; kesen değişmez.');
});

test('an unknown purse says nothing about coins, and a turn without words keeps the old sentence', () => {
  assert.equal(lastTurn.undoConfirmText('etrafa bakıyorum', null), '“etrafa bakıyorum” ve sonuçları geri alınacak.');
  assert.equal(lastTurn.undoConfirmText(undefined, undefined), 'Bu tur ve sonuçları geri alınacak.');
  assert.equal(lastTurn.undoConfirmText('/item shop_buy barman bira 1 0 4', 4), 'Bu tur ve sonuçları geri alınacak; kesene 4 bakır geri döner.');
  assert.match(lastTurn.undoConfirmText('a'.repeat(200), null), /“a{117}\.\.\.”/);
});

test('the bar and the play screen carry the label and the purse change into the confirmation', async () => {
  const bar = await readFile('src/components/last-turn-bar.tsx', 'utf8');
  assert.match(bar, /undoConfirmText\(turnLabel, purseSpentCp\)/);
  assert.doesNotMatch(bar, /<span>Bu tur ve sonuçları geri alınacak\.<\/span>/);
  const page = readGameBrowserSource();
  assert.match(page, /turnLabel=\{visibleLastTurn\?\.label\}/);
  assert.match(page, /purseSpentCp=\{visibleLastTurn\?\.purseSpentCp\}/);
  // A retried stored move cannot know the purse before it: no number is guessed.
  assert.match(page, /const purseBefore = stored \? null : state\?\.wallet\?\.total_cp \?\? null;/);
});
