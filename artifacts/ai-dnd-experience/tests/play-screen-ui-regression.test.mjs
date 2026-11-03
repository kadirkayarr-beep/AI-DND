import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { constants as fsConstants } from "node:fs";
import { access, mkdir, mkdtemp, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";

const chromiumPath = process.env.CHROMIUM_PATH;
if (!chromiumPath || !path.isAbsolute(chromiumPath)) {
  throw new Error("CHROMIUM_PATH must be set to an absolute executable browser path");
}
const chromiumStat = await stat(chromiumPath);
if (!chromiumStat.isFile() || (process.platform !== "win32" && (chromiumStat.mode & 0o111) === 0)) {
  throw new Error(`CHROMIUM_PATH is not an executable file: ${chromiumPath}`);
}
await access(chromiumPath, fsConstants.X_OK);
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

async function press(page, key, code, keyCode, modifiers = 0, includeEnterText = true) {
  const text = key === "Enter" && includeEnterText ? "\n" : undefined;
  await page.send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: keyCode, modifiers });
  if (text) await page.send("Input.dispatchKeyEvent", { type: "char", key, code, windowsVirtualKeyCode: keyCode, modifiers, text, unmodifiedText: text });
  await page.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: keyCode, modifiers });
}

async function targetPoint(page, selector) {
  const rect = await page.evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)})?.getBoundingClientRect(); return r && { x:r.left+r.width/2, y:r.top+r.height/2 }; })()`);
  assert.ok(rect, `No visible target for ${selector}`);
  return rect;
}

async function mouseClick(page, selector) {
  const { x, y } = await targetPoint(page, selector);
  await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await page.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await page.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}

async function mouseWheel(page, selector, deltaY) {
  const { x, y } = await targetPoint(page, selector);
  await page.send("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaY, deltaX: 0 });
}

async function mouseWheelAt(page, x, y, deltaY) {
  await page.send("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaY, deltaX: 0 });
}

async function touchTap(page, selector) {
  const { x, y } = await targetPoint(page, selector);
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function touchSwipeAt(page, x, y, endX, endY) {
  await page.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y, id: 1 }] });
  await page.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: endX, y: endY, id: 1 }] });
  await page.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function tabTo(page, selector, maxTabs = 60) {
  for (let index = 0; index < maxTabs; index += 1) {
    if (await page.evaluate(`document.activeElement === document.querySelector(${JSON.stringify(selector)})`)) return;
    await press(page, "Tab", "Tab", 9);
  }
  assert.fail(`Keyboard Tab did not reach ${selector}`);
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
  const require = createRequire(import.meta.url);
  const viteCli = path.join(path.dirname(require.resolve("vite/package.json")), "bin", "vite.js");
  const vite = spawn(process.execPath, [viteCli, "--config", "vite.config.ts", "--host", "127.0.0.1"], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(vitePort), BASE_PATH: "/", REPL_ID: undefined, AI_DND_API_ORIGIN: `http://127.0.0.1:${await freePort()}` },
    stdio: "ignore",
  });
  const browser = spawn(chromiumPath, [
    "--headless=new", "--disable-gpu", "--disable-dev-shm-usage",
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

  for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 360, height: 640 }, { width: 800, height: 900 }, { width: 768, height: 1024 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    const menu = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=opening`, viewport.width, viewport.height);
    await waitForSelector(menu.page, '[data-testid="app-start"]');
    const menuMeasure = await menu.page.evaluate(`(() => { const image=document.querySelector('[data-testid="image-approved-ouroboros"]'); return { width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,approvedImage:Boolean(image&&image.complete&&image.naturalWidth>0),imageAlt:image?.alt,create:Boolean(document.querySelector('[data-testid="button-create-session"]')),continue:Boolean(document.querySelector('[data-testid="button-continue-session"]')),heading:document.querySelector('h1')?.innerText }; })()`);
    assert.equal(menuMeasure.approvedImage, true, `approved entry art missing at ${viewport.width}px`);
    assert.match(menuMeasure.imageAlt, /ejderha/i);
    assert.equal(menuMeasure.create, true);
    assert.equal(menuMeasure.continue, true);
    assert.equal(menuMeasure.heading, "UNWRITTEN");
    assert.ok(menuMeasure.scrollWidth <= viewport.width, `opening menu overflows at ${viewport.width}px`);
    assert.equal(await menu.page.evaluate("document.querySelector('[data-testid=\"button-create-session\"]').tagName"), "BUTTON");
    await saveScreenshot(menu.page, `opening-${viewport.width}x${viewport.height}.jpg`);
    menu.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${menu.targetId}`);

    const play = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play`, viewport.width, viewport.height);
    await waitForSelector(play.page, '[data-testid="app-session"]');
    await waitForSelector(play.page, '[data-testid="transcript-scroll"]');
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"input-player-message\"]'))"), true, "the input is simply there");
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"button-open-composer\"]'))"), false);
    assert.notEqual(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "input-player-message", "loading the page must not raise a phone keyboard");
    if (viewport.width === 390 || viewport.width === 1920) await saveScreenshot(play.page, `play-reading-${viewport.width}.jpg`);
    const inputBox = await play.page.evaluate("(() => { const r=document.querySelector('[data-testid=\"input-player-message\"]').getBoundingClientRect(); return {top:r.top,bottom:r.bottom,height:innerHeight}; })()");
    assert.ok(inputBox.top >= 0 && inputBox.bottom <= inputBox.height, `the input must be on screen without scrolling at ${viewport.width}x${viewport.height}: ${JSON.stringify(inputBox)}`);
    const longStory = await play.page.evaluate(`(() => { const nodes = [...document.querySelectorAll('.story-text')]; const area = document.querySelector('[data-testid="transcript-scroll"]'); const rect = (node) => { const r = node?.getBoundingClientRect(); return r ? { top: r.top, bottom: r.bottom, width: r.width, height: r.height } : null; }; const areaRect = rect(area); const lastParagraph = rect(nodes.at(-1)); const context=document.querySelector('[aria-label="Sahne bilgileri"]'); return { count:nodes.length,chars:nodes.map(n=>n.innerText).join('').length,scrollHeight:area.scrollHeight,clientHeight:area.clientHeight,scrollTop:area.scrollTop,scrollWidth:document.documentElement.scrollWidth,storyColumn:rect(document.querySelector('[data-testid="panel-story"]')),sceneContext:rect(context),transcript:areaRect,lastParagraph,lastParagraphVisible:Boolean(lastParagraph&&areaRect&&lastParagraph.bottom>areaRect.top&&lastParagraph.top<areaRect.bottom),css:{contextOverflow:getComputedStyle(context).overflow,transcriptOverflow:getComputedStyle(area).overflowY,transcriptMaxHeight:getComputedStyle(area).maxHeight,playDisplay:getComputedStyle(document.querySelector('.preview-play')).display}}; })()`);
    assert.ok(longStory.count >= 18);
    assert.ok(longStory.chars > 1000);
    assert.match(await play.page.evaluate("document.querySelector('[data-testid=\"skill-check-result\"]')?.innerText ?? ''"), /Gizlilik/i, "translated skill label should use the existing Turkish catalog");
    const initialRollCard = await play.page.evaluate("(() => { const card=document.querySelector('[data-testid=\"skill-check-result\"]'); return { open:card?.open, width:card?.clientWidth, scrollWidth:card?.scrollWidth, label:card?.querySelector('summary')?.getAttribute('aria-label') ?? '', text:card?.innerText ?? '' }; })()");
    assert.equal(initialRollCard.open, false, "the in-story result card should start compact");
    assert.ok(initialRollCard.scrollWidth <= initialRollCard.width + 1, `roll card overflows at ${viewport.width}px`);
    assert.doesNotMatch(`${initialRollCard.label} ${initialRollCard.text}`, /DC\s*\d/i, "hidden DC must not appear in visible or accessible text");
    await play.page.evaluate("document.querySelector('[data-testid=\"skill-check-result\"] summary').scrollIntoView({block:'center'})");
    const readingPositionBeforeCardToggle = await play.page.evaluate("(() => { const area=document.querySelector('[data-testid=\"transcript-scroll\"]'); return area.scrollHeight>area.clientHeight+1 ? area.scrollTop : window.scrollY; })()");
    await play.page.evaluate("document.querySelector('[data-testid=\"skill-check-result\"] summary').focus()");
    assert.equal(await play.page.evaluate("document.activeElement?.tagName === 'SUMMARY'"), true, "the disclosure summary should be keyboard-focusable");
    if (viewport.width === 390 || viewport.width === 1440) await saveScreenshot(play.page, `skill-check-card-${viewport.width}-closed.jpg`);
    await press(play.page, " ", "Space", 32);
    await waitForValue(play.page, "document.querySelector('[data-testid=\"skill-check-result\"]')?.open === true");
    const openedRollCard = await play.page.evaluate("(() => { const area=document.querySelector('[data-testid=\"transcript-scroll\"]'); const card=document.querySelector('[data-testid=\"skill-check-result\"]'); return {position:area.scrollHeight>area.clientHeight+1 ? area.scrollTop : window.scrollY,text:card.innerText}; })()");
    if (viewport.width === 390 || viewport.width === 1440) await saveScreenshot(play.page, `skill-check-card-${viewport.width}-open.jpg`);
    assert.ok(Math.abs(openedRollCard.position - readingPositionBeforeCardToggle) <= 2, "expanding result details must not jump the story");
    assert.match(openedRollCard.text, /Atılan zarlar|Kullanılan D20/);
    assert.match(openedRollCard.text, /Orta/);
    assert.doesNotMatch(openedRollCard.text, /DC\s*\d/i);
    await press(play.page, " ", "Space", 32);
    await waitForValue(play.page, "document.querySelector('[data-testid=\"skill-check-result\"]')?.open === false");
    const closedRollPosition = await play.page.evaluate("(() => { const area=document.querySelector('[data-testid=\"transcript-scroll\"]'); return area.scrollHeight>area.clientHeight+1 ? area.scrollTop : window.scrollY; })()");
    assert.ok(Math.abs(closedRollPosition - readingPositionBeforeCardToggle) <= 2, "closing result details must not jump the story");
    const readingSettings = await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"reading-settings\"]'))");
    assert.ok(readingSettings, "small reading settings control should be available");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"reading-settings\"]').open"), false);
    await play.page.evaluate("document.querySelector('[data-testid=\"reading-settings\"] summary').focus()");
    await press(play.page, " ", "Space", 32);
    await waitForValue(play.page, "document.querySelector('[data-testid=\"reading-settings\"]')?.open === true");
    await play.page.evaluate("document.querySelector('#reading-font-size').focus()");
    await press(play.page, "ArrowRight", "ArrowRight", 39);
    await play.page.evaluate("document.querySelector('#reading-line-height').focus()");
    await press(play.page, "ArrowRight", "ArrowRight", 39);
    await waitForValue(play.page, "document.querySelector('#reading-font-size')?.value === '25' && document.querySelector('#reading-line-height')?.value === '1.7'");
    const adjustedReading = await play.page.evaluate("(() => { const story=document.querySelector('.story-text'); const menu=document.querySelector('[data-testid=\"reading-settings\"]'); const panel=menu.querySelector('.reading-settings__panel'); const firstStory=story.getBoundingClientRect(); const panelRect=panel.getBoundingClientRect(); const stored=JSON.parse(localStorage.getItem('ai-dnd-reading-preferences-v1')); return {fontSize:getComputedStyle(story).fontSize,lineHeight:getComputedStyle(story).lineHeight,scrollWidth:document.documentElement.scrollWidth,innerWidth,menuPosition:getComputedStyle(panel).position,panelLeft:panelRect.left,panelRight:panelRect.right,panelBelowStoryHeading:panelRect.top>=menu.getBoundingClientRect().top,overlapsStory:panelRect.bottom>Math.max(firstStory.top,document.querySelector('[data-testid=\"transcript-scroll\"]').getBoundingClientRect().top),storedKeys:Object.keys(stored).sort()}; })()");
    assert.equal(adjustedReading.fontSize, "25px");
    assert.equal(adjustedReading.lineHeight, "42.5px");
    assert.ok(adjustedReading.scrollWidth <= adjustedReading.innerWidth, `reading controls overflow at ${viewport.width}px`);
    assert.ok(adjustedReading.panelLeft >= 0 && adjustedReading.panelRight <= adjustedReading.innerWidth, `reading settings panel is clipped at ${viewport.width}px: ${JSON.stringify(adjustedReading)}`);
    assert.equal(adjustedReading.menuPosition, "static", "settings must stay in document flow instead of covering the story");
    assert.equal(adjustedReading.overlapsStory, false, `settings panel must not cover narrative text at ${viewport.width}x${viewport.height}: ${JSON.stringify(adjustedReading)}`);
    assert.deepEqual(adjustedReading.storedKeys, ["fontSizePx", "lineHeight"]);
    await play.page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
    assert.equal(await play.page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"), true);
    assert.equal(await play.page.evaluate("getComputedStyle(document.querySelector('.skill-check-result__chevron')).transitionDuration"), "0s");
    await play.page.send("Emulation.setEmulatedMedia", { features: [] });
    await mouseClick(play.page, ".reading-settings__reset");
    await waitForValue(play.page, "document.querySelector('#reading-font-size')?.value === '24' && document.querySelector('#reading-line-height')?.value === '1.68'");
    assert.equal(await play.page.evaluate("document.querySelector('#reading-font-size').closest('label').querySelector('output').textContent"), "Varsayılan");
    if (viewport.width === 390 || viewport.width === 800 || viewport.width === 1440) await saveScreenshot(play.page, `reading-settings-${viewport.width}.jpg`);
    await play.page.evaluate("document.querySelector('[data-testid=\"reading-settings\"]').open = false");
    const zoomEquivalent = await play.page.evaluate("({scrollWidth:document.documentElement.scrollWidth,innerWidth})");
    if (viewport.width === 800) {
      assert.ok(zoomEquivalent.scrollWidth <= zoomEquivalent.innerWidth, "1600px desktop at 200% browser zoom should fit an 800px CSS viewport");
    }
    if (viewport.width > 760) assert.ok(longStory.scrollHeight > longStory.clientHeight, `desktop transcript should scroll within its readable viewport at ${viewport.width}px`);
    else assert.ok(longStory.transcript?.height > 1000, `mobile narrative should expand into the page instead of clipping: ${JSON.stringify(longStory)}`);
    assert.ok(longStory.storyColumn?.height > 0, `story column is not visible at ${viewport.width}px: ${JSON.stringify(longStory)}`);
    assert.ok(longStory.sceneContext?.height > 0, `live scene context is not visible at ${viewport.width}px`);
    assert.ok(longStory.transcript?.height > 0, `campaign transcript is not visible at ${viewport.width}px`);
    assert.equal(longStory.lastParagraphVisible, true, `latest narration is outside the transcript viewport at ${viewport.width}px`);
    assert.ok(longStory.scrollWidth <= viewport.width, `play UI overflows at ${viewport.width}px`);
    assert.notEqual(longStory.css.contextOverflow, "auto", `scene context is clipped at ${viewport.width}px`);
    if (viewport.width > 760) assert.ok(longStory.transcript.height >= 320, `desktop narrative area too short: ${JSON.stringify(longStory)}`);
    else assert.equal(longStory.css.transcriptOverflow, "visible", `mobile narrative is trapped in a scroll box: ${JSON.stringify(longStory)}`);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"header-character-hp\"]')?.textContent.trim()"), "12 / 12", "persistent health missing during exploration");
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"button-open-active-combat\"]'))"), false, "exploration fixture unexpectedly has active combat");

    const draft = "Kuzgun avlusunda dikkatlice yaklaşıyorum. ".repeat(20).slice(0, 825);
    await play.page.evaluate("document.querySelector('[data-testid=\"button-close-composer\"]').click()");
    await waitForSelector(play.page, '[data-testid="button-open-composer"]');
    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-composer\"]').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="button-open-composer"]');
    await waitForSelector(play.page, '[data-testid="input-player-message"]');
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "input-player-message", "opening should focus the draft");
    await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
    const turnRequestCount = () => play.page.evaluate("window.__playFixture.apiRequests.filter((request) => request.path.endsWith('/turn') && request.method === 'POST').length");
    const clearDraft = () => play.page.evaluate("(() => { const input=document.querySelector('[data-testid=\"input-player-message\"]'); const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set; setter.call(input,''); input.dispatchEvent(new Event('input',{bubbles:true})); })()");
    if (viewport.width <= 640) {
      assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"desktop-enter-hint\"]'))"), false, "touch-sized layouts must not advertise desktop Enter submission");
      await play.page.send("Input.insertText", { text: "telefon" });
      await press(play.page, "Enter", "Enter", 13);
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "telefon", "touch-sized Enter must leave the non-empty draft unsent");
      assert.equal(await turnRequestCount(), 0);
      await clearDraft();
    } else {
      assert.notEqual(await play.page.evaluate("getComputedStyle(document.querySelector('[data-testid=\"desktop-enter-hint\"]')).display"), "none");
      await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').focus()");
      await press(play.page, "Enter", "Enter", 13);
      assert.equal(await turnRequestCount(), 0, "Enter outside the message box must not submit");
      await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
      await play.page.send("Input.insertText", { text: "satır bir" });
      await play.page.evaluate("window.__shiftEnterPrevented = null; window.addEventListener('keydown', event => { if (event.key === 'Enter' && event.shiftKey) window.__shiftEnterPrevented = event.defaultPrevented; }, { once: true });");
      await press(play.page, "Enter", "Enter", 13, 8);
      assert.equal(await turnRequestCount(), 0, "Shift+Enter must not submit");
      assert.equal(await play.page.evaluate("window.__shiftEnterPrevented"), false, "Shift+Enter must retain the browser default instead of being intercepted");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "satır bir", "the fixture must not fake a Shift+Enter newline");
      assert.equal(await turnRequestCount(), 0);
      await clearDraft();
      await play.page.send("Input.insertText", { text: "   " });
      await press(play.page, "Enter", "Enter", 13);
      assert.equal(await turnRequestCount(), 0, "whitespace-only Enter must not submit");
      await clearDraft();
      await play.page.send("Input.insertText", { text: "ime-marker" });
      await play.page.evaluate("(() => { const input=document.querySelector('[data-testid=\"input-player-message\"]'); input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,isComposing:true})); input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})); })()");
      await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,repeat:true}))");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "ime-marker", "IME confirmation and repeated Enter must preserve the non-empty draft");
      assert.equal(await turnRequestCount(), 0, "IME confirmation and repeated Enter must not submit");
      await clearDraft();
    }
    await play.page.send("Input.insertText", { text: draft });
    const draftMeasure = await play.page.evaluate(`(() => { const input = document.querySelector('[data-testid="input-player-message"]'); const button = document.querySelector('[data-testid="button-send-turn"]'); const rect = button.getBoundingClientRect(); return { length: input.value.length, top: rect.top, bottom: rect.bottom, height: innerHeight, scrollY, scrollHeight: document.documentElement.scrollHeight, disabled: button.disabled }; })()`);
    assert.equal(draftMeasure.length, 825);
    assert.equal(draftMeasure.disabled, false);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').options.length"), 3);
    await mouseClick(play.page, '[aria-label=\"Sonraki hamle türü\"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "say");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value.length"), 825, "changing mode must preserve the draft");
    assert.equal(await play.page.evaluate("window.__playFixture.lastTurn"), null, "changing mode must not submit a turn");
    await mouseClick(play.page, '[aria-label=\"Önceki hamle türü\"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "do");
    await mouseClick(play.page, '[data-testid="button-close-composer"]');
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"input-player-message\"]'))"), false);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-composer", "closing should return focus to the reopen button");
    await mouseClick(play.page, '[data-testid=\"button-open-composer\"]');
    await waitForSelector(play.page, '[data-testid=\"input-player-message\"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value.length"), 825, "manual close/reopen must preserve the draft");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "do", "manual close/reopen must preserve the mode");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').maxLength"), 4000);
    await tabTo(play.page, '[data-testid=\"select-interaction-mode\"]');
    await press(play.page, "ArrowDown", "ArrowDown", 40);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "say", "native mode picker must be keyboard operable");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value.length"), 825);
    await mouseClick(play.page, '[aria-label=\"Önceki hamle türü\"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "do");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"panel-story\"] .location-ribbon')"), null, "large duplicate location card must not sit above the story");
    assert.match(await play.page.evaluate("document.querySelector('[data-testid=\"header-location\"]')?.innerText ?? ''"), /Kuzgun Hanı avlusu/, "header must show the real current location");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"panel-story\"] [data-testid=\"exploration-disclosure\"]')"), null, "experimental controls must be removed from the story column");
    await mouseClick(play.page, '[data-testid="button-close-composer"]');
    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-world\"]').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="button-open-world"]');
    await waitForSelector(play.page, '[data-testid="world-experimental"] > summary');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"]').open"), false, "experimental controls must default closed");
    assert.match(await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"] > summary')?.innerText ?? ''"), /Keşif ve yolculuk/i);
    const beforeExperimentalToggle = await play.page.evaluate("({requests:window.__playFixture.apiRequests.length,state:window.__playFixture.stateSnapshot(),draft:document.querySelector('[data-testid=\"input-player-message\"]')?.value ?? null,lastTurn:window.__playFixture.lastTurn})");
    await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"] > summary').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="world-experimental"] > summary');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"]').open"), true);
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"exploration-disclosure\"]'))"), true);
    const experimentalLayout = await play.page.evaluate("(() => { const content=document.querySelector('.world-experimental-content'); const r=content.getBoundingClientRect(); return { width:r.width, scrollWidth:content.scrollWidth, clientWidth:content.clientWidth, overflowY:getComputedStyle(content).overflowY }; })()");
    assert.ok(experimentalLayout.width > 0 && experimentalLayout.scrollWidth <= experimentalLayout.clientWidth, `experimental controls overflow horizontally: ${JSON.stringify(experimentalLayout)}`);
    assert.equal(experimentalLayout.overflowY, "visible", "experimental controls must not be trapped in a narrow inner scroll box");
    if (viewport.width === 390 || viewport.width === 1920) await saveScreenshot(play.page, `world-experimental-open-${viewport.width}.jpg`);
    assert.equal(await play.page.evaluate("window.__playFixture.apiRequests.length"), beforeExperimentalToggle.requests, "show/hide must not call any API");
    assert.equal(await play.page.evaluate("window.__playFixture.stateSnapshot()"), beforeExperimentalToggle.state, "show/hide must not change campaign mechanics/state");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]')?.value ?? null"), beforeExperimentalToggle.draft, "show/hide must preserve the draft state");
    assert.equal(await play.page.evaluate("window.__playFixture.lastTurn"), beforeExperimentalToggle.lastTurn, "show/hide must not submit a turn");
    await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"] > summary').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="world-experimental"] > summary');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"]').open"), false);
    assert.equal(await play.page.evaluate("window.__playFixture.apiRequests.length"), beforeExperimentalToggle.requests);
    assert.equal(await play.page.evaluate("window.__playFixture.stateSnapshot()"), beforeExperimentalToggle.state);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]')?.value ?? null"), beforeExperimentalToggle.draft);
    await press(play.page, "Escape", "Escape", 27);
    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-composer\"]').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="button-open-composer"]');
    await waitForSelector(play.page, '[data-testid="input-player-message"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value.length"), 825, "reopening after the world panel preserves the existing draft");
    if (viewport.height >= 800) assert.ok(draftMeasure.bottom <= viewport.height, `Gönder is not visible without scrolling at ${viewport.width}px`);
    else {
      await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').scrollIntoView({ block: 'center' })");
      assert.ok(await play.page.evaluate("(() => { const r = document.querySelector('[data-testid=\"button-send-turn\"]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight })()"));
    }
    if (viewport.width === 390) {
      await play.page.send("Emulation.setDeviceMetricsOverride", { width:390, height:420, deviceScaleFactor:1, mobile:true });
      await delay(250);
      await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus(); document.querySelector('[data-testid=\"button-send-turn\"]').scrollIntoView({ block:'end' })");
      const keyboardMeasure = await play.page.evaluate("(() => { const r=document.querySelector('[data-testid=\"button-send-turn\"]').getBoundingClientRect(); return { viewport:innerHeight, top:r.top, bottom:r.bottom, visible:r.top>=0&&r.bottom<=innerHeight, visualViewport:visualViewport?.height }; })()");
      assert.equal(keyboardMeasure.visible, true, `send control obscured in keyboard-height viewport: ${JSON.stringify(keyboardMeasure)}`);
      metrics.push({ viewport:{width:390,height:420}, keyboardViewportSimulation:keyboardMeasure, note:"Headless browser: reduced mobile viewport height; OS keyboard itself is not available." });
      await saveScreenshot(play.page, "play-keyboard-viewport-390.jpg");
      await play.page.send("Emulation.setDeviceMetricsOverride", { width:390, height:844, deviceScaleFactor:1, mobile:true });
      await delay(100);
    }
    await saveScreenshot(play.page, `play-${viewport.width}x${viewport.height}-draft.jpg`);
    await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-send-turn");
    let preservedScrollTop = null;
    if (viewport.width > 760) {
      if (viewport.width >= 1440) {
        await mouseWheel(play.page, '[data-testid="transcript-scroll"]', -1200);
        await waitForValue(play.page, "(() => { const n=document.querySelector('[data-testid=\"transcript-scroll\"]'); return n.scrollTop < n.scrollHeight-n.clientHeight-20; })()");
        preservedScrollTop = await play.page.evaluate("document.querySelector('[data-testid=\"transcript-scroll\"]').scrollTop");
      }
      await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
      await press(play.page, "Enter", "Enter", 13, 0, false);
    } else {
          await mouseClick(play.page, '[data-testid="button-send-turn"]');
    }
    await waitForValue(play.page, "window.__playFixture.lastTurn?.message?.length === 825");
    await waitForValue(play.page, "Array.from(document.querySelectorAll('.story-text')).some(node => node.innerText.includes('Yankı:'))");
    await waitForValue(play.page, "document.querySelector('[data-testid=\"input-player-message\"]')?.value === ''");
    assert.equal(await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"button-open-composer\"]'))"), false, "a turn leaves the input in place");
    assert.equal(await play.page.evaluate("Array.from(document.querySelectorAll('.player-entry')).at(-1)?.querySelector('.player-text')?.textContent"), draft, "the transcript must show the original player words verbatim");
    assert.match(await play.page.evaluate("Array.from(document.querySelectorAll('.player-entry')).at(-1)?.querySelector('.player-label')?.innerText ?? ''"), /Hamlen/i);
    if (preservedScrollTop !== null) {
      // The cleared draft shrinks the input, so the story region grows a line or two; the reader stays where they were.
      assert.ok(Math.abs(await play.page.evaluate("document.querySelector('[data-testid=\"transcript-scroll\"]').scrollTop") - preservedScrollTop) <= 120, "a new response must not jump away from history being read");
      await waitForSelector(play.page, '[data-testid=\"button-new-response\"]');
      assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "input-player-message", "new responses must leave the focus in the input");
      await mouseClick(play.page, '[data-testid="button-new-response"]');
      await waitForValue(play.page, "(() => { const a=document.querySelector('[data-testid=\"transcript-scroll\"]'); const t=Array.from(document.querySelectorAll('.story-entry')).at(-1)?.getBoundingClientRect(); const r=a.getBoundingClientRect(); return Boolean(t&&t.bottom>r.top&&t.top<r.bottom&&a.scrollTop>0); })()");
      assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "input-player-message", "pointer jump must preserve the existing focus");
    }

    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-character\"]').scrollIntoView({block:'center'})");
    await mouseClick(play.page, '[data-testid="button-open-character"]');
    await waitForSelector(play.page, '[role="dialog"][aria-modal="true"]');
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-close-drawer");
    const identityMeasure = await play.page.evaluate("(() => { const p=document.querySelector('[data-testid=\"character-identity-notes\"]'); const r=p.getBoundingClientRect(); return {width:r.width, scrollWidth:p.scrollWidth, clientWidth:p.clientWidth}; })()");
    assert.ok(identityMeasure.width >= 250, `character identity box too narrow: ${JSON.stringify(identityMeasure)}`);
    await play.page.evaluate("document.querySelector('[role=\"dialog\"]').scrollTop=document.querySelector('[role=\"dialog\"]').scrollHeight");
    assert.equal(await play.page.evaluate("(() => { const r=document.querySelector('[data-testid=\"button-close-drawer\"]').getBoundingClientRect(); return r.top>=0&&r.bottom<=innerHeight; })()"), true, "drawer close control must remain visible while scrolled");
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("!!document.activeElement?.closest('[role=\"dialog\"]')"), true);
    if (viewport.width === 390) await saveScreenshot(play.page, "character-panel-390.jpg");
    await press(play.page, "Escape", "Escape", 27);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-character");

    await play.page.evaluate("document.querySelector('[data-testid=\"button-open-world\"]').scrollIntoView({block:'center'})");
    await touchTap(play.page, '[data-testid="button-open-world"]');
    await waitForSelector(play.page, '[role="dialog"][aria-modal="true"]');
    assert.equal(await play.page.evaluate("document.querySelector('[role=\"dialog\"]').getAttribute('aria-label')"), "Dünyanın çevresi");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"tab-world\"]')?.getAttribute('aria-selected')"), "true");
    if (viewport.width === 1440) {
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"world-experimental\"]')?.open ?? false"), false);
      await play.page.evaluate("document.querySelector('[data-testid=\"button-close-drawer\"]').focus()");
      const reverseWorldWrap = await play.page.evaluate("(() => { const event=new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}); document.activeElement?.dispatchEvent(event); return {prevented:event.defaultPrevented,inside:!!document.activeElement?.closest('[role=\"dialog\"]'),experimentalOpen:document.querySelector('[data-testid=\"world-experimental\"]')?.open??false}; })()");
      assert.equal(reverseWorldWrap.prevented, true, "Shift+Tab at the first visible World control is trapped");
      assert.equal(reverseWorldWrap.inside, true, "World-tab focus stays inside the drawer");
      assert.equal(reverseWorldWrap.experimentalOpen, false, "focus wrapping is verified with Experimental closed");
    }
    await play.page.evaluate("document.querySelector('[data-testid=\"tab-world\"]').focus()");
    await press(play.page, "ArrowRight", "ArrowRight", 39);
    assert.equal(await play.page.evaluate("document.activeElement?.id"), "tab-npcs");
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('aria-selected')"), "true");
    if (viewport.width === 1440) {
      const scrollBefore = await play.page.evaluate("({page:document.scrollingElement.scrollTop,shell:document.querySelector('.play-shell').scrollTop})");
      const outsidePoint = await play.page.evaluate("(() => { const d=document.querySelector('[role=\"dialog\"]').getBoundingClientRect(); return {x:d.left>40?5:innerWidth-5,y:d.top>80?Math.min(innerHeight-5,d.top+40):innerHeight-5}; })()");
      await mouseWheelAt(play.page, outsidePoint.x, outsidePoint.y, 700);
      await delay(100);
      assert.deepEqual(await play.page.evaluate("({page:document.scrollingElement.scrollTop,shell:document.querySelector('.play-shell').scrollTop})"), scrollBefore, "wheel input outside the world drawer must not scroll the background");

      const firstIsClose = await play.page.evaluate("(() => { const d=document.querySelector('[role=\"dialog\"]'); const s='button:not([disabled]):not([tabindex=\"-1\"]),a[href]:not([tabindex=\"-1\"]),input:not([disabled]):not([tabindex=\"-1\"]),select:not([disabled]):not([tabindex=\"-1\"]),textarea:not([disabled]):not([tabindex=\"-1\"]),summary:not([tabindex=\"-1\"]),[tabindex]:not([tabindex=\"-1\"])'; const a=[...d.querySelectorAll(s)].filter(e=>!e.disabled&&e.getClientRects().length); return a[0]===d.querySelector('[data-testid=\"button-close-drawer\"]'); })()");
      assert.equal(firstIsClose, true);
      await play.page.evaluate("document.querySelector('[data-testid=\"button-close-drawer\"]').focus()");
      const focusableCount = await play.page.evaluate("(() => { const d=document.querySelector('[role=\"dialog\"]'); const s='button:not([disabled]):not([tabindex=\"-1\"]),a[href]:not([tabindex=\"-1\"]),input:not([disabled]):not([tabindex=\"-1\"]),select:not([disabled]):not([tabindex=\"-1\"]),textarea:not([disabled]):not([tabindex=\"-1\"]),summary:not([tabindex=\"-1\"]),[tabindex]:not([tabindex=\"-1\"])'; return [...d.querySelectorAll(s)].filter(e=>!e.disabled&&e.getClientRects().length).length; })()");
      let focusTrail = [];
      for (let i=0; i<focusableCount-1; i++) {
        await press(play.page, "Tab", "Tab", 9);
        const focusState = await play.page.evaluate("(() => { const a=document.activeElement; return {inside:Boolean(a?.closest('[role=\"dialog\"]')),hidden:Boolean(a?.closest('details:not([open]) .world-experimental-content'))}; })()");
        assert.equal(focusState.inside, true, "Tab focus must stay in the drawer");
        assert.equal(focusState.hidden, false, "closed experimental controls must not receive focus");
        focusTrail.push(await play.page.evaluate("(() => { const a=document.activeElement; return a?.getAttribute('data-testid') || a?.id || a?.getAttribute('aria-label') || `${a?.tagName}:${(a?.innerText||'').trim().slice(0,32)}`; })()"));
      }
      assert.ok(new Set(focusTrail).size >= Math.min(4, focusableCount-1), `forward Tab traversal must visit real visible controls; focusable=${focusableCount}, trail=${JSON.stringify(focusTrail)}`);
      await press(play.page, "Tab", "Tab", 9);
      assert.equal(await play.page.evaluate("document.activeElement === document.querySelector('[data-testid=\"button-close-drawer\"]')"), true, "Tab must wrap from the last focusable control");
      const reverseFocus = await play.page.evaluate("(() => { const event=new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}); document.activeElement?.dispatchEvent(event); return {prevented:event.defaultPrevented,focus:document.activeElement?.getAttribute('data-testid')||document.activeElement?.id}; })()");
      assert.equal(reverseFocus.prevented, true, "Shift+Tab at the first drawer control must be trapped");
      assert.equal(reverseFocus.focus, focusTrail.at(-1), "Shift+Tab must return focus to the last visible control");
    }
    await press(play.page, "Tab", "Tab", 9);
    assert.equal(await play.page.evaluate("!!document.activeElement?.closest('[role=\"dialog\"]')"), true);
    if (viewport.width === 390 || viewport.width === 1440) await saveScreenshot(play.page, `world-panel-${viewport.width}.jpg`);
    await press(play.page, "Escape", "Escape", 27);
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-world");
    const beforeSuggestionRequests = await turnRequestCount();
    const suggestionSelector = '[data-testid="button-suggestion-talk-npc-marek"]';
    const openSceneIdeas = async () => {
      await waitForSelector(play.page, '[data-testid="scene-ideas"] > summary');
      if (!await play.page.evaluate("document.querySelector('[data-testid=\"scene-ideas\"]')?.open")) {
        await play.page.evaluate("document.querySelector('[data-testid=\"scene-ideas\"] > summary')?.scrollIntoView({block:'center'})");
        await mouseClick(play.page, '[data-testid="scene-ideas"] > summary');
      }
      await waitForValue(play.page, "document.querySelector('[data-testid=\"scene-ideas\"]')?.open === true");
      await play.page.evaluate("document.querySelector('[data-testid=\"button-suggestion-talk-npc-marek\"]')?.scrollIntoView({block:'center'})");
    };
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"scene-ideas\"]')?.open"), false, "scene ideas stay closed until the player opens them");
    await openSceneIdeas();
    await mouseClick(play.page, suggestionSelector);
    await waitForSelector(play.page, '[data-testid="input-player-message"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "Marek ile konuşmak istiyorum.", "a suggestion opens a previously closed composer with the selected draft");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "say");
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "input-player-message");
    assert.equal(await turnRequestCount(), beforeSuggestionRequests, "choosing a suggestion does not submit");
    await openSceneIdeas();
    await mouseClick(play.page, suggestionSelector);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "Marek ile konuşmak istiyorum.", "a suggestion replaces the draft when the composer was already open");
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "say");
    assert.equal(await turnRequestCount(), beforeSuggestionRequests, "replacing a draft does not submit");
    await clearDraft();
    await tabTo(play.page, '[data-testid="select-interaction-mode"]');
    await press(play.page, "ArrowUp", "ArrowUp", 38);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "do", "subsequent turn checks begin with their own draft and mode");
    await tabTo(play.page, '[data-testid="button-open-panel-journal"]');
    assert.equal(await play.page.evaluate("document.activeElement?.getAttribute('data-testid')"), "button-open-panel-journal");
    await press(play.page, " ", "Space", 32);
    await waitForSelector(play.page, '[data-testid="summary-journal"]');
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"button-open-panel-journal\"]')?.getAttribute('aria-expanded')"), "true");
    assert.equal(await play.page.evaluate("document.querySelector('[role=\"dialog\"]')"), null, "sidebar summary must not open a modal");
    if (viewport.width === 1920) await saveScreenshot(play.page, "rail-summary-journal-1920.jpg");
    await press(play.page, " ", "Space", 32);
    assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"button-open-panel-journal\"]')?.getAttribute('aria-expanded')"), "false");
    if (viewport.width === 390) {
      const enterText = async (text, mode) => {
        if (!await play.page.evaluate("Boolean(document.querySelector('[data-testid=\"input-player-message\"]'))")) {
          await play.page.evaluate("document.querySelector('[data-testid=\"button-open-composer\"]').click()");
          await waitForSelector(play.page, '[data-testid=\"input-player-message\"]');
        }
        if (mode === 'say') {
          await play.page.evaluate("document.querySelector('[aria-label=\"Sonraki hamle türü\"]').scrollIntoView({block:'center'})");
          await mouseClick(play.page, '[aria-label=\"Sonraki hamle türü\"]');
        }
        await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
        await play.page.send("Input.insertText", { text });
        await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').click()");
      };
      await enterText("normal-marker");
      await waitForValue(play.page, "Array.from(document.querySelectorAll('.story-text')).some(node => node.innerText.includes('Yankı: normal-marker'))");

      await play.page.evaluate("window.__playFixture.holdNext()");
      await enterText("pending-marker");
      await waitForValue(play.page, "document.querySelector('[data-testid=\"button-send-turn\"]').disabled");
      await waitForSelector(play.page, '[data-testid="pending-turn-status"]');
      await mouseWheel(play.page, '[data-testid="transcript-scroll"]', -1000);
      await delay(100);
      const mobileReadingPosition = await play.page.evaluate("({scrollY, transcriptTop:document.querySelector('[data-testid=\"transcript-scroll\"]').scrollTop})");
      await saveScreenshot(play.page, "pending-turn-390.jpg");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"pending-turn-status\"]').innerText.trim()"), "Hamlen işleniyor");
      assert.equal(await play.page.evaluate("getComputedStyle(document.querySelector('.pending-turn-mark .ouroboros')).animationDuration"), "22s");
      await play.page.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
      assert.equal(await play.page.evaluate("getComputedStyle(document.querySelector('.pending-turn-mark .ouroboros')).animationName"), "none", "reduced motion should show the mark without animation");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"button-close-composer\"]').disabled"), true);
      const pendingRequests = await play.page.evaluate("window.__playFixture.apiRequests.filter((request) => request.path.endsWith('/turn') && request.method === 'POST').length");
      await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').click()");
      await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}))");
      assert.equal(await play.page.evaluate("window.__playFixture.apiRequests.filter((request) => request.path.endsWith('/turn') && request.method === 'POST').length"), pendingRequests, "pending request must block a duplicate submit");
      assert.equal(await play.page.evaluate("Array.from(document.querySelectorAll('.story-text')).some(node => node.innerText.includes('Yankı: pending-marker'))"), false);
      await play.page.evaluate("window.__playFixture.release()");
      await waitForValue(play.page, "Array.from(document.querySelectorAll('.story-text')).some(node => node.innerText.includes('Yankı: pending-marker'))");
      await waitForValue(play.page, "!document.querySelector('[data-testid=\"pending-turn-status\"]')");
      assert.equal(await play.page.evaluate("window.scrollY"), mobileReadingPosition.scrollY, "closing the composer after a mobile response must not scroll the reader");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"transcript-scroll\"]').scrollTop"), mobileReadingPosition.transcriptTop, "a response must preserve the transcript's mobile reading position");
      await waitForSelector(play.page, '[data-testid="button-new-response"]');

      await play.page.evaluate("window.__playFixture.failNext()");
      await enterText("retry-marker", "say");
      await waitForValue(play.page, "!!document.querySelector('[data-testid=\"status-error\"]')");
      await waitForValue(play.page, "!document.querySelector('[data-testid=\"pending-turn-status\"]')");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "retry-marker");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"select-interaction-mode\"]').value"), "say", "error must preserve the selected mode");
      const failedActionId = await play.page.evaluate("window.__playFixture.lastTurn.action_id");
      // R02: the unclear failure offers an explicit retry; pressing Send again must not send a second move.
      await waitForSelector(play.page, '[data-testid="button-retry-turn"]');
      const requestsBeforeSend = await play.page.evaluate("window.__playFixture.apiRequests.filter((request) => request.path.endsWith('/turn') && request.method === 'POST').length");
      await play.page.evaluate("document.querySelector('[data-testid=\"button-send-turn\"]').click()");
      assert.equal(await play.page.evaluate("window.__playFixture.apiRequests.filter((request) => request.path.endsWith('/turn') && request.method === 'POST').length"), requestsBeforeSend, "a new move must not go out while the previous one is unresolved");
      assert.equal(await play.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "retry-marker", "the draft is kept");
      await play.page.evaluate("document.querySelector('[data-testid=\"button-retry-turn\"]').click()");
      await waitForValue(play.page, "Array.from(document.querySelectorAll('.story-text')).some(node => node.innerText.includes('Yankı: retry-marker'))");
      assert.equal(await play.page.evaluate("window.__playFixture.lastTurn.action_id"), failedActionId, "retry must retain the original action id");
      await waitForValue(play.page, "document.querySelector('[data-testid=\"input-player-message\"]')?.value === ''");
    }
    const errors = play.page.exceptions;
    assert.deepEqual(errors, []);
    metrics.push({ viewport, longStory, draft: draftMeasure, menu: menuMeasure, jsExceptions: errors });
    play.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${play.targetId}`);
  }

  const empty = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play&empty-state=1`, 1920, 1080);
  await waitForSelector(empty.page, '[data-testid=\"app-session\"]');
  await mouseClick(empty.page, '[data-testid=\"button-open-panel-npcs\"]');
  assert.equal(await empty.page.evaluate("document.querySelector('[data-testid=\"summary-npcs\"]')?.innerText"), "Bu sahnede görünür kişi yok.");
  await mouseClick(empty.page, '[data-testid=\"button-open-panel-combat\"]');
  assert.equal(await empty.page.evaluate("document.querySelector('[data-testid=\"summary-combat\"]')?.innerText"), "Çatışma yok.");
  assert.equal(await empty.page.evaluate("window.__playFixture.lastTurn"), null);
  empty.page.close();

  const touchDesktop = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play&touch=1`, 1440, 900);
  await waitForSelector(touchDesktop.page, '[data-testid="app-session"]');
  assert.equal(await touchDesktop.page.evaluate("navigator.maxTouchPoints"), 1);
  await waitForSelector(touchDesktop.page, '[data-testid="input-player-message"]');
  await touchDesktop.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').focus()");
  assert.equal(await touchDesktop.page.evaluate("Boolean(document.querySelector('[data-testid=\"desktop-enter-hint\"]'))"), false, "touch-enabled desktop must hide the Enter hint while the composer is open");
  await touchDesktop.page.send("Input.insertText", { text: "touch-enter-marker" });
  await press(touchDesktop.page, "Enter", "Enter", 13, 0, false);
  assert.equal(await touchDesktop.page.evaluate("window.__playFixture.apiRequests.filter(request=>request.path.endsWith('/turn')&&request.method==='POST').length"), 0, "touch-enabled desktop Enter must not submit");
  assert.equal(await touchDesktop.page.evaluate("document.querySelector('[data-testid=\"input-player-message\"]').value"), "touch-enter-marker", "touch-enabled desktop Enter must preserve the draft");
  assert.deepEqual(touchDesktop.page.exceptions, []);
  touchDesktop.page.close();

  const mobileScroll = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play`, 390, 844);
  await waitForSelector(mobileScroll.page, '[data-testid=\"app-session\"]');
  const pageBeforeDrawer = await mobileScroll.page.evaluate("(() => { const sc=document.scrollingElement; const max=sc.scrollHeight-sc.clientHeight; if(max<120) return {max,top:sc.scrollTop}; sc.scrollTop=160; document.querySelector('[data-testid=\"button-open-character\"]').click(); return {max,top:sc.scrollTop}; })()");
  assert.ok(pageBeforeDrawer.max > 0, `mobile narrative page must genuinely scroll: ${JSON.stringify(pageBeforeDrawer)}`);
  assert.ok(pageBeforeDrawer.top > 0, `test must start from a nonzero page scroll: ${JSON.stringify(pageBeforeDrawer)}`);
  await waitForSelector(mobileScroll.page, '[role=\"dialog\"][aria-modal=\"true\"]');
  const modalCanScroll = await mobileScroll.page.evaluate("(() => { const d=document.querySelector('[role=\"dialog\"]'); return {max:d.scrollHeight-d.clientHeight, top:d.scrollTop}; })()");
  assert.ok(modalCanScroll.max > 0, `mobile drawer content must have an internal scroll range: ${JSON.stringify(modalCanScroll)}`);
  await touchSwipeAt(mobileScroll.page, 190, 640, 190, 440);
  await delay(80);
  assert.ok(await mobileScroll.page.evaluate("document.querySelector('[role=\"dialog\"]').scrollTop > 0"), "touch scrolling remains available inside the drawer");
  const pageDuringDrawer = await mobileScroll.page.evaluate("document.scrollingElement.scrollTop");
  await mouseWheelAt(mobileScroll.page, 190, 20, 550);
  await touchSwipeAt(mobileScroll.page, 190, 30, 190, 5);
  await delay(100);
  assert.equal(await mobileScroll.page.evaluate("document.scrollingElement.scrollTop"), pageDuringDrawer, "wheel and touch gestures outside the drawer must not move the long mobile page");
  await press(mobileScroll.page, "Escape", "Escape", 27);
  assert.equal(await mobileScroll.page.evaluate("document.scrollingElement.scrollTop"), pageBeforeDrawer.top, "closing restores the page's previous scroll position");
  await mouseWheelAt(mobileScroll.page, 190, 700, 240);
  await delay(80);
  assert.notEqual(await mobileScroll.page.evaluate("document.scrollingElement.scrollTop"), pageBeforeDrawer.top, "page scrolling works again after the drawer closes");
  mobileScroll.page.close();

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    const combat = await createPage(browserPort, `${baseUrl}${fixturePath}?screen=play&combat=1`, viewport.width, viewport.height);
    await waitForSelector(combat.page, '[data-testid="button-open-active-combat"]');
    assert.equal(await combat.page.evaluate("document.querySelector('[data-testid=\"header-character-hp\"]')?.textContent.trim()"), "12 / 12");
    assert.match(await combat.page.evaluate("document.querySelector('[data-testid=\"button-open-active-combat\"]')?.innerText ?? ''"), /12\/12 CAN/);
    await saveScreenshot(combat.page, `combat-hp-${viewport.width}.jpg`);
    metrics.push({ viewport, combatHp: await combat.page.evaluate("({header:document.querySelector('[data-testid=\"header-character-hp\"]')?.innerText,combat:document.querySelector('[data-testid=\"button-open-active-combat\"]')?.innerText})") });
    combat.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${combat.targetId}`);
  }

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    const creation = await createPage(browserPort, `${baseUrl}/tests/character-creation-fixture/`, viewport.width, viewport.height);
    await waitForSelector(creation.page, '[data-testid="screen-character-creation"]');
    await delay(800);
    assert.equal(await creation.page.evaluate("getComputedStyle(document.querySelector('.character-creation-screen')).backgroundColor"), "rgb(23, 26, 26)");
    if (viewport.width === 390) await saveScreenshot(creation.page, "character-creation-390.jpg");
    if (viewport.width === 1440) await saveScreenshot(creation.page, "character-creation-1440.jpg");
    await creation.page.evaluate("document.querySelector('.cc-portrait-grid .cc-choice-card').click()");
    assert.equal(await creation.page.evaluate("!!document.querySelector('.cc-portrait-grid .cc-choice-card.selected')"), true);
    await creation.page.evaluate("document.querySelector('.cc-nav-next').click()");
    assert.equal(await creation.page.evaluate("document.querySelector('.cc-step-title-text')?.innerText"), "Geçmişini Seç");
    await creation.page.evaluate("document.querySelector('.cc-nav-prev').click()");
    assert.equal(await creation.page.evaluate("document.querySelector('.cc-step-title-text')?.innerText"), "Sınıfını Seç");
    assert.equal(await creation.page.evaluate("!!document.querySelector('.cc-portrait-grid .cc-choice-card.selected')"), true);
    await creation.page.evaluate("document.querySelector('[data-testid=\"button-back-character-creation\"]').click()");
    assert.equal(await creation.page.evaluate("window.__creationFixture.backCount"), 1);
    await creation.page.evaluate("document.querySelector('[data-testid=\"button-mode-random\"]').click()");
    const created = await creation.page.evaluate("window.__creationFixture.created");
    assert.equal(created?.character?.mode, "random");
    assert.equal(created?.campaignStart?.starting_location_id, "waterdeep");
    assert.equal(created?.deathMode, "PERMADEATH");
    assert.deepEqual(creation.page.exceptions, []);
    metrics.push({ viewport, characterCreation: "selection, next/back, return and random-create callback verified" });
    creation.page.close();
    await fetch(`http://127.0.0.1:${browserPort}/json/close/${creation.targetId}`);
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
  const finalValue = await page.evaluate(expression);
  const state = await page.evaluate(`(() => ({ button: document.querySelector('[data-testid="button-send-turn"]')?.outerHTML, draft: document.querySelector('[data-testid="input-player-message"]')?.value, error: document.querySelector('[data-testid="status-error"]')?.innerText, lastTurn: window.__playFixture?.lastTurn }))()`);
  throw new Error(`Timed out waiting for ${expression}; value=${JSON.stringify(finalValue)}; state=${JSON.stringify(state)}`);
}
