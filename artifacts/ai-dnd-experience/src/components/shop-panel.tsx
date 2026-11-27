import { useEffect, useRef, useState } from 'react';
import {
  getGameSessionShop, type EconomicAction, type EconomicProposalIn, type PublicEconomicOffer,
  type PublicEconomicResolution, type ShopCounterResponse, type TurnOutcome,
} from '@workspace/api-client-react';
import { useActionLifetime } from '@/lib/action-reconciliation';
import { currentAccountOwner } from '@/lib/account-session';
import {
  createConfirmGate, createOfferCardController, createPrepareController, prepareProposal, shopOutcomeStep, shopReasonText,
  type PrepareForm,
} from '@/lib/shop-controllers';

/** Count per good key; one good is bought per trade, so at most one key is set. */
type ShopCounts = Record<string, number>;

const capital = (text: string) => text.slice(0, 1).toLocaleUpperCase('tr-TR') + text.slice(1);
const purseText = (purse: ShopCounterResponse['purse']) => `${purse.gp} altın ${purse.sp} gümüş ${purse.cp} bakır`;

/** Who stands here; a counter is looked for only where someone stands. */
export function shopProbeKey(state: { location?: string | null; npcs?: readonly { id: string; location?: string | null }[] | null }): string {
  const here = (state.npcs ?? []).filter(npc => npc.location === state.location).map(npc => npc.id).sort();
  return here.length ? `${state.location}:${here.join(',')}` : '';
}

export function ShopCounterCard({ counter, counts, onCounts, onConfirm, onClose, disabled = false, notice = null }: {
  counter: ShopCounterResponse; counts: ShopCounts; onCounts: (counts: ShopCounts) => void;
  onConfirm: (text: string) => void; onClose: () => void; disabled?: boolean; notice?: string | null;
}) {
  // Close stays usable while a trade is on its way: it only drops the card, never the sent turn.
  const close = <button type="button" className="dnd-button secondary" data-testid="button-close-shop" onClick={onClose}>Kapat</button>;
  if (counter.status !== 'ready' || !counter.vendor) {
    return <div role="status" data-testid="shop-unavailable"><p>{shopReasonText(counter.reason)}</p>{close}</div>;
  }
  const vendor = counter.vendor;
  const chosen = counter.lines.find(line => (counts[line.key] ?? 0) > 0);
  const count = chosen ? counts[chosen.key] : 0;
  const held = counter.held;
  const tipped = !!chosen && count === 1 && held?.count === 1
    && held.npc_id === vendor.npc_id && held.key === chosen.key;
  const total = tipped ? held.total_cp : chosen ? chosen.unit_cp * count : 0;
  const affordable = total <= counter.purse.total_cp;
  const valid = !!chosen && count >= 1 && count <= chosen.stock && affordable;
  const step = (key: string, next: number, stock: number) => {
    const bounded = Math.max(0, Math.min(next, stock));
    onCounts(bounded > 0 ? { [key]: bounded } : {});
  };
  return <><fieldset disabled={disabled} data-testid="shop-counter">
    <legend>{vendor.name} · tezgâh</legend>
    <p>Kesende: {purseText(counter.purse)}</p>
    <ul className="space-y-2">
      {counter.lines.map(line => {
        const n = counts[line.key] ?? 0;
        return <li key={line.key} className="flex items-center gap-2" data-testid={`shop-line-${line.key}`}>
          <span className="flex-1">{capital(line.label)} — {line.unit_cp} bakır{line.discount_cp > 0 ? ` (${line.discount_cp} bakır indirimli)` : ''} · kalan {line.stock}</span>
          <button type="button" className="dnd-button secondary" data-testid={`shop-less-${line.key}`} aria-label={`${capital(line.label)} azalt`} disabled={disabled || n < 1} onClick={() => step(line.key, n - 1, line.stock)}>−</button>
          <span aria-live="polite">{n}</span>
          <button type="button" className="dnd-button secondary" data-testid={`shop-more-${line.key}`} aria-label={`${capital(line.label)} artır`} disabled={disabled || n >= line.stock} onClick={() => step(line.key, n + 1, line.stock)}>+</button>
        </li>;
      })}
    </ul>
    {notice && <p role="alert" data-testid="shop-notice">{notice}</p>}
    {chosen && !affordable && <p role="status">{shopReasonText('insufficient_funds')}</p>}
    {tipped ? <p>Toplam: {chosen!.unit_cp} + bahşiş {held.tip_cp} = {total} bakır.</p>
      : <p>Toplam: {total} bakır. Para üstü verilmez; ödeme bakır karşılığıyla düşülür.</p>}
    <button type="button" className="dnd-button" data-testid="button-confirm-shop" disabled={disabled || !valid} onClick={() => {
      if (disabled || !valid || !chosen) return;
      onConfirm(`/item shop_buy ${vendor.npc_id} ${chosen.key} ${count} ${counter.seq} ${total}`);
    }}>Onayla ({total} bakır)</button>
  </fieldset>{close}</>;
}

