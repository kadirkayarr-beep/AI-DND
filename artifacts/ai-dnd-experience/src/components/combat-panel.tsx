import type { CombatTurnResult, GameState } from '@workspace/api-client-react';
import { SpeciesTraitControls, speciesEffectText } from './species-trait-controls';
import { DeathRecoveryControls } from './death-recovery-controls';
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
  if (value === 'dead') return 'Ölü';
  if (value === 'defeated') return 'Etkisiz';
  return value ?? undefined;
}

function outcomeLabel(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const labels: Record<string, string> = {
    critical_hit: 'Kritik isabet',
    hit: 'İsabet',
    miss: 'Iskaladı',
    invalid_target: 'Hedef seçilemedi',
    no_target: 'Hedef bulunamadı',
    target_mismatch: 'Seçilen hedef uyuşmuyor',
    no_weapon: 'Kullanılabilir silah yok',
    ambiguous_target: 'Bir hedef seç',
    player_unconscious: 'Karakter bilincini kaybetti',
    enemy_turn_resolved: 'Rakip hamlesini yaptı',
    out_of_turn: 'Sıra sende değil',
    success: 'Başarılı',
    failure: 'Başarısız',
    natural_1: 'Doğal 1',
    stable: 'Sabit',
    revived: 'Canlandı',
    dead: 'Öldü',
    rolled_back: 'Çatışma öncesine dönüldü',
  };
  return labels[value] ?? value;
}

function actionLabel(value: string | undefined): string | undefined {
  if (value === 'monster_dodge') return 'Savunmaya geçti';
  if (value === 'monster_flee_declared') return 'Geri çekildi';
  if (value === 'monster_dash') return 'Hızla ilerledi';
  if (value === 'monster_disengage') return 'Yakın dövüşten ayrıldı';
  if (value === 'monster_parley_proposed') return 'Konuşmayı önerdi';
  if (value === 'monster_surrender_proposed') return 'Teslim olmayı önerdi';
  if (value === 'attack') return 'Saldırı';
  if (value === 'enemy_attack') return 'Karşı saldırı';
  if (value === 'death_save') return 'Otomatik ölüm kurtarma zarı';
  return value;
}

function endReasonLabel(value: string | undefined): string | undefined {
  if (value === 'target_defeated') return 'Rakip etkisiz hale getirildi';
  if (value === 'player_defeated') return 'Karakter bilinç kaybetti';
  if (value === 'player_dead') return 'Karakter öldü';
  if (value === 'player_stable') return 'Karakter sabit ve bilinçsiz';
  if (value === 'combat_ended') return 'Çatışma sonlandırıldı';
  return value;
}

function deathModeLabel(mode: GameState['death_state']['mode']): string {
  if (mode === 'PERMADEATH') return 'Permadeath';
  if (mode === 'IRONMAN') return 'Ironman';
  return 'Normal';
}

function deathStatusLabel(status: GameState['death_state']['status']): string {
  if (status === 'unconscious') return 'Bilinçsiz';
  if (status === 'stable') return 'Sabit, bilinçsiz';
  if (status === 'dead') return 'Ölü';
  return 'Ayakta';
}

