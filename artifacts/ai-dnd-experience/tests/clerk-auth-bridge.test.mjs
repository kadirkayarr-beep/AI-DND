import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, test } from 'node:test';
import {
  ApiRequestError,
  classifyApiDestination,
  customFetch,
  currentAuthEpoch,
  rotateAuthEpoch,
  setAuthTokenGetter,
  setBaseUrl,
} from '@workspace/api-client-react/custom-fetch';
import {
  accountWriteAllowed,
  clearAccountBrowserState,
  clerkSessionIdentity,
  createAccountQueryClient,
  nextAccountClient,
  readClerkToken,
} from '../src/lib/account-session.ts';

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
const consoleMethods = ['log', 'info', 'debug', 'warn', 'error'];
const originalConsole = Object.fromEntries(consoleMethods.map((method) => [method, console[method]]));

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    get length() { return map.size; },
    key(index) { return [...map.keys()][index] ?? null; },
    getItem(key) { return map.has(key) ? map.get(key) : null; },
    setItem(key, value) { map.set(String(key), String(value)); },
    removeItem(key) { map.delete(key); },
  };
}

function installWindow(origin = 'http://127.0.0.1:5173') {
  const localStorage = memoryStorage({
    'ai-dnd-transcript-old': 'once upon a time',
    'ai-dnd-last-selected-campaign-id': 'campaign-old',
    'ai-dnd-ui-sound-muted': '1',
    'ai-dnd-ui-sound-volume': '0.2',
  });
  const sessionStorage = memoryStorage({
    'ai-dnd-pending-turns:scope': '{"walk":"action-old"}',
    'ai-dnd-turn-context:scope:action-old': '{}',
  });
  globalThis.window = { location: { origin }, localStorage, sessionStorage };
  return { localStorage, sessionStorage };
}

function jsonResponse(body = { ok: true }, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

afterEach(() => {
  setAuthTokenGetter(null);
  setBaseUrl(null);
  globalThis.fetch = originalFetch;
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  for (const method of consoleMethods) console[method] = originalConsole[method];
});

test('Clerk loading and signed-out sessions do not expose an account identity', () => {
  assert.equal(clerkSessionIdentity({ isLoaded: false, isSignedIn: true, userId: 'user-a', sessionId: 'sess-a' }), '');
  assert.equal(clerkSessionIdentity({ isLoaded: true, isSignedIn: false, userId: 'user-a', sessionId: 'sess-a' }), '');
  assert.equal(clerkSessionIdentity({ isLoaded: true, isSignedIn: true, userId: '', sessionId: 'sess-a' }), '');
  assert.equal(clerkSessionIdentity({ isLoaded: true, isSignedIn: true, userId: 'user-a', sessionId: null }), '');
  const first = clerkSessionIdentity({ isLoaded: true, isSignedIn: true, userId: 'user-a', sessionId: 'sess-a' });
  const second = clerkSessionIdentity({ isLoaded: true, isSignedIn: true, userId: 'user-b', sessionId: 'sess-b' });
  assert.equal(first, 'user-a:sess-a');
  assert.notEqual(first, second);
});

test('a fresh Clerk token is attached only to an approved same-origin API request', async () => {
  installWindow();
  const secret = 'fresh-session-token';
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    calls += 1;
    const headers = new Headers(init.headers);
    assert.equal(headers.get('authorization'), `Bearer ${secret}`);
    assert.equal(headers.get('cookie'), null);
    assert.equal(init.credentials, 'omit');
    assert.equal(init.redirect, 'error');
    assert.equal(headers.get('x-ai-dnd-request'), '1');
    assert.equal(String(input).includes(secret), false);
    return jsonResponse({ campaigns: [] });
  };
  setAuthTokenGetter(async () => secret);
  const body = await customFetch('/api/campaigns?access_token=sekret&ok=1', { method: 'POST', body: '{}' });
  assert.deepEqual(body, { campaigns: [] });
  assert.equal(calls, 1);
});

