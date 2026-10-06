import type { CombatTurnResult, GameState } from '@workspace/api-client-react';
import './combat-panel.css';

export interface CombatLogEntry {
  id: string;
  turnIndex: number;
  result: CombatTurnResult;
}

type AttackResult = CombatTurnResult;

function hasValue(value: unknown): value is string | number | boolean {
  return value !== undefined && value !== null;
}

function percentage(current: number, maximum: number): number {
  if (maximum <= 0) return 0;
  return Math.max(0, Math.min(100, (current / maximum) * 100));
}

function combatStatusLabel(value: string | null | undefined): string | undefined {
  if (value === 'active') return 'Ayakta';
  if (value === 'unconscious') return 'Bilinçsiz';
  if (value === 'defeated') return 'Etkisiz';
  return value ?? undefined;
}

function outcomeLabel(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const labels: Record<string, string> = {
    critical_hit: 'Kritik isabet',
    hit: 'İsabet',
    miss: 'Iskaladı',
    invalid_target: 'Geçersiz hedef',
    no_target: 'Hedef bulunamadı',
    target_mismatch: 'Mevcut hedefle eşleşmiyor',
    no_weapon: 'Uygun silah yok',
    ambiguous_target: 'Hedef belirsiz',
    player_unconscious: 'Oyuncu bilinçsiz',
    enemy_turn_resolved: 'Rakip sırası çözüldü',
    out_of_turn: 'Sıra sende değil',
    saved: 'Kurtuldu',
    failed_save: 'Kurtulamadı',
    automatic_hit: 'Otomatik isabet',
    healed: 'İyileşti',
    no_slot: 'Yuva yok',
    not_known: 'Büyü bilinmiyor',
    invalid_class: 'Sınıf kullanamaz',
    invalid_level: 'Seviye yetmiyor',
    unsupported: 'Büyü kullanılamıyor',
    unknown_spell: 'Büyü anlaşılmadı',
  };
  return labels[value] ?? value;
}

function actionLabel(value: string | undefined): string | undefined {
  if (value === 'attack') return 'Oyuncu saldırısı';
  if (value === 'cast') return 'Büyü';
  if (value === 'enemy_attack') return 'Düşman karşı hamlesi';
  return value;
}

function endReasonLabel(value: string | undefined): string | undefined {
  if (value === 'target_defeated') return 'Rakip etkisiz hale getirildi';
  if (value === 'player_defeated') return 'Karakter bilinç kaybetti';
  if (value === 'combat_ended') return 'Çatışma sonlandırıldı';
  return value;
}

function outcomeMarkers(result: AttackResult): string[] {
  const markers: string[] = [];
  if (result.critical === true || result.outcome === 'critical_hit') markers.push('CRITICAL');
  if (
    result.outcome !== 'healed'
    && (result.success === true || result.outcome === 'hit' || result.outcome === 'critical_hit')
  ) markers.push('HIT');
  if (result.outcome === 'miss') markers.push('MISS');

  return [...new Set(markers)];
}

const OUTCOME_LABELS: Record<string, string> = {
  CRITICAL: 'KRİTİK',
  HIT: 'İSABET',
  MISS: 'ISKA',
};

function participantName(participant: string, state: GameState): string {
  if (participant === 'player' || participant === 'character' || participant === state.character.name) {
    return state.character.name;
  }

  return state.npcs.find((npc) => npc.id === participant)?.name ?? participant;
}

function HealthMetric({
  current,
  maximum,
  testId,
  label = 'CAN',
}: {
  current: number | null | undefined;
  maximum: number | null | undefined;
  testId: string;
  label?: string;
}) {
  if (!hasValue(current) || !hasValue(maximum) || typeof current !== 'number' || typeof maximum !== 'number') return null;

  return (
    <div className="combat-health" data-testid={testId}>
      <div className="combat-metric-label">
        <span>{label}</span>
        <strong>{current} / {maximum}</strong>
      </div>
      <div className="combat-health-track" aria-hidden="true">
        <span className="combat-health-fill" style={{ width: `${percentage(current, maximum)}%` }} />
      </div>
    </div>
  );
}

