import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { after, before, test } from 'node:test';

// A4: the card and the panel controls. These are controller and render checks, not a mount proof (D6).
process.env.PORT ||= '4188';
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

const shownOffer = {
  offer_id: 'a'.repeat(32), confirmation_digest: 'b'.repeat(64), counterparty_label: 'Barmen',
  lines: [
    { line_id: 'room:0', label: 'Oda (bir gece)', count: 1, unit_cp: 50, total_cp: 50, optional: false },
    { line_id: 'tip:1', label: 'Bahşiş', count: 1, unit_cp: 5, total_cp: 5, optional: true },
  ],
  dependency: 'base_required', max_total_cp: 55, tender_cp: 100, may_refuse: true,
};

/** What game-browser sends: the fixed display message with the economic action, and nothing else. */
function sender() {
  const sentActions = [];
  const send = action => { sentActions.push(ui.economicTurnRequest(action)); return Promise.resolve(); };
  return { sentActions, send };
}

test('test_confirm_uses_bound_offer', () => {
  const { sentActions, send } = sender();
  const card = ui.createOfferCardController({
    onConfirm: (offerId, digest) => send({ kind: 'confirm', offer_id: offerId, confirmation_digest: digest }),
    onCancel: offerId => send({ kind: 'cancel', offer_id: offerId }),
  });
  assert.equal(card.confirm(shownOffer), true);
  assert.equal(sentActions.length, 1);
  assert.equal(sentActions[0].economic_action.offer_id, shownOffer.offer_id);
  assert.equal(sentActions[0].economic_action.confirmation_digest, shownOffer.confirmation_digest);
  assert.equal(sentActions[0].message, 'Teklifi onayla');
  const html = render(React.createElement(ui.EconomicOfferCard, { offer: shownOffer, onConfirm: async () => {}, onCancel: async () => {} }));
  assert.match(html, /Barmen/);
  assert.match(html, /Oda \(bir gece\)/);
  assert.match(html, /50 bakır/);
  assert.match(html, /Bahşiş/);
  assert.match(html, /reddedilebilir/);
  assert.match(html, /Uzattığın para: 100 bakır/);
  assert.match(html, /en çok 55 bakır/);
  assert.match(html, /kabul etmeyebilir/);
});

test('test_double_click_sends_one_action', () => {
  const { sentActions, send } = sender();
  const card = ui.createOfferCardController({
    onConfirm: (offerId, digest) => send({ kind: 'confirm', offer_id: offerId, confirmation_digest: digest }),
    onCancel: offerId => send({ kind: 'cancel', offer_id: offerId }),
  });
  assert.equal(card.confirm(shownOffer), true);
  assert.equal(card.confirm(shownOffer), false);
  assert.equal(card.cancel(shownOffer), false);
  assert.equal(card.busy(), true);
  assert.equal(sentActions.length, 1);
  card.reopen();
  assert.equal(card.busy(), false);
});

test('test_repriced_card_requires_second_click', () => {
  const notice = ui.economicResolutionNotice({ status: 'refused', reason_code: 'stale', public_summary: 'x', net_debit_cp: 0 });
  assert.match(notice, /Teklif değişti; yeni kart gerekir/);
  const { sentActions, send } = sender();
  const card = ui.createOfferCardController({
    onConfirm: (offerId, digest) => send({ kind: 'confirm', offer_id: offerId, confirmation_digest: digest }),
    onCancel: offerId => send({ kind: 'cancel', offer_id: offerId }),
  });
  card.confirm(shownOffer);
  const repriced = { ...shownOffer, offer_id: 'c'.repeat(32), confirmation_digest: 'd'.repeat(64) };
  assert.equal(card.confirm(repriced), false);  // nothing is confirmed for the player without a new click
  card.reopen();
  assert.equal(card.confirm(repriced), true);
  assert.equal(sentActions.length, 2);
  assert.equal(sentActions[1].economic_action.offer_id, repriced.offer_id);
});

test('test_cancel_restores_chat_without_mutation', () => {
  const { sentActions, send } = sender();
  const card = ui.createOfferCardController({
    onConfirm: (offerId, digest) => send({ kind: 'confirm', offer_id: offerId, confirmation_digest: digest }),
    onCancel: offerId => send({ kind: 'cancel', offer_id: offerId }),
  });
  assert.equal(card.cancel(shownOffer), true);
  assert.deepEqual(sentActions, [{ message: 'Teklifi iptal et', economic_action: { kind: 'cancel', offer_id: shownOffer.offer_id } }]);
});

test('test_refused_resolution_shows_engine_summary', () => {
  const refused = { status: 'refused', reason_code: 'check_failed', public_summary: 'Teklif kabul görmedi; para kesende kaldı.', net_debit_cp: 0 };
  assert.equal(ui.economicResolutionNotice(refused), refused.public_summary);
  const wallet = { total_cp: 100 };
  const after = ui.walletAfterResolution(wallet, refused);
  assert.deepEqual(after, wallet);  // a refused result leaves the purse as it was
  assert.equal(ui.economicResolutionNotice(null), null);
});

