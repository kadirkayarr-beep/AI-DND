// R02 live check: REAL GameBrowser in REAL Chrome (two tabs) against a REAL temporary backend over real HTTP.
// Run it only through the isolated runner (scrubbed env, temp database, guard); it starts its own loopback-only backend
// (tests/r02-live-backend/serve.py), Vite proxy and headless Chrome with a temporary profile. It never touches port
// 8008, the real game, or any personal save. The deterministic engine answers "Yanıt: <message>"; a message containing
// OUTAGE raises the 503 provider outage before any effect.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { mkdtemp, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

// Opt-in: it needs the isolated runner's disposable database and a real browser, so the ordinary suite skips it.
const live = process.env.R02_LIVE === "1";
const chromiumPath = process.env.CHROMIUM_PATH;
if (live) {
  if (!chromiumPath || !path.isAbsolute(chromiumPath)) throw new Error("CHROMIUM_PATH must be an absolute executable path");
  await stat(chromiumPath);
  // Never the bare name "python": under the scrubbed environment it resolves to the Windows Store/installer shim, which
  // tries to download and install a Python runtime. An absolute interpreter path is required.
  if (!process.env.R02_PYTHON || !path.isAbsolute(process.env.R02_PYTHON)) throw new Error("R02_PYTHON must be an absolute interpreter path");
  await stat(process.env.R02_PYTHON);
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitFor(url, json = false, attempts = 150) {
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
  async until(expression, label, attempts = 150) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (await this.evaluate(expression)) return;
      await delay(100);
    }
    const body = await this.evaluate("document.body.innerText").catch(() => "(unreadable)");
    const buttons = await this.evaluate("[...document.querySelectorAll('[data-testid]')].map((n) => n.getAttribute('data-testid')).slice(0, 40).join(',')").catch(() => "");
    assert.fail(`Timed out waiting for ${label}. Page text: ${String(body).slice(0, 700).replace(/\s+/g, " ")} | testids: ${buttons}`);
  }
  close() { this.socket.close(); }
}

async function openTab(browserPort, url) {
  const target = await fetch(`http://127.0.0.1:${browserPort}/json/new?${encodeURIComponent(url)}`, { method: "PUT" }).then((r) => r.json());
  const page = new CdpPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width: 1100, height: 900, deviceScaleFactor: 1, mobile: false });
  return page;
}

const sel = (testid) => `document.querySelector('[data-testid="${testid}"]')`;
const hasNotice = (text) => `[...document.querySelectorAll('.notice')].some((n) => n.innerText.includes(${JSON.stringify(text)}))`;
const playScreen = `(!!${sel("input-player-message")} || !!${sel("button-open-composer")})`;
async function sendMove(page, text) {
  await page.until(playScreen, "play screen");
  // The composer opens on demand ("HAMLE YAP"); a pending move or a draft may already have it open.
  if (await page.evaluate(`!${sel("input-player-message")} && !!${sel("button-open-composer")}`)) {
    await page.evaluate(`${sel("button-open-composer")}.click()`);
  }
  await page.until(`!!${sel("input-player-message")} && !${sel("input-player-message")}.disabled`, "composer ready");
  await page.evaluate(`${sel("input-player-message")}.focus()`);
  await page.send("Input.insertText", { text });
  await page.until(`!${sel("button-send-turn")}.disabled`, "send enabled");
  await page.evaluate(`${sel("button-send-turn")}.click()`);
}
const click = (page, testid) => page.evaluate(`${sel(testid)}.click()`);
const pendingKey = (campaign) => `ai-dnd-pending-turns:action:${JSON.stringify(["local", campaign])}`;
const readPending = (page, campaign) => page.evaluate(`JSON.parse(window.sessionStorage.getItem(${JSON.stringify(pendingKey(campaign))}) ?? "null")`);

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill();
  await Promise.race([new Promise((resolve) => child.once("exit", resolve)), delay(4000)]);
}