function StatusLine({ value, testId }: { value: string | null | undefined; testId: string }) {
  if (!value) return null;

  return (
    <div className="combat-status-line" data-testid={testId}>
      <span>Durum</span>
      <strong>{combatStatusLabel(value)}</strong>
    </div>
  );
}

function CombatantCard({
  participantId,
  kind,
  name,
  currentHp,
  maxHp,
  armorClass,
  status,
  isCurrentActor,
}: {
  participantId: string;
  kind: 'player' | 'opponent';
  name: string;
  currentHp: number | null | undefined;
  maxHp: number | null | undefined;
  armorClass: number | null | undefined;
  status?: string | null;
  isCurrentActor: boolean;
}) {
  const isPlayer = kind === 'player';
  const testPrefix = isPlayer ? 'combat-player' : `combat-opponent-${participantId}`;

  return (
    <article className={`combat-combatant combat-combatant-${kind} ${isCurrentActor ? 'combat-combatant-current' : ''}`} data-testid={testPrefix}>
      <div className="combat-combatant-heading">
        <span className="combat-overline">{isPlayer ? 'YOLCU' : isCurrentActor ? 'SIRADAKİ RAKİP' : 'RAKİP'}</span>
        <span className="combat-combatant-mark" aria-hidden="true">{isPlayer ? 'P' : 'T'}</span>
      </div>
      <h3 data-testid={`${testPrefix}-name`}>{name}</h3>
      {isCurrentActor && <span className="combat-current-actor" data-testid={`combat-current-actor-${participantId}`}>SIRA ONDA</span>}
      <HealthMetric current={currentHp} maximum={maxHp} testId={`${testPrefix}-hp`} />
      <div className="combat-combatant-metrics">
        {hasValue(armorClass) && (
          <div className="combat-small-metric" data-testid={`${testPrefix}-ac`}>
            <span>ZIRH</span>
            <strong>{armorClass}</strong>
          </div>
        )}
        <StatusLine value={status} testId={`${testPrefix}-status`} />
      </div>
    </article>
  );
}

