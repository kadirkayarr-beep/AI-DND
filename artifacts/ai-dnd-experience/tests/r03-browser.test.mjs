// R03 in a real browser: the real GameBrowser behind the real account-boundary helpers, a scripted API whose replies can be
// held while the world moves on. Proves the production paths (not source text): a late quest/ambient reply cannot regress
// HP, clock or journal, and a reply that belongs to a previous owner/epoch cannot write into the new account.
// Limits: scripted fetch (not the Python backend), headless Chrome, ClerkApiSession replaced by the same lib helpers it calls.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { mkdtemp, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

const chromiumPath = process.env.CHROMIUM_PATH;
if (!chromiumPath || !path.isAbsolute(chromiumPath)) throw new Error("CHROMIUM_PATH must be set to an absolute executable browser path");
await stat(chromiumPath);
const fixturePath = "/tests/r03-fixture/";

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitFor(url, parseJson = false) {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return parseJson ? response.json() : response;
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
    this.exceptions = [];
    this.ready = new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data.toString());
      if (message.method === "Runtime.exceptionThrown") this.exceptions.push(message.params.exceptionDetails.text);
      const pending = message.id ? this.pending.get(message.id) : undefined;
      if (!pending) return;
      this.pending.delete(message.id);
      message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result);
    });
  }
  async send(method, params = {}) {
    await this.ready;
    const id = ++this.nextId;
    const result = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    this.socket.send(JSON.stringify({ id, method, params }));
    return result;
  }
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    return result.result.value;
  }
  close() { this.socket.close(); }
}

const env = {};
async function newPage(query = '') {
  const url = `${env.baseUrl}${fixturePath}${query}`;
  const target = await fetch(`http://127.0.0.1:${env.browserPort}/json/new?${encodeURIComponent(url)}`, { method: "PUT" }).then((r) => r.json());
  const page = new CdpPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  return page;
}

async function until(page, expression, what, attempts = 150) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await page.evaluate(`!!(${expression})`)) return;
    await delay(100);
  }
  const body = await page.evaluate("document.body?.innerText?.slice(0, 600) ?? ''");
  const log = await page.evaluate("JSON.stringify(window.__r03?.log().slice(-8)) + ' ids=' + [...document.querySelectorAll('[data-testid]')].map((n) => n.dataset.testid).join(',')");
  throw new Error(`Timed out: ${what}; body=${body}; log=${log}; exceptions=${JSON.stringify(page.exceptions)}`);
}

const click = (page, selector) => page.evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const cache = (page) => page.evaluate("window.__r03.cache()");
const world = (page) => page.evaluate("window.__r03.world()");

async function sendTurn(page, text) {
  if (await page.evaluate("!!document.querySelector('[data-testid=\"button-open-composer\"]')")) await click(page, '[data-testid="button-open-composer"]');
  await until(page, "document.querySelector('#player-message')", "composer textarea");
  await page.evaluate("document.querySelector('#player-message').focus()");
  await page.send("Input.insertText", { text });
  await until(page, "!document.querySelector('[data-testid=\"button-send-turn\"]').disabled", "send enabled");
  await click(page, '[data-testid="button-send-turn"]');
}

// Replies are sampled while released so a temporary regression cannot hide behind a later healing refetch.
async function sampleFor(page, ms) {
  const samples = [];
  for (let elapsed = 0; elapsed < ms; elapsed += 50) {
    samples.push(await cache(page));
    await delay(50);
  }
  return samples;
}

function assertNeverBelow(samples, floor) {
  for (const sample of samples) {
    assert.ok(sample.hp <= floor.hp, `HP regressed: ${JSON.stringify(sample)}`);
    assert.ok(sample.minute >= floor.minute, `clock regressed: ${JSON.stringify(sample)}`);
    assert.ok(sample.events >= floor.events, `journal regressed: ${JSON.stringify(sample)}`);
  }
}

