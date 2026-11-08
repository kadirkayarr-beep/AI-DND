import { DEFAULT_CATALOG } from '@/lib/character-catalog-defaults';
import { catalogDisplayName } from '@/lib/catalog-display';
import { term, termTitle, abilitySentence } from '@/lib/tr-terms';
import type { EconomyStepInput, FighterState, GameState } from '@workspace/api-client-react';
import type { InteractionMode } from '@/lib/action-suggestions';
import { readFighterProjection, tacticalMindAvailable } from '@/lib/fighter-projection';
export { readFighterProjection, tacticalMindAvailable } from '@/lib/fighter-projection';

/** The typed step for Second Wind; a Tactical Shift distance is sent only when the server says it exists. Null means do not send. */
export function secondWindStep(fighter: FighterState, shift: string): EconomyStepInput | null {
  if (shift.trim() === '') return { kind: 'second_wind', resource: 'bonus' };
  const distance = Number(shift);
  if (!fighter.second_wind.tactical_shift || !Number.isSafeInteger(distance) || distance < 1) return null;
  return { kind: 'second_wind', resource: 'bonus', distance_ft: distance };
}

export function TacticalMindControl({ state, mode, targetId, checked, blocked, onChange }: {
  state: GameState; mode: InteractionMode; targetId: string | null; checked: boolean; blocked: boolean; onChange: (checked: boolean) => void;
}) {
  const projection = readFighterProjection(state.character.fighter)?.tactical_mind;
  if (!projection) return null;
  const available = tacticalMindAvailable(state, { interaction_mode: mode, target_id: targetId });
  return <div className="story-meta" style={{ flex: '0 0 100%', minWidth: 0 }} data-testid="tactical-mind-control">
    <label><input type="checkbox" data-testid="tactical-mind-confirm" checked={available && checked} disabled={blocked || !available}
      onChange={event => { if (!blocked && available) onChange(event.target.checked); }} />{' '}
      Bu kontrol başarısız olursa <span title={termTitle('tactical_mind')}>{term('tactical_mind')}</span> kullan
    </label>
    <p>Başarısız kontrole 1d10 eklenir; kullanım yalnız kontrol başarıya dönerse <span title={termTitle('second_wind')}>{term('second_wind')}</span> havuzundan harcanır. Yalnız anlık, hedefsiz Yap kontrolleri; seçim zarı görmeden yapılır.</p>
    {!available && <p role="status" data-testid="tactical-mind-unavailable">{projection.reason ?? 'Bu hamlede seçilemez.'}</p>}
  </div>;
}

export function FighterStatus({ fighter }: { fighter: unknown }) {
  const value = readFighterProjection(fighter);
  if (!value) return null;
  return <div className="story-meta mt-3" data-testid="fighter-status">
    <p data-testid="fighter-second-wind-uses"><span title={termTitle('second_wind')}>{term('second_wind')}</span>: {value.second_wind.uses_remaining}/{value.second_wind.max_uses} · 1d{value.second_wind.die} + {value.second_wind.level_bonus}</p>
    {value.action_surge && <p data-testid="fighter-action-surge-uses"><span title={termTitle('action_surge')}>{term('action_surge')}</span>: {value.action_surge.uses_remaining}/{value.action_surge.max_uses}</p>}
    {value.fighting_style && <p data-testid="fighter-style">Dövüş tarzı: {catalogDisplayName((DEFAULT_CATALOG.classes?.Fighter as { fighting_styles?: unknown } | undefined)?.fighting_styles, value.fighting_style) ?? value.fighting_style}</p>}
  </div>;
}

export function FighterControl({ fighter, blocked, shift, onShiftChange, onCommand }: {
  fighter: unknown; blocked: boolean; shift: string; onShiftChange: (value: string) => void;
  onCommand: (label: string, step: EconomyStepInput) => void;
}) {
  const value = readFighterProjection(fighter);
  if (!value) return null;
  const windStep = secondWindStep(value, shift);
  const windEnabled = !blocked && value.second_wind.activate.available && windStep !== null;
  const surge = value.action_surge;
  const surgeEnabled = !blocked && surge?.activate.available === true;
  return <div className="story-meta mt-3" data-testid="fighter-controls">
    <FighterStatus fighter={value} />
    {value.second_wind.tactical_shift && <label><span title={termTitle('tactical_shift')}>{term('tactical_shift')}</span> (<span title={termTitle('feet')}>{term('feet')}</span>, en çok <span title={termTitle('speed')}>{term('speed')}</span>'in yarısı) <input aria-label={term('tactical_shift') + " mesafesi"} data-testid="fighter-tactical-shift" type="number" min="1" step="1"
      className="w-16 bg-transparent border border-amber-100/20 rounded px-1" value={shift} onChange={event => onShiftChange(event.target.value)} /></label>}
    <button type="button" className="action-suggestion" data-testid="button-second-wind" disabled={!windEnabled} onClick={() => {
      if (windEnabled && windStep) onCommand(abilitySentence(term('second_wind')), windStep);
    }}><span title={termTitle('second_wind')}>{term('second_wind')}</span> · <span title={termTitle('bonus_action')}>{term('bonus_action')}</span></button>
    {value.second_wind.activate.reason && <p role="status"><span title={termTitle('second_wind')}>{term('second_wind')}</span> kullanılamıyor: {value.second_wind.activate.reason === 'bonus_action_spent' ? 'Bu tur bonus eylemini kullandın.' : value.second_wind.activate.reason}</p>}
    {surge && <button type="button" className="action-suggestion" data-testid="button-action-surge" disabled={!surgeEnabled} onClick={() => {
      if (surgeEnabled) onCommand(abilitySentence(term('action_surge')), { kind: 'action_surge' });
    }}><span title={termTitle('action_surge')}>{term('action_surge')}</span> · ek eylem (Magic hariç)</button>}
    {surge?.activate.reason && <p role="status"><span title={termTitle('action_surge')}>{term('action_surge')}</span> kullanılamıyor: {surge.activate.reason}</p>}
  </div>;
}
