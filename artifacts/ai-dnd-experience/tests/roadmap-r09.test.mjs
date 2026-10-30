// R09: the real shell -> HTTP -> identity-boundary chain, in a real browser against a real (temporary) backend.
//
// What is REAL here: headless Chrome, the real GameBrowser inside the real account-boundary helpers, real HTTP over
// loopback through the Vite proxy, the real FastAPI app, SessionManager and SQLite store (a temporary file).
// What is NOT real: the identity. The backend runs FixedAuthenticator and the page uses a fixture token; Clerk is not
// involved and the evidence says so (real_identity: false). The real-Clerk layer is reported BLOCKED, never mocked as accepted.
//
// Opt-in (spawns Python, Vite and Chrome): R09_LIVE=1, CHROMIUM_PATH and R09_PYTHON (or R02_PYTHON) as absolute paths.
// Never touches port 8008, the real game or any personal save: it uses its own temporary database and loopback ports.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { mkdtemp, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

const live = process.env.R09_LIVE === "1";
const chromiumPath = process.env.CHROMIUM_PATH;
const python = process.env.R09_PYTHON ?? process.env.R02_PYTHON;
if (live) {
  if (!chromiumPath || !path.isAbsolute(chromiumPath)) throw new Error("CHROMIUM_PATH must be an absolute executable path");
  await stat(chromiumPath);
  if (!python || !path.isAbsolute(python)) throw new Error("R09_PYTHON (or R02_PYTHON) must be an absolute interpreter path");
  await stat(python);
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitFor(url, json = false, attempts = 300) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return json ? response.json() : response;
    } catch { /* not up yet */ }
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

class CdpPage {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data.toString());
      if (message.method) for (const listener of this.listeners.get(message.method) ?? []) void listener(message.params);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      }
    });
  }
  on(method, listener) { this.listeners.set(method, [...(this.listeners.get(method) ?? []), listener]); }
  async send(method, params = {}) {
    await this.ready;
    const id = ++this.nextId;
    const result = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    this.socket.send(JSON.stringify({ id, method, params }));
    return result;
  }
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(`${result.exceptionDetails.text}: ${result.exceptionDetails.exception?.description ?? ""}`);
    return result.result.value;
  }
  async until(expression, label, attempts = 200) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (await this.evaluate(expression).catch(() => false)) return;
      await delay(100);
    }
    const body = await this.evaluate("document.body.innerText").catch(() => "(unreadable)");
    assert.fail(`Timed out waiting for ${label}. Page text: ${String(body).slice(0, 700).replace(/\s+/g, " ")}`);
  }
  close() { this.socket.close(); }
}

const sel = (testid) => `document.querySelector('[data-testid="${testid}"]')`;
const hasNotice = (text) => `[...document.querySelectorAll('.notice')].some((n) => n.innerText.includes(${JSON.stringify(text)}))`;
const playScreen = `(!!${sel("input-player-message")} || !!${sel("button-open-composer")})`;

async function sendMove(page, text) {
  await page.until(playScreen, "play screen");
  if (await page.evaluate(`!${sel("input-player-message")} && !!${sel("button-open-composer")}`)) {
    await page.evaluate(`${sel("button-open-composer")}.click()`);
  }
  await page.until(`!!${sel("input-player-message")} && !${sel("input-player-message")}.disabled`, "composer ready");
  await page.evaluate(`${sel("input-player-message")}.focus()`);
  await page.send("Input.insertText", { text });
  await page.until(`!${sel("button-send-turn")}.disabled`, "send enabled");
  await page.evaluate(`${sel("button-send-turn")}.click()`);
}

const pendingSlots = (page) => page.evaluate("Object.keys(sessionStorage).filter((k) => k.startsWith('ai-dnd-pending-turns:action:'))");
const readSlot = (page, key) => page.evaluate(`JSON.parse(sessionStorage.getItem(${JSON.stringify(key)}) ?? "null")`);