test("R03 real browser flows", async (t) => {
  const tempProfile = await mkdtemp(path.join(os.tmpdir(), "ai-dnd-r03-"));
  const vitePort = await freePort();
  env.browserPort = await freePort();
  const require = createRequire(import.meta.url);
  const viteCli = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
  const vite = spawn(process.execPath, [viteCli, "--config", "vite.config.ts", "--host", "127.0.0.1"], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(vitePort), BASE_PATH: "/", REPL_ID: undefined, AI_DND_API_ORIGIN: `http://127.0.0.1:${await freePort()}` },
    stdio: "ignore",
  });
  const browser = spawn(chromiumPath, [
    "--headless=new", "--disable-gpu", "--disable-dev-shm-usage",
    `--remote-debugging-port=${env.browserPort}`, `--user-data-dir=${tempProfile}`, "about:blank",
  ], { stdio: "ignore" });
  t.after(async () => {
    for (const child of [vite, browser]) {
      if (child.exitCode === null) {
        child.kill("SIGTERM");
        await Promise.race([new Promise((resolve) => child.once("exit", resolve)), delay(4000)]);
      }
    }
    await rm(tempProfile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  });
  env.baseUrl = `http://127.0.0.1:${vitePort}`;
  await waitFor(`${env.baseUrl}${fixturePath}`);
  await waitFor(`http://127.0.0.1:${env.browserPort}/json/version`, true);
  // Warm-up: the first load compiles the whole app on demand, which can exceed a normal page wait.
  const warm = await newPage();
  await until(warm, "document.querySelector('[data-testid=\"button-open-world\"]')", "warm-up play screen", 600);
  warm.close();

  const openJournal = async (page) => {
    await until(page, "document.querySelector('[data-testid=\"button-open-world\"]')", "play screen");
    await click(page, '[data-testid="button-open-world"]');
    await until(page, "document.querySelector('[data-testid=\"tab-journal\"]')", "world drawer");
    await click(page, '[data-testid="tab-journal"]');
    await until(page, "document.querySelector('[data-testid=\"button-accept-quest-quest-1\"]')", "quest offer");
  };

  await t.test("a quest reply held while a new turn lands cannot regress HP, clock or journal", async () => {
    const page = await newPage();
    await openJournal(page);
    await page.evaluate("window.__r03.hold('quest')");
    await click(page, '[data-testid="button-accept-quest-quest-1"]');
    await until(page, "window.__r03.log().some((l) => l.includes('/quests/quest-1/accept'))", "quest request sent");
    // The server already processed the quest (held copy: hp 11, minute 41, 1 journal event). Now a turn lands on top of it.
    await sendTurn(page, "Avluyu inceliyorum");
    await until(page, "window.__r03.cache()?.hp === 10", "turn applied");
    await page.evaluate("window.__r03.release('quest')");
    assertNeverBelow(await sampleFor(page, 2000), { hp: 10, minute: 42, events: 2 });
    const final = await cache(page);
    const server = await world(page);
    assert.deepEqual(
      { hp: final.hp, minute: final.minute, events: final.events, questAccepted: final.questAccepted },
      { hp: server.hp, minute: server.minute, events: server.events, questAccepted: server.questAccepted },
      "the view ends on the server's own state",
    );
    assert.deepEqual(page.exceptions, []);
    page.close();
  });

  await t.test("while an ambient action is unresolved the client does not send a turn over it, and a quest accepted meanwhile is not overwritten by the late ambient reply", async () => {
    const page = await newPage();
    await until(page, "document.querySelector('[data-testid=\"button-ambient-action-observe\"]')", "ambient panel");
    await page.evaluate("window.__r03.hold('ambient')");
    await click(page, '[data-testid="button-ambient-action-observe"]');
    await until(page, "window.__r03.log().some((l) => l.includes('/ambient-events/amb-1/actions'))", "ambient request sent");
    // Production gate (R02): a turn is not sent while the ambient answer is unresolved.
    await sendTurn(page, "Gölgeye bakıyorum");
    await delay(600);
    assert.equal(await page.evaluate("window.__r03.log().filter((l) => l.endsWith('/turn')).length"), 0, "a turn overtook an unresolved ambient action");
    // A quest command is not blocked by it; it lands while the ambient reply is still held.
    await openJournal(page);
    await click(page, '[data-testid="button-accept-quest-quest-1"]');
    await until(page, "window.__r03.cache()?.hp === 11", "quest applied while ambient is held");
    await page.evaluate("window.__r03.release('ambient')");
    assertNeverBelow(await sampleFor(page, 2000), { hp: 11, minute: 41, events: 1 });
    const final = await cache(page);
    const server = await world(page);
    assert.deepEqual(
      { hp: final.hp, minute: final.minute, events: final.events, questAccepted: final.questAccepted, ambientOpen: final.ambientOpen },
      { hp: server.hp, minute: server.minute, events: server.events, questAccepted: server.questAccepted, ambientOpen: server.ambientOpen },
    );
    page.close();
  });

  await t.test("R07: an expired deadline shows the unknown outcome, keeps draft and ActionKey, and a late commit gives one effect", async () => {
    const page = await newPage("?deadline=1500");
    await until(page, "document.querySelector('[data-testid=\"button-open-world\"]')", "play screen");
    await page.evaluate("window.__r03.hold('turn')");
    await sendTurn(page, "Avluyu inceliyorum");
    await until(page, "document.body.innerText.includes('Hamlenin sonucu belirsiz')", "unknown-outcome notice", 80);
    // The server committed once (the reply is only delayed); the page must not have sent anything else on its own.
    assert.deepEqual((await page.evaluate("window.__r03.turnActionIds()")).length, 1, "no automatic second action");
    assert.equal((await world(page)).hp, 11, "the late commit is exactly one effect");
    const pending = await page.evaluate("Object.keys(sessionStorage).filter((k) => k.startsWith('ai-dnd-pending-turns:action:')).map((k) => sessionStorage.getItem(k)).join('|')");
    assert.match(pending, /Avluyu inceliyorum/, "the ActionKey and request stay stored");
    await page.evaluate("window.__r03.release('turn')");
    await delay(800);
    assert.equal((await page.evaluate("window.__r03.turnActionIds()")).length, 1, "the late reply triggered nothing");
    // The player's own retry resends the SAME id; the server replays its receipt and nothing changes twice.
    await until(page, "document.querySelector('[data-testid=\"button-retry-turn\"]')", "retry offered");
    await click(page, '[data-testid="button-retry-turn"]');
    await until(page, "window.__r03.turnActionIds().length === 2", "retry sent");
    const ids = await page.evaluate("window.__r03.turnActionIds()");
    assert.equal(ids[0], ids[1], "same action id");
    await until(page, "window.__r03.cache()?.hp === 11", "view shows the single committed effect");
    assert.equal((await world(page)).hp, 11, "still exactly one effect after the retry");
    assert.equal((await world(page)).events, 1);
    page.close();
  });

  await t.test("R07: a hung undo is bounded by the same deadline, shows the uncertainty and is not resent on its own", async () => {
    const page = await newPage("?deadline=1500");
    await until(page, "document.querySelector('[data-testid=\"button-open-world\"]')", "play screen");
    await sendTurn(page, "Avluyu inceliyorum");
    await until(page, "window.__r03.cache()?.hp === 11", "turn applied");
    await until(page, "document.querySelector('[data-testid=\"button-undo-last-turn\"]')", "undo offered");
    await page.evaluate("window.__r03.hold('undo')");
    await click(page, '[data-testid="button-undo-last-turn"]');
    await until(page, "document.querySelector('[data-testid=\"confirm-undo\"] button')", "undo confirmation");
    await click(page, '[data-testid="confirm-undo"] button');
    await until(page, "document.body.innerText.includes('Geri alma sonucu')", "unknown undo outcome shown", 80);
    assert.equal((await page.evaluate("window.__r03.undoRequests()")).length, 1, "no automatic resend of the undo");
    assert.equal((await world(page)).hp, 12, "the server applied the undo once (its reply is only delayed)");
    await until(page, "[...document.querySelectorAll('button')].some((b) => b.innerText.toLocaleLowerCase('tr').includes('geri almayı yeniden dene'))", "the retry is offered, the busy state is not stuck", 40);
    page.close();
  });

  for (const [label, identity] of [["owner", "owner-b:session-2"], ["session (same owner, new epoch)", "owner-a:session-2"]]) {
    await t.test(`a reply from the previous ${label} cannot write into the new account, and the new account does not refetch forever`, async () => {
      const page = await newPage();
      await openJournal(page);
      // The held reply is poisoned (hp 99 / minute 99) so any write of it is unmistakable.
      await page.evaluate("window.__r03.hold('quest', { hp: 99, minute: 99 })");
      await click(page, '[data-testid="button-accept-quest-quest-1"]');
      await until(page, "window.__r03.log().some((l) => l.includes('/quests/quest-1/accept'))", "quest request sent");
      await page.evaluate(`window.__r03.switchIdentity(${JSON.stringify(identity)})`);
      await page.evaluate("window.__r03.openPlay()");
      await until(page, "window.__r03.cache()?.hp === 11", "new account loaded its own state");
      const readsBefore = await page.evaluate("window.__r03.stateReads()");
      const requestsBefore = await page.evaluate("window.__r03.log().length");
      await page.evaluate("window.__r03.release('quest')");
      const samples = await sampleFor(page, 2500);
      for (const sample of samples) assert.notEqual(sample?.hp, 99, "the previous account's reply reached the new account");
      assert.equal((await cache(page)).hp, 11);
      assert.equal((await cache(page)).minute, 41);
      const readsAfter = await page.evaluate("window.__r03.stateReads()");
      const requestsAfter = await page.evaluate("window.__r03.log().length");
      assert.ok(readsAfter - readsBefore <= 2, `state refetch loop: ${readsAfter - readsBefore} reads`);
      assert.ok(requestsAfter - requestsBefore <= 6, `request storm: ${requestsAfter - requestsBefore} requests`);
      page.close();
    });
  }
});