test('public catalogs and unexpected destinations do not receive a bearer token', async () => {
  installWindow();
  let getterCalls = 0;
  const seen = [];
  globalThis.fetch = async (input, init) => {
    seen.push({ url: String(input), authorization: new Headers(init.headers).get('authorization') });
    return jsonResponse({ options: [] });
  };
  setAuthTokenGetter(async () => {
    getterCalls += 1;
    return 'fresh-session-token';
  });

  await customFetch('/api/character-options');
  await customFetch('/api/health');
  await customFetch('/api/logout', { method: 'POST' });
  await customFetch('https://example.test/collect', { headers: { Authorization: 'Bearer fresh-session-token' } });

  assert.equal(getterCalls, 0);
  assert.deepEqual(seen.map((entry) => entry.authorization), [null, null, null, null]);
  assert.equal(seen.some((entry) => entry.url.includes('fresh-session-token')), false);

  let protectedCalls = 0;
  globalThis.fetch = async () => {
    protectedCalls += 1;
    return jsonResponse();
  };
  await assert.rejects(
    () => customFetch('https://evil.test/api/campaigns'),
    (error) => error instanceof ApiRequestError && error.code === 'unapproved_destination',
  );
  await assert.rejects(
    () => customFetch('http://127.0.0.1:8008/api/campaigns'),
    (error) => error instanceof ApiRequestError && error.code === 'unapproved_destination',
  );
  setBaseUrl('https://evil.example');
  await assert.rejects(
    () => customFetch('/api/campaigns'),
    (error) => error instanceof ApiRequestError && error.code === 'unapproved_destination',
  );
  assert.equal(protectedCalls, 0);
  assert.equal(classifyApiDestination('/api/game/character-creation-catalog'), 'public');
  assert.equal(classifyApiDestination('/api/game/sessions/session/turn'), 'protected');
  assert.equal(classifyApiDestination('http://127.0.0.1:5173/api/campaigns'), 'protected');
});

test('a missing or expired token does not send a protected campaign request', async () => {
  installWindow();
  const logs = [];
  for (const method of consoleMethods) {
    console[method] = (...args) => logs.push(args.join(' '));
  }
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse();
  };
  const secret = 'expired-session-token';
  setAuthTokenGetter(async () => null);
  await assert.rejects(
    () => customFetch('/api/campaigns', { method: 'POST', body: '{"name":"macera"}' }),
    (error) => {
      assert.equal(error instanceof ApiRequestError, true);
      assert.equal(error.code, 'authentication_required');
      assert.equal(String(error.message).includes(secret), false);
      assert.equal(String(error.message).includes('token'), false);
      return true;
    },
  );
  setAuthTokenGetter(async () => {
    throw new Error(secret);
  });
  await assert.rejects(() => customFetch('/api/campaigns'));
  setAuthTokenGetter(async () => ` ${secret}`);
  await assert.rejects(() => customFetch('/api/campaigns'));
  assert.equal(calls, 0);
  assert.equal(logs.some((line) => line.includes(secret)), false);
});

