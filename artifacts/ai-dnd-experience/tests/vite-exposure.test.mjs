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

test('the isolated API proxy strips only the approved Replit identity header when enabled', async () => {
  const previous = {
    PORT: process.env.PORT,
    BASE_PATH: process.env.BASE_PATH,
    REPL_ID: process.env.REPL_ID,
    AI_DND_API_ORIGIN: process.env.AI_DND_API_ORIGIN,
    AI_DND_F03_P03_STRIP_REPLIT_ID: process.env.AI_DND_F03_P03_STRIP_REPLIT_ID,
  };
  const restore = () => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  };
  const loadProxy = async (port, stripReplitId) => {
    process.env.PORT = String(port);
    process.env.BASE_PATH = '/';
    process.env.AI_DND_API_ORIGIN = 'http://127.0.0.1:8017';
    if (stripReplitId === undefined) delete process.env.AI_DND_F03_P03_STRIP_REPLIT_ID;
    else process.env.AI_DND_F03_P03_STRIP_REPLIT_ID = stripReplitId;
    // Avoid loading Replit-only optional plugins in this isolated config test.
    delete process.env.REPL_ID;
    const { loadConfigFromFile } = await import('vite');
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode: 'development' },
      path.join(process.cwd(), 'vite.config.ts'),
    );
    assert.equal(loaded.config.server.proxy['/api'].target, 'http://127.0.0.1:8017');
    let proxyReqHandler;
    loaded.config.server.proxy['/api'].configure({
      on(event, handler) {
        if (event === 'proxyReq') proxyReqHandler = handler;
      },
    });
    assert.equal(typeof proxyReqHandler, 'function');
    const headers = new Map([
      ['cookie', 'private-preview-cookie'],
      ['x-replit-user-id', 'preview-user'],
      ['authorization', 'Bearer clerk-test-token'],
    ]);
    const removed = [];
    proxyReqHandler({
      removeHeader(name) {
        removed.push(name);
        headers.delete(name);
      },
    });
    assert.equal(headers.get('authorization'), 'Bearer clerk-test-token');
    assert.equal(headers.has('cookie'), false);
    return { removed, headers };
  };

  try {
    const enabled = await loadProxy(22886, '1');
    assert.deepEqual(enabled.removed, ['cookie', 'x-replit-user-id']);
    assert.equal(enabled.headers.has('x-replit-user-id'), false);

    const disabled = await loadProxy(22886, undefined);
    assert.deepEqual(disabled.removed, ['cookie']);
    assert.equal(disabled.headers.get('x-replit-user-id'), 'preview-user');

    const wrongPort = await loadProxy(4194, '1');
    assert.deepEqual(wrongPort.removed, ['cookie']);
    assert.equal(wrongPort.headers.get('x-replit-user-id'), 'preview-user');
  } finally {
    restore();
  }
});
