import { useState } from 'react';
import type { CombatActionInput, EconomyStepInput, GameState } from '@workspace/api-client-react';

interface ActorResources {
  base_action_spent: boolean;
  additional_actions: { source: string; remaining: number; allowed_action_types: string[] }[];
  bonus_action_available: boolean;
  bonus_action_spent: boolean;
  bonus_rules: string[];
  reaction_available: boolean;
  movement_remaining: number;
  speed_ft: number;
  ready: { trigger: { event: string; actor_id: string }; response: { kind: string } } | null;
  opportunity: { id: string } | null;
  attack_action?: { remaining_attacks: number } | null;
  legal_actions: { kind: string; legal: boolean; reason: string | null }[];
}

export function ActionEconomyPanel({ state, targetId, sending, onCommand }: {
  state: GameState;
  targetId: string;
  sending: boolean;
  onCommand: (message: string, command: CombatActionInput) => void;
}) {
  const [distance, setDistance] = useState('5');
  const [triggerEvent, setTriggerEvent] = useState<'actor_attacks' | 'actor_moves'>('actor_attacks');
  const [triggerActor, setTriggerActor] = useState('target');
  const [readyKind, setReadyKind] = useState<'attack' | 'move'>('attack');
  const economy = state.combat.action_economy as { actors?: Record<string, ActorResources> } | null;
  const resources = economy?.actors?.player;
  if (!state.combat.active || !resources) return null;
  const current = state.combat.current_actor_id === 'player';
  const pending = !!resources.opportunity;
  const legal = (kind: string) => resources.legal_actions.some((item) => item.kind === kind && item.legal);
  const distanceValue = Number(distance);
  const distanceValid = Number.isSafeInteger(distanceValue) && distanceValue > 0;
  const blocked = sending || pending || !current;
  const send = (label: string, step: EconomyStepInput) => onCommand(label, { steps: [step] });
  return (
    <section className="px-4 py-3 border-t border-amber-100/10" aria-label="Tur kaynakları" data-testid="action-economy-panel">
      <div className="story-meta flex flex-wrap gap-x-4 gap-y-1" data-testid="action-economy-resources">
        <span>Action: {resources.base_action_spent ? 'kullanıldı' : 'hazır'}</span>
        <span>Bonus: {resources.bonus_action_spent ? 'kullanıldı' : resources.bonus_action_available ? 'hazır' : 'uygun yetenek yok'}</span>
        <span>Reaction: {resources.reaction_available ? 'hazır; tetikleyici gerekir' : 'kullanılamaz'}</span>
        <span>Hareket: {resources.movement_remaining} ft · Speed: {resources.speed_ft} ft</span>
      </div>
      {resources.additional_actions.map((grant, index) => <div className="story-meta mt-1" key={index}>
        Ek Action · {grant.source}: {grant.remaining} · {grant.allowed_action_types.join(', ')}
      </div>)}
      {resources.ready && <p className="story-meta mt-2" data-testid="ready-status">
        Ready: {resources.ready.trigger.event === 'actor_moves' ? 'hareket' : 'saldırı'} sonrası {resources.ready.response.kind === 'move' ? 'hareket' : 'Action'}.
      </p>}
      {pending ? (
        <div className="action-suggestion-list mt-2" data-testid="reaction-opportunity">
          <span className="story-meta">Hazırladığın hamlenin koşulu gerçekleşti.</span>
          <button type="button" className="action-suggestion" disabled={sending || !resources.reaction_available}
            onClick={() => send('Ready Reaction kullanıyorum.', { kind: 'react', opportunity_id: resources.opportunity!.id })}>Reaction kullan</button>
          <button type="button" className="action-suggestion" disabled={sending}
            onClick={() => send('Ready Reaction fırsatını atlıyorum.', { kind: 'decline_reaction', opportunity_id: resources.opportunity!.id })}>Fırsatı atla</button>
        </div>
      ) : (
        <>
          <div className="action-suggestion-list mt-2">
            <button type="button" className="action-suggestion" disabled={blocked || !legal('attack') || !targetId}
              onClick={() => send('Saldırı Action kullanıyorum.', { kind: 'attack', target_id: targetId })}>Saldır · Action</button>
            {!!resources.attack_action?.remaining_attacks && <button type="button" className="action-suggestion" disabled={blocked || !targetId}
              onClick={() => send('Aynı Attack Action içindeki saldırıya devam ediyorum.', { kind: 'continue_attack', target_id: targetId })}>Attack Action devamı</button>}
            <button type="button" className="action-suggestion" disabled={blocked || !legal('dash')}
              onClick={() => send('Dash Action kullanıyorum.', { kind: 'dash' })}>Dash · Action</button>
            {resources.bonus_rules.map((ability) => <button key={ability} type="button" className="action-suggestion" disabled={blocked || !resources.bonus_action_available}
              onClick={() => send(`${ability} Bonus Action kullanıyorum.`, { kind: 'species', ability, ...(ability === 'celestial_revelation' ? { form: 'heavenly_wings' } : {}) })}>
              {ability === 'adrenaline_rush' ? 'Adrenalin / Dash' : ability === 'large_form' ? 'Büyük Biçim' : ability === 'cloud_jaunt' ? 'Bulut Sıçrayışı' : 'Göksel Tecelli · Kanatlar'} · Bonus
            </button>)}
            <button type="button" className="action-suggestion" disabled={blocked}
              onClick={() => send('Turumu bitiriyorum.', { kind: 'end_turn' })}>Turu bitir</button>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3 story-meta">
            <label>Mesafe (ft) <input aria-label="Hareket mesafesi" type="number" min="1" step="1" className="w-16 bg-transparent border border-amber-100/20 rounded px-1" value={distance} onChange={(event) => setDistance(event.target.value)} /></label>
            <button type="button" className="action-suggestion" disabled={blocked || !distanceValid || resources.movement_remaining <= 0}
              onClick={() => send(`${distanceValue} feet hareket ediyorum.`, { kind: 'move', distance_ft: distanceValue })}>Hareket et</button>
            <label>Tetikleyici <select aria-label="Ready tetikleyicisi" className="bg-stone-900 border border-amber-100/20 rounded" value={triggerEvent} onChange={(event) => setTriggerEvent(event.target.value as typeof triggerEvent)}>
              <option value="actor_attacks">Saldırı tamamlandığında</option><option value="actor_moves">Hareket tamamlandığında</option>
            </select></label>
            <select aria-label="Ready tetikleyicisinin aktörü" className="bg-stone-900 border border-amber-100/20 rounded" value={triggerActor} onChange={(event) => setTriggerActor(event.target.value)}>
              <option value="target">Seçili hedef</option><option value="player">Ben</option>
            </select>
            <select aria-label="Ready yanıtı" className="bg-stone-900 border border-amber-100/20 rounded" value={readyKind} onChange={(event) => setReadyKind(event.target.value as typeof readyKind)}>
              <option value="attack">Saldırı</option><option value="move">Hareket</option>
            </select>
            <button type="button" className="action-suggestion" disabled={blocked || !legal('ready') || (triggerActor === 'target' && !targetId) || (readyKind === 'attack' && !targetId) || (readyKind === 'move' && !distanceValid)}
              onClick={() => send('Ready Action hazırlıyorum.', { kind: 'ready',
                trigger: { event: triggerEvent, actor_id: triggerActor === 'player' ? 'player' : targetId },
                response: readyKind === 'attack' ? { kind: 'attack', target_id: targetId } : { kind: 'move', distance_ft: distanceValue } })}>Ready · Action</button>
          </div>
        </>
      )}
    </section>
  );
}