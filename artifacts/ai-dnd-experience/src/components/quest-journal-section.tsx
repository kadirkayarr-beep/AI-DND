import type { GameState } from '@workspace/api-client-react';

const QUEST_STATUS_LABELS: Record<string, string> = {
  accepted: 'Sürüyor',
  active: 'Sürüyor',
  completed: 'Tamamlandı',
  cancelled: 'İptal edildi',
};

type QuestJournalSectionProps = {
  quests: GameState['quests'];
  offers: NonNullable<GameState['quest_offers']>;
  knownNpcs: GameState['journal']['known_npcs'];
  onAccept: (questId: string) => void;
  onCancel: (questId: string) => void;
  acceptPending: boolean;
  cancelPending: boolean;
  hasError: boolean;
  commandNotice?: string | null;
};

export function QuestJournalSection({
  quests,
  offers,
  knownNpcs,
  onAccept,
  onCancel,
  acceptPending,
  cancelPending,
  hasError,
  commandNotice,
}: QuestJournalSectionProps) {
  const giverName = (giverNpcId: string | null | undefined) => (
    giverNpcId
      ? knownNpcs.find((npc) => npc.npc_id === giverNpcId)?.name ?? giverNpcId
      : null
  );

  return (
    <section className="journal-section" data-testid="section-journal-quests">
      <div className="journal-section-heading">
        <div><span className="eyebrow">Kayıt defteri</span><h3>Görevler</h3></div>
        <span className="character-badge">{String(quests.length).padStart(2, '0')}</span>
      </div>
      {hasError && (
        <p className="mt-3 text-sm text-red-700" role="alert" data-testid="quest-command-error">
          Görev işlemi kaydedilemedi. Lütfen yeniden dene.
        </p>
      )}
      {commandNotice && (
        <p className="mt-3 text-sm" role="status" data-testid="quest-command-outcome">
          {commandNotice}
        </p>
      )}
      {(offers.length > 0 || quests.length > 0) ? (
        <div className="mt-3">
          {offers.map((quest) => (
            <article
              className="data-row journal-record"
              key={quest.quest_id}
              data-testid={`journal-quest-offer-${quest.quest_id}`}
            >
              <div className="data-row-head">
                <span>{quest.title}</span>
                <span className="status-pill">Teklif</span>
              </div>
              <p className="data-row-desc">{quest.description}</p>
              {giverName(quest.giver_npc_id) && (
                <div className="data-row-meta">Görevi veren: {giverName(quest.giver_npc_id)}</div>
              )}
              <ul className="journal-objectives">
                {quest.objectives.map((objective) => (
                  <li key={objective.objective_id}>
                    <span>{objective.description}</span>
                    <span className="status-pill">
                      {objective.kind} · {objective.target} · {objective.required_count}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex gap-2">
                <button
                  className="dnd-button"
                  type="button"
                  disabled={acceptPending || cancelPending}
                  data-testid={`button-accept-quest-${quest.quest_id}`}
                  data-quest-id={quest.quest_id}
                  onClick={() => onAccept(quest.quest_id)}
                >
                  Kabul et
                </button>
                <button
                  className="dnd-button secondary"
                  type="button"
                  disabled={acceptPending || cancelPending}
                  data-testid={`button-cancel-quest-${quest.quest_id}`}
                  data-quest-id={quest.quest_id}
                  onClick={() => onCancel(quest.quest_id)}
                >
                  Reddet
                </button>
              </div>
            </article>
          ))}
          {quests.map((quest) => (
            <article
              className="data-row journal-record"
              key={quest.quest_id}
              data-testid={`journal-quest-${quest.quest_id}`}
            >
              <div className="data-row-head">
                <span>{quest.title}</span>
                <span className="status-pill">{QUEST_STATUS_LABELS[quest.status] ?? quest.status}</span>
              </div>
              <p className="data-row-desc">{quest.description}</p>
              {giverName(quest.giver_npc_id) && (
                <div className="data-row-meta">Görevi veren: {giverName(quest.giver_npc_id)}</div>
              )}
              {quest.objectives.length > 0 && (
                <ul className="journal-objectives">
                  {quest.objectives.map((objective) => (
                    <li
                      key={objective.objective_id}
                      data-testid={`journal-objective-${objective.objective_id}`}
                    >
                      <span>{objective.description}</span>
                      <span className="status-pill">
                        {objective.progress}/{objective.required_count} · {QUEST_STATUS_LABELS[objective.status] ?? objective.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {quest.status === 'accepted' && (
                <div className="mt-3">
                  <button
                    className="dnd-button secondary"
                    type="button"
                    disabled={acceptPending || cancelPending}
                    data-testid={`button-cancel-accepted-quest-${quest.quest_id}`}
                    data-quest-id={quest.quest_id}
                    onClick={() => onCancel(quest.quest_id)}
                  >
                    Görevi iptal et
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-line mt-3" data-testid="empty-journal-quests">
          Henüz kayıtlı görev yok.
        </div>
      )}
    </section>
  );
}