/** The counter panel: inline above the story like the level-up card; a quote is fetched fresh at every opening. */
export function ShopControls({ sessionId, campaignId, disabled, outcome, outcomeKey, probeKey, onTrade }: {
  sessionId: string; campaignId: string; disabled: boolean; outcome: TurnOutcome | null; outcomeKey: string | null;
  probeKey: string; onTrade: (text: string) => void;
}) {
  const [counter, setCounter] = useState<ShopCounterResponse | null>(null);
  const [available, setAvailable] = useState(false);
  const [counts, setCounts] = useState<ShopCounts>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const lifetime = useActionLifetime(`${currentAccountOwner() ?? 'local'}:${campaignId}:${sessionId}`);
  // The gate calls the latest submit, never the one from the first render.
  const send = useRef(onTrade);
  send.current = onTrade;
  const gate = useRef<ReturnType<typeof createConfirmGate> | null>(null);
  gate.current ??= createConfirmGate(text => send.current(text));

  // Only the newest read may show its quote: an older answer arriving late never replaces a fresher one.
  const latest = useRef(0);
  const read = async (open: boolean, keep: { counts?: ShopCounts; notice?: string | null } = {}) => {
    const operation = lifetime.begin(); if (!operation) return;
    const mine = open ? ++latest.current : latest.current;  // a silent probe never supersedes an opening
    const current = () => operation.isCurrent() && (!open || mine === latest.current);
    if (open) { setLoading(true); setError(false); }
    try {
      const result = await getGameSessionShop(sessionId, { signal: operation.signal });
      if (!current() || result.session_id !== sessionId || result.campaign_id !== campaignId) return;
      setAvailable(result.status === 'ready');
      if (open) { setCounter(result); setCounts(keep.counts ?? {}); setNotice(keep.notice ?? null); }
    } catch { if (open && current()) setError(true); }
    finally { if (open && current()) setLoading(false); operation.close(); }
  };

  // Look for a counter only where someone stands; the probe writes nothing and opens nothing.
  useEffect(() => { if (probeKey) void read(false); else setAvailable(false); }, [probeKey]);  // eslint-disable-line react-hooks/exhaustive-deps

  const lastCounts = useRef<ShopCounts>({});
  useEffect(() => {
    if (!outcomeKey) return;
    const step = shopOutcomeStep(outcome, gate.current!.waiting(), !!counter);
    if (step && step !== 'open') { gate.current!.reopen(); setWaiting(false); }
    if (step === 'open') void read(true);
    else if (step === 'refresh') void read(true, { counts, notice });
    else if (step === 'ask_again') void read(true, { counts: lastCounts.current, notice: shopReasonText(outcome?.reason) });
    else if (step === 'refused') void read(true, { counts: lastCounts.current, notice: shopReasonText(outcome?.reason) });
    else if (step === 'done') { setCounter(null); setCounts({}); setNotice(null); void read(false); }
  }, [outcomeKey]);  // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => { setCounter(null); setCounts({}); setNotice(null); gate.current!.reopen(); setWaiting(false); };
  if (!available && !counter && !loading && !error) return null;
  return <section className="dnd-card p-4" data-testid="shop-controls" aria-label="Tezgâh">
    {!counter && <button type="button" className="dnd-button secondary" data-testid="button-open-shop" disabled={disabled || loading} onClick={() => void read(true)}>{loading ? 'Tezgâha bakılıyor…' : 'Tezgâhtan satın al'}</button>}
    {error && <p role="alert">Tezgâh yüklenemedi. Yeniden dene.</p>}
    {counter && <ShopCounterCard counter={counter} counts={counts} onCounts={setCounts} notice={notice} disabled={disabled || waiting}
      onClose={close} onConfirm={text => {
        lastCounts.current = counts;
        if (gate.current!.fire(text)) { setWaiting(true); setNotice(null); }
      }} />}
  </section>;
}

