import type { GameState } from '@workspace/api-client-react';
import { Swords } from 'lucide-react';
import { combatStatusLabel } from './combat-panel';

export function CombatStatusStrip({ combat }: { combat: GameState['combat'] }) {
  if (!combat.active) return null;
  const records = combat.participant_records ?? [];
  const ordered = [
    ...records.filter((participant) => participant.kind === 'player'),
    ...records.filter((participant) => participant.kind !== 'player'),
  ];
  return <section className="combat-status-strip" data-testid="combat-status-strip">
    <h3>{`Çatışma · Tur ${combat.round}`}</h3>
    {ordered.map((participant) => <div key={participant.id} data-testid={`combat-status-${participant.id}`}>
      <span>{`${participant.name} · Can ${participant.current_hp}/${participant.max_hp} · ${combatStatusLabel(participant.status) ?? ''}`}</span>
      {participant.is_current_actor && <strong>sırada</strong>}
    </div>)}
  </section>;
}

export function CombatTransitionBanner({ kind, text }: { kind: 'start' | 'end'; text: string }) {
  return <div className="combat-transition-banner" role="status" data-testid={kind === 'start' ? 'status-combat-started' : 'status-combat-ended'}>
    <Swords size={14} aria-hidden="true" />
    <div><strong>{kind === 'start' ? 'ÇATIŞMA BAŞLADI' : 'ÇATIŞMA SONA ERDİ'}</strong>{!(kind === 'end' && text === 'Çatışma sona erdi.') && <span>{text}</span>}</div>
  </div>;
}
