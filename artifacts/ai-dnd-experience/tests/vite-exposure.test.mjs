import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

test('local Vite and preview listen on loopback and disallow arbitrary hosts', async () => {
  const previous = { PORT: process.env.PORT, BASE_PATH: process.env.BASE_PATH, REPL_ID: process.env.REPL_ID };
  process.env.PORT = '4192';
  process.env.BASE_PATH = '/';
  delete process.env.REPL_ID;
  try {
    const { loadConfigFromFile } = await import('vite');
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode: 'development' },
      path.join(process.cwd(), 'vite.config.ts'),
    );
    assert.ok(loaded);
    assert.equal(loaded.config.server.host, '127.0.0.1');
    assert.equal(loaded.config.preview.host, '127.0.0.1');
    assert.notEqual(loaded.config.server.allowedHosts, true);
    assert.notEqual(loaded.config.preview.allowedHosts, true);
    const pkg = JSON.parse(await readFile('package.json', 'utf8'));
    assert.doesNotMatch(pkg.scripts.dev, /--host/);
    assert.doesNotMatch(pkg.scripts.serve, /--host/);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});

test('Replit keeps its required public listener but only trusts named hosts', async () => {
  const previous = {
    PORT: process.env.PORT, BASE_PATH: process.env.BASE_PATH,
    REPL_ID: process.env.REPL_ID, REPLIT_DEV_DOMAIN: process.env.REPLIT_DEV_DOMAIN,
  };
  process.env.PORT = '4193';
  process.env.BASE_PATH = '/';
  process.env.REPL_ID = 'test-repl';
  process.env.REPLIT_DEV_DOMAIN = 'test-app.replit.dev';
  try {
    const { loadConfigFromFile } = await import('vite');
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode: 'development' },
      path.join(process.cwd(), 'vite.config.ts'),
    );
    assert.equal(loaded.config.server.host, '0.0.0.0');
    assert.ok(loaded.config.server.allowedHosts.includes('test-app.replit.dev'));
    assert.notEqual(loaded.config.server.allowedHosts, true);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
