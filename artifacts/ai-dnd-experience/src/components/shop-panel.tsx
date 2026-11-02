import { useEffect, useRef, useState } from 'react';
import { getGameSessionShop, type ShopCounterResponse, type TurnOutcome } from '@workspace/api-client-react';
import { useActionLifetime } from '@/lib/action-reconciliation';
import { currentAccountOwner } from '@/lib/account-session';

/** Count per good key; one good is bought per trade, so at most one key is set. */
export type ShopCounts = Record<string, number>;

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

const capital = (text: string) => text.slice(0, 1).toLocaleUpperCase('tr-TR') + text.slice(1);
const purseText = (purse: ShopCounterResponse['purse']) => `${purse.gp} altın ${purse.sp} gümüş ${purse.cp} bakır`;

/** What the last turn means for the counter, read from the turn outcome's status and reason only. */
export function shopOutcomeStep(outcome: TurnOutcome | null | undefined, awaiting: boolean): 'open' | 'ask_again' | 'refused' | 'done' | 'other' | null {
  if (outcome?.action === 'shop_offer') return outcome.status === 'offer_open' ? 'open' : null;
  if (!awaiting) return null;
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
  const total = chosen ? chosen.unit_cp * count : 0;
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
    <p>Toplam: {total} bakır. Para üstü verilmez; ödeme bakır karşılığıyla düşülür.</p>
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
    const step = shopOutcomeStep(outcome, gate.current!.waiting());
    if (step && step !== 'open') { gate.current!.reopen(); setWaiting(false); }
    if (step === 'open') void read(true);
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
