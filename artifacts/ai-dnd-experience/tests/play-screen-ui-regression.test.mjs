import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

const chromiumPath = process.env.CHROMIUM_PATH || "/repl/tools/bin/chromium";
const outputDir = process.env.UI_TEST_OUTPUT || path.join(os.tmpdir(), "ai-dnd-ui-verification");
const fixturePath = "/tests/play-screen-fixture/";

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return address.port;
}

async function waitFor(url, parseJson = false) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return parseJson ? response.json() : response;
    } catch {}
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
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result);
      }
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
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }

  close() {
    this.socket.close();
  }
}

async function press(page, key, code, keyCode) {
  await page.send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: keyCode });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: keyCode });
}

async function saveScreenshot(page, name) {
  const result = await page.send("Page.captureScreenshot", { format: "jpeg", quality: 86, captureBeyondViewport: false });
  await writeFile(path.join(outputDir, name), Buffer.from(result.data, "base64"));
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    delay(4000),
  ]);
}

async function createPage(browserPort, url, width, height) {
  const target = await fetch(`http://127.0.0.1:${browserPort}/json/new?${encodeURIComponent(url)}`, { method: "PUT" }).then((response) => response.json());
  const page = new CdpPage(target.webSocketDebuggerUrl);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Emulation.setDeviceMetricsOverride", {
    width, height, deviceScaleFactor: 1, mobile: width < 600,
  });
  await waitFor(`${url}`);
  await page.evaluate("document.readyState === 'complete'");
  return { page, targetId: target.id };
}

