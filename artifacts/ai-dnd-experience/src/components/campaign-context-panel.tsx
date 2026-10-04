import type { GameState } from '@workspace/api-client-react';
import { campaignDateLabel, currentSceneContext } from '@/lib/campaign-presentation';

export function CampaignDate({ state }: { state: GameState }) {
  const label = campaignDateLabel(state.campaign_time);
  return label ? <span data-testid="campaign-date" data-year={state.campaign_time!.year} title={state.campaign_time!.detail}>{label}</span> : null;
}

/** Supporting scene information only; this component cannot issue game commands. */
export function CampaignContextPanel({ state }: { state: GameState }) {
  const { location, scene, people } = currentSceneContext(state);
  const quests = (state.quests ?? []).filter((quest) => quest.status === 'accepted');
  const actor = state.combat.participant_records.find((participant) => participant.id === state.combat.current_actor_id);
  return <section className="state-panel" data-testid="panel-world">
    <div className="dnd-kicker">İçinde bulunduğun sahne</div><h2>Çevre</h2>
    <div className="location-current" data-testid="text-current-location">
      <small>Şu anki konum</small>{location?.name ?? 'Konum ayrıntıları henüz görünmüyor.'}
    </div>
    {location?.description && <p className="subtle-text mt-3">{location.description}</p>}
    {state.campaign_time && <div className="data-row mt-3" data-testid="world-time"><CampaignDate state={state} /></div>}
    {scene && <div className="data-row mt-3" data-testid="context-scene">
      <div className="data-row-head">Şu anki sahne</div>
      <p className="data-row-desc">{scene.opening ?? 'Ayrıntıları kişiler ve çevredeki nesneler arasında inceleyebilirsin.'}</p>
    </div>}
    <div className="mt-4" data-testid="context-people"><h3 className="dnd-kicker">Yakınındaki kişiler</h3>
      {people.length ? people.map((person) => <div className="data-row" key={person.id}>
        <span>{person.name}</span>{person.role && <span className="data-row-meta"> · {person.role}</span>}
      </div>) : <p className="empty-line mt-2">Bu sahnede görünen biri yok.</p>}
    </div>
    {quests.length > 0 && <div className="mt-4" data-testid="context-quests"><h3 className="dnd-kicker">Etkin görevler</h3>
      {quests.map((quest) => <details className="data-row" key={quest.quest_id}><summary>{quest.title}</summary>
        <p className="data-row-desc">{quest.description}</p>
        {quest.objectives.map((objective) => <p className="subtle-text" key={objective.objective_id}>{objective.description} — {objective.status === 'completed' ? 'Tamamlandı' : 'Sürüyor'}</p>)}
      </details>)}
    </div>}
    {state.combat.active && <div className="data-row mt-4" data-testid="context-combat">
      <strong>Çatışma sürüyor · Raunt {state.combat.round}</strong>
      {actor && <p className="data-row-desc">Sıra: {actor.name}</p>}
      <p className="subtle-text">İnisiyatif ve hamlelerini Çatışma sekmesinde incele.</p>
    </div>}
    {state.player_combat_status !== 'active' && <p className="data-row mt-3" data-testid="context-condition">
      {state.player_combat_status === 'dead' ? 'Yaşamın sona erdi.' : state.death_state.stable ? 'Durumun dengelendi; bilincin kapalı.' : 'Bilincin kapalı.'}
      {' '}Ölüm kurtarışlarını ve iyileşme durumunu Çatışma sekmesinde incele.
    </p>}
    {state.known_scheduled_events?.length > 0 && <details className="mt-4">
      <summary className="dnd-kicker">Bildiğin yaklaşan olaylar</summary>
      {state.known_scheduled_events.map((event, index) => <p className="data-row-desc mt-2" key={index}>{event.summary}</p>)}
    </details>}
    <p className="subtle-text mt-4">Keşfettiğin diğer yerler ve karşılaşmalar Günlük sekmesinde.</p>
  </section>;
}