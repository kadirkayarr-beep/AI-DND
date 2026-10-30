// Local play: only the dev server, only on loopback, and the Clerk entry stays the default.
import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { afterEach, test } from 'node:test';
import {
  customFetch,
  setAuthTokenGetter,
  setProtectedRequestCredentials,
} from '@workspace/api-client-react/custom-fetch';
import { startLocalPlaySession } from '../src/lib/local-play-session.ts';

const ENV_KEYS = [
  'PORT', 'BASE_PATH', 'REPL_ID', 'REPLIT_DEPLOYMENT', 'REPLIT_DEV_DOMAIN', 'REPLIT_DOMAINS',
  'REPLIT_APP_DOMAIN', 'NODE_ENV', 'AI_DND_ALLOWED_HOSTS', 'VITE_AI_DND_LOCAL_PLAY',
];

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  setAuthTokenGetter(null);
  setProtectedRequestCredentials('omit');
});

async function loadConfig(env, configEnv = { command: 'serve', mode: 'development' }) {
  const previous = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
  for (const key of ENV_KEYS) delete process.env[key];
  Object.assign(process.env, { PORT: '4193', BASE_PATH: '/ai-dnd-experience/' }, env);
  try {
    const { loadConfigFromFile } = await import('vite');
    return (await loadConfigFromFile(configEnv, path.join(process.cwd(), 'vite.config.ts'))).config;
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

function localPlayPlugin(config) {
  return config.plugins.flat().find((plugin) => plugin?.name === 'ai-dnd-local-play');
}

const HTML = '<script type="module" src="/src/main.tsx"></script>';

test('off by default: no local plugin and the page keeps the Clerk entry', async () => {
  const config = await loadConfig({});
  assert.equal(localPlayPlugin(config), undefined);
  for (const value of ['0', 'true', 'yes', '', ' 1']) {
    assert.equal(localPlayPlugin(await loadConfig({ VITE_AI_DND_LOCAL_PLAY: value })), undefined, value);
  }
  const page = await readFile('index.html', 'utf8');
  assert.match(page, /src="\/src\/main\.tsx"/);
});

test('local play swaps the entry and pins the dev server to loopback hosts', async () => {
  const config = await loadConfig({
    VITE_AI_DND_LOCAL_PLAY: '1',
    AI_DND_ALLOWED_HOSTS: 'evil.example,tunnel.example',
  });
  assert.equal(config.server.host, '127.0.0.1');
  assert.deepEqual(config.server.allowedHosts, ['localhost', '127.0.0.1']);
  const plugin = localPlayPlugin(config);
  const html = plugin.transformIndexHtml.handler(HTML);
  assert.equal(html, '<script type="module" src="/src/local-play-main.tsx"></script>');
  assert.doesNotThrow(() => plugin.config({}, { command: 'serve', mode: 'development' }));
});

test('local play never reaches a build or a preview', async () => {
  const plugin = localPlayPlugin(await loadConfig({ VITE_AI_DND_LOCAL_PLAY: '1' }));
  assert.throws(() => plugin.config({}, { command: 'build', mode: 'production' }), /local play/i);
  assert.throws(
    () => plugin.config({}, { command: 'serve', mode: 'production', isPreview: true }),
    /local play/i,
  );
  assert.equal(plugin.apply, undefined);
});

test('a hosted or production environment refuses to start the mode', async () => {
  for (const marker of [
    { REPL_ID: 'abc' },
    { REPLIT_DEPLOYMENT: '1' },
    { REPLIT_DEV_DOMAIN: 'x.replit.dev' },
    { REPLIT_DOMAINS: 'x.replit.app' },
    { REPLIT_APP_DOMAIN: 'x.replit.app' },
    { NODE_ENV: 'production' },
  ]) {
    await assert.rejects(
      loadConfig({ VITE_AI_DND_LOCAL_PLAY: '1', ...marker }),
      /local play/i,
      JSON.stringify(marker),
    );
  }
});

test('the local entry reaches the app shell without any Clerk module', async () => {
  const seen = new Set();
  const visit = async (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const source = await readFile(file, 'utf8');
    const imports = [...source.matchAll(/^\s*(?:import|export)\s[^;]*?from\s+"([^"]+)"/gm)].map((match) => match[1]);
    assert.ok(!imports.some((name) => /clerk/i.test(name)), `${file} imports Clerk`);
    for (const name of imports) {
      if (name === './App' || name === '@/App') throw new Error(`${file} imports the Clerk app`);
      if (['@/components/clerk-access', '@/components/clerk-api-session'].includes(name)) {
        throw new Error(`${file} imports the Clerk gate`);
      }
    }
  };
  await visit('src/local-play-main.tsx');
  await visit('src/app-shell.tsx');
  await visit('src/lib/local-play-session.ts');
  const clerkApp = await readFile('src/App.tsx', 'utf8');
  assert.match(clerkApp, /<ClerkAccess>/);
  assert.match(clerkApp, /<AppShell \/>/);
});

test('the session sends the non-secret placeholder, the marker and no cookie mode', async () => {
  globalThis.window = { location: { origin: 'http://127.0.0.1:22785' } };
  const boundary = startLocalPlaySession();
  assert.equal(boundary.identity, 'local-owner:local-play');
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } });
  };
  await customFetch('/api/game/campaigns', { method: 'POST', body: '{}' });
  assert.equal(calls.length, 1);
  const headers = new Headers(calls[0].init.headers);
  assert.equal(headers.get('authorization'), 'Bearer local-play');
  assert.equal(headers.get('x-ai-dnd-request'), '1');
  assert.equal(calls[0].init.credentials, 'omit');
  await boundary.client.cancelQueries();
  boundary.client.clear();
});
