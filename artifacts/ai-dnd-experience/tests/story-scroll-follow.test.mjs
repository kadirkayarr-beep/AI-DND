// G1.7 (D-088, D-089, D-090, D-180, D-574): the story scroll follow logic and the 409 `unresolved_action` message.
// Browserless: the production callbacks run in a vm (helpers/story-follow-harness.mjs); no browser is started.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { after, before, test } from 'node:test';
import ts from 'typescript';
import { storyFollowHarness } from './helpers/story-follow-harness.mjs';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import * as recovery from '../src/lib/action-recovery.ts';

process.env.PORT ||= '4187';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
});
after(async () => { await vite?.close(); });

// D-090 (1): the reader moved but the scroll event has not arrived; a ResizeObserver run in between must not drag them down.
test('resizeBeforeScrollKeepsReader: a layout run before the reader scroll event does not throw the story to the bottom', async () => {
  const h = await storyFollowHarness();
  h.readerInput('wheel'); h.node.scrollTop = 100; // the reader scrolled up; the scroll event is still queued
  h.resize(220, 375, 600); // a card opens: the observer runs first
  assert.equal(h.node.scrollTop, 100, 'the reader is not dragged back');
  h.context.scroll({ currentTarget: h.node });
  assert.equal(h.context.wasAtBottom.current, false, 'the reader left the bottom');
  assert.equal(h.node.scrollTop, 100);
});

// D-090 (2): a layout scroll that lands right after the reader touched the story (rotate the phone) is still layout.
test('layoutScrollAfterReaderInputKeepsPosition: a rotate right after a touch keeps following', async () => {
  const h = await storyFollowHarness();
  h.resize(154, 178, 8715); h.context.scroll({ currentTarget: h.node });
  assert.equal(h.node.scrollTop, 8561);
  h.readerInput('pointerdown'); // the reader touches the story, then turns the phone
  h.node.clientHeight = 359; h.node.clientWidth = 352; h.node.scrollHeight = 3772;
  h.node.scrollTop = 3211; // the browser's own move during the resize
  h.context.scroll({ currentTarget: h.node });
  h.resize(359, 352, 3772);
  assert.equal(h.context.wasAtBottom.current, true, 'a layout move is not the reader leaving the bottom');
  assert.equal(h.node.scrollTop, 3413, 'the latest narration stays in view');
});

// D-088: a scroll nobody asked for by touch or key (find in page, a screen reader) that lands with a layout change is the user's.
test('programmaticScrollDoesNotForceBottom: a find-in-page jump with a layout change is not undone', async () => {
  const h = await storyFollowHarness();
  h.resize(220, 375, 4075); h.context.scroll({ currentTarget: h.node });
  assert.equal(h.node.scrollTop, 3855);
  h.node.clientHeight = 219; h.node.scrollTop = 160; // a match far up is brought into view while the header grows 1 px
  h.context.scroll({ currentTarget: h.node });
  assert.equal(h.context.wasAtBottom.current, false, 'the view left the bottom');
  assert.equal(h.node.scrollTop, 160, 'the story is not thrown back to the bottom');
});

// D-089: the observer and the reader-input listeners follow the story box itself, not the entry count.
test('observersReattachToNewStoryNode: the story node is a callback ref and the observer effect depends on it', () => {
  const source = readGameBrowserSource();
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let deps;
  const visit = (node) => {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect' && (node.arguments[0]?.getText(ast) ?? '').includes('new ResizeObserver')) deps = node.arguments[1]?.getText(ast);
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.ok(deps, 'the observer effect exists');
  assert.doesNotMatch(deps, /entries/, 'not keyed on the entry count');
  assert.match(deps, /storyNode/, 'keyed on the story node');
  assert.match(source, /scrollRef=\{attachStory\}/, 'the transcript box reports its node through a callback ref');
});

// D-180: the server's 409 unresolved_action has one message, on every route.
const refusal = { status: 409, data: { detail: { code: 'unresolved_action', unresolved_action_id: 'open-1' } } };
const other409 = { status: 409, data: { detail: { code: 'something_else' } } };
test('unresolved409ShowsRecovery: one recovery message for the refusal, none for other errors', () => {
  const message = recovery.unresolvedActionMessage(refusal);
  assert.match(message, /sonucu henüz kesinleşmemiş bir hamle var/);
  assert.match(message, /sunucudan kontrol et ya da bilinçli olarak vazgeç/);
  assert.equal(recovery.unresolvedActionMessage(other409), null);
  assert.equal(recovery.unresolvedActionMessage(null), null);
});
test('unresolved409ShowsRecovery: the shared error mapper (undo, save, level-up) shows it instead of the generic line', async () => {
  const { friendlyError } = await vite.ssrLoadModule('/src/pages/game/shell-parts.tsx');
  assert.equal(friendlyError(refusal, 'Bu tur artık geri alınamıyor.'), recovery.unresolvedActionMessage(refusal));
  assert.doesNotMatch(friendlyError(other409, 'Bu tur artık geri alınamıyor.'), /kesinleşmemiş/);
});
test('unresolved409ShowsRecovery: spell preparation, species action, quest and ambient routes map the refusal', async () => {
  const prep = await vite.ssrLoadModule('/src/lib/spell-preparation.ts');
  assert.equal(prep.prepareRefusalText(refusal), recovery.unresolvedActionMessage(refusal));
  const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8');
  for (const file of ['components/species-trait-controls.tsx', 'pages/game/world-panels.tsx', 'pages/game-browser.tsx']) {
    assert.match(read(file), /unresolvedActionMessage\(/, `${file} maps the refusal through action-recovery`);
  }
});

// D-574: the story scroll code is its own hook; GameBrowser no longer carries it.
test('GameBrowser keeps no scroll internals; they live in use-story-scroll', () => {
  const page = readFileSync(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(page, /new ResizeObserver|readerInputAt|storyLayoutRef/);
  assert.match(page, /useStoryScroll\(/);
  assert.match(readFileSync(new URL('../src/pages/game/use-story-scroll.ts', import.meta.url), 'utf8'), /new ResizeObserver/);
  assert.ok(page.split('\n').length <= 1330, `game-browser.tsx has ${page.split('\n').length} lines; it only shrinks`);
});
