import type { GameState } from '@workspace/api-client-react';

const labels: Record<string, string> = {
  discovered: 'Yeni bir iz', offered: 'Bir olasılık', active: 'Peşindesin',
  progressing: 'İlerliyorsun', reframed: 'Yönü değişti', succeeded: 'Sonuca ulaştı',
  failed: 'Yarım kaldı', abandoned: 'Geride bıraktın', expired: 'Zamanı geçti',
};

/** Read-only engine projection. Free-text turns remain the only action owner. */
export function AdventureJournalSection({ adventure }: { adventure: GameState['adventure'] }) {
  if (!adventure) return null;
  const { threads, commitments, plan } = adventure;
  if (!threads.length && !commitments.length && !plan) return null;
  return (
    <section className="journal-section" data-testid="adventure-journal">
      <div className="journal-section-heading">
        <div><span className="eyebrow">Kendi yolun</span><h3>Macera izleri</h3></div>
      </div>
      <p className="mt-3 text-sm">Nasıl ilerleyeceğini kendi sözlerinle anlatabilirsin.</p>
      {threads.map((thread) => (
        <article className="data-row journal-record" key={thread.thread_id} data-testid={`adventure-${thread.thread_id}`}>
          <span className="eyebrow">{labels[thread.status]}</span>
          <p>{thread.title}</p>
          <ul className="mt-2 text-sm">
            {thread.objectives.map((objective) => <li key={objective.objective_id}>
              {objective.status === 'completed' ? 'Tamamlandı · ' : ''}{objective.description}
              {objective.optional ? ' · İstersen' : ''}
            </li>)}
          </ul>
        </article>
      ))}
      {commitments.length > 0 && <div className="data-row">
        <h4>Aranızda kalan sözler</h4>
        {commitments.map((commitment) => <p className="mt-2 text-sm" key={commitment.commitment_id}>
          {commitment.quote} · {commitment.status === 'fulfilled' ? 'Yerine geldi' : commitment.status === 'broken' ? 'Tutulmadı' : 'Henüz yerine gelmedi'}
        </p>)}
      </div>}
      {plan && <div className="data-row" data-testid="adventure-plan">
        <h4>Düşündüğün adımlar</h4>
        <p className="text-sm">{plan.status === 'paused' ? 'Durum değişti; planın bekliyor.' :
          plan.status === 'completed' ? 'Adımların tamamlandı.' :
          plan.status === 'abandoned' ? 'Bu planı geride bıraktın.' : 'Bir sonraki adımı sen seçersin.'}</p>
        <ol className="mt-2 list-decimal pl-5 text-sm">
          {plan.steps.map((step, index) => <li key={`${index}:${step.quote}`}>
            {index < plan.cursor ? 'Tamamlandı · ' : ''}{step.quote}
            {step.precondition ? ` · Önce: ${step.precondition}` : ''}
          </li>)}
        </ol>
      </div>}
    </section>
  );
}