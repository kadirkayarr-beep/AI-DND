import { term, termTitle, abilitySentence } from '@/lib/tr-terms';
import type { EconomyStepInput } from '@workspace/api-client-react';
import { readRogueProjection, tripRefused } from '@/lib/rogue-projection';
export { cunningStrikeFields, readRogueProjection } from '@/lib/rogue-projection';

const STRIKE_LABELS: Record<string, string> = { poison: 'Poison', trip: 'Trip', withdraw: 'Withdraw' };

export function RogueStatus({ rogue }: { rogue: unknown }) {
  const value = readRogueProjection(rogue);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="rogue-status">
    <p data-testid="rogue-sneak-attack"><span title={termTitle('sneak_attack')}>{term('sneak_attack')}</span>: {value.sneak_attack.dice}d{value.sneak_attack.die}{value.sneak_attack.used_this_turn ? ' · bu tur kullanıldı' : ''}</p>
    {value.subclass === 'assassin' && <p data-testid="rogue-subclass">Alt sınıf: Assassin</p>}
    {value.cunning_strike && <p data-testid="rogue-strike-dc">Cunning Strike DC: {value.cunning_strike.dc}</p>}
    {value.uncanny_dodge && <p data-testid="rogue-uncanny">Uncanny Dodge: {value.uncanny_dodge.enabled ? 'açık' : 'kapalı'}</p>}
  </div>;
}

/** The pick travels with the next attack; the server pays the die only if Sneak Attack lands. */
export function CunningStrikeControl({ rogue, targetId, option, distance, disabled, onOptionChange, onDistanceChange }: {
  rogue: unknown; targetId: string; option: string; distance: string; disabled: boolean;
  onOptionChange: (option: string) => void; onDistanceChange: (distance: string) => void;
}) {
  const value = readRogueProjection(rogue);
  const strike = value?.cunning_strike;
  if (!value || !strike || value.sneak_attack.used_this_turn) return null;
  return <div className="story-meta mt-2" data-testid="cunning-strike-control">
    <label>Cunning Strike <select aria-label="Cunning Strike" data-testid="cunning-strike-option" className="bg-(--unw-surface-sunken) border border-(color:--unw-border) rounded"
      value={option} disabled={disabled} onChange={event => onOptionChange(event.target.value)}>
      <option value="">Yok</option>
      {strike.options.map(item => {
        const refused = tripRefused(value, item.id, targetId);
        const reason = item.reason ?? (refused ? 'cunning_strike_target_too_large' : null);
        return <option key={item.id} value={item.id} disabled={!item.available || refused}>{STRIKE_LABELS[item.id]} · {item.cost}d{value.sneak_attack.die}{reason ? ` · ${reason}` : ''}</option>;
      })}
    </select></label>
    {tripRefused(value, option, targetId) && <p role="status" data-testid="cunning-strike-refused">Bu hedefe Trip uygulanamaz: hedef Large boyutundan büyük.</p>}
    {option === 'withdraw' && <label>{' '}Mesafe (<span title={termTitle('feet')}>{term('feet')}</span>, en çok {strike.withdraw_max_ft}) <input aria-label="Withdraw mesafesi" data-testid="cunning-strike-distance" type="number" min="1" step="1"
      className="w-16 bg-transparent border border-(color:--unw-border) rounded px-1" value={distance} disabled={disabled} onChange={event => onDistanceChange(event.target.value)} /></label>}
    <p>Saldırıdan önce seçilir. <span title={termTitle('sneak_attack')}>{term('sneak_attack')}</span> gerçekleşirse zar düşülür ve etki hasardan hemen sonra olur; gerçekleşmezse bir şey harcanmaz.</p>
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
        if (!blocked && action.dash.available) onCommand(abilitySentence(term('cunning_action') + " ile " + term('dash')), { kind: 'cunning_action', resource: 'bonus', cunning_option: 'dash' });
      }}><span title={termTitle('cunning_action')}>{term('cunning_action')}</span> · <span title={termTitle('dash')}>{term('dash')}</span></button>
      <button type="button" className="action-suggestion" data-testid="button-cunning-disengage" disabled={blocked || !action.disengage.available} onClick={() => {
        if (!blocked && action.disengage.available) onCommand(abilitySentence(term('cunning_action') + " ile Disengage"), { kind: 'cunning_action', resource: 'bonus', cunning_option: 'disengage' });
      }}><span title={termTitle('cunning_action')}>{term('cunning_action')}</span> · Disengage</button>
      {action.dash.reason && <p role="status"><span title={termTitle('cunning_action')}>{term('cunning_action')}</span> kullanılamıyor: {action.dash.reason}</p>}
    </>}
    {aim && <button type="button" className="action-suggestion" data-testid="button-steady-aim" disabled={blocked || !aim.available} onClick={() => {
      if (!blocked && aim.available) onCommand('Steady Aim kullanıyorum.', { kind: 'steady_aim', resource: 'bonus' });
    }}>Steady Aim · <span title={termTitle('bonus_action')}>{term('bonus_action')}</span></button>}
    {aim?.active && <p data-testid="steady-aim-active">Steady Aim etkin: bu tur Hızın 0.</p>}
    {aim?.reason && <p role="status">Steady Aim kullanılamıyor: {aim.reason}</p>}
    {dodge && <label><input type="checkbox" data-testid="uncanny-dodge-toggle" checked={dodge.enabled} disabled={blocked} onChange={event => {
      if (!blocked) onCommand(event.target.checked ? 'Uncanny Dodge açıyorum.' : 'Uncanny Dodge kapatıyorum.', { kind: 'uncanny_dodge', uncanny_dodge_enabled: event.target.checked });
    }} /> Uncanny Dodge: gördüğüm saldırganın ilk isabetinde <span title={termTitle('reaction')}>{term('reaction')}</span> kullan</label>}
  </div>;
}
