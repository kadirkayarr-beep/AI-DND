// The owner's first browser play (31 Oct 2026): the UI items, rendered from the real components.
import assert from 'node:assert/strict';
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
