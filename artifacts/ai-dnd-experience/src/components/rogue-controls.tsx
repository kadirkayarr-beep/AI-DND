import type { EconomyStepInput } from '@workspace/api-client-react';
import { readRogueProjection } from '@/lib/rogue-projection';
export { cunningStrikeFields, readRogueProjection } from '@/lib/rogue-projection';

const STRIKE_LABELS: Record<string, string> = { poison: 'Poison', trip: 'Trip', withdraw: 'Withdraw' };

export function RogueStatus({ rogue }: { rogue: unknown }) {
  const value = readRogueProjection(rogue);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="rogue-status">
    <p data-testid="rogue-sneak-attack">Sneak Attack: {value.sneak_attack.dice}d{value.sneak_attack.die}{value.sneak_attack.used_this_turn ? ' · bu tur kullanıldı' : ''}</p>
    {value.subclass === 'assassin' && <p data-testid="rogue-subclass">Alt sınıf: Assassin</p>}
    {value.cunning_strike && <p data-testid="rogue-strike-dc">Cunning Strike DC: {value.cunning_strike.dc}</p>}
    {value.uncanny_dodge && <p data-testid="rogue-uncanny">Uncanny Dodge: {value.uncanny_dodge.enabled ? 'açık' : 'kapalı'}</p>}
  </div>;
}

/** The pick travels with the next attack; the server pays the die only if Sneak Attack lands. */
export function CunningStrikeControl({ rogue, option, distance, disabled, onOptionChange, onDistanceChange }: {
  rogue: unknown; option: string; distance: string; disabled: boolean;
  onOptionChange: (option: string) => void; onDistanceChange: (distance: string) => void;
}) {
  const value = readRogueProjection(rogue);
  const strike = value?.cunning_strike;
  if (!value || !strike || value.sneak_attack.used_this_turn) return null;
  return <div className="story-meta mt-2" data-testid="cunning-strike-control">
    <label>Cunning Strike <select aria-label="Cunning Strike" data-testid="cunning-strike-option" className="bg-stone-900 border border-amber-100/20 rounded"
      value={option} disabled={disabled} onChange={event => onOptionChange(event.target.value)}>
      <option value="">Yok</option>
      {strike.options.map(item => <option key={item.id} value={item.id} disabled={!item.available}>{STRIKE_LABELS[item.id]} · {item.cost}d{value.sneak_attack.die}{item.reason ? ` · ${item.reason}` : ''}</option>)}
    </select></label>
    {option === 'withdraw' && <label>{' '}Mesafe (ft, en çok {strike.withdraw_max_ft}) <input aria-label="Withdraw mesafesi" data-testid="cunning-strike-distance" type="number" min="1" step="1"
      className="w-16 bg-transparent border border-amber-100/20 rounded px-1" value={distance} disabled={disabled} onChange={event => onDistanceChange(event.target.value)} /></label>}
    <p>Saldırıdan önce seçilir. Sneak Attack gerçekleşirse zar düşülür ve etki hasardan hemen sonra olur; gerçekleşmezse bir şey harcanmaz.</p>
  </div>;
}

export function RogueControl({ rogue, blocked, onCommand }: {
  rogue: unknown; blocked: boolean; onCommand: (label: string, step: EconomyStepInput) => void;
}) {
  const value = readRogueProjection(rogue);
  if (!value) return null;
  const action = value.cunning_action;
  const aim = value.steady_aim;
  const dodge = value.uncanny_dodge;
  return <div className="story-meta mt-3" data-testid="rogue-controls">
    <RogueStatus rogue={value} />
    {action && <>
      <button type="button" className="action-suggestion" data-testid="button-cunning-dash" disabled={blocked || !action.dash.available} onClick={() => {
        if (!blocked && action.dash.available) onCommand('Cunning Action ile Dash kullanıyorum.', { kind: 'cunning_action', resource: 'bonus', cunning_option: 'dash' });
      }}>Cunning Action · Dash</button>
      <button type="button" className="action-suggestion" data-testid="button-cunning-disengage" disabled={blocked || !action.disengage.available} onClick={() => {
        if (!blocked && action.disengage.available) onCommand('Cunning Action ile Disengage kullanıyorum.', { kind: 'cunning_action', resource: 'bonus', cunning_option: 'disengage' });
      }}>Cunning Action · Disengage</button>
      {action.dash.reason && <p role="status">Cunning Action kullanılamıyor: {action.dash.reason}</p>}
    </>}
    {aim && <button type="button" className="action-suggestion" data-testid="button-steady-aim" disabled={blocked || !aim.available} onClick={() => {
      if (!blocked && aim.available) onCommand('Steady Aim kullanıyorum.', { kind: 'steady_aim', resource: 'bonus' });
    }}>Steady Aim · Bonus Action</button>}
    {aim?.active && <p data-testid="steady-aim-active">Steady Aim etkin: bu tur Hızın 0.</p>}
    {aim?.reason && <p role="status">Steady Aim kullanılamıyor: {aim.reason}</p>}
    {dodge && <label><input type="checkbox" data-testid="uncanny-dodge-toggle" checked={dodge.enabled} disabled={blocked} onChange={event => {
      if (!blocked) onCommand(event.target.checked ? 'Uncanny Dodge açıyorum.' : 'Uncanny Dodge kapatıyorum.', { kind: 'uncanny_dodge', uncanny_dodge_enabled: event.target.checked });
    }} /> Uncanny Dodge: gördüğüm saldırganın ilk isabetinde Reaction kullan</label>}
  </div>;
}