// ---------------------------------------------------------------------------------------------------------------
// A4: the economic card and the panel that prepares one. The card is bound to the server's offer id and digest;
// the screen's text, amount or name is never authority. Every request is a turn with a fixed display message.
// ---------------------------------------------------------------------------------------------------------------

export const ECONOMIC_MESSAGES = { prepare: 'Teklif hazırla', confirm: 'Teklifi onayla', cancel: 'Teklifi iptal et' } as const;

/** The body game-browser sends for one economic step: the fixed message and the action, nothing else. */
export function economicTurnRequest(action: EconomicAction): { message: string; economic_action: EconomicAction } {
  return { message: ECONOMIC_MESSAGES[action.kind], economic_action: action };
}

/** What the engine's receipt says, for the notice under the story; a changed offer asks for a new card. */
export function economicResolutionNotice(resolution: Pick<PublicEconomicResolution, 'status' | 'reason_code' | 'public_summary'> | null | undefined): string | null {
  if (!resolution) return null;
  if (resolution.reason_code === 'stale') return 'Teklif değişti; yeni kart gerekir.';
  return resolution.public_summary;
}

/** The purse the screen may show before the fresh state arrives: a refused result leaves it as it was. */
export function walletAfterResolution(wallet: { total_cp: number }, resolution: Pick<PublicEconomicResolution, 'status' | 'net_debit_cp'> | null | undefined) {
  if (!resolution || resolution.status !== 'applied') return wallet;
  return { total_cp: wallet.total_cp - resolution.net_debit_cp };
}

const DEPENDENCY_TEXT = {
  base_required: 'Bahşiş reddedilirse temel bedel yine ödenir.',
  all_or_none: 'Bahşiş reddedilirse hiçbiri olmaz.',
} as const;