function RollMetric({
  label,
  value,
  testId,
}: {
  label: string;
  value: number | undefined;
  testId: string;
}) {
  if (!hasValue(value)) return null;

  return (
    <div className="combat-roll-metric" data-testid={testId}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AttackReadout({
  result,
  entryId,
  heading,
  enemy = false,
}: {
  result: AttackResult;
  entryId: string;
  heading: string;
  enemy?: boolean;
}) {
  const markers = outcomeMarkers(result);
  const prefix = `combat-entry-${entryId}${enemy ? '-enemy' : ''}`;
  const hasRollData = [result.attack_roll, result.attack_bonus, result.attack_total, result.target_ac].some(hasValue);
  const hasHpWindow = hasValue(result.target_hp_before) || hasValue(result.target_hp_after);
  const naturalRoll = result.attack_roll === 20 ? 'DOĞAL 20' : result.attack_roll === 1 ? 'DOĞAL 1' : undefined;

  return (
    <article className={`combat-result-card ${enemy ? 'combat-result-enemy' : ''} ${naturalRoll === 'DOĞAL 20' ? 'combat-result-critical' : ''} ${naturalRoll === 'DOĞAL 1' ? 'combat-result-fumble' : ''}`} data-testid={prefix}>
      <div className="combat-result-heading">
        <div>
          <span className="combat-overline">{enemy ? 'KANONİK KARŞI HAMLE' : 'PYTHON SONUCU'}</span>
          <h4>{heading}</h4>
        </div>
        <div className="combat-result-side">
          {result.weapon && <span className="combat-weapon">{result.weapon}</span>}
          <span className="combat-result-die" aria-hidden="true">d20</span>
        </div>
      </div>

      {(markers.length > 0 || naturalRoll || result.outcome) && (
        <div className="combat-outcome" data-testid={`${prefix}-outcome`} aria-label="Sonuç">
          {markers.map((marker) => <span className={`combat-outcome-marker combat-outcome-${marker.toLowerCase()}`} key={marker}>{OUTCOME_LABELS[marker]}</span>)}
          {naturalRoll && <span className={`combat-outcome-natural ${naturalRoll === 'DOĞAL 20' ? 'combat-outcome-natural-critical' : 'combat-outcome-natural-fumble'}`}>{naturalRoll}</span>}
          {result.outcome && <span className="combat-outcome-raw">{outcomeLabel(result.outcome)}</span>}
        </div>
      )}

      {result.action && <div className="combat-action" data-testid={`${prefix}-action`}>{actionLabel(result.action)}</div>}

      {hasRollData && (
        <div className="combat-roll-grid" aria-label="Saldırı değerleri">
          <RollMetric label={naturalRoll ?? 'D20'} value={result.attack_roll ?? undefined} testId={`${prefix}-roll`} />
          <RollMetric label="BONUS" value={result.attack_bonus ?? undefined} testId={`${prefix}-bonus`} />
          <RollMetric label="TOPLAM" value={result.attack_total ?? undefined} testId={`${prefix}-total`} />
          <RollMetric label="HEDEF ZIRHI" value={result.target_ac ?? undefined} testId={`${prefix}-target-ac`} />
        </div>
      )}

      {result.spell && (
        <div className="combat-action" data-testid={`${prefix}-spell`}>
          {result.spell}
          {result.attack_or_save ? ` · ${result.attack_or_save}` : ''}
          {result.slot_spent === true ? ' · yuva harcandı' : result.slot_spent === false ? ' · yuva harcanmadı' : ''}
        </div>
      )}

      {hasValue(result.save_roll) && (
        <div className="combat-roll-grid" aria-label="Kurtarma değeri">
          <RollMetric label="KURTARMA" value={result.save_roll ?? undefined} testId={`${prefix}-save-roll`} />
          <RollMetric label="DC" value={result.save_dc ?? undefined} testId={`${prefix}-save-dc`} />
        </div>
      )}

      {hasValue(result.damage) && !(result.outcome === 'healed' && result.damage === 0) && (
        <div className="combat-damage" data-testid={`${prefix}-damage`}>
          <span>HASAR</span>
          <strong>{result.damage}</strong>
        </div>
      )}

      {hasValue(result.healing) && (
        <div className="combat-damage" data-testid={`${prefix}-healing`}>
          <span>İYİLEŞME</span>
          <strong>{result.healing}</strong>
        </div>
      )}

      {hasHpWindow && (
        <div className="combat-hp-window" data-testid={`${prefix}-hp-window`}>
          {hasValue(result.target_hp_before) && <span>Önce <strong>{result.target_hp_before}</strong></span>}
          {hasValue(result.target_hp_after) && <span>Sonra <strong>{result.target_hp_after}</strong></span>}
        </div>
      )}

      {result.target_status && <div className="combat-target-status" data-testid={`${prefix}-target-status`}>{combatStatusLabel(result.target_status)}</div>}
    </article>
  );
}

function InitiativeStrip({ state }: { state: GameState }) {
  const order = state.combat.initiative_order;
  if (!order?.length) return null;

  return (
    <section className="combat-initiative" aria-labelledby="combat-initiative-heading">
      <div className="combat-section-heading">
        <span className="combat-overline" id="combat-initiative-heading">İNİSİYATİF SIRASI</span>
        <span className="combat-section-note">Atış toplamları gösterilmez</span>
      </div>
      <ol className="combat-initiative-list" data-testid="combat-initiative">
        {order.map((participant, index) => (
          <li className={`combat-initiative-item ${state.combat.current_actor_id === participant ? 'combat-initiative-current' : ''}`} key={`${participant}-${index}`} data-testid={`combat-initiative-${index}`} aria-current={state.combat.current_actor_id === participant ? 'step' : undefined}>
            <span className="combat-initiative-index">{String(index + 1).padStart(2, '0')}</span>
            <span>{participantName(participant, state)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function EntryCard({ entry }: { entry: CombatLogEntry }) {
  const result = entry.result;
  const enemyActions = result.enemy_actions?.length
    ? result.enemy_actions
    : result.enemy_action
      ? [result.enemy_action]
      : [];
  const target = result.target_name ? ` · ${result.target_name}` : '';
  const heading = result.action ? `${actionLabel(result.action)}${target}` : result.target_name ?? 'Yapılan hamle';

  return (
    <div className="combat-entry" data-testid={`combat-log-entry-${entry.id}`}>
      <div className="combat-entry-index" aria-hidden="true">{String(entry.turnIndex).padStart(2, '0')}</div>
      <div className="combat-entry-body">
        {result.combat_started && <div className="combat-event combat-event-started" data-testid={`combat-log-entry-${entry.id}-started`}>ÇATIŞMA BAŞLADI</div>}
        <AttackReadout result={result} entryId={entry.id} heading={heading} />
        {enemyActions.map((enemyAction, index) => (
          <AttackReadout
            key={`${entry.id}-enemy-${index}`}
            result={enemyAction}
            entryId={`${entry.id}-enemy-${index}`}
            heading={`${enemyAction.actor_name ?? 'Rakip'} · ${enemyAction.target_name ?? 'oyuncu'}`}
            enemy
          />
        ))}
        {result.combat_ended && (
          <div className="combat-event combat-event-ended" data-testid={`combat-log-entry-${entry.id}-ended`}>
            <span>ÇATIŞMA SONA ERDİ</span>
            {result.end_reason && <strong>{endReasonLabel(result.end_reason)}</strong>}
          </div>
        )}
      </div>
    </div>
  );
}

export function CombatPanel({ state, entries }: { state: GameState; entries: CombatLogEntry[] }) {
  const active = Boolean(state.combat.active);
  const latest = entries[entries.length - 1]?.result;
  const ended = !active && latest?.combat_ended === true;
  const combatants = state.combat.participant_records ?? [];
  const currentActorName = combatants.find(
    (participant) => participant.id === state.combat.current_actor_id,
  )?.name;

  return (
    <section className="combat-panel" data-testid="panel-combat">
      <header className="combat-panel-header">
        <div>
          <span className="combat-overline">MOTOR DURUMU</span>
          <h2>Çatışma kaydı</h2>
        </div>
        <div className={`combat-state-seal combat-state-${ended ? 'ended' : active ? 'active' : 'idle'}`} data-testid="combat-status">
          <span className="combat-seal-dot" aria-hidden="true" />
          {ended ? 'Sona erdi' : active ? 'Sürüyor' : 'Pasif'}
        </div>
      </header>

      {ended ? (
        <div className="combat-ended-state" data-testid="combat-ended-state">
          <span className="combat-overline">SON KANONİK KAYIT</span>
          <strong>Çatışma sona erdi.</strong>
            {latest?.end_reason && <span data-testid="combat-end-reason">{endReasonLabel(latest.end_reason)}</span>}
        </div>
      ) : active ? (
        <>
          <div className="combat-round-line">
            <span>ÇATIŞMA AKTİF</span>
            {typeof state.combat.round === 'number' && <strong data-testid="combat-round">Tur {state.combat.round}</strong>}
            {currentActorName && <strong data-testid="combat-turn-owner">Sıra: {currentActorName}</strong>}
          </div>
          <div className="combat-combatants">
            {combatants.map((participant) => (
              <CombatantCard
                key={participant.id}
                participantId={participant.id}
                kind={participant.kind === 'player' ? 'player' : 'opponent'}
                name={participant.name}
                currentHp={participant.current_hp}
                maxHp={participant.max_hp}
                armorClass={participant.armor_class}
                status={participant.status}
                isCurrentActor={participant.is_current_actor}
              />
            ))}
          </div>
          <InitiativeStrip state={state} />
        </>
      ) : (
        <div className="combat-idle-state" data-testid="combat-idle-state">
          <span className="combat-die" aria-hidden="true"><i /><i /><i /></span>
          <div>
            <strong>Çatışma yok</strong>
            <span>Motor yeni bir karşılaşma başlattığında kanonik atışlar burada görünür.</span>
          </div>
        </div>
      )}

      {entries.length > 0 && (
        <section className="combat-log" aria-labelledby="combat-log-heading" aria-live="polite">
          <div className="combat-section-heading">
            <span className="combat-overline" id="combat-log-heading">KARAR KAYDI</span>
            <span className="combat-section-note">Python tarafından döndürülen sonuçlar</span>
          </div>
          <div className="combat-log-list">
            {entries.map((entry) => <EntryCard entry={entry} key={entry.id} />)}
          </div>
        </section>
      )}
    </section>
  );
}