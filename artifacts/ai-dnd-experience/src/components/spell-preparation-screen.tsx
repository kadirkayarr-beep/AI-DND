import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  getGameSessionSpellPreparation,
  getGameSessionState,
  getGetGameSessionStateQueryKey,
  prepareGameSessionSpells,
  type GameState,
  type SpellPrepareViewResponse,
} from '@workspace/api-client-react';
import { applyGameState, nextRevision } from '@/lib/game-state-gate';
import { clearPendingTurnAction, reconcileState, ReconciliationError, stableTurnActionId, useActionLifetime } from '@/lib/action-reconciliation';
import { currentAccountOwner } from '@/lib/account-session';
import { readPending } from '@/lib/pending-action';
import { spellLabel } from '@/lib/spell-names';
import {
  droppedText, isPrepareRefusal, lockedSpells, prepareRefusalText, prepareRequest, resultText, spellChoices, toggleSpell, windowReasonText,
} from '@/lib/spell-preparation';
import { SpellStatusRows } from './spellcasting-panel';
import './spell-preparation.css';

type Feedback = { tone: 'success' | 'error' | 'warning'; text: string };

/** The Hazırlık screen itself: what the server offers and the player's own list. It never picks a spell. */
export function SpellPreparationPanel({ view, draft, combatActive, expanded, sending, disabled, feedback, label = id => spellLabel(id), onToggle, onSave, onExpand, onReset }: {
  view: SpellPrepareViewResponse; draft: readonly string[]; combatActive: boolean; expanded: boolean; sending: boolean; disabled: boolean;
  feedback: Feedback | null; label?: (id: string) => string;
  onToggle: (id: string) => void; onSave: () => void; onExpand: () => void; onReset: () => void;
}) {
  const editable = view.supported && view.open;
  const locked = lockedSpells(view);
  const request = prepareRequest(view, draft);
  const atCap = draft.length >= view.limit;
  const unchanged = draft.length === view.prepared.length && draft.every((id, index) => view.prepared[index] === id);
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (request && !sending && !disabled) onSave(); };
  return <section className="spell-prep dnd-card" data-testid="spell-preparation" aria-labelledby="spell-prep-title">
    <div className="spell-prep-head">
      <h2 id="spell-prep-title">Büyü hazırlığı</h2>
      <button type="button" className="dnd-button secondary" data-testid="button-toggle-spell-preparation" aria-expanded={expanded} aria-controls="spell-prep-body" onClick={onExpand}>
        {expanded ? 'Gizle' : editable ? 'Hazırlığı aç' : 'Ayrıntılar'}
      </button>
    </div>
    <SpellStatusRows view={view} combatActive={combatActive} label={label} />
    {expanded && <div id="spell-prep-body" className="spell-prep-body">
      <p className="spell-prep-reason" data-testid="spell-prepare-reason">{windowReasonText(view, combatActive)}</p>
      {editable && <form onSubmit={submit}>
        <fieldset disabled={disabled || sending}>
          <legend>Hazırlanacak büyüler</legend>
          <p className="spell-prep-count" data-testid="spell-prepare-count">{`${draft.length} / ${view.limit} hazır`}</p>
          {atCap && <p className="spell-prep-note">Sınıra ulaştın: yeni bir büyü eklemek için önce birini çıkar.</p>}
          <ul className="spell-prep-list">
            {spellChoices(view).map(id => {
              const checked = draft.includes(id);
              const isLocked = checked && locked.has(id);
              return <li key={id}><label className="spell-prep-choice">
                <input type="checkbox" value={id} checked={checked} disabled={isLocked || (!checked && (atCap || !view.candidates.includes(id)))} onChange={() => onToggle(id)} />
                <span>{label(id)}</span>
                {isLocked && <small>önceki hazırlık · uzun dinlenmede değişir</small>}
              </label></li>;
            })}
          </ul>
          <p className="spell-prep-note">Bazı büyüler yalnız katalogda: hazırlanabilir ama oyunda henüz atılamayabilir.</p>
          <div className="spell-prep-actions">
            <button type="submit" className="dnd-button" data-testid="button-save-prepared" disabled={!request}>{sending ? 'Kaydediliyor…' : 'Listeyi kaydet'}</button>
            <button type="button" className="dnd-button secondary" data-testid="button-reset-prepared" disabled={unchanged} onClick={onReset}>Seçimi sıfırla</button>
          </div>
        </fieldset>
      </form>}
    </div>}
    {feedback && (feedback.tone === 'success'
      ? <p role="status" className="spell-prep-feedback" data-tone="success" data-testid="spell-prepare-feedback">{feedback.text}</p>
      : <p role="alert" className="spell-prep-feedback" data-tone={feedback.tone} data-testid="spell-prepare-feedback">{feedback.text}</p>)}
  </section>;
}

const UNKNOWN = 'Listenin kaydedilip kaydedilmediği doğrulanamadı. Aynı listeyi yeniden kaydet: işlem kimliği korunuyor, liste iki kez yazılmaz.';
const PENDING = 'Önceki hamle henüz doğrulanamadı. Önce o hamleyi sonuçlandır; büyü listesi bundan sonra kaydedilir.';