// Records the real HTTP exchanges the browser made (method, path, status, and turn action ids).
function traceHttp(page, trace) {
  page.on("Network.requestWillBeSent", (event) => {
    const url = new URL(event.request.url);
    if (!url.pathname.startsWith("/api/")) return;
    let actionId;
    if (/\/turn$/.test(url.pathname) && event.request.postData) {
      try { actionId = JSON.parse(event.request.postData).action_id; } catch { /* not JSON */ }
    }
    trace.push({ requestId: event.requestId, method: event.request.method, host: url.hostname, path: url.pathname, actionId });
  });
  page.on("Network.responseReceived", (event) => {
    const entry = trace.find((item) => item.requestId === event.requestId);
    if (entry) entry.status = event.response.status;
  });
  page.on("Network.loadingFailed", (event) => {
    const entry = trace.find((item) => item.requestId === event.requestId);
    if (entry) entry.status = `failed:${event.errorText}`;
  });
}

test("R09 chain: lost reply + reload keeps one effect and the same receipt; an old account's late reply cannot regress the new one",
  { timeout: 360_000, skip: live ? false : "set R09_LIVE=1 (needs CHROMIUM_PATH and an absolute R09_PYTHON/R02_PYTHON)" }, async (t) => {
    const workdir = await mkdtemp(path.join(os.tmpdir(), "r09-live-"));
    const [backendPort, vitePort] = [await freePort(), await freePort()];
    const externalBrowser = Boolean(process.env.R09_BROWSER_PORT);
    const browserPort = externalBrowser ? Number(process.env.R09_BROWSER_PORT) : await freePort();
    const backendOrigin = `http://127.0.0.1:${backendPort}`;
    const backendLog = [];
    const backend = spawn(python, [path.join(process.cwd(), "tests", "r02-live-backend", "serve.py"), String(backendPort)], {
      env: { ...process.env, AI_DND_CAMPAIGN_DB: path.join(workdir, "campaigns.sqlite3") }, stdio: ["ignore", "pipe", "pipe"],
    });
    backend.stdout.on("data", (chunk) => backendLog.push(String(chunk)));
    backend.stderr.on("data", (chunk) => backendLog.push(String(chunk)));
    const require = createRequire(import.meta.url);
    const viteCli = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
    const vite = spawn(process.execPath, [viteCli, "--config", "vite.config.ts", "--host", "127.0.0.1"], {
      cwd: process.cwd(), env: { ...process.env, PORT: String(vitePort), BASE_PATH: "/", REPL_ID: undefined, AI_DND_API_ORIGIN: backendOrigin }, stdio: "ignore",
    });
    const browser = externalBrowser ? null : spawn(chromiumPath, [
      "--headless=new", "--disable-gpu", "--disable-dev-shm-usage", `--remote-debugging-port=${browserPort}`,
      `--user-data-dir=${path.join(workdir, "chrome-profile")}`, "about:blank",
    ], { stdio: "ignore" });
    t.after(async () => {
      for (const child of [backend, vite, browser]) {
        if (child && child.exitCode === null) {
          child.kill();
          await Promise.race([new Promise((resolve) => child.once("exit", resolve)), delay(4000)]);
        }
      }
      await rm(workdir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    });

    try { await waitFor(`${backendOrigin}/api/game/health`); } catch (error) { assert.fail(`${error.message}\nbackend output: ${backendLog.join("").slice(-800)}`); }
    const created = await fetch(`${backendOrigin}/api/game/campaigns`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    assert.equal(created.status, 200);
    const campaign = (await created.json()).campaign_id;
    const backendGet = (p) => fetch(`${backendOrigin}${p}`).then((r) => r.json());
    const history = async () => (await backendGet(`/api/game/campaigns/${campaign}`)).history.map((entry) => entry.player_message);
    const base = `http://127.0.0.1:${vitePort}`;
    await waitFor(`${base}/tests/r09-fixture/`);
    const version = await waitFor(`http://127.0.0.1:${browserPort}/json/version`, true, 1200);
    const url = `${base}/tests/r09-fixture/?campaign=${campaign}`;

    const open = async () => {
      const target = await fetch(`http://127.0.0.1:${browserPort}/json/new?${encodeURIComponent(url)}`, { method: "PUT" }).then((r) => r.json());
      const page = new CdpPage(target.webSocketDebuggerUrl);
      await page.send("Page.enable");
      await page.send("Runtime.enable");
      await page.send("Network.enable");
      await page.send("Emulation.setDeviceMetricsOverride", { width: 1100, height: 900, deviceScaleFactor: 1, mobile: false });
      return page;
    };

    const trace = [];
    const layers = {};

    // ---- Chain 1: the reply is lost, the page reloads (same owner), the retry replays one receipt --------------------
    const a = await open();
    traceHttp(a, trace);
    let sessionId = "";
    let dropNextReply = false;
    await a.send("Fetch.enable", { patterns: [{ urlPattern: "*/api/game/sessions/*/turn", requestStage: "Response" }] });
    a.on("Fetch.requestPaused", async (paused) => {
      const match = /sessions\/([^/]+)\/turn/.exec(paused.request.url);
      if (match) sessionId = match[1];
      if (dropNextReply && match) {
        dropNextReply = false;
        await a.send("Fetch.failRequest", { requestId: paused.requestId, errorReason: "ConnectionReset" });
      } else {
        await a.send("Fetch.continueResponse", { requestId: paused.requestId });
      }
    });
    await a.until(playScreen, "play screen", 600);
    dropNextReply = true;
    await sendMove(a, "ilk hamle");
    await a.until(hasNotice("sonuçlanamadı"), "lost-reply notice");
    assert.deepEqual(await history(), ["ilk hamle"], "the server committed the move whose reply was lost");
    const [slot] = await pendingSlots(a);
    const pending = await readSlot(a, slot);
    assert.ok(pending?.actionId, "the unresolved move is stored for this owner and campaign");
    const receiptBefore = await backendGet(`/api/game/sessions/${sessionId}/actions/${pending.actionId}`);
    assert.equal(receiptBefore.state, "applied");

    await a.send("Page.reload"); // a real reload: new JS realm, same sessionStorage, the account boundary mounts again
    await a.until(playScreen, "play screen after reload", 600);
    await a.until(`!!${sel("button-retry-turn")}`, "retry offered after reload", 300);
    await a.evaluate(`${sel("button-retry-turn")}.click()`);
    await a.until(`${JSON.stringify(slot)} && sessionStorage.getItem(${JSON.stringify(slot)}) === null`, "pending closed after the receipt replay", 300);
    const turnPosts = trace.filter((item) => item.method === "POST" && item.actionId);
    assert.ok(turnPosts.length >= 2, "the move was sent before and after the reload");
    assert.equal(new Set(turnPosts.map((item) => item.actionId)).size, 1, "both sends carry the SAME action id");
    assert.deepEqual(await history(), ["ilk hamle"], "one effect only");
    const receiptAfter = await backendGet(`/api/game/sessions/${sessionId}/actions/${pending.actionId}`);
    const digest = (value) => createHash("sha256").update(JSON.stringify(value.response)).digest("hex");
    assert.equal(digest(receiptAfter), digest(receiptBefore), "the same stored receipt, byte for byte");
    layers.lost_reply_reload_same_owner = "PASS";
    a.close();

    // ---- Chain 2: an account change while a reply is still in flight --------------------------------------------------
    const b = await open();
    traceHttp(b, trace);
    let held = null;
    await b.send("Fetch.enable", { patterns: [{ urlPattern: "*/api/game/sessions/*/turn", requestStage: "Response" }] });
    let holdNext = true;
    b.on("Fetch.requestPaused", async (paused) => {
      const match = /sessions\/([^/]+)\/turn/.exec(paused.request.url);
      if (match) sessionId = match[1];
      if (holdNext && match) { holdNext = false; held = paused.requestId; return; } // never answered until released
      await b.send("Fetch.continueResponse", { requestId: paused.requestId });
    });
    await b.until(playScreen, "play screen in tab B", 600);
    await sendMove(b, "eski hesap hamlesi");
    for (let attempt = 0; attempt < 100 && !(await history()).includes("eski hesap hamlesi"); attempt += 1) await delay(100);
    assert.ok((await history()).includes("eski hesap hamlesi"), "the server committed the held move");
    assert.ok(held, "its reply is being held in the browser");

    await b.evaluate(`window.__r09.setSession(${JSON.stringify(sessionId)}); window.__r09.switchIdentity("owner-b:session-2")`);
    await b.evaluate("window.__r09.openPlay()");
    await b.until(playScreen, "play screen of the new account", 600);
    await sendMove(b, "yeni hesap hamlesi");
    await b.until("document.body.innerText.includes('Yanıt: yeni hesap hamlesi')", "the new account's own move applied", 300);
    const indexBefore = await b.evaluate("window.__r09.cacheTurnIndex()");
    assert.equal(typeof indexBefore, "number");
    const postsBefore = trace.filter((item) => item.method === "POST" && item.actionId).length;
    // The old account's reply finally arrives. Its request belonged to the previous auth epoch, so the browser may already have
    // aborted it; whether it was still deliverable is recorded, not assumed.
    const lateReplyDelivered = await b.send("Fetch.continueResponse", { requestId: held }).then(() => true, () => false);
    await delay(2000);
    assert.equal(await b.evaluate("window.__r09.cacheTurnIndex()"), indexBefore, "the old account's late reply did not move the new account's view");
    assert.equal(trace.filter((item) => item.method === "POST" && item.actionId).length, postsBefore, "nothing was resent on its own");
    assert.deepEqual(await history(), ["ilk hamle", "eski hesap hamlesi", "yeni hesap hamlesi"], "each move took effect exactly once");
    layers.account_change_old_reply_invisible = lateReplyDelivered
      ? "PASS (late reply was delivered and did not move the new view)"
      : "PASS (the old account's request was aborted at the epoch change, so the late reply was never delivered; the stale-reply gate itself is covered by tests/r03-browser.test.mjs)";
    b.close();

    // ---- The evidence record --------------------------------------------------------------------------------------
    const apiRequests = trace.filter((item) => item.path.startsWith("/api/"));
    assert.ok(apiRequests.length > 0 && apiRequests.every((item) => item.host === "127.0.0.1"), "every request is real loopback HTTP");
    assert.ok(apiRequests.some((item) => /\/turn$/.test(item.path) && item.status === 200), "a real 200 turn response is in the trace");
    const evidence = {
      task: "R09",
      real_browser: true,
      browser: version.Browser,
      real_http: true,
      real_identity: false,
      identity: "FixedAuthenticator(TEST_PLAYER) fixture identity; NOT Clerk",
      layers: { ...layers, real_clerk_identity: "BLOCKED: no authorized external test account or token; nothing was mocked as Clerk acceptance" },
      http_trace: apiRequests.map(({ requestId, ...entry }) => entry),
    };
    assert.equal(evidence.real_identity, false);
    const evidencePath = path.join(process.env.R09_EVIDENCE_DIR ?? workdir, "r09-action-lifecycle-evidence.json");
    await writeFile(evidencePath, JSON.stringify(evidence, null, 2), "utf8");
    console.log("R09 evidence:", JSON.stringify({ ...evidence, http_trace: `${evidence.http_trace.length} real requests` }));
  });

test("R09 real Clerk identity layer", { skip: "BLOCKED: needs an authorized real Clerk test account; this task may not create accounts or change token/account settings, and a fixture result is never presented as Clerk acceptance" }, () => {});