function outcomeMarkers(result: AttackResult): string[] {
  const markers: string[] = [];
  if (result.critical === true || result.outcome === 'critical_hit') markers.push('CRITICAL');
  if (result.success === true || result.outcome === 'hit' || result.outcome === 'critical_hit') markers.push('HIT');
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
  if (result.action?.startsWith('monster_')) {
    return <div className="combat-roll-block" data-testid={`combat-monster-action-${entryId}`}>
      <div className="combat-result-title">{result.actor_name ?? heading}</div>
      <div className="combat-outcome">{actionLabel(result.action)}
        {result.target_name ? ` · ${result.target_name}` : ''}
        {result.action.includes('proposed') ? ' · Yanıtını bekliyor' : ''}
      </div>
    </div>;
  }
  const markers = outcomeMarkers(result);
  const prefix = `combat-entry-${entryId}${enemy ? '-enemy' : ''}`;
  const hasRollData = [result.attack_roll, result.attack_bonus, result.attack_total, result.target_ac].some(hasValue);
  const hasHpWindow = hasValue(result.target_hp_before) || hasValue(result.target_hp_after);
  const naturalRoll = result.attack_roll === 20 ? 'DOĞAL 20' : result.attack_roll === 1 ? 'DOĞAL 1' : undefined;
  const deathResolution = result.death_resolution ?? result.death_save?.death_resolution;

  return (
    <article className={`combat-result-card ${enemy ? 'combat-result-enemy' : ''} ${naturalRoll === 'DOĞAL 20' ? 'combat-result-critical' : ''} ${naturalRoll === 'DOĞAL 1' ? 'combat-result-fumble' : ''}`} data-testid={prefix}>
      <div className="combat-result-heading">
        <div>
          <span className="combat-overline">{enemy ? 'RAKİBİN KARŞILIĞI' : 'HAMLE SONUCU'}</span>
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

      {hasValue(result.damage) && (
        <div className="combat-damage" data-testid={`${prefix}-damage`}>
          <span>HASAR</span>
          <strong>{result.damage}</strong>
        </div>
      )}
      {result.species_effects?.length ? (
        <ul className="combat-species-effects" data-testid={`${prefix}-species-effects`}>
          {result.species_effects.map((effect, index) => (
            <li key={`${prefix}-species-effect-${index}`}>
              {speciesEffectText(effect)}
            </li>
          ))}
        </ul>
      ) : null}

      {hasHpWindow && (
        <div className="combat-hp-window" data-testid={`${prefix}-hp-window`}>
          {hasValue(result.target_hp_before) && <span>Önce <strong>{result.target_hp_before}</strong></span>}
          {hasValue(result.target_hp_after) && <span>Sonra <strong>{result.target_hp_after}</strong></span>}
        </div>
      )}

      {result.target_status && <div className="combat-target-status" data-testid={`${prefix}-target-status`}>{combatStatusLabel(result.target_status)}</div>}
      {result.death_save && (
        <div className="combat-death-save" data-testid={`${prefix}-death-save`}>
          <strong>Ölüm kurtarma zarı · d20: {result.death_save.roll}</strong>
          <span>{outcomeLabel(result.death_save.outcome)}</span>
          <small>
            Başarı {result.death_save.successes}/3 · Başarısızlık {result.death_save.failures}/3
          </small>
        </div>
      )}
      {deathResolution && (
        <div className="combat-death-resolution" data-testid={`${prefix}-death-resolution`}>
          {deathResolution.rolled_back
            ? 'Normal mod: çatışma öncesi durum geri yüklendi.'
            : deathResolution.terminal
              ? 'Ironman: karakter öldü ve kampanya sona erdi.'
              : 'Karakter öldü.'}
        </div>
      )}
    </article>
  );
}

