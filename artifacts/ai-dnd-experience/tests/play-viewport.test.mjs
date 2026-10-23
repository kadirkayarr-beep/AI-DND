import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { after, before, test } from 'node:test';
import ts from 'typescript';
import { clippedControlOverflow, focusReturnTarget, keyboardInset, transcriptFollowsBottom } from '../src/lib/play-viewport.ts';

process.env.PORT ||= '4183';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let renderTranscript;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const transcript = await vite.ssrLoadModule('/src/components/campaign-transcript.tsx');
  renderTranscript = (entries, resultCue = '') => renderToStaticMarkup(React.createElement(transcript.Transcript, {
    entries,
    scrollRef: React.createRef(),
    onScroll: () => {},
    resultCue,
  }));
});

after(async () => {
  await vite?.close();
});

const skill = {
  skill: 'Stealth',
  ability: 'dexterity',
  d20: 8,
  ability_modifier: 1,
  proficiency_modifier: 2,
  total_modifier: 3,
  total: 11,
  dc: 15,
  outcome: 'failure',
  difficulty: 'medium',
  proficient: true,
};

test('focus returns to the opener and falls back to the draft', () => {
  assert.equal(focusReturnTarget(true), 'opener');
  assert.equal(focusReturnTarget(false), 'draft');
});

test('history reading does not follow the bottom; the bottom still follows', () => {
  assert.equal(transcriptFollowsBottom(true), true);
  assert.equal(transcriptFollowsBottom(false), false);
});

test('keyboard inset is the covered bottom and never negative', () => {
  assert.equal(keyboardInset(800, 430, 0), 370);
  assert.equal(keyboardInset(800, 800, 0), 0);
  assert.equal(keyboardInset(800, 900, 20), 0);
});

test('keyboard recovery respects the clipping container as well as the viewport', () => {
  assert.equal(clippedControlOverflow(580, 500, 640), 80);
  assert.equal(clippedControlOverflow(580, 700, 430), 150);
  assert.equal(clippedControlOverflow(420, 500, 640), 0);
  assert.equal(clippedControlOverflow(580, Number.NaN, 640), 0);
});

test('a validated own turn returns to the live transcript before sending', async () => {
  const source = await readFile('src/pages/game-browser.tsx', 'utf8');
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let submit = '';
  const visit = node => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === 'submitTurn') submit = node.getText(ast);
    ts.forEachChild(node, visit);
  };
  visit(ast);
  const guard = submit.indexOf('if (!operation) return;');
  const follow = submit.indexOf('wasAtBottom.current = true;');
  const send = submit.indexOf('void playGameTurn(');
  assert.ok(guard >= 0 && follow > guard && send > follow);
  assert.match(submit.slice(follow, send), /transcript\.scrollTop = transcript\.scrollHeight/);
  assert.match(source, /const container = send\.closest<HTMLElement>\('\.app-main'\) \?\? shell/);
  assert.match(source, /if \(overflow > 1\) container\.scrollTop \+= overflow/);
});

test('transcript keeps player then narration order, the recorded roll, and a focus-free result cue', () => {
  const html = renderTranscript([
    { kind: 'player', text: 'Kapıya bakıyorum.' },
    { kind: 'narration', text: 'Kapı kilitli.', skillCheckResult: skill },
  ], 'Yeni sonuç geldi. 2');
  const playerAt = html.indexOf('data-testid="transcript-player-0"');
  const narrationAt = html.indexOf('data-testid="transcript-narration-1"');
  assert.ok(playerAt >= 0 && narrationAt > playerAt);
  assert.match(html, /Kapıya bakıyorum\./);
  assert.match(html, /Kapı kilitli\./);
  assert.match(html, /D20 8/);
  assert.match(html, /BAŞARISIZ/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /Yeni sonuç geldi\. 2/);
  assert.doesNotMatch(html, /autofocus|tabIndex=\{0\}|focus\(\)/);
});

