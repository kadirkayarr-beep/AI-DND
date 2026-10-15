import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4181';
process.env.BASE_PATH ||= '/oyun/';

let vite;
let React;
let renderToStaticMarkup;
let NotFound;

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  ({ default: NotFound } = await vite.ssrLoadModule('/src/pages/not-found.tsx'));
  React = await import('react');
  ({ renderToStaticMarkup } = await import('react-dom/server'));
});

after(async () => {
  if (vite) await vite.close();
});

test('unknown route uses Turkish copy and links to the configured app base', () => {
  const html = renderToStaticMarkup(React.createElement(NotFound));
  assert.ok(html.includes('Bu sayfa bulunamadı.'));
  assert.ok(html.includes('Aradığın kapı bu yolda yok.'));
  assert.ok(html.includes('Ana ekrana dön'));
  assert.ok(html.includes('href="/oyun/"'));
  assert.ok(!html.includes('Page Not Found'));
  assert.ok(!html.includes('Did you forget'));
});