test('logout and account switching isolate cache, storage, and in-flight results', async () => {
  const { localStorage, sessionStorage } = installWindow();
  const logs = [];
  for (const method of consoleMethods) {
    console[method] = (...args) => logs.push(args.join(' '));
  }
  const first = nextAccountClient(null, 'user-a:sess-a');
  localStorage.setItem('ai-dnd-transcript-old', 'once upon a time');
  localStorage.setItem('ai-dnd-last-selected-campaign-id', 'campaign-old');
  sessionStorage.setItem('ai-dnd-pending-turns:scope', '{"walk":"action-old"}');
  sessionStorage.setItem('ai-dnd-turn-context:scope:action-old', '{}');
  first.client.setQueryData(['campaigns'], ['campaign-a']);
  assert.deepEqual(first.client.getQueryData(['campaigns']), ['campaign-a']);
  let release = () => {};
  let markStarted = () => {};
  const fetchStarted = new Promise((resolve) => { markStarted = resolve; });
  globalThis.fetch = (_input, init) => new Promise((resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    release = () => resolve(jsonResponse({ campaign: 'campaign-a', narration: 'secret-story' }));
    markStarted();
  });
  setAuthTokenGetter(async () => 'token-a');
  const pending = customFetch('/api/game/sessions/session-a/turn', {
    method: 'POST',
    body: '{"message":"yürü","action_id":"action-a"}',
  });
  await fetchStarted;
  const second = nextAccountClient(first, 'user-b:sess-b');
  release();
  await assert.rejects(pending, (error) => error instanceof ApiRequestError && error.code === 'authentication_changed');
  first.client.setQueryData(['campaigns'], ['leaked-into-a']);
  assert.equal(first.client.getQueryData(['campaigns']), undefined);
  assert.equal(second.client.getQueryData(['campaigns']), undefined);
  second.client.setQueryData(['campaigns'], ['campaign-b']);
  assert.deepEqual(second.client.getQueryData(['campaigns']), ['campaign-b']);
  assert.equal(localStorage.getItem('ai-dnd-transcript-old'), null);
  assert.equal(localStorage.getItem('ai-dnd-last-selected-campaign-id'), null);
  assert.equal(sessionStorage.getItem('ai-dnd-pending-turns:scope'), null);
  assert.equal(sessionStorage.getItem('ai-dnd-turn-context:scope:action-old'), null);
  assert.equal(localStorage.getItem('ai-dnd-ui-sound-muted'), '1');
  assert.equal(localStorage.getItem('ai-dnd-ui-sound-volume'), '0.2');
  assert.equal(accountWriteAllowed(currentAuthEpoch() - 1), false);
  clearAccountBrowserState();
  setAuthTokenGetter(null);
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse();
  };
  await assert.rejects(() => customFetch('/api/campaigns'));
  assert.equal(calls, 0);
  assert.equal(logs.some((line) => line.includes('token-a') || line.includes('secret-story')), false);
});

test('authentication failures do not replay a gameplay request', async () => {
  installWindow();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse({ detail: { message: 'Kimlik doğrulaması gerekli.' } }, 401);
  };
  setAuthTokenGetter(async () => 'fresh-session-token');
  const client = createAccountQueryClient();
  assert.equal(client.getDefaultOptions().mutations.retry, false);
  const retry = client.getDefaultOptions().queries.retry;
  assert.equal(typeof retry, 'function');
  assert.equal(retry(0, new ApiRequestError('authentication_required')), false);
  assert.equal(retry(0, new ApiRequestError('authentication_changed')), false);
  assert.equal(retry(0, { status: 401 }), false);
  assert.equal(retry(0, new Error('network')), true);
  assert.equal(retry(3, new Error('network')), false);
  await assert.rejects(() => customFetch('/api/game/sessions/session/turn', {
    method: 'POST',
    body: '{"message":"yürü","action_id":"action-1"}',
  }));
  assert.equal(calls, 1);
});

test('a token that expires while it is being read is not sent', async () => {
  installWindow();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse();
  };
  let finish = () => {};
  const pendingToken = readClerkToken(
    () => new Promise((resolve) => { finish = () => resolve('late-token'); }),
    () => false,
  );
  finish();
  assert.equal(await pendingToken, null);
  setAuthTokenGetter(async () => {
    rotateAuthEpoch();
    return 'late-token';
  });
  await assert.rejects(
    () => customFetch('/api/campaigns'),
    (error) => error instanceof ApiRequestError && error.code === 'authentication_changed',
  );
  assert.equal(calls, 0);
});

test('the signed-in shell waits for Clerk and does not persist session tokens', async () => {
  const [access, session, app] = await Promise.all([
    readFile(new URL('../src/components/clerk-access.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/clerk-api-session.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/App.tsx', import.meta.url), 'utf8'),
  ]);
  assert.match(access, /ClerkLoading/);
  assert.match(access, /Kapılar açılıyor\.\.\./);
  assert.match(access, /Macera seni bekliyor\./);
  assert.match(access, /<ClerkApiSession>/);
  assert.match(session, /getToken/);
  assert.match(session, /Kapılar açılıyor\.\.\./);
  assert.doesNotMatch(session, /localStorage|sessionStorage|SECRET|console\./);
  assert.doesNotMatch(app, /new QueryClient/);
});