test('play shell locks desktop viewports and allows scroll for narrow, short, and zoomed viewports', async () => {
  const css = await readFile('src/index.css', 'utf8');
  const play = css.slice(css.indexOf('.play-shell {'));
  assert.ok(play.startsWith('.play-shell {'));
  assert.match(play, /\.play-shell \.story-text \{ font-size: clamp\(1\.25rem, 1\.05rem \+ 0\.8vw, 1\.5rem\); \}/);
  assert.match(play, /\.play-shell \.player-entry \{ font-size: 1\.1875rem; \}/);
  assert.match(play, /\.play-shell \.command-input \{ font-size: 1\.3125rem; max-height: 8rem; min-width: 0; width: auto; flex: 1 1 auto; overflow-y: auto; \}/);
  assert.match(play, /\.play-shell \.command-form \{[^}]*flex-wrap: wrap/);
  assert.match(play, /\.play-shell \.command-form \.command-target-label \{ flex: 0 1 12rem; min-width: 0; max-width: 100%; \}/);
  assert.match(play, /@media \(max-width: 560px\) \{\s*\.play-shell \.command-form \{ display: block; \}/);
  assert.match(play, /\.play-shell \.transcript-scroll \{ flex: 1 1 auto; min-height: 8rem; max-height: 30dvh; overflow-y: auto; \}/);
  assert.match(play, /height: calc\(100dvh - var\(--keyboard-inset, 0px\)\)/);
  assert.doesNotMatch(play, /padding-bottom: var\(--keyboard-inset/);
  assert.match(play, /@media \(max-width: 1120px\), \(max-height: 699px\)/);
  assert.doesNotMatch(play, /\.play-shell \.transcript-scroll \{ overflow: visible/);
  assert.match(play, /\.play-shell \.drawer-trigger \{ display: inline-flex/);
  assert.match(play, /font-size: 0\.875rem/);
  assert.match(play, /min-height: 44px/);
  const viewport = await readFile('index.html', 'utf8');
  assert.match(viewport, /interactive-widget=resizes-content/);
  assert.doesNotMatch(viewport, /maximum-scale|user-scalable\s*=\s*no/);
  assert.doesNotMatch(play, /cc-point-buy|cc-method-tab|opening-screen|reveal-screen/);
  const creation = await readFile('src/components/character-creation-screen.css', 'utf8');
  assert.match(creation, /\.cc-point-buy-bar,\s*\.cc-roll-bar \{[^}]*background: rgba\(238, 228, 204, \.65\)/s);
});

test('the play screen fixture renders GameBrowser and does not touch auth', async () => {
  const fixture = await readFile('tests/play-screen-fixture/main.tsx', 'utf8');
  assert.match(fixture, /import GameBrowser from "@\/pages\/game-browser"/);
  assert.match(fixture, /ui-fixture-not-backend/);
  assert.doesNotMatch(fixture, /ClerkProvider|clerk-access|VITE_CLERK/);
  const app = await readFile('src/main.tsx', 'utf8');
  assert.match(app, /ClerkProvider/);
  assert.doesNotMatch(app, /play-screen-fixture/);
});

test('this package keeps the mode buttons and the existing turn submission path', async () => {
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(page, /data-testid="interaction-mode-selector"/);
  assert.match(page, /data-testid=\{`button-mode-\$\{mode\}`\}/);
  assert.match(page, /\['say', 'SÖYLE'\]/);
  assert.match(page, /\['do', 'YAP'\]/);
  assert.match(page, /\['ask_dm', 'ANLATICIYA SOR'\]/);
  assert.match(page, /getTurnInteractionMetadata\(/);
  assert.match(page, /action_id: actionId/);
  assert.match(page, /submitTurn\(message, undefined, interactionMode\)/);
  assert.match(page, /setInteractionMode\(suggestion\.mode\)/);
  assert.match(page, /event\.key === 'Escape'/);
  assert.match(page, /getElementById\('player-message'\)/);
  assert.doesNotMatch(page, /interaction_mode:\s*undefined/);
});


test('the final composer rule cannot cover the bounded story and scene regions', async () => {
  const css = await readFile('src/index.css', 'utf8');
  const rules = [...css.matchAll(/\.play-shell \.command-box\s*\{([^}]*)\}/g)];
  assert.ok(rules.length > 0);
  const positions = [...rules.at(-1)[1].matchAll(/(?:^|;)\s*position\s*:\s*([^;]+)/g)];
  assert.equal(positions.at(-1)?.[1].trim(), 'static');
  assert.match(css, /\.play-shell \.story-scene-context\s*\{[^}]*overflow-y:\s*auto/s);
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(page, /className="story-scene-context"[^>]*aria-label="Sahne bilgileri"/);
});

test('overflow stays inside the main region and the mobile composer can wrap', async () => {
  const css = await readFile('src/index.css', 'utf8');
  const main = [...css.matchAll(/\.play-shell \.app-main\.workspace-grid\s*\{([^}]*)\}/g)].at(-1)[1];
  assert.match(main, /overflow:\s*auto/);
  const form = [...css.matchAll(/\.play-shell \.command-form\s*\{([^}]*)\}/g)].at(-1)[1];
  assert.match(form, /display:\s*flex/);
  assert.match(form, /flex-wrap:\s*wrap/);
  assert.match(css, /\.play-shell \.app-header\s*\{[^}]*max-height:\s*20dvh[^}]*overflow-y:\s*auto/s);
  assert.match(css, /\.play-shell \.session-footnote\s*\{[^}]*max-height:\s*3\.5rem[^}]*overflow:\s*auto/s);
});


test('transcript follow-bottom ends at the answer rather than a decorative tail', () => {
  const html = renderTranscript([{ kind: 'narration', text: 'Son cevap tamamen okunmalı.' }]);
  assert.match(html, /aria-description="Sahne, kişiler ve öykü notları karakter ve dünya panellerinde"/);
  assert.doesNotMatch(html, /class="reader-note"/,
    'a trailing note must not push a short answer above the small transcript viewport');
  assert.match(html, /Son cevap tamamen okunmalı\.<\/p><\/div><\/div><\/div>$/);
});