/** Reads the server's window (GET, writes nothing) whenever the visible state moves, and saves through `spellcasting/prepare`. */
export function SpellPreparationControls({ state, sessionId, campaignId, catalog, disabled }: {
  state: GameState; sessionId: string; campaignId: string; catalog?: unknown; disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const owner = currentAccountOwner() ?? 'local';
  const lifetime = useActionLifetime(`${owner}:${campaignId}:${sessionId}`);
  const [view, setView] = useState<SpellPrepareViewResponse | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const busy = useRef(false);
  const label = useCallback((id: string) => spellLabel(id, catalog), [catalog]);
  const combatActive = Boolean(state.combat?.active);
  // Anything a turn, an undo, a rest or a level step changes; the window itself is not in the public state.
  const signature = JSON.stringify([state.spellcasting, state.character.level, (state.character as { progression_level?: unknown }).progression_level ?? null,
    state.campaign_time, combatActive, (state as { turn_index?: unknown }).turn_index ?? null]);

  const load = useCallback(async () => {
    const operation = lifetime.begin(); if (!operation) return;
    try {
      const result = await getGameSessionSpellPreparation(sessionId, { signal: operation.signal });
      if (!operation.isCurrent() || result.session_id !== sessionId) return;
      setLoadFailed(false);
      setView(result);
      if (!busy.current) setDraft([...result.prepared]);
      if (result.open) setExpanded(true);
    } catch { if (operation.isCurrent()) setLoadFailed(true); }
    finally { operation.close(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);
  useEffect(() => { void load(); }, [load, signature]);

  const save = () => {
    if (busy.current || disabled || !view) return;
    const body = prepareRequest(view, draft); if (!body) return;
    if (readPending(owner, campaignId || sessionId)) { setFeedback({ tone: 'error', text: PENDING }); return; }
    const scope = `prepare:${campaignId || sessionId}`;
    let actionId: string;
    try { actionId = stableTurnActionId(scope, JSON.stringify(body)); }
    catch { setFeedback({ tone: 'error', text: 'Güvenli işlem kimliği üretilemedi; liste gönderilmedi.' }); return; }
    const operation = lifetime.begin(); if (!operation) return;
    busy.current = true; setSending(true); setFeedback(null);
    void (async () => {
      const response = await prepareGameSessionSpells(sessionId, { ...body, action_id: actionId }, { signal: operation.signal });
      if (!operation.isCurrent()) return;
      if (response.session_id !== sessionId) throw new ReconciliationError();
      if (response.result.status === 'too_many') {  // a question: the server saved nothing and kept no receipt
        clearPendingTurnAction(scope, actionId);
        setFeedback({ tone: 'error', text: resultText(response.result, label) });
        return;
      }
      if (response.action_id !== actionId) throw new ReconciliationError();
      const readRevision = nextRevision();
      const fresh = await reconcileState(queryClient, getGetGameSessionStateQueryKey(sessionId), operation, signal => getGameSessionState(sessionId, { signal }));
      if (!operation.isCurrent()) return;
      if (!applyGameState(queryClient, sessionId, fresh, { revision: readRevision, isCurrent: operation.isCurrent })) throw new ReconciliationError();
      clearPendingTurnAction(scope, actionId);
      setFeedback({ tone: 'success', text: [resultText(response.result, label), droppedText(response.result.dropped, label)].filter(Boolean).join(' ') });
      return 'settled';
    })().catch((error: unknown) => {
      if (!operation.isCurrent()) return 'stale';
      if (isPrepareRefusal(error)) {  // an answer: nothing was saved, a new list gets a new id
        clearPendingTurnAction(scope, actionId);
        setFeedback({ tone: 'error', text: prepareRefusalText(error) });
        return 'settled';
      }
      setFeedback({ tone: 'warning', text: UNKNOWN });  // the draft stays so the same list (same id) can be sent again
      return 'unknown';
    }).then(outcome => {
      busy.current = false;
      if (operation.isCurrent()) setSending(false);
      operation.close();
      if (outcome === 'settled') void load();  // the server's window after a saved list or a refusal
    });
  };

  if (!view) return <section className="spell-prep dnd-card" data-testid="spell-preparation" aria-label="Büyü hazırlığı">
    {loadFailed
      ? <p role="alert" className="spell-prep-feedback" data-tone="error">Büyü hazırlığı okunamadı. <button type="button" className="dnd-button secondary" onClick={() => void load()}>Yeniden dene</button></p>
      : <p className="spell-prep-note">Büyü hazırlığı okunuyor…</p>}
  </section>;
  return <SpellPreparationPanel view={view} draft={draft} combatActive={combatActive} expanded={expanded} sending={sending} disabled={disabled} feedback={feedback} label={label}
    onToggle={id => { setFeedback(null); setDraft(current => toggleSpell(view, current, id)); }}
    onSave={save} onExpand={() => setExpanded(value => !value)} onReset={() => setDraft([...view.prepared])} />;
}
