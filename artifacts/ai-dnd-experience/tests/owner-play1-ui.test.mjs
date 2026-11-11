// The owner's first browser play (31 Oct 2026): the UI items, rendered from the real components.
import assert from 'node:assert/strict';
import { readGameBrowserSource } from './helpers/read-game-browser-source.mjs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4181';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let React;
let render;
let levelUp;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  levelUp = await vite.ssrLoadModule('/src/components/level-up-controls.tsx');
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  render = (type, props) => renderToStaticMarkup(React.createElement(type, props));
});

after(async () => {
  await vite?.close();
});

test('the level button only exists once a level has really been earned', () => {
  assert.equal(levelUp.levelUpEarned({ level: 3, progression_level: 3 }), false);
  assert.equal(levelUp.levelUpEarned({ level: 1 }), false);
  assert.equal(levelUp.levelUpEarned({ level: 4, progression_level: 3 }), true);
  assert.equal(levelUp.levelUpEarned({ level: 2 }), true);
  assert.equal(levelUp.levelUpEarned(null), false);
});

test('a blocked level check speaks Turkish, never a raw code, and Kapat is its own button', () => {
  const html = render(levelUp.LevelUpChoices, {
    preview: { status: 'blocked', reason: 'level_not_earned' },
    draft: { cantrip: '', preparedSpell: '', confirmed: false },
    onChange() {}, onConfirm() {}, onCancel() {},
  });
  assert.doesNotMatch(html, /level_not_earned/);
  assert.match(html, /Henüz yeni bir seviye kazanmadın\./);
  assert.match(html, /<button[^>]*class="dnd-button secondary"[^>]*>Kapat<\/button>/);
});

test('the starting level sits above the class cards in its own marked block, not under the feature list', async () => {
  const source = await readFile('src/components/character-creation-screen.tsx', 'utf8');
  const block = source.indexOf('data-testid="starting-level-block"');
  const control = source.indexOf('<FighterStartingLevelControl', block);
  const cards = source.indexOf('cc-cards-grid cc-portrait-grid');
  assert.ok(block > 0 && block < control && control < cards, 'level block, then the control, then the class cards');
  const css = await readFile('src/components/character-creation-screen.css', 'utf8');
  assert.match(css, /\.cc-starting-level select[^}]*min-height:\s*44px/);
});

test('the wizard heading follows the chosen level', async () => {
  const source = await readFile('src/components/character-creation-screen.tsx', 'utf8');
  assert.match(source, /Karakter Defteri · Seviye \{startingDraft\.startingLevel\}/);
});

test('the input is simply there: open at the start and still open after a turn', async () => {
  const source = readGameBrowserSource();
  assert.match(source, /const \[composerOpen, setComposerOpen\] = useState\(true\);/);
  const afterTurn = source.slice(source.indexOf('if (stillVisible && (!stored'), source.indexOf('if (stillVisible) setLastTurn'));
  assert.doesNotMatch(afterTurn, /setComposerOpen\(false\)/);
});

test('the composer does not grab focus when the page loads, so a phone keyboard stays down', async () => {
  const source = readGameBrowserSource();
  assert.match(source, /if \(composerOpen && !wasComposerOpen\.current\) messageInputRef\.current\?\.focus\(\);/);
});
