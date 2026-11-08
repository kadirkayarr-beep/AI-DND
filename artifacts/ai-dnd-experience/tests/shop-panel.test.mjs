import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4187';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite, ui, React, render;
before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({ configFile: path.join(process.cwd(), 'vite.config.ts'), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' });
  ui = await vite.ssrLoadModule('/src/components/shop-panel.tsx');
  React = await import('react');
  render = (await import('react-dom/server')).renderToStaticMarkup;
});
after(async () => { await vite?.close(); });

const counter = {
  session_id: 'session', campaign_id: 'campaign', revision: 3, status: 'ready', reason: null,
  vendor: { npc_id: 'barman', name: 'Barmen' },
  lines: [
    { key: 'bira', label: 'bira', unit_cp: 4, stock: 3, discount_cp: 0 },
    { key: 'yemek', label: 'tabak yemek', unit_cp: 30, stock: 12, discount_cp: 0 },
  ],
  purse: { total_cp: 1234, gp: 12, sp: 3, cp: 4 }, seq: 7,
};

function nodes(e) { return Array.isArray(e) ? e.flatMap(nodes) : e && typeof e === 'object' ? [e, ...nodes(e.props?.children)] : []; }
function harness(view = counter, extra = {}) {
  let counts = {}, sent = [], closed = 0;
  const props = () => ({ counter: view, counts, onCounts: next => { counts = next; }, onConfirm: text => sent.push(text), onClose: () => closed++, disabled: false, ...extra });
  const tree = () => nodes(ui.ShopCounterCard(props()));
  const byId = id => tree().find(n => n.props?.['data-testid'] === id);
  return { props, tree, byId, get counts() { return counts; }, sent, get closed() { return closed; } };
}

test('the card shows the server price, stock and purse, and confirm sends the one typed trade line with the fresh total', () => {
  const h = harness();
  const html = render(React.createElement(ui.ShopCounterCard, h.props()));
  assert.match(html, /Bira/);
  assert.match(html, /4 bakır/);
  assert.match(html, /12 altın 3 gümüş 4 bakır/);
  assert.equal(h.byId('button-confirm-shop').props.disabled, true);
  h.byId('shop-more-bira').props.onClick();
  h.byId('shop-more-bira').props.onClick();
  assert.deepEqual(h.counts, { bira: 2 });
  assert.match(render(React.createElement(ui.ShopCounterCard, h.props())), /Onayla \(8 bakır\)/);
  assert.equal(h.byId('button-confirm-shop').props.disabled, false);
  h.byId('button-confirm-shop').props.onClick();
  assert.deepEqual(h.sent, ['/item shop_buy barman bira 2 7 8']);
});

test('steppers stay within stock and zero, and one good is bought per trade', () => {
  const h = harness();
  for (let i = 0; i < 5; i++) h.byId('shop-more-bira').props.onClick();
  assert.deepEqual(h.counts, { bira: 3 });
  assert.equal(h.byId('shop-more-bira').props.disabled, true);
  h.byId('shop-more-yemek').props.onClick();
  assert.deepEqual(h.counts, { yemek: 1 });
  h.byId('shop-less-yemek').props.onClick();
  h.byId('shop-less-yemek').props.onClick();
  assert.deepEqual(h.counts, {});
});

test('a total above the purse cannot be confirmed and says so', () => {
  const h = harness({ ...counter, purse: { total_cp: 5, gp: 0, sp: 0, cp: 5 } });
  h.byId('shop-more-bira').props.onClick();
  h.byId('shop-more-bira').props.onClick();
  assert.equal(h.byId('button-confirm-shop').props.disabled, true);
  assert.match(render(React.createElement(ui.ShopCounterCard, h.props())), /Kesende bu kadar para yok/);
});

test('an unavailable counter shows why, offers only close, and a notice asks again', () => {
  const h = harness({ ...counter, status: 'unavailable', reason: 'no_vendor', vendor: null, lines: [] });
  assert.equal(h.byId('button-confirm-shop'), undefined);
  assert.match(render(React.createElement(ui.ShopCounterCard, h.props())), /Burada sana bir şey satacak kimse yok/);
  h.byId('button-close-shop').props.onClick();
  assert.equal(h.closed, 1);
  const asked = render(React.createElement(ui.ShopCounterCard, harness(counter, { notice: ui.shopReasonText('price_changed') }).props()));
  assert.match(asked, /Fiyat değişti, yeniden onayla/);
});

