import type { GameState } from '@workspace/api-client-react';

/** Read-only character information; preparation, resources and legality stay in Python. */
export function SpellcastingPanel({ spellcasting }: { spellcasting: GameState['spellcasting'] }) {
  if (!spellcasting) return null;
  return (
    <section className="state-panel spellcasting-panel" aria-label="Büyüler ve büyü yuvaları" data-testid="panel-spellcasting">
      <div className="dnd-kicker">Büyü bilgisi</div>
      <h2>Büyüler</h2>
      <div className="mt-4">
        <h3 className="dnd-kicker">Hileler</h3>
        {spellcasting.cantrips.length ? <ul className="mt-2 flex flex-wrap gap-2" data-testid="spell-cantrips">
          {spellcasting.cantrips.map((spell) => <li className="status-pill" key={spell}>{spell}</li>)}
        </ul> : <p className="subtle-text mt-2">Bilinen hile yok.</p>}
      </div>
      <div className="mt-4">
        <h3 className="dnd-kicker">Hazırlanmış büyüler</h3>
        {spellcasting.prepared.length ? <ul className="mt-2 flex flex-wrap gap-2" data-testid="spell-prepared">
          {spellcasting.prepared.map((spell) => <li className="status-pill" key={spell}>{spell}</li>)}
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
      {spellcasting.slot_turn && <p className="subtle-text mt-3" data-testid="spell-slot-turn">
        Son yuva kullanımı: Raunt {spellcasting.slot_turn[1]} · Sıra {spellcasting.slot_turn[2]}
      </p>}
      <p className="subtle-text mt-3">Büyü kullanımı hedefe ve sıra koşullarına bağlıdır.</p>
    </section>
  );
}