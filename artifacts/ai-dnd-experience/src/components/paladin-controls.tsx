import { term, termTitle, abilitySentence } from '@/lib/tr-terms';
import { useState } from 'react';
import type { EconomyStepInput } from '@workspace/api-client-react';
import { divineSmiteStep, layOnHandsStep, readPaladinProjection } from '@/lib/paladin-projection';
export { readPaladinProjection } from '@/lib/paladin-projection';

export function PaladinStatus({ paladin }: { paladin: unknown }) {
  const value = readPaladinProjection(paladin);
  if (!value) return null;
  const notCastable = value.prepared_spells.filter(spell => !spell.castable).map(spell => spell.id);
  return <div className="story-meta mt-3" data-testid="paladin-status">
    <p data-testid="paladin-lay-on-hands"><span title={termTitle('lay_on_hands')}>{term('lay_on_hands')}</span>: {value.lay_on_hands.pool_remaining}/{value.lay_on_hands.pool_maximum}</p>
    {value.channel_divinity && <p data-testid="paladin-channel-divinity">Channel Divinity: {value.channel_divinity.uses_remaining}/{value.channel_divinity.max_uses}</p>}
    {value.fighting_style && <p data-testid="paladin-style">Dövüş tarzı: {value.fighting_style}</p>}
    {value.divine_sense?.active && <p data-testid="paladin-divine-sense">Divine Sense: {value.divine_sense.remaining_seconds} sn · {value.divine_sense.detected.length
      ? value.divine_sense.detected.map(creature => `${creature.creature_type} ${creature.distance_ft} ft`).join(', ') : 'çatışmada algılanan yok'}</p>}
    {value.sacred_weapon?.active && <p data-testid="paladin-sacred-weapon">Sacred Weapon: +{value.sacred_weapon.attack_bonus} · {value.sacred_weapon.weapon_id} · {value.sacred_weapon.remaining_seconds} sn</p>}
    {value.always_prepared.length > 0 && <p data-testid="paladin-always-prepared">Her zaman hazır: {value.always_prepared.join(', ')}</p>}
    {notCastable.length > 0 && <p data-testid="paladin-catalog-only">Hazırlı, oyunda henüz etkisi yok: {notCastable.join(', ')}</p>}
  </div>;
}

/** Sacred Weapon is a choice on the Attack action, so the panel keeps it and adds it to the attack it sends. */
export function SacredWeaponChoice({ paladin, wanted, radiant, disabled, onChange }: {
  paladin: unknown; wanted: boolean; radiant: boolean; disabled: boolean; onChange: (next: { wanted: boolean; radiant: boolean }) => void;
}) {
  const sacred = readPaladinProjection(paladin)?.sacred_weapon;
  if (!sacred) return null;
  return <div className="story-meta mt-2" data-testid="paladin-sacred-weapon-choice">
    {!sacred.active && <label><input type="checkbox" data-testid="paladin-sacred-weapon-start" checked={wanted} disabled={disabled || !sacred.start.available}
      onChange={event => onChange({ wanted: event.target.checked, radiant })} /> Sacred Weapon: bu saldırıda Channel Divinity harca (+{sacred.attack_bonus})</label>}
    {sacred.start.reason && !sacred.active && <p role="status">Sacred Weapon kullanılamıyor: {sacred.start.reason}</p>}
    {(sacred.active || wanted) && <label><input type="checkbox" data-testid="paladin-radiant-damage" checked={radiant} disabled={disabled}
      onChange={event => onChange({ wanted, radiant: event.target.checked })} /> Bu saldırı Radiant hasar versin</label>}
  </div>;
}

export function PaladinControl({ paladin, blocked, onCommand }: {
  paladin: unknown; blocked: boolean; onCommand: (label: string, step: EconomyStepInput) => void;
}) {
  const [amount, setAmount] = useState('');
  const [poison, setPoison] = useState(false);
  const [slot, setSlot] = useState('');
  const value = readPaladinProjection(paladin);
  if (!value) return null;
  const touch = layOnHandsStep(value, amount, poison);
  const touchEnabled = !blocked && value.lay_on_hands.activate.available && touch !== null;
  const smite = value.divine_smite;
  const smiteStep = divineSmiteStep(value, slot);
  const smiteEnabled = !blocked && smite?.activate.available === true && smiteStep !== null;
  const sense = value.divine_sense;
  const senseEnabled = !blocked && sense?.activate.available === true;
  return <div className="story-meta mt-3" data-testid="paladin-controls">
    <PaladinStatus paladin={value} />
    <label><span title={termTitle('lay_on_hands')}>{term('lay_on_hands')}</span> (can) <input aria-label={term('lay_on_hands') + ' miktarı'} data-testid="paladin-lay-amount" type="number" min="1" step="1"
      className="w-16 bg-transparent border border-(color:--unw-border) rounded px-1" value={amount} onChange={event => setAmount(event.target.value)} /></label>
    <label><input type="checkbox" data-testid="paladin-lay-poison" checked={poison} onChange={event => setPoison(event.target.checked)} /> Poisoned kaldır ({value.lay_on_hands.poison_cost} puan)</label>
    <button type="button" className="action-suggestion" data-testid="button-lay-on-hands" disabled={!touchEnabled} onClick={() => {
      if (touchEnabled && touch) { setAmount(''); setPoison(false); onCommand(abilitySentence(term('lay_on_hands')), touch); }
    }}><span title={termTitle('lay_on_hands')}>{term('lay_on_hands')}</span> · <span title={termTitle('bonus_action')}>{term('bonus_action')}</span></button>
    {value.lay_on_hands.activate.reason && <p role="status"><span title={termTitle('lay_on_hands')}>{term('lay_on_hands')}</span> kullanılamıyor: {value.lay_on_hands.activate.reason}</p>}
    {smite && <>
      <label><span title={termTitle('divine_smite')}>{term('divine_smite')}</span> <select aria-label={term('divine_smite') + " yuvası"} data-testid="paladin-smite-slot" value={slot} onChange={event => setSlot(event.target.value)}>
        <option value="">Yuvasız kullanım{smite.free_cast_available ? '' : ' (uzun dinlenme bekliyor)'}</option>
        {smite.slot_levels.map(level => <option key={level} value={level}>{level}. seviye yuva</option>)}
      </select></label>
      <button type="button" className="action-suggestion" data-testid="button-divine-smite" disabled={!smiteEnabled} onClick={() => {
        if (smiteEnabled && smiteStep) onCommand(abilitySentence(term('divine_smite')), smiteStep);
      }}><span title={termTitle('divine_smite')}>{term('divine_smite')}</span> · <span title={termTitle('bonus_action')}>{term('bonus_action')}</span></button>
      {smite.activate.reason && <p role="status"><span title={termTitle('divine_smite')}>{term('divine_smite')}</span> kullanılamıyor: {smite.activate.reason}</p>}
    </>}
    {sense && <>
      <button type="button" className="action-suggestion" data-testid="button-divine-sense" disabled={!senseEnabled} onClick={() => {
        if (senseEnabled) onCommand('Divine Sense kullanıyorum.', { kind: 'divine_sense', resource: 'bonus' });
      }}>Divine Sense · <span title={termTitle('bonus_action')}>{term('bonus_action')}</span></button>
      {sense.activate.reason && <p role="status">Divine Sense kullanılamıyor: {sense.activate.reason}</p>}
    </>}
  </div>;
}
