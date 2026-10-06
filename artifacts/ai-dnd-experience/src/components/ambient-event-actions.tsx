import type {
  AmbientEventActionInput,
  AmbientEventActionInputAction,
  AmbientEventResult,
  GameSceneAmbientEvent,
  GameSceneReferent,
  GameState,
} from '@workspace/api-client-react';

export type AmbientEventActionRequest = {
  sessionId: string;
  eventInstanceId: string;
  data: AmbientEventActionInput;
};

export function isActiveBlueAmbientEvent(
  event: GameSceneAmbientEvent | null | undefined,
  referents: GameSceneReferent[],
) {
  return Boolean(
    event
      && event.event_type === 'BLUE'
      && event.instance_id
      && referents.some(
        (referent) => referent.event_instance_id === event.instance_id
          && referent.lifecycle === 'presented',
      ),
  );
}

export function createAmbientEventActionRequest(
  sessionId: string,
  eventInstanceId: string,
  action: AmbientEventActionInputAction,
  createUuidV4: () => string = () => {
    if (!globalThis.crypto?.randomUUID) {
      throw new Error('Secure UUIDv4 generation is unavailable in this browser.');
    }
    return globalThis.crypto.randomUUID();
  },
): AmbientEventActionRequest {
  return {
    sessionId,
    eventInstanceId,
    data: {
      action_id: createUuidV4(),
      action,
    },
  };
}

export function findPersistedAmbientEventResult(
  state: GameState,
  eventInstanceId: string,
): AmbientEventResult | null {
  const entry = [...state.journal.notable_events].reverse().find(
    (candidate) => candidate.event_type === 'ambient_event_outcome'
      && candidate.event_result?.event_instance_id === eventInstanceId,
  );
  const result = entry?.event_result;
  if (!entry || !result) return null;

  return {
    event_instance_id: result.event_instance_id,
    action_id: result.action_id,
    status: result.status,
    reason_code: result.reason_code,
    transition_id: result.transition_id,
    canonical_event_id: entry.event_id,
  };
}

const statusLabels: Record<AmbientEventResult['status'], string> = {
  APPLIED: 'Karşılaşma ilerledi.',
  REJECTED: 'Şu anda buna müdahale edemiyorsun.',
  NO_EFFECT: 'Bir süre gözlemliyorsun; belirgin bir değişiklik olmuyor.',
  ALREADY_APPLIED: 'Bu karşılaşma zaten gelişti.',
};

export function AmbientEventActionPanel({
  event,
  referents,
  result,
  retryRequest,
  sending,
  hasError,
  onAction,
  onRetry,
}: {
  event: GameSceneAmbientEvent | null;
  referents: GameSceneReferent[];
  result: AmbientEventResult | null;
  retryRequest: AmbientEventActionRequest | null;
  sending: boolean;
  hasError: boolean;
  onAction: (action: AmbientEventActionInputAction) => void;
  onRetry: () => void;
}) {
  const active = isActiveBlueAmbientEvent(event, referents);
  const eventReferent = referents.find(
    (referent) => referent.event_instance_id === event?.instance_id,
  );
  const resultForEvent = result?.event_instance_id === event?.instance_id ? result : null;
  const retryForEvent = retryRequest?.eventInstanceId === event?.instance_id
    ? retryRequest
    : null;

  if (
    !event
    || event.event_type !== 'BLUE'
    || (!active && !resultForEvent && !retryForEvent)
  ) {
    return null;
  }

  return (
    <section className="ambient-event-panel" aria-label="Yakındaki dikkat çekici hareket" data-testid="panel-ambient-event">
      <div className="ambient-event-heading">
        <div>
          <span className="ambient-event-kicker">DİKKATİNİ ÇEKEN</span>
          <strong>{eventReferent?.description ?? 'Yakındaki hareketlilik'}</strong>
        </div>
        {active && !retryForEvent && (
          <div className="ambient-event-actions">
            <button
              className="dnd-button"
              type="button"
              disabled={sending}
              data-testid="button-ambient-action-interact"
              onClick={() => onAction('interact')}
            >
              {sending ? 'İşleniyor…' : 'Etkileşime geç'}
            </button>
            <button
              className="dnd-button secondary"
              type="button"
              disabled={sending}
              data-testid="button-ambient-action-observe"
              onClick={() => onAction('observe')}
            >
              Gözlemle
            </button>
          </div>
        )}
        {retryForEvent && (
          <div className="ambient-event-retry">
            {hasError && (
              <span role="alert" data-testid="ambient-action-network-error">
                Hamlenin sonucu ulaşmadı. Aynı hamleyi güvenle yeniden deneyebilirsin.
              </span>
            )}
            <button
              className="dnd-button secondary"
              type="button"
              disabled={sending}
              data-testid="button-ambient-action-retry"
              onClick={onRetry}
            >
              {sending ? 'İşleniyor…' : 'Tekrar dene'}
            </button>
          </div>
        )}
      </div>
      {resultForEvent && (
        <div
          className="ambient-event-result"
          role="status"
          aria-live="polite"
          data-testid="ambient-event-result"
          data-status={resultForEvent.status}
        >
          <strong>{statusLabels[resultForEvent.status]}</strong>
        </div>
      )}
    </section>
  );
}