test('the panel reads what the last turn did from its outcome status and reason, never from an HTTP code', () => {
  const step = ui.shopOutcomeStep;
  assert.equal(step({ action: 'shop_offer', status: 'offer_open' }, false), 'open');
  assert.equal(step({ action: 'shop_offer', status: 'refused' }, false), null);
  assert.equal(step({ action: 'equipment_transaction', status: 'rejected', reason: 'offer_stale' }, true), 'ask_again');
  assert.equal(step({ action: 'equipment_transaction', status: 'rejected', reason: 'price_changed' }, true), 'ask_again');
  assert.equal(step({ action: 'equipment_transaction', status: 'rejected', reason: 'insufficient_funds' }, true), 'refused');
  assert.equal(step({ action: 'equipment_transaction', status: 'resolved' }, true), 'done');
  assert.equal(step({ action: 'equipment_transaction', status: 'resolved' }, false), null);
  assert.equal(step({ action: 'dialogue', status: 'resolved' }, true), 'other');
  assert.equal(step(null, true), 'other');
});

test('an open counter refreshes after a turn it did not send, so a paid card never leaves a stale purse or stock', () => {
  const step = ui.shopOutcomeStep;
  assert.equal(step({ action: 'economic_offer', status: 'resolved' }, false, true), 'refresh');
  assert.equal(step({ action: 'dialogue', status: 'resolved' }, false, true), 'refresh');
  assert.equal(step({ action: 'dialogue', status: 'resolved' }, false, false), null);
  assert.equal(step({ action: 'equipment_transaction', status: 'resolved' }, true, true), 'done');
  assert.equal(step({ action: 'shop_offer', status: 'offer_open' }, false, true), 'open');
});

test('a double press of confirm sends one trade until the gate is reopened', () => {
  const sent = [];
  const gate = ui.createConfirmGate(text => sent.push(text));
  assert.equal(gate.fire('/item shop_buy barman bira 1 7 4'), true);
  assert.equal(gate.fire('/item shop_buy barman bira 1 7 4'), false);
  assert.equal(gate.waiting(), true);
  gate.reopen();
  assert.equal(gate.fire('/item shop_buy barman bira 1 8 4'), true);
  assert.deepEqual(sent, ['/item shop_buy barman bira 1 7 4', '/item shop_buy barman bira 1 8 4']);
});

test('the probe key names the people here, so a counter is looked for only where someone stands', () => {
  assert.equal(ui.shopProbeKey({ location: 'han', npcs: [] }), '');
  assert.equal(ui.shopProbeKey({ location: 'han', npcs: [{ id: 'b', location: 'han' }, { id: 'a', location: 'han' }, { id: 'c', location: 'yol' }] }), 'han:a,b');
});

