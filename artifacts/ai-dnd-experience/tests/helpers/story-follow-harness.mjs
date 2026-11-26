import assert from 'node:assert/strict';
import ts from 'typescript';
import { readGameBrowserSource } from './read-game-browser-source.mjs';
import { transcriptFollowsBottom } from '../../src/lib/play-viewport.ts';

// Execute the production callbacks with a deterministic layout-event queue.
// Regression trigger: only the scrolling viewport shrinks, before content RO.
export async function storyFollowHarness({ following = true } = {}) {
  const { runInNewContext } = await import('node:vm');
  const source = readGameBrowserSource();
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const declarations = new Map(); let resizeEffect, windowEffect;
  const visit = node => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) declarations.set(node.name.text, node.initializer?.getText(ast));
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect') {
      const body = node.arguments[0]?.getText(ast) ?? '';
      if (body.includes('new ResizeObserver')) resizeEffect = body;
      if (body.includes("window.addEventListener('scroll', handleStoryScroll")) windowEffect = body;
    }
    ts.forEachChild(node, visit);
  }; visit(ast);
  assert.ok(resizeEffect && windowEffect);
  const trace = []; const observed = new Set(); let resizeCallback;
  const content = {}; let top = 200;
  const node = { clientHeight: 220, clientWidth: 375, scrollHeight: 420,
    get scrollTop() { return top; },
    set scrollTop(value) { top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); trace.push(['follow', top]); },
    querySelector() { return content; }, getBoundingClientRect() { return { bottom: 420 }; },
    listeners: {}, addEventListener(type, callback) { this.listeners[type] = callback; }, removeEventListener() {} };
  const clock = { now: 10_000 };
  const window = { innerHeight: 812, addEventListener(_, callback) { this.scroll = callback; }, removeEventListener() {} };
  const context = { storyScrollRef: { current: node }, wasAtBottom: { current: following }, storyLayoutRef: { current: null }, storyLayoutScrollTopRef: { current: null },
    readerInputAt: { current: -Infinity }, performance: { now: () => clock.now },
    window, getComputedStyle: () => ({ overflowY: 'auto' }), transcriptFollowsBottom,
    setNewResponseEntryIndex() {}, setResultCue() {},
    ResizeObserver: class { constructor(callback) { resizeCallback = callback; } observe(target) { observed.add(target); } disconnect() { observed.clear(); } } };
  const names = ['readStoryLayout', 'readerIsScrolling', 'isStoryNearBottom', 'scrollStoryToBottom', 'layoutExplainsPosition', 'handleStoryScroll'];
  const code = names.filter(name => declarations.has(name)).map(name => `const ${name} = ${declarations.get(name)};`).join('\n')
    + `\n(${resizeEffect})(); (${windowEffect})(); globalThis.scroll = handleStoryScroll;`;
  runInNewContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
  return { node, context, trace,
    resize(height, width = node.clientWidth, contentHeight = node.scrollHeight, scrollFirst = false) {
      node.clientHeight = height; node.clientWidth = width; node.scrollHeight = contentHeight;
      trace.push(['resize', height, width, contentHeight]);
      if (node.scrollTop > Math.max(0, contentHeight - height)) node.scrollTop = Math.max(0, contentHeight - height);
      if (scrollFirst) { trace.push(['layout-scroll']); context.scroll({ currentTarget: node }); }
      if (observed.has(node) || (contentHeight !== 420 && observed.has(content))) { trace.push(['observer']); resizeCallback([]); }
    },
    userScroll(top) { node.scrollTop = top; context.scroll({ currentTarget: node }); },
    readerInput(type = 'wheel') { node.listeners[type](); },
    wait(ms) { clock.now += ms; },
    documentScroll() { window.scroll({ currentTarget: window }); },
  };
}