test("R02 live: lost reply, second tab and server-proven exits (real Chrome, real temporary backend)", { timeout: 300_000, skip: live ? false : "set R02_LIVE=1 and run through the isolated runner" }, async (t) => {
  const profile = await mkdtemp(path.join(os.tmpdir(), "r02-live-chrome-"));
  // Chrome did not expose its debugging port when started inside the scrubbed environment, so the runner may be given
  // a browser that was started separately (temporary profile, loopback debugging port): R02_BROWSER_PORT.
  const externalBrowser = Boolean(process.env.R02_BROWSER_PORT);
  const [backendPort, vitePort] = [await freePort(), await freePort()];
  const browserPort = externalBrowser ? Number(process.env.R02_BROWSER_PORT) : await freePort();
  const backendOrigin = `http://127.0.0.1:${backendPort}`;
  const backendLog = [];
  const backend = spawn(process.env.R02_PYTHON, [path.join(process.cwd(), "tests", "r02-live-backend", "serve.py"), String(backendPort)], { env: process.env, stdio: ["ignore", "pipe", "pipe"] });
  backend.stdout.on("data", (chunk) => backendLog.push(String(chunk)));
  backend.stderr.on("data", (chunk) => backendLog.push(String(chunk)));
  const require = createRequire(import.meta.url);
  const viteCli = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
  const vite = spawn(process.execPath, [viteCli, "--config", "vite.config.ts", "--host", "127.0.0.1"], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(vitePort), BASE_PATH: "/", REPL_ID: undefined, AI_DND_API_ORIGIN: backendOrigin },
    stdio: "ignore",
  });
  const browserLog = [];
  const browser = externalBrowser ? null : spawn(chromiumPath, [
    "--headless=new", "--disable-gpu", "--disable-dev-shm-usage", `--remote-debugging-port=${browserPort}`,
    `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  if (browser) {
    browser.stdout.on("data", (chunk) => browserLog.push(String(chunk)));
    browser.stderr.on("data", (chunk) => browserLog.push(String(chunk)));
    browser.on("exit", (code) => browserLog.push(`[chrome exited ${code}]`));
  }
  t.after(async () => {
    if (externalBrowser) {
      // Close only the browser this check was given, through its own debugging socket.
      try {
        const version = await fetch(`http://127.0.0.1:${browserPort}/json/version`).then((r) => r.json());
        const closer = new CdpPage(version.webSocketDebuggerUrl);
        await closer.send("Browser.close");
      } catch { /* already closed */ }
    }
    await Promise.all([stop(backend), stop(vite), ...(browser ? [stop(browser)] : [])]);
    await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  });

  try {
    await waitFor(`${backendOrigin}/api/game/health`);
  } catch (error) {
    assert.fail(`${error.message}\nbackend output: ${backendLog.join("").slice(-800)}`);
  }
  const created = await fetch(`${backendOrigin}/api/game/campaigns`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  assert.equal(created.status, 200, await created.clone().text());
  const campaign = (await created.json()).campaign_id;
  const backendGet = (p) => fetch(`${backendOrigin}${p}`).then((r) => r.json());
  const history = async () => (await backendGet(`/api/game/campaigns/${campaign}`)).history.map((entry) => entry.player_message);

  const base = `http://127.0.0.1:${vitePort}`;
  await waitFor(`${base}/tests/r02-live-fixture/`);
  try {
    // A first start in a fresh temporary profile can take a while under the scrubbed environment.
    await waitFor(`http://127.0.0.1:${browserPort}/json/version`, true, 1200);
  } catch (error) {
    assert.fail(`${error.message}\nchrome output: ${browserLog.join("").slice(-1200)}`);
  }
  const url = `${base}/tests/r02-live-fixture/?campaign=${campaign}`;

  // ---- Tab A -------------------------------------------------------------------------------------------------
  const a = await openTab(browserPort, url);
  let sessionOfA = "";
  let dropNextReply = false;
  await a.send("Fetch.enable", { patterns: [{ urlPattern: "*/api/game/sessions/*/turn", requestStage: "Response" }] });
  a.on("Fetch.requestPaused", async (paused) => {
    const match = /sessions\/([^/]+)\/turn/.exec(paused.request.url);
    if (match) sessionOfA = match[1];
    if (dropNextReply && match) {
      dropNextReply = false;
      await a.send("Fetch.failRequest", { requestId: paused.requestId, errorReason: "ConnectionReset" });
    } else {
      await a.send("Fetch.continueResponse", { requestId: paused.requestId });
    }
  });
  await a.until(playScreen, "play screen in tab A", 300);

  // 1. LOST REPLY: the server commits, tab A never sees the answer.
  dropNextReply = true;
  await sendMove(a, "ilk hamle");
  await a.until(hasNotice("sonuçlanamadı"), "lost-reply notice");
  const pendingA = await readPending(a, campaign);
  assert.ok(pendingA?.actionId, "tab A keeps the unresolved move");
  assert.deepEqual(await history(), ["ilk hamle"], "the server really committed the move whose reply was lost");
  assert.equal((await backendGet(`/api/game/sessions/${sessionOfA}/actions/${pendingA.actionId}`)).state, "applied");
  assert.ok(await a.evaluate(`!!${sel("button-check-action")} && !!${sel("button-abandon-action")} && !!${sel("button-retry-turn")}`), "retry, check and abandon are offered");
  await click(a, "button-check-action");
  await a.until(hasNotice("sunucudan alındı"), "server-confirmed notice");
  assert.equal(await readPending(a, campaign), null, "closed only after the server verdict and reconcile");
  assert.ok((await a.evaluate("document.body.innerText")).includes("Yanıt: ilk hamle"), "the story shows the move reconciled from the server");
  assert.deepEqual(await history(), ["ilk hamle"], "nothing was resent: still exactly one committed move");

  // 2. OPEN INTENT: a provider outage leaves the action unresolved on the server.
  await sendMove(a, "OUTAGE bekleyen hamle");
  await a.until(hasNotice("sessiz"), "outage notice in tab A");
  const stuck = await readPending(a, campaign);
  assert.ok(stuck?.actionId);
  const open = await backendGet(`/api/game/sessions/${sessionOfA}/actions/unresolved`);
  assert.equal(open.unresolved?.action_id, stuck.actionId, "the server records the open action");

  // ---- Tab B: a second tab with its own sessionStorage ------------------------------------------------------------
  const b = await openTab(browserPort, url);
  await b.until(playScreen, "play screen in tab B", 300);
  assert.equal(await readPending(b, campaign), null, "tab B has no browser record of the move");
  await b.until(hasNotice("Tamamlanmamış bir hamle var"), "server-read open-action notice in tab B");
  assert.ok(await b.evaluate(`!!${sel("button-check-action")} && !!${sel("button-abandon-action")} && !${sel("button-retry-turn")}`), "check and abandon, no resend (there is no request body)");
  assert.equal(await readPending(b, campaign), null, "the browser record is not fabricated");

  // B's different move is refused by the server before any effect; the draft stays.
  await sendMove(b, "ikinci sekme hamlesi");
  await b.until(hasNotice("Yeni hamle uygulanmadı"), "unresolved_action refusal notice in tab B");
  assert.equal(await b.evaluate(`${sel("input-player-message")}.value`), "ikinci sekme hamlesi", "the draft is kept");
  assert.deepEqual(await history(), ["ilk hamle"], "the refused move changed nothing");

  // B's explicit, server-proven abandon, then an explicit new move works.
  await click(b, "button-abandon-action");
  await b.until(hasNotice("Hamle uygulanmadı"), "abandon verdict in tab B");
  await b.until(`!${sel("button-send-turn")}.disabled`, "draft still sendable");
  await b.evaluate(`${sel("button-send-turn")}.click()`);
  await b.until("document.body.innerText.includes('Yanıt: ikinci sekme hamlesi')", "tab B move applied after abandon");
  assert.deepEqual(await history(), ["ilk hamle", "ikinci sekme hamlesi"]);

  // ---- Back in tab A: the old retry can never apply ---------------------------------------------------------------
  await click(a, "button-retry-turn");
  await a.until(`window.sessionStorage.getItem(${JSON.stringify(pendingKey(campaign))}) === null`, "tab A closes the abandoned move on the server's durable refusal", 100);
  assert.deepEqual(await history(), ["ilk hamle", "ikinci sekme hamlesi"], "the abandoned move never ran: a late same-id request cannot apply");

  a.close();
  b.close();
});