test("isolated real play UI stays usable at phone and desktop sizes", async (t) => {
  await mkdir(outputDir, { recursive: true });
  const tempProfile = await mkdtemp(path.join(os.tmpdir(), "ai-dnd-chromium-"));
  const vitePort = await freePort();
  const browserPort = await freePort();
  const vite = spawn("pnpm", ["exec", "vite", "--config", "vite.config.ts", "--host", "127.0.0.1"], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(vitePort), BASE_PATH: "/", REPL_ID: undefined, AI_DND_API_ORIGIN: `http://127.0.0.1:${await freePort()}` },
    stdio: "ignore",
  });
  const browser = spawn(chromiumPath, [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    `--remote-debugging-port=${browserPort}`, `--user-data-dir=${tempProfile}`,
    "about:blank",
  ], { stdio: "ignore" });
  t.after(async () => {
    await Promise.all([stopChild(vite), stopChild(browser)]);
    await rm(tempProfile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  });

  const baseUrl = `http://127.0.0.1:${vitePort}`;
  await waitFor(`${baseUrl}${fixturePath}`);
  await waitFor(`http://127.0.0.1:${browserPort}/json/version`, true);
  const metrics = [];

  for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 360, height: 640 }, { width: 1440, height: 900 }]) {
    const menu = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=opening`, viewport.width, viewport.height);
    await waitForSelector(menu.page, '[data-testid="app-start"]');
    const menuMeasure = await menu.page.evaluate(`(() => ({ width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth, emblem: !!document.querySelector('.opening-emblem-frame'), create: !!document.querySelector('[data-testid="button-create-session"]'), continue: !!document.querySelector('[data-testid="button-continue-session"]') }))()`);
    assert.equal(menuMeasure.emblem, true);
    assert.equal(menuMeasure.create, true);
    assert.equal(menuMeasure.continue, true);
    assert.ok(menuMeasure.scrollWidth <= viewport.width, `opening menu overflows at ${viewport.width}px`);
    await saveScreenshot(menu.page, `opening-${viewport.width}x${viewport.height}.jpg`);
    menu.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${menu.targetId}`);

    const play = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play`, viewport.width, viewport.height);
    await waitForSelector(play.page, '[data-testid="app-session"]');
    await waitForSelector(play.page, '[data-testid="transcript-scroll"]');
    const textarea = await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]') !== null");
    assert.equal(textarea, true);
    const longStory = await play.page.evaluate(`(() => { const nodes = [...document.querySelectorAll('.story-text')]; const area = document.querySelector('[data-testid="transcript-scroll"]'); return { count: nodes.length, chars: nodes.map(n => n.innerText).join('').length, scrollHeight: area.scrollHeight, clientHeight: area.clientHeight, scrollWidth: document.documentElement.scrollWidth }; })()`);
    assert.ok(longStory.count >= 18);
    assert.ok(longStory.chars > 1000);
    assert.ok(longStory.scrollHeight > longStory.clientHeight);
    assert.ok(longStory.scrollWidth <= viewport.width, `play UI overflows at ${viewport.width}px`);

    const draft = "Kuzgun avlusunda dikkatlice yaklaşıyorum. ".repeat(20).slice(0, 825);
    await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
    await play.page.send("Input.insertText", { text: draft });
    const draftMeasure = await play.page.evaluate(`(() => { const input = document.querySelector('[data-testid="input-player-message"]'); const button = document.querySelector('[data-testid="button-send-turn"]'); const rect = button.getBoundingClientRect(); return { length: input.value.length, top: rect.top, bottom: rect.bottom, height: innerHeight, scrollY, scrollHeight: document.documentElement.scrollHeight, disabled: button.disabled }; })()`);
    assert.equal(draftMeasure.length, 825);
    assert.equal(draftMeasure.disabled, false);
    if (viewport.height >= 800) assert.ok(draftMeasure.bottom <= viewport.height, `Gönder is not visible without scrolling at ${viewport.width}px`);
    else {
      await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').scrollIntoView({ block: 'center' })");
      assert.ok(await play.page.evaluate("(() => { const r = document.querySelector('[data-testid=\"button-send-turn\"]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight })()"));
    }
    await saveScreenshot(play.page, `play-${viewport.width}x${viewport.height}-draft.jpg`);
    await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-send-turn");
    await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').click()");
    await waitForValue(play.page, "window.__playFixture.lastTurn?.message?.length === 825");

    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-character\"]').click()");
    await waitForSelector(play.page, '[role="dialog"][aria-modal="true"]');
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-close-drawer");
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("!!document.activeElement?.closest('[role=\"dialog\"]')"), true);
    if (viewport.width === 390) await saveScreenshot(play.page, "character-panel-390.jpg");
    await press(play.page, "Escape", "Escape", 27);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-character");

    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-world\"]').click()");
    await waitForSelector(play.page, '[role="dialog"][aria-modal="true"]');
    await play.page.evaluate("document.querySelector('[data-testid=\"tab-world\"]').focus()");
    await press(play.page, "ArrowRight", "ArrowRight", 39);
    assert.equal(await play.page.evaluate("document.activeElement?.id"), "tab-npcs");
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('aria-selected')"), "true");
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("!!document.activeElement?.closest('[role=\"dialog\"]')"), true);
    if (viewport.width === 390 || viewport.width === 1440) await saveScreenshot(play.page, `world-panel-${viewport.width}.jpg`);
    await press(play.page, "Escape", "Escape", 27);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-world");
    const errors = play.page.exceptions;
    assert.deepEqual(errors, []);
    metrics.push({ viewport, longStory, draft: draftMeasure, menu: menuMeasure, jsExceptions: errors });
    play.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${play.targetId}`);
  }

  await writeFile(path.join(outputDir, "measurements.json"), JSON.stringify({ fixture: "fixed mock responses; not signed in and not a real campaign", metrics }, null, 2));
});

async function waitForSelector(page, selector) {
  const encoded = JSON.stringify(selector);
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await page.evaluate(`!!document.querySelector(${encoded})`)) return;
    await delay(100);
  }
  const state = await page.evaluate(`(() => ({
    url: location.href,
    title: document.title,
    body: document.body?.innerText?.slice(0, 1200) ?? "",
    root: document.querySelector("#root")?.innerHTML?.slice(0, 1200) ?? "",
  }))()`);
  throw new Error(`Timed out waiting for selector ${selector}; state=${JSON.stringify(state)}; exceptions=${JSON.stringify(page.exceptions)}`);
}

async function waitForValue(page, expression) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await page.evaluate(expression)) return;
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${expression}`);
}