test('the play screen mounts one counter in the auxiliary pane, outside the drawer, and confirms through the turn submit', async () => {
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  const mount = page.indexOf('<ShopControls');
  assert.ok(mount > 0);
  const ts = await import('typescript');
  const file = ts.createSourceFile('game-browser.tsx', page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const nodes = [];
  const visit = node => { nodes.push(node); ts.forEachChild(node, visit); };
  visit(file);
  const shops = nodes.filter(node => ts.isJsxSelfClosingElement(node) && node.tagName.getText(file) === 'ShopControls');
  assert.equal(shops.length, 1);
  const ancestors = node => { const list = []; for (let p = node.parent; p; p = p.parent) list.push(p); return list; };
  const shop = shops[0];
  const prop = ancestors(shop).find(node => ts.isJsxAttribute(node) && node.name.getText(file) === 'topControls');
  assert.ok(prop, 'counter belongs to topControls');
  assert.equal(prop.parent.parent.tagName.getText(file), 'StoryColumn');
  assert.ok(ancestors(shop).some(node => ts.isBinaryExpression(node) && node.left.getText(file) === 'showsCounter(state, campaignId)'));
  const attributes = Object.fromEntries(shop.attributes.properties.map(node => [node.name.getText(file), node.initializer.expression.getText(file)]));
  assert.equal(attributes.disabled, 'turnSending || undoBusy || Boolean(blockingMutation())');
  assert.equal(attributes.key, '`${currentAccountOwner() ?? LOCAL_OWNER}:${campaignId}:${sessionId}:${panelEpoch}`');
  assert.equal(attributes.sessionId, 'sessionId');
  assert.equal(attributes.campaignId, 'campaignId');
  assert.equal(attributes.probeKey, 'shopProbeKey(state)');
  assert.equal(attributes.outcome, 'visibleLastTurn?.outcome ?? null');
  assert.equal(attributes.outcomeKey, 'visibleLastTurn?.actionId ?? null');
  assert.equal(attributes.onTrade, "(text) => submitTurn(text, undefined, 'do')");
  const content = nodes.filter(node => ts.isJsxExpression(node) && node.expression?.getText(file) === 'topControls');
  assert.equal(content.length, 1);
  assert.ok(ancestors(content[0]).some(node => ts.isJsxElement(node) && node.openingElement.attributes.properties.some(attr => ts.isJsxAttribute(attr) && attr.name.getText(file) === 'className' && attr.initializer?.text === 'story-scene-context')));
  assert.ok(ancestors(content[0]).some(node => ts.isFunctionDeclaration(node) && node.name?.text === 'StoryColumn'));
  assert.ok(!ancestors(shop).some(node => ts.isFunctionDeclaration(node) && node.name?.text === 'DrawerSheet'));
  assert.match(page.slice(mount, page.indexOf('/>', mount)), /onTrade=\{\(text\) => submitTurn\(text, undefined, 'do'\)\}/);
  assert.doesNotMatch(await readFile('src/components/shop-panel.tsx', 'utf8'), /DrawerSheet|playGameTurn|fetch\(/);
});

// Task 11: prepared regression cases. Execute only through the approved D1 web runner.
const tippedCounter = () => ({ ...counter, seq: 0,
  held: { npc_id: 'barman', key: 'bira', count: 1, tip_cp: 1, total_cp: 5 } });

test('shows the tip and confirms the total with it', () => {
  const h = harness(tippedCounter());
  h.byId('shop-more-bira').props.onClick();
  const html = render(React.createElement(ui.ShopCounterCard, h.props()));
  assert.ok(html.includes('Toplam: 4 + bahşiş 1 = 5 bakır.'));
  assert.ok(html.includes('Onayla (5 bakır)'));
  assert.equal(h.byId('button-confirm-shop').props.disabled, false);
  h.byId('button-confirm-shop').props.onClick();
  assert.deepEqual(h.sent, ['/item shop_buy barman bira 1 0 5']);
});

test('held tip applies only to its single selected good from the same vendor', () => {
  for (const change of ['count', 'good', 'vendor']) {
    const view = tippedCounter();
    if (change === 'vendor') view.held.npc_id = 'another-vendor';
    const h = harness(view);
    h.byId('shop-more-bira').props.onClick();
    if (change === 'count') h.byId('shop-more-bira').props.onClick();
    if (change === 'good') h.byId('shop-more-yemek').props.onClick();
    const expected = change === 'count' ? 8 : change === 'good' ? 30 : 4;
    const html = render(React.createElement(ui.ShopCounterCard, h.props()));
    assert.ok(html.includes(`Onayla (${expected} bakır)`));
    assert.equal(html.includes('+ bahşiş'), false);
    h.byId('button-confirm-shop').props.onClick();
    assert.deepEqual(h.sent, [change === 'count' ? '/item shop_buy barman bira 2 0 8'
      : change === 'good' ? '/item shop_buy barman yemek 1 0 30' : '/item shop_buy barman bira 1 0 4']);
  }
});

test('the displayed goods plus held tip must fit the purse before confirmation', () => {
  const view = tippedCounter();
  view.purse = { total_cp: 4, gp: 0, sp: 0, cp: 4 };
  const h = harness(view);
  h.byId('shop-more-bira').props.onClick();
  assert.equal(h.byId('button-confirm-shop').props.disabled, true);
  h.byId('button-confirm-shop').props.onClick();
  assert.deepEqual(h.sent, []);
});