import { nameLang, trName } from '@/lib/tr-names';
import { term, termTitle } from '@/lib/tr-terms';
import { SpellSlotConversionControl } from './spell-slot-conversion';
export { SpellSlotConversionChoice, createConversionDraft } from './spell-slot-conversion';
import type { CombatActionInput, GameState, SpellPrepareViewResponse } from '@workspace/api-client-react';
import { WINDOW_SHORT } from '@/lib/spell-preparation';

/** Read-only rows from the server's preparation view (D-065): window, prepared count and the Wizard spellbook. */
export function SpellStatusRows({ view, combatActive, label }: { view: SpellPrepareViewResponse; combatActive: boolean; label: (id: string) => string }) {
  const windowText = !view.supported ? 'Kullanılamıyor' : view.open ? WINDOW_SHORT[view.reason ?? ''] ?? 'Açık' : combatActive ? 'Kapalı · çatışma' : 'Kapalı';
  return <dl className="spell-status-rows" data-testid="spell-status-rows">
    <div className="spell-status-row"><dt>Hazırlık penceresi</dt><dd data-testid="spell-window-row">{windowText}</dd></div>
    <div className="spell-status-row"><dt>Hazırlanan büyüler</dt><dd data-testid="spell-prepared-count-row">{view.prepared.length} / {view.limit}</dd></div>
    {view.spellbook && <div className="spell-status-row spell-status-book"><dt>Büyü kitabı</dt><dd data-testid="spell-spellbook-row">
      <span>{view.spellbook.length} büyü</span>
      <ul>{view.spellbook.map(id => <li key={id}>{label(id)}</li>)}</ul>
    </dd></div>}
  </dl>;
}

/** Read-only character information; preparation, resources and legality stay in Python. */
export function SpellcastingPanel({ spellcasting, decisionScope = '', conversionBlocked = true, onCommand }: { spellcasting: GameState['spellcasting']; decisionScope?: string; conversionBlocked?: boolean; onCommand?: (message: string, command: CombatActionInput) => void }) {
  if (!spellcasting) return null;
  return (
    <section className="state-panel spellcasting-panel" aria-label="Büyüler ve büyü yuvaları" data-testid="panel-spellcasting">
      <div className="dnd-kicker">Büyü bilgisi</div>
      <h2>Büyüler</h2>
      <div className="mt-4">
        <h3 className="dnd-kicker">Hileler</h3>
        {spellcasting.cantrips.length ? <ul className="mt-2 flex flex-wrap gap-2" data-testid="spell-cantrips">
          {spellcasting.cantrips.map((spell) => <li className="status-pill" lang={nameLang(spell, 'spells')} key={spell}>{trName(spell, 'spells')}</li>)}
        </ul> : <p className="subtle-text mt-2">Bilinen hile yok.</p>}
      </div>
      <div className="mt-4">
        <h3 className="dnd-kicker">Hazırlanmış büyüler</h3>
        {spellcasting.prepared.length ? <ul className="mt-2 flex flex-wrap gap-2" data-testid="spell-prepared">
          {spellcasting.prepared.map((spell) => <li className="status-pill" lang={nameLang(spell, 'spells')} key={spell}>{trName(spell, 'spells')}</li>)}
        </ul> : <p className="subtle-text mt-2" data-testid="spell-prepared-empty">Hazırlanmış büyü yok.</p>}
      </div>
      <div className="mt-4">
        <h3 className="dnd-kicker">Kalan büyü yuvaları</h3>
        <dl className="mt-2" data-testid="spell-slots">
          {Object.entries(spellcasting.slots).map(([level, remaining]) => <div className="data-row flex items-center justify-between gap-3" key={level}>
            <dt>{level}. seviye</dt><dd className="font-mono" data-testid={`spell-slots-${level}`}>{remaining}</dd>
          </div>)}
        </dl>
      </div>
      {spellcasting.sorcery_points && <p className="subtle-text mt-3" data-testid="spell-sorcery-points"><span title={termTitle('sorcery_points')}>{term('sorcery_points')}</span>: {spellcasting.sorcery_points.current}/{spellcasting.sorcery_points.max}</p>}
      {onCommand && <SpellSlotConversionControl spellcasting={spellcasting} decisionScope={decisionScope} blocked={conversionBlocked} onCommand={onCommand} />}
      {spellcasting.slot_turn && <p className="subtle-text mt-3" data-testid="spell-slot-turn">
        Son yuva kullanımı: Raunt {spellcasting.slot_turn[1]} · Sıra {spellcasting.slot_turn[2]}
      </p>}
      <p className="subtle-text mt-3">Büyü kullanımı hedefe ve sıra koşullarına bağlıdır.</p>
    </section>
  );
}