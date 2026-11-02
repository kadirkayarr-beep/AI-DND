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

test('the play screen mounts the counter inline above the story, never in the drawer, and confirms through the turn submit', async () => {
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  const mount = page.indexOf('<ShopControls');
  assert.ok(mount > 0);
  assert.ok(mount < page.indexOf('<StoryColumn', mount));
  assert.match(page.slice(mount, page.indexOf('/>', mount)), /onTrade=\{\(text\) => submitTurn\(text, undefined, 'do'\)\}/);
  assert.doesNotMatch(await readFile('src/components/shop-panel.tsx', 'utf8'), /DrawerSheet|playGameTurn|fetch\(/);
});
