// C06 in a real browser: the real GameBrowser behind the real account-boundary helpers, a scripted API whose replies can be
// held while the world moves on. Exercises the production paths (not source text): level-up choice, pending retry and canonical recovery use the real UI; old lifetime replies cannot write into a new one.
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
const fixturePath = "/tests/c06-level4-fixture/";

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
  const log = await page.evaluate("JSON.stringify(window.__c06?.log().slice(-8)) + ' ids=' + [...document.querySelectorAll('[data-testid]')].map((n) => n.dataset.testid).join(',')");
  throw new Error(`Timed out: ${what}; body=${body}; log=${log}; exceptions=${JSON.stringify(page.exceptions)}`);
}

const click = (page, selector) => page.evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const cache = (page) => page.evaluate("window.__c06.cache()");
const world = (page) => page.evaluate("window.__c06.world()");

async function sendTurn(page, text) {
  if (await page.evaluate("!!document.querySelector('[data-testid=\"button-open-composer\"]')")) await click(page, '[data-testid="button-open-composer"]');
  await until(page, "document.querySelector('#player-message')", "composer textarea");
  await page.evaluate("document.querySelector('#player-message').focus()");
  await page.send("Input.insertText", { text });
  await until(page, "!document.querySelector('[data-testid=\"button-send-turn\"]').disabled", "send enabled");
  await click(page, '[data-testid="button-send-turn"]');
}

