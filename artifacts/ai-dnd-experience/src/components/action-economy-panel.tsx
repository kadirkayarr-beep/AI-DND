import { RageControl, readRageProjection } from './rage-controls';
export { RageControl, RageStatus, readRageProjection } from './rage-controls';
import { useRef, useState } from 'react';
import { createRecklessIntent } from '../lib/reckless-intent';
export { createRecklessIntent } from '../lib/reckless-intent';
import type { CombatActionInput, EconomyStepInput, GameState } from '@workspace/api-client-react';

interface ActorResources {
  reckless_attack?: unknown;
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

export function RecklessAttackControl({ available, active, selected, disabled, onChange }: {
  available: boolean; active: boolean; selected: boolean; disabled: boolean; onChange: (selected: boolean) => void;
}) {
  if (!available && !active) return null;
  return <div className="story-meta mt-2" data-testid="reckless-attack-control">
    {active ? <p data-testid="reckless-attack-active">Reckless Attack etkin.</p> : <label>
      <input type="checkbox" checked={selected} disabled={disabled} onChange={event => { if (!disabled) onChange(event.target.checked); }} />
      {' '}Bu saldırıda Reckless Attack seç
    </label>}
    <p>Sonraki kendi turun başlayana kadar Strength saldırı zarların Avantaj kazanır; sana karşı saldırı zarları da Avantaj kazanır. Dexterity saldırısı bu seçimi yapabilir ancak saldırı Avantajı kazanmaz.</p>
  </div>;
}

/** Ephemeral consent only; pending-action owns the immutable submitted command. */
export function createQuickenedIntent() {
  let key = ''; let available = false; let blocked = true; let selected = false;
  return {
    get selected() { return selected; },
    sync(next: { key: string; available: boolean; blocked: boolean }) {
      if (key !== next.key || !next.available || next.blocked) selected = false;
      key = next.key; available = next.available; blocked = next.blocked;
    },
    choose(value: boolean) { selected = value === true && available && !blocked; },
  };
}

function quickenedProjection(state: GameState) {
  const pool = state.spellcasting?.sorcery_points;
  const mode = (state.combat.action_economy as { actors?: { player?: { quickened_spell?: { available?: unknown; reason?: unknown } } } } | null)?.actors?.player?.quickened_spell;
  if (!pool || !Number.isSafeInteger(pool.current) || !Number.isSafeInteger(pool.max)
    || Number(pool.current) < 0 || Number(pool.max) < Number(pool.current)
    || !mode || typeof mode.available !== 'boolean' || !(mode.reason === null || typeof mode.reason === 'string')) return null;
  return { current: Number(pool.current), max: Number(pool.max), available: mode.available, reason: mode.reason as string | null };
}

/** Candidates come from the shared combat target selector; spell_scope alone decides range, visibility and defenses. */
export function MagicMissileControl({ state, targetId, slot, onSlotChange, blocked, magicAvailable, quickened = false, onQuickenedChange, onCommand }: {
  state: GameState; targetId: string; slot: string; onSlotChange: (slot: string) => void;
  blocked: boolean; magicAvailable: boolean; quickened?: boolean; onQuickenedChange?: (selected: boolean) => void; onCommand: (message: string, command: CombatActionInput) => void;
}) {
  if (!state.spellcasting?.prepared.includes('Magic Missile')) return null;
  const projection = quickenedProjection(state);
  const optedIn = !!projection && quickened;
  const slots = state.spellcasting.slots;
  const offered = [1, 2, 3].filter(level => Object.prototype.hasOwnProperty.call(slots, String(level)));
  const selected = Number(slot);
  const candidate = state.combat.participant_records.some(actor => actor.id === targetId && actor.kind === 'npc' && actor.status === 'active' && actor.current_hp > 0);
  const enabled = !blocked && (optedIn ? projection!.available : magicAvailable) && state.combat.active && state.combat.current_actor_id === 'player'
    && candidate && offered.includes(selected) && (slots[String(selected)] ?? 0) > 0;
  return <div className="mt-3 story-meta" data-testid="magic-missile-controls">
    {projection && <div>
      <p data-testid="sorcery-points">Sorcery Points: {projection.current}/{projection.max}</p>
      <label><input type="checkbox" data-testid="select-quickened-spell" checked={optedIn}
        disabled={blocked || !projection.available} onChange={event => { if (!blocked && projection.available) onQuickenedChange?.(event.target.checked); }} />
        {' '}Bu Magic Missile için Quickened Spell · 2 Sorcery Points · Bonus Action</label>
      {projection.reason && <p role="status">Quickened Spell kullanılamıyor: {projection.reason}</p>}
      <p>Yalnızca bu büyü için açık seçimdir; diğer Metamagic etkileri uygulanmış değildir. Bu tur başka seviye 1+ büyü kullanımı sunucu tarafından denetlenir.</p>
    </div>}
    <label>Magic Missile · yuva seviyesi <select data-testid="select-magic-missile-slot" value={slot} disabled={blocked} onChange={event => onSlotChange(event.target.value)}>
      {offered.map(level => <option key={level} value={String(level)} disabled={(slots[String(level)] ?? 0) <= 0}>{level}. seviye · kalan {slots[String(level)]}</option>)}
    </select></label>
    <button type="button" className="action-suggestion" data-testid="button-cast-magic-missile" disabled={!enabled} onClick={() => {
      if (!enabled) return;
      onCommand('Magic Missile kullanıyorum.', { steps: [{ kind: 'magic', ability: 'Magic Missile', target_id: targetId, slot_level: selected, ...(optedIn ? { metamagic: 'quickened_spell' as const } : {}) }] });
    }}>Magic Missile · {optedIn ? 'Bonus Action (Quickened)' : 'Action'}</button>
    <p>Ortak hedef alanından bir hedef seç. Menzil, görüş ve hedef koşullarını sunucu doğrular; seçili hedef önceden onaylanmış değildir.</p>
  </div>;
}

export function ActionEconomyPanel({ state, targetId, sending, decisionScope = '', onCommand }: {
  state: GameState;
  targetId: string;
  sending: boolean;
  decisionScope?: string;
  onCommand: (message: string, command: CombatActionInput) => void;
}) {
  const intentRef = useRef<ReturnType<typeof createRecklessIntent> | null>(null);
  if (!intentRef.current) intentRef.current = createRecklessIntent();
  const intent = intentRef.current;
  const [, redrawIntent] = useState(0);
  const [magicSlot, setMagicSlot] = useState('1');
  const quickenedRef = useRef<ReturnType<typeof createQuickenedIntent> | null>(null);
  if (!quickenedRef.current) quickenedRef.current = createQuickenedIntent();
  const quickenedIntent = quickenedRef.current;
  const rageRef = useRef<ReturnType<typeof createQuickenedIntent> | null>(null);
  if (!rageRef.current) rageRef.current = createQuickenedIntent();
  const rageIntent = rageRef.current;
  const [distance, setDistance] = useState('5');
  const [triggerEvent, setTriggerEvent] = useState<'actor_attacks' | 'actor_moves'>('actor_attacks');
  const [triggerActor, setTriggerActor] = useState('target');
  const [readyKind, setReadyKind] = useState<'attack' | 'move'>('attack');
  const economy = state.combat.action_economy as { actors?: Record<string, ActorResources> } | null;
  const resources = economy?.actors?.player;
  if (!state.combat.active || !resources) {
    quickenedIntent.sync({ key: 'inactive', available: false, blocked: true });
    rageIntent.sync({ key: 'inactive', available: false, blocked: true });
    intent.sync({decisionKey: 'inactive', projection: null, sending, attackEnabled: false, continueEnabled: false, reactionEnabled: false});
    return null;
  }
  const current = state.combat.current_actor_id === 'player';
  const pending = !!resources.opportunity;
  const legal = (kind: string) => resources.legal_actions.some((item) => item.kind === kind && item.legal);
  const distanceValue = Number(distance);
  const distanceValid = Number.isSafeInteger(distanceValue) && distanceValue > 0;
  const blocked = sending || pending || !current;
  quickenedIntent.sync({ key: JSON.stringify([decisionScope, targetId, magicSlot, state.combat.combat_id, state.combat.round, state.combat.current_turn_index, state.combat.current_actor_id]), available: quickenedProjection(state)?.available === true, blocked });
  const rage = readRageProjection(state.character?.rage);
  const rageAvailable = (rage?.active ? rage.extend.available : rage?.activate.available) === true;
  rageIntent.sync({ key: JSON.stringify([decisionScope, state.combat.combat_id, state.combat.round, state.combat.current_turn_index, state.combat.current_actor_id, rage]), available: rageAvailable, blocked });
  const attackEnabled = !blocked && legal('attack') && !!targetId;
  const continueEnabled = !blocked && !!resources.attack_action?.remaining_attacks && !!targetId;
  const reactionEnabled = !sending && current && pending && resources.reaction_available && resources.ready?.response.kind === 'attack';
  intent.sync({
    decisionKey: JSON.stringify([state.combat.combat_id, state.combat.round, state.combat.current_turn_index,
      state.combat.current_actor_id, resources.opportunity?.id, resources.ready?.response.kind]),
    projection: resources.reckless_attack, sending, attackEnabled, continueEnabled, reactionEnabled,
  });
  const send = (label: string, step: EconomyStepInput) => {
    const mode = step.kind === 'attack' ? 'attack' : step.kind === 'continue_attack' ? 'continue' : step.kind === 'react' ? 'reaction' : 'other';
    const enabled = step.kind === 'react' ? pending && resources.reaction_available : step.kind === 'decline_reaction' ? pending : !blocked;
    quickenedIntent.choose(false);
    rageIntent.choose(false);
    intent.submit(mode, step, onCommand, label, enabled);
    redrawIntent(value => value + 1);
  };
  const recklessControl = <RecklessAttackControl available={intent.available} active={intent.active} selected={intent.selected}
    disabled={sending || !(attackEnabled || continueEnabled || reactionEnabled)} onChange={value => { intent.choose(value); redrawIntent(n => n + 1); }} />;
  return (
    <section className="px-4 py-3 border-t border-amber-100/10" aria-label="Tur kaynakları" data-testid="action-economy-panel">
      <div className="story-meta flex flex-wrap gap-x-4 gap-y-1" data-testid="action-economy-resources">
        <span>Action: {resources.base_action_spent ? 'kullanıldı' : 'hazır'}</span>
        <span>Bonus: {resources.bonus_action_spent ? 'kullanıldı' : (resources.bonus_action_available || quickenedProjection(state)?.available || rageAvailable) ? 'hazır' : 'uygun yetenek yok'}</span>
        <span>Reaction: {resources.reaction_available ? 'hazır; tetikleyici gerekir' : 'kullanılamaz'}</span>
        <span>Hareket: {resources.movement_remaining} ft · Speed: {resources.speed_ft} ft</span>
      </div>
      {resources.additional_actions.map((grant, index) => <div className="story-meta mt-1" key={index}>
        Ek Action · {grant.source}: {grant.remaining} · {grant.allowed_action_types.join(', ')}
      </div>)}
      {resources.ready && <p className="story-meta mt-2" data-testid="ready-status">
        Ready: {resources.ready.trigger.event === 'actor_moves' ? 'hareket' : 'saldırı'} sonrası {resources.ready.response.kind === 'move' ? 'hareket' : 'Action'}.
      </p>}
      {(!pending || reactionEnabled || intent.active) && recklessControl}
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
          <RageControl rage={rage} confirmed={rageIntent.selected} blocked={blocked} onChange={value => { rageIntent.choose(value); redrawIntent(n => n + 1); }} onCommand={(label, command) => { if (command.steps[0]) send(label, command.steps[0]); }} />
          <MagicMissileControl state={state} targetId={targetId} slot={magicSlot} onSlotChange={setMagicSlot} blocked={blocked} magicAvailable={legal('magic')} quickened={quickenedIntent.selected} onQuickenedChange={value => { quickenedIntent.choose(value); redrawIntent(n => n + 1); }} onCommand={(label, command) => { if (command.steps[0]) send(label, command.steps[0]); }} />
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