import type {
  EconomicProposalIn, PublicEconomicOffer, TurnOutcome,
} from '@workspace/api-client-react';

// Pure shop and economic-card controllers (D-566): no React, no fetch. shop-panel.tsx wires them to the screen.

const REASONS: Record<string, string> = {
  offer_stale: 'Fiyat değişti, yeniden onayla.',
  price_changed: 'Fiyat değişti, yeniden onayla.',
  insufficient_funds: 'Kesende bu kadar para yok.',
  out_of_stock: 'Tezgâhta o kadar kalmamış.',
  vendor_refuses: 'Seninle alışveriş etmek istemiyor.',
  npc_unavailable: 'Satıcı şu an burada değil.',
  vendor_unavailable: 'Satıcı şu an burada değil.',
  npc_unknown: 'Satıcı şu an burada değil.',
  no_vendor: 'Burada sana bir şey satacak kimse yok.',
  not_now: 'Şu an alışverişin sırası değil.',
};
const ASK_AGAIN = new Set(['offer_stale', 'price_changed']);

export function shopReasonText(reason: string | null | undefined): string {
  return REASONS[reason ?? ''] ?? 'Alışveriş yapılamadı; dünya durumu değişmedi.';
}

/** What the last turn means for the counter, read from the turn outcome's status and reason only. */
export function shopOutcomeStep(outcome: TurnOutcome | null | undefined, awaiting: boolean, panelOpen = false): 'open' | 'ask_again' | 'refused' | 'done' | 'other' | 'refresh' | null {
  if (outcome?.action === 'shop_offer') return outcome.status === 'offer_open' ? 'open' : null;
  // A turn this panel did not send (a paid card, a word to the barman) may have moved the purse or the stock.
  if (!awaiting) return panelOpen ? 'refresh' : null;
  if (outcome?.action !== 'equipment_transaction') return 'other';
  if (outcome.status === 'resolved') return 'done';
  return ASK_AGAIN.has(outcome.reason ?? '') ? 'ask_again' : 'refused';
}

/** One trade per press: a second press waits until the turn's answer reopens the gate. */
export function createConfirmGate(send: (text: string) => void) {
  let waiting = false;
  return {
    fire(text: string) { if (waiting) return false; waiting = true; send(text); return true; },
    waiting: () => waiting,
    reopen() { waiting = false; },
  };
}

/** One press until reopened: a second click while the first is on its way sends nothing. */
function createOnceGate() {
  let busy = false;
  return {
    run(send: () => unknown) { if (busy) return false; busy = true; void send(); return true; },
    busy: () => busy,
    reopen() { busy = false; },
  };
}

/** Confirm and cancel of the card on screen, by its own offer id and digest, at most one at a time. */
export function createOfferCardController(handlers: {
  onConfirm: (offerId: string, digest: string) => unknown; onCancel: (offerId: string) => unknown;
}) {
  const gate = createOnceGate();
  return {
    confirm: (offer: PublicEconomicOffer) => gate.run(() => handlers.onConfirm(offer.offer_id, offer.confirmation_digest)),
    cancel: (offer: PublicEconomicOffer) => gate.run(() => handlers.onCancel(offer.offer_id)),
    busy: gate.busy,
    reopen: gate.reopen,
  };
}

export type PrepareForm = { purpose: '' | 'gift' | 'tip' | 'room'; recipientId: string; amount: string; tip: string; allOrNone: boolean };

// A whole copper amount from 1 to 999 999 999 with no sign, point or leading zero: matches "7", rejects "0" and "2.5".
// Tester: https://regex101.com/?regex=%5E%5B1-9%5D%5Cd%7B0%2C8%7D%24&testString=7
const POSITIVE = /^[1-9]\d{0,8}$/;

/** The proposal the panel may send, or null when it is not complete: no price for a room, a positive amount otherwise. */
export function prepareProposal(form: PrepareForm): EconomicProposalIn | null {
  const recipient = form.recipientId.trim();
  if (!recipient) return null;
  if (!form.purpose) return null; // Görev 32: an empty Ne is never read as a gift
  if (form.purpose === 'room') {
    const tip = form.tip.trim();
    if (tip && !POSITIVE.test(tip)) return null;
    return { purpose: 'room', recipient_id: recipient, amount_cp: null, tip_cp: tip ? Number(tip) : 0,
      dependency: form.allOrNone ? 'all_or_none' : 'base_required' };
  }
  const amount = form.amount.trim();
  if (!POSITIVE.test(amount)) return null;
  return { purpose: form.purpose, recipient_id: recipient, amount_cp: Number(amount) };
}

/** Prepare from the panel: one valid proposal per press; an incomplete form sends nothing. */
export function createPrepareController(onPrepare: (proposal: EconomicProposalIn) => unknown) {
  return {
    submit(form: PrepareForm) {
      const proposal = prepareProposal(form);
      if (!proposal) return false;
      void onPrepare(proposal);
      return true;
    },
  };
}