test("C06 real GameBrowser with scripted transport (not backend E2E)", async (t) => {
  const tempProfile = await mkdtemp(path.join(os.tmpdir(), "ai-dnd-c06-"));
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

  const posts = page => page.evaluate("window.__c06.requests().filter(r=>r.method==='POST' && r.path.endsWith('/level-up'))");
  const pending = page => page.evaluate('window.__c06.pending()');
  const open = async page => {await until(page,"document.querySelector('[data-testid=\"button-open-level-up\"]')",'earned level-up affordance');await click(page,'[data-testid="button-open-level-up"]');await until(page,"document.querySelector('[data-testid=\"level-up-cantrip\"]')",'authoritative choice options');};
  const choose = async page => {
    for(const [id,value] of [['level-up-cantrip','Shocking Grasp'],['level-up-prepared','Mage Armor']])await page.evaluate(`(()=>{const n=document.querySelector('[data-testid="${id}"]');const select=n.matches('select')?n:n.querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(select,${JSON.stringify(value)});select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await click(page,'[data-testid="level-up-confirm-con"]');
    await until(page,"!document.querySelector('[data-testid=\"button-confirm-level-up\"]').disabled",'explicit complete choice confirmation');
  };
  // Removing cancel-before-send, explicit confirmation, or the exact choice payload must break this.
  await t.test('selection requires explicit CON confirmation; cancelling a draft sends no POST',async()=>{
    const page=await newPage();try{await open(page);assert.equal(await page.evaluate("document.querySelector('[data-testid=\"button-confirm-level-up\"]').disabled"),true);await choose(page);await click(page,'[data-testid="button-cancel-level-up"]');assert.equal((await posts(page)).length,0);assert.equal((await pending(page)).length,0);assert.equal((await cache(page)).con,14);}finally{page.close();}
  });
  await t.test('repeated confirmation sends one immutable server choice request and renders canonical state',async()=>{
    const page=await newPage();try{await open(page);await choose(page);await page.evaluate("window.__c06.hold('apply')");await page.evaluate("(()=>{const b=document.querySelector('[data-testid=\"button-confirm-level-up\"]');b.click();b.click();})()");await until(page,"window.__c06.requests().some(r=>r.method==='POST'&&r.path.endsWith('/level-up'))",'apply sent');assert.equal((await posts(page)).length,1);const request=(await posts(page))[0].body;assert.match(request.action_id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);assert.deepEqual({...request,action_id:'ID'},{action_id:'ID',campaign_id:'11111111-1111-4111-8111-111111111111',expected_revision:7,target_level:4,choices:{cantrips:['Shocking Grasp'],prepared_spells:['Mage Armor'],asi:{feat:'Ability Score Improvement',increase:{constitution:2}}}});await page.evaluate("window.__c06.release('apply')");await until(page,"window.__c06.cache()?.con===16 && window.__c06.pending().length===0",'canonical applied result');assert.deepEqual(await cache(page),{hp:26,con:16,maxHp:30});assert.deepEqual(page.exceptions,[]);}finally{page.close();}
  });
  // Wrong retry dispatch, minting an ID on retry, or rebuilding options rather than reusing the request fails this.
  await t.test('lost acknowledgement survives remount and retry uses exactly the original ID and payload',async()=>{
    const page=await newPage();try{await open(page);await choose(page);await page.evaluate('window.__c06.loseApply()');await click(page,'[data-testid="button-confirm-level-up"]');await until(page,"document.querySelector('[data-testid=\"button-retry-turn\"]')",'unresolved retry notice');const original=(await posts(page))[0];assert.equal((await pending(page)).length,1);await page.evaluate("window.__c06.switchIdentity('owner-a:session-2')");await page.evaluate('window.__c06.openPlay()');await until(page,"document.querySelector('[data-testid=\"button-retry-turn\"]')",'same-owner retained pending retry');await click(page,'[data-testid="button-retry-turn"]');await until(page,"window.__c06.requests().filter(r=>r.method==='POST'&&r.path.endsWith('/level-up')).length===2",'exact retry sent');assert.deepEqual((await posts(page))[1],original);await until(page,'window.__c06.pending().length===0','receipt reconciled');}finally{page.close();}
  });
  // Clearing on a durable applied verdict alone loses state; canonical read must succeed first.
  await t.test('applied/null response retains pending on failed canonical read and closes only after canonical recovery',async()=>{
    const page=await newPage();try{await open(page);await choose(page);await page.evaluate('window.__c06.loseApply(); window.__c06.failCanonical(true)');await click(page,'[data-testid="button-confirm-level-up"]');await until(page,"document.querySelector('[data-testid=\"button-check-action\"]')",'check durable status');await click(page,'[data-testid="button-check-action"]');await until(page,"window.__c06.requests().some(r=>r.method==='GET'&&r.path==='/api/game/campaigns/11111111-1111-4111-8111-111111111111')",'canonical read attempted');await delay(300);assert.equal((await pending(page)).length,1);assert.equal((await posts(page)).length,1);await page.evaluate('window.__c06.failCanonical(false)');await click(page,'[data-testid="button-check-action"]');await until(page,'window.__c06.pending().length===0 && window.__c06.cache()?.con===16','canonical result then clear');assert.equal((await posts(page)).length,1);assert.deepEqual(await cache(page),{hp:26,con:16,maxHp:30},'canonical ASI raises max HP without healing');}finally{page.close();}
  });
  await t.test('unknown abandon keeps exact pending identity; only durable not_applied releases it',async()=>{
    const page=await newPage();try{await open(page);await choose(page);await page.evaluate('window.__c06.loseBeforeApply()');await click(page,'[data-testid="button-confirm-level-up"]');await until(page,"document.querySelector('[data-testid=\"button-abandon-action\"]')",'abandon offered');const before=await pending(page);await click(page,'[data-testid="button-abandon-action"]');await until(page,"window.__c06.requests().some(r=>r.path.endsWith('/abandon'))",'abandon queried');await delay(200);assert.deepEqual(await pending(page),before,'unknown is not cancellation');assert.equal((await cache(page)).con,14);await page.evaluate("window.__c06.verdict('not_applied')");await click(page,'[data-testid="button-abandon-action"]');await until(page,'window.__c06.pending().length===0','durable refusal releases pending');assert.equal((await posts(page)).length,1);assert.equal((await cache(page)).con,14);}finally{page.close();}
  });
  await t.test('an unresolved level-up prevents competing play and another level-up POST',async()=>{
    const page=await newPage();try{await open(page);await choose(page);await page.evaluate('window.__c06.loseBeforeApply()');await click(page,'[data-testid="button-confirm-level-up"]');await until(page,"document.querySelector('[data-testid=\"button-retry-turn\"]')",'unresolved action');
      if(await page.evaluate("!!document.querySelector('[data-testid=\"button-open-composer\"]')"))await click(page,'[data-testid="button-open-composer"]');
      await until(page,"document.querySelector('#player-message')",'composer');await page.evaluate("document.querySelector('#player-message').focus()");await page.send('Input.insertText',{text:'Avluyu inceliyorum'});await click(page,'[data-testid="button-send-turn"]');
      const openButton=await page.evaluate("document.querySelector('[data-testid=\"button-open-level-up\"]')?.disabled");assert.equal(openButton,true);await delay(200);assert.equal(await page.evaluate("window.__c06.requests().filter(r=>r.method==='POST'&&r.path.endsWith('/turn')).length"),0);assert.equal((await posts(page)).length,1);assert.equal((await pending(page)).length,1);
    }finally{page.close();}
  });
  for(const [label,transition] of [['owner',"window.__c06.switchIdentity('owner-b:session-2')"],['auth epoch',"window.__c06.switchIdentity('owner-a:session-2')"],['campaign/session','window.__c06.switchCampaign()']]){
    for(const held of ['preview','apply','canonical'])await t.test(`${label} change rejects a stale ${held} reply`,async()=>{
      const page=await newPage();try{
        if(held==='preview'){await until(page,"document.querySelector('[data-testid=\"button-open-level-up\"]')",'open');await page.evaluate("window.__c06.hold('preview')");await click(page,'[data-testid="button-open-level-up"]');await until(page,"window.__c06.requests().some(r=>r.path.endsWith('/level-up'))",'preview held');}
        else{await open(page);await choose(page);await page.evaluate(`window.__c06.hold('${held}')`);await click(page,'[data-testid="button-confirm-level-up"]');await until(page,held==='apply'?"window.__c06.requests().some(r=>r.method==='POST'&&r.path.endsWith('/level-up'))":"window.__c06.requests().some(r=>r.method==='GET'&&r.path==='/api/game/campaigns/11111111-1111-4111-8111-111111111111')",`${held} held`);}
        await page.evaluate('window.__c06.resetWorld()');await page.evaluate(transition);await page.evaluate('window.__c06.openPlay()');await until(page,'window.__c06.cache()?.con===14','new lifetime state');await page.evaluate(`window.__c06.release('${held}')`);
        for(let i=0;i<20;i++){assert.equal((await cache(page))?.con,14,'stale applied response wrote into new lifetime');await delay(50);}
        if(held==='preview')assert.equal(await page.evaluate("!!document.querySelector('[data-testid=\"level-up-cantrip\"]')"),false,'previous lifetime reopened draft');
      }finally{page.close();}
    });
  }
});