export function EconomicOfferCard({ offer, onConfirm, onCancel, disabled = false }: {
  offer: PublicEconomicOffer; onConfirm(offerId: string, digest: string): Promise<void>;
  onCancel(offerId: string): Promise<void>; disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const handlers = useRef({ onConfirm, onCancel });
  handlers.current = { onConfirm, onCancel };
  const controller = useRef<ReturnType<typeof createOfferCardController> | null>(null);
  controller.current ??= createOfferCardController({
    onConfirm: (offerId, digest) => handlers.current.onConfirm(offerId, digest),
    onCancel: offerId => handlers.current.onCancel(offerId),
  });
  // A new card, or the end of the request that was sent, opens the buttons again.
  useEffect(() => { if (!disabled) { controller.current!.reopen(); setBusy(false); } }, [offer.offer_id, offer.confirmation_digest, disabled]);
  const off = disabled || busy;
  const hasOptional = offer.lines.some(line => line.optional);
  return <fieldset disabled={off} className="dnd-card p-4" data-testid="economic-offer-card">
    <legend>{offer.counterparty_label} · teklif</legend>
    <ul className="space-y-1">
      {offer.lines.map(line => <li key={line.line_id} data-testid={`economic-line-${line.line_id}`}>
        {line.label}{line.count > 1 ? ` × ${line.count}` : ''} — {line.total_cp} bakır{line.optional ? ' (reddedilebilir)' : ''}
      </li>)}
    </ul>
    {hasOptional && <p>{DEPENDENCY_TEXT[offer.dependency]}</p>}
    {offer.tender_cp != null && <p>Uzattığın para: {offer.tender_cp} bakır; artanı para üstü sayılır.</p>}
    <p>Toplam: en çok {offer.max_total_cp} bakır.</p>
    {offer.may_refuse && <p role="note">Karşındaki teklifi kabul etmeyebilir; reddederse para kesende kalır.</p>}
    <button type="button" className="dnd-button" data-testid="button-confirm-offer" disabled={off}
      onClick={() => { if (!off && controller.current!.confirm(offer)) setBusy(true); }}>Onayla</button>
    <button type="button" className="dnd-button secondary" data-testid="button-cancel-offer" disabled={off}
      onClick={() => { if (!off && controller.current!.cancel(offer)) setBusy(true); }}>İptal</button>
  </fieldset>;
}

export function EconomicPrepareControls({ counterparties, onPrepare, disabled = false }: {
  counterparties: { id: string; label: string }[]; onPrepare(proposal: EconomicProposalIn): Promise<void>; disabled?: boolean;
}) {
  const [form, setForm] = useState<PrepareForm>({ purpose: '', recipientId: counterparties[0]?.id ?? '', amount: '', tip: '', allOrNone: false });
  const send = useRef(onPrepare);
  send.current = onPrepare;
  const controls = useRef<ReturnType<typeof createPrepareController> | null>(null);
  controls.current ??= createPrepareController(proposal => send.current(proposal));
  const recipient = counterparties.some(person => person.id === form.recipientId) ? form.recipientId : counterparties[0]?.id ?? '';
  const ready = prepareProposal({ ...form, recipientId: recipient }) !== null;
  const set = (patch: Partial<PrepareForm>) => setForm(current => ({ ...current, ...patch }));
  if (!counterparties.length) return null;
  return <fieldset disabled={disabled} className="dnd-card p-4" data-testid="economic-prepare-controls">
    <legend>Teklif hazırla</legend>
    <label>Kime <select data-testid="economic-recipient" value={recipient} onChange={event => set({ recipientId: event.target.value })}>
      {counterparties.map(person => <option key={person.id} value={person.id}>{person.label}</option>)}
    </select></label>
    <label>Ne <select data-testid="economic-purpose" value={form.purpose} onChange={event => set({ purpose: event.target.value as PrepareForm['purpose'] })}>
      <option value="" disabled>Seç</option><option value="gift">Hediye</option><option value="tip">Bahşiş</option><option value="room">Oda (bir gece)</option>
    </select></label>
    {/* The room's price is the house's own; the amount is only for a gift or a tip. */}
    <label>Tutar (bakır) <input data-testid="economic-amount" inputMode="numeric" disabled={form.purpose === 'room'} value={form.amount} onChange={event => set({ amount: event.target.value })} /></label>
    <label>Odayla ayrı bahşiş (bakır, isteğe bağlı) <input data-testid="economic-tip" inputMode="numeric" disabled={form.purpose !== 'room'} value={form.tip} onChange={event => set({ tip: event.target.value })} /></label>
    <label><input type="checkbox" data-testid="economic-all-or-none" disabled={form.purpose !== 'room'} checked={form.allOrNone} onChange={event => set({ allOrNone: event.target.checked })} /> Bahşiş reddedilirse oda da olmasın</label>
    <button type="button" className="dnd-button" data-testid="button-prepare-offer" disabled={disabled || !ready}
      onClick={() => { if (!disabled) controls.current!.submit({ ...form, recipientId: recipient }); }}>Kartı hazırla</button>
  </fieldset>;
}