test('test_prepare_controls_send_room_with_null_amount', () => {
  const { sentActions, send } = sender();
  const controls = ui.createPrepareController(proposal => send({ kind: 'prepare', proposal }));
  assert.equal(controls.submit({ purpose: 'room', recipientId: 'barman', amount: '', tip: '', allOrNone: false }), true);
  assert.equal(sentActions.length, 1);
  assert.equal(sentActions[0].message, 'Teklif hazırla');
  assert.deepEqual(sentActions[0].economic_action, {
    kind: 'prepare', proposal: { purpose: 'room', recipient_id: 'barman', amount_cp: null, tip_cp: 0, dependency: 'base_required' },
  });
  assert.equal('source_action_id' in sentActions[0].economic_action.proposal, false);
  assert.equal(JSON.stringify(sentActions[0]).includes('source_action_id'), false);
  assert.equal(ui.economicTurnRequest({ kind: 'confirm', offer_id: shownOffer.offer_id, confirmation_digest: shownOffer.confirmation_digest }).message, 'Teklifi onayla');
});

test('test_prepare_controls_gift_and_tip_require_positive_amount', () => {
  const { sentActions, send } = sender();
  const controls = ui.createPrepareController(proposal => send({ kind: 'prepare', proposal }));
  for (const purpose of ['gift', 'tip']) {
    for (const amount of ['', '0', '-3', '2.5', 'beş']) {
      assert.equal(controls.submit({ purpose, recipientId: 'barman', amount, tip: '', allOrNone: false }), false, `${purpose}:${amount}`);
    }
  }
  assert.equal(sentActions.length, 0);
  assert.equal(controls.submit({ purpose: 'gift', recipientId: 'barman', amount: '7', tip: '', allOrNone: false }), true);
  assert.deepEqual(sentActions[0].economic_action.proposal, { purpose: 'gift', recipient_id: 'barman', amount_cp: 7 });
  assert.equal(controls.submit({ purpose: 'tip', recipientId: '', amount: '7', tip: '', allOrNone: false }), false);
});

test('Görev 32: the Ne field opens empty and an empty Ne sends nothing, never a gift', () => {
  const { sentActions, send } = sender();
  const controls = ui.createPrepareController(proposal => send({ kind: 'prepare', proposal }));
  for (const amount of ['7', '5900', '']) {
    assert.equal(ui.prepareProposal({ purpose: '', recipientId: 'barman', amount, tip: '', allOrNone: false }), null, amount);
    assert.equal(controls.submit({ purpose: '', recipientId: 'barman', amount, tip: '', allOrNone: false }), false, amount);
  }
  assert.equal(sentActions.length, 0);
  const counterparties = [{ id: 'barman', label: 'Barmen' }];
  const fresh = render(React.createElement(ui.EconomicPrepareControls, { counterparties, onPrepare: async () => {} }));
  // The select shows the empty choice, no option is pre-selected, and the prepare button stays closed.
  assert.match(fresh, /<select data-testid="economic-purpose"[^>]*>\s*<option value="" disabled="" selected="">Seç<\/option>/);
  assert.doesNotMatch(fresh, /<option value="gift" selected/);
  assert.match(fresh, /<button[^>]*data-testid="button-prepare-offer"[^>]*disabled=""/);
});

test('test_prepare_controls_disabled_while_card_open', () => {
  const counterparties = [{ id: 'barman', label: 'Barmen' }];
  const open = render(React.createElement(ui.EconomicPrepareControls, { counterparties, onPrepare: async () => {}, disabled: true }));
  assert.match(open, /<fieldset[^>]*disabled/);
  const closed = render(React.createElement(ui.EconomicPrepareControls, { counterparties, onPrepare: async () => {}, disabled: false }));
  assert.doesNotMatch(closed, /<fieldset[^>]*disabled/);
  assert.match(closed, /Barmen/);
  assert.match(closed, /Bahşiş reddedilirse oda da olmasın/);
});

test('test_prepare_controls_room_tip_and_dependency', () => {
  const { sentActions, send } = sender();
  const controls = ui.createPrepareController(proposal => send({ kind: 'prepare', proposal }));
  assert.equal(controls.submit({ purpose: 'room', recipientId: 'barman', amount: '', tip: '5', allOrNone: false }), true);
  assert.equal(sentActions[0].economic_action.proposal.tip_cp, 5);
  assert.equal(sentActions[0].economic_action.proposal.dependency, 'base_required');
  assert.equal(controls.submit({ purpose: 'room', recipientId: 'barman', amount: '', tip: '5', allOrNone: true }), true);
  assert.equal(sentActions[1].economic_action.proposal.dependency, 'all_or_none');
  assert.equal(controls.submit({ purpose: 'room', recipientId: 'barman', amount: '', tip: '0', allOrNone: false }), false);
  assert.equal(sentActions.length, 2);
  assert.equal(controls.submit({ purpose: 'room', recipientId: 'barman', amount: '', tip: '', allOrNone: false }), true);
  assert.equal(sentActions[2].economic_action.proposal.tip_cp, 0);
});

test('the play screen mounts the card and the controls and sends them through the turn submit', async () => {
  const page = await readFile('src/pages/game-browser.tsx', 'utf8');
  assert.match(page, /<EconomicOfferCard/);
  assert.match(page, /<EconomicPrepareControls/);
  assert.match(page, /economic_action: economicAction/);
  const panel = await readFile('src/components/shop-panel.tsx', 'utf8');
  assert.doesNotMatch(panel, /playGameTurn|fetch\(/);
});