function InitiativeStrip({ state }: { state: GameState }) {
  const order = state.combat.initiative_order;
  if (!order?.length) return null;

  return (
    <section className="combat-initiative" aria-labelledby="combat-initiative-heading">
      <div className="combat-section-heading">
        <span className="combat-overline" id="combat-initiative-heading">HAMLE SIRASI</span>
        <span className="combat-section-note">Önce davranan en üstte</span>
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
  if (result.action === 'action_economy') {
    return <div className="combat-entry" data-testid={`combat-log-entry-${entry.id}`}>
      <div className="combat-entry-index">{String(entry.turnIndex).padStart(2, '0')}</div>
      <div className="combat-entry-body">
        {(result.economy_steps ?? []).map((step, index) => {
          const kind = typeof step.kind === 'string' ? step.kind : 'hamle';
          const rawAttack = kind === 'attack' ? step.result : kind === 'react' ? step.response : null;
          const attack = rawAttack !== null && typeof rawAttack === 'object' && 'action' in rawAttack && rawAttack.action === 'attack'
            ? rawAttack as AttackResult : null;
          const npcAttacks = kind === 'end_turn' && Array.isArray(step.enemy_actions) ? step.enemy_actions : [];
          return <div key={index}>
            <div className="combat-event">{kind === 'move' ? `Hareket · ${String(step.distance_ft)} ft · maliyet ${String(step.movement_cost_ft)} ft`
              : kind === 'dash' ? `Dash · ${String(step.resource)} · +${String(step.movement_added_ft)} ft`
              : kind === 'ready' ? 'Ready Action hazırlandı'
              : kind === 'end_turn' ? 'Tur tamamlandı'
              : kind === 'decline_reaction' ? 'Reaction fırsatı atlandı'
              : kind === 'species' ? 'Tür yeteneği çözüldü'
              : kind === 'react' ? 'Ready Reaction çözüldü' : 'Attack Action çözüldü'}</div>
            {attack !== null && <AttackReadout result={attack} entryId={`${entry.id}-${index}`} heading="Sunucu saldırı sonucu" />}
            {npcAttacks.map((npcAttack, npcIndex) => <AttackReadout key={npcIndex}
              result={npcAttack as AttackResult} entryId={`${entry.id}-${index}-${npcIndex}`} heading="Rakibin saldırısı" enemy />)}
          </div>;
        })}
      </div>
    </div>;
  }
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

export function CombatPanel({
  state,
  entries,
  sessionId,
}: {
  state: GameState;
  entries: CombatLogEntry[];
  sessionId: string;
}) {
  const active = Boolean(state.combat.active);
  const latest = entries[entries.length - 1]?.result;
  const ended = !active && latest?.combat_ended === true;
  const combatants = state.combat.participant_records ?? [];
  const currentActorName = combatants.find(
    (participant) => participant.id === state.combat.current_actor_id,
  )?.name;
  const death = state.death_state;

  return (
    <section className={`combat-panel ${active ? 'combat-panel-active' : ''}`} data-testid="panel-combat">
      <SpeciesTraitControls state={state} sessionId={sessionId} />
      <DeathRecoveryControls state={state} sessionId={sessionId} />
      <header className="combat-panel-header">
        <div>
          <span className="combat-overline">KARŞILAŞMANIN SEYRİ</span>
          <h2>Çatışma</h2>
        </div>
        <div className={`combat-state-seal combat-state-${ended ? 'ended' : active ? 'active' : 'idle'}`} data-testid="combat-status">
          <span className="combat-seal-dot" aria-hidden="true" />
          {ended ? 'Sona erdi' : active ? 'Sürüyor' : 'Pasif'}
        </div>
      </header>

      {(death.status !== 'active' || death.last_death_save) && (
        <aside className="combat-death-state" data-testid="death-state-panel" aria-live="polite">
          <div>
            <span className="combat-overline">{deathModeLabel(death.mode)} · ÖLÜM KURTARMA</span>
            <strong>{deathStatusLabel(death.status)}</strong>
          </div>
          {(death.status === 'unconscious' || death.status === 'stable') && (
            <span>Başarı {death.successes}/3 · Başarısızlık {death.failures}/3</span>
          )}
          {death.terminal && <span>Kampanya sona erdi.</span>}
        </aside>
      )}

      {ended ? (
        <div className="combat-ended-state" data-testid="combat-ended-state">
          <span className="combat-overline">SON AN</span>
          <strong>Çatışma sona erdi.</strong>
            {latest?.end_reason && <span data-testid="combat-end-reason">{endReasonLabel(latest.end_reason)}</span>}
        </div>
      ) : active ? (
        <>
          <div className="combat-round-line">
            <span>KILIÇLAR ÇEKİLDİ</span>
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
            <span>Yeni bir karşılaşmada zarların ve hamlelerin izi burada belirecek.</span>
          </div>
        </div>
      )}

      {entries.length > 0 && (
        <section className="combat-log" aria-labelledby="combat-log-heading" aria-live="polite">
          <div className="combat-section-heading">
            <span className="combat-overline" id="combat-log-heading">ÇATIŞMANIN İZLERİ</span>
            <span className="combat-section-note">Atılan zarlar, isabetler ve karşı hamleler</span>
          </div>
          <div className="combat-log-list">
            {entries.map((entry) => <EntryCard entry={entry} key={entry.id} />)}
          </div>
        </section>
      )}
    </section>
  );
}