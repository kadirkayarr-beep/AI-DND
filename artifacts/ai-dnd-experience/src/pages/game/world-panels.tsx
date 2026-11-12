import { CharacterPanel, InventoryPanel } from '@/components/character-panel';
import { unresolvedElsewhere } from '@/lib/pending-action';
import { useRef, useState, type KeyboardEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CombatPanel, type CombatLogEntry } from '@/components/combat-panel';
import { ExplorationControls } from '@/components/exploration-controls';
import { CourtyardHelp } from '@/components/courtyard-help';
import {
  BookOpen,
  DoorOpen,
  KeyRound,
  LockKeyhole,
  MapPinned,
  ScrollText,
  Users,
} from 'lucide-react';
import {
  getGetCampaignsQueryKey,
  useAcceptGameQuest,
  useCancelGameQuest,
} from '@workspace/api-client-react';
import { currentAccountOwner } from '@/lib/account-session';
import { applyGameState, nextRevision } from '@/lib/game-state-gate';
import { QuestJournalSection } from '@/components/quest-journal-section';
import { AdventureJournalSection } from '@/components/adventure-journal-section';
import type { GameDoor, GameState } from '@workspace/api-client-react';
import { SpellcastingPanel } from '@/components/spellcasting-panel';
import { CampaignContextPanel, CampaignDate } from '@/components/campaign-context-panel';
import { currentSceneContext, classLabel, speciesLabel } from '@/lib/campaign-presentation';
import type { CombatActionInput } from '@workspace/api-client-react';
import { getContextualActionSuggestions, type InteractionMode } from '@/lib/action-suggestions';
import { LOCAL_OWNER, Kicker, Rule } from '@/pages/game/shell-parts';

export type WorldTab = 'world' | 'npcs' | 'journal' | 'combat';

function WorldPanel({ state }: { state: GameState }) {
  return <CampaignContextPanel state={state} />;
}

export function SceneIdeas({ state, recentText, sending, onDraft }: {
  state: GameState;
  recentText: string;
  sending: boolean;
  onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void;
}) {
  const ideas = [
    ...getContextualActionSuggestions(state, recentText),
    ...(state.campaign_adventures?.affordances ?? []).map((label: string) => ({
      id: `adventure-${label}`, label, message: label, mode: 'do' as const, targetId: undefined,
    })),
  ].slice(0, 4);
  if (ideas.length === 0) return null;
  return <details className="scene-ideas" data-testid="scene-ideas">
    <summary>Fikir lazım mı?</summary>
    <div className="action-suggestion-list" role="group" aria-label="Bu sahne için fikirler" data-testid="action-suggestions">
      {ideas.map((idea) => (
        <button className="action-suggestion" data-testid={`button-suggestion-${idea.id}`} disabled={sending} key={idea.id} type="button"
          onClick={(event) => {
            event.currentTarget.closest('details')?.removeAttribute('open');
            onDraft(idea.message, idea.mode, idea.targetId);
          }}>{idea.label}</button>
      ))}
    </div>
  </details>;
}

function ExperimentalWorldControls({ state, sending, onExplorationCommand, onDraft, onSetCombatTarget }: {
  state: GameState;
  sending: boolean;
  onExplorationCommand: (message: string) => void;
  onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void;
  onSetCombatTarget: (targetId: string) => void;
}) {
  return <details className="world-experimental" data-testid="world-experimental">
    <summary><strong>Keşif ve yolculuk</strong><span>isteğe bağlı araçlar</span></summary>
    <div className="world-experimental-content">
      <CourtyardHelp state={state} disabled={sending} onDraft={(text) => onDraft(text, 'do')} />
      <section className="data-row" data-testid="exploration-disclosure">
        <h3>Keşif ve yolculuk</h3>
        <ExplorationControls state={state}
          disabled={sending || state.combat.active || state.character.current_hp <= 0 || !!state.pending_event_decisions?.length}
          onCommand={onExplorationCommand} />
      </section>
      {state.pending_event_decisions?.map((event, index) => <div className="data-row" data-testid="scheduled-event-decision" key={index}>
        <p>{event.summary}</p>
        <small>{event.in_combat ? 'Çatışma sonrasında sonraki kararını sen vereceksin.' : event.forced ? 'Fiziksel engel: başka bir kayıtlı konum veya rota seçebilirsin.' : 'Kararın bekleniyor; zaman kendiliğinden ilerlemiyor.'}</small>
        {!event.in_combat && <div className="action-suggestion-list">
          {[
            ...(!event.forced ? [['Devam etmeyi seç', 'Karşılaşmada devam etmeyi seçiyorum.'], ['Konuş', 'Karşılaşmada konuşmayı seçiyorum.']] : []),
            ...(event.can_fight ? [['Savaş', 'Karşılaşmada savaşmayı seçiyorum.']] : []),
            ...(state.journey ? [['Geri dön', 'Geri dönüyorum.']] : []),
          ].map(([label, intent]) => <button key={label} className="action-suggestion" type="button" disabled={sending || state.combat.active} onClick={() => {
            if (state.exploration) {
              const choice = label === 'Savaş' ? 'fight' : label === 'Geri dön' ? 'return' : label === 'Konuş' ? 'talk' : 'continue';
              onExplorationCommand('/explore decision ' + choice);
            } else onDraft(`Karşılaşma: ${event.summary}\nKararım: ${intent}`, 'do');
          }}>{label}</button>)}
        </div>}
      </div>)}
      {state.journey && <div className="data-row" data-testid="journey-decision">
        <p>{state.locations[state.journey.destination]?.name ?? state.journey.destination} yolunda · {state.journey.stage} / {state.journey.stage_count}</p>
        {state.journey.encounter && <p>{state.journey.encounter}</p>}
        <div className="action-suggestion-list">
          {[
            ['Yola devam', 'Yolculuğa devam ediyorum.'],
            ['Dur', 'Yolculuğu durduruyorum.'],
            ['Geri dön', 'Geri dönüyorum.'],
          ].map(([label, intent]) => <button key={label} className="action-suggestion" type="button" disabled={sending || state.combat.active || !!state.pending_event_decisions?.length} onClick={() => {
            if (state.exploration) onExplorationCommand('/travel ' + (label === 'Yola devam' ? 'continue' : label === 'Dur' ? 'stop' : 'return'));
            else onDraft(intent, 'do');
          }}>{label}</button>)}
        </div>
      </div>}
    </div>
  </details>;
}

export type RailPanelId = 'character' | 'world' | 'npcs' | 'journal' | 'combat';

export function RailSummary({ panel, state }: { panel: RailPanelId; state: GameState }) {
  if (panel === 'character') return <div className="rail-summary" data-testid="summary-character">
    <strong>{state.character.name}</strong>
    <span>{speciesLabel(state.character.race)} · {classLabel(state.character.class)} · Seviye {state.character.level}</span>
    <span>Can {state.character.current_hp}/{state.character.max_hp} · Zırh {state.character.armor_class}</span>
  </div>;
  if (panel === 'world') return <div className="rail-summary" data-testid="summary-world">
    <strong>{state.locations[state.location]?.name ?? 'Konum bilinmiyor'}</strong>
    <span><CampaignDate state={state} /></span>
  </div>;
  if (panel === 'npcs') {
    const people = currentSceneContext(state).people;
    return <div className="rail-summary" data-testid="summary-npcs">
      {people.length ? people.slice(0, 3).map((person) => <span key={person.id}>{person.name}{person.role ? ` · ${person.role}` : ''}</span>) : <span>Bu sahnede görünür kişi yok.</span>}
    </div>;
  }
  if (panel === 'journal') return <div className="rail-summary" data-testid="summary-journal">
    <span>Yerler {state.journal.discovered_locations.length} · Kişiler {state.journal.known_npcs.length}</span>
    <span>Süren görevler {state.quest_log?.active_count ?? 0}</span>
  </div>;
  return <div className="rail-summary" data-testid="summary-combat">
    {state.combat.active
      ? <><strong>Çatışma sürüyor · Tur {state.combat.round}</strong><span>{state.combat.participant_records.filter((item) => item.status === 'active').length} etkin katılımcı</span></>
      : <span>Çatışma yok.</span>}
  </div>;
}

function PeoplePanel({ state }: { state: GameState }) {
  const scenePeople = currentSceneContext(state).people;
  const sceneIds = new Set(scenePeople.map((npc) => npc.id));
  const otherPeople = currentSceneContext(state).scene ? [] : state.npcs.filter((npc) => npc.location === state.location && !sceneIds.has(npc.id));
  const referents = (currentSceneContext(state).scene?.referents ?? []).filter(
    (referent) => !(
      referent.lifecycle === 'promoted'
      && referent.promoted_npc_id
      && sceneIds.has(referent.promoted_npc_id)
    ),
  );
  return <section className="state-panel" data-testid="panel-npcs">
    <div className="flex items-end justify-between"><div><Kicker><Users size={12} className="mr-1 inline" /> Karşılaşılanlar</Kicker><h2>Kişiler</h2></div><span className="character-badge">{String(scenePeople.length + otherPeople.length).padStart(2, '0')}</span></div>
    <div className="mt-4">
      <Kicker>Yakınında</Kicker>
      {scenePeople.length ? scenePeople.map((npc) => <div className="data-row mt-2" key={npc.id} data-testid={`scene-npc-${npc.id}`}>
        <div className="data-row-head"><span>{npc.name}</span>{npc.role && <span className="status-pill">{npc.role}</span>}</div>
        {npc.appearance && <div className="data-row-desc">{npc.appearance}</div>}
      </div>) : <div className="empty-line mt-2">Şu an yakında tanıdık biri görünmüyor.</div>}
    </div>
    {referents.length > 0 && <div className="mt-4">
      <Kicker>Arka plandaki hareketlilik</Kicker>
      {referents.map((referent) => <div className="data-row mt-2" key={referent.id} data-testid={`scene-referent-${referent.id}`}>
        <div className="data-row-head"><span>Dikkatini çeken</span><span className="status-pill">{referent.lifecycle === 'promoted' ? 'fark ettin' : 'uzakta'}</span></div>
        <div className="data-row-desc">{referent.description}</div>
      </div>)}
    </div>}
    {otherPeople.length > 0 && <div className="mt-4">
      <Kicker>Diğer karşılaştıkların</Kicker>
      {otherPeople.map((npc) => <div className="data-row mt-2" key={npc.id} data-testid={`npc-${npc.id}`}>
        <div className="data-row-head"><span>{npc.name}</span>{npc.combat_status && <span className="status-pill">{npc.combat_status === 'active' ? 'Ayakta' : npc.combat_status === 'unconscious' ? 'Bilinçsiz' : npc.combat_status === 'defeated' ? 'Etkisiz' : npc.combat_status}</span>}</div>
        <div className="data-row-meta">{npc.role ? `${npc.role} · ` : ''}{state.locations[npc.location]?.name ?? npc.location}</div>
        {npc.appearance && <div className="data-row-desc">{npc.appearance}</div>}
      </div>)}
    </div>}
  </section>;
}

export function DetailsPanel({ state }: { state: GameState }) {
  const { features, doors, wayOut } = currentSceneContext(state);
  return <section className="state-panel" data-testid="panel-details">
    <Kicker><DoorOpen size={12} className="mr-1 inline" /> İncelenebilir</Kicker><h2>Ayrıntılar</h2>
    <div className="mt-4">{doors.length ? doors.map((door: GameDoor) => <div className="data-row" key={door.id} data-testid={`door-${door.id}`}>
      <div className="data-row-head"><span className="flex items-center gap-2">{door.locked ? <LockKeyhole size={14} className="text-(color:--unw-danger-text)" /> : <KeyRound size={14} className="text-(color:--unw-accent-light)" />}{door.name}</span><span className="status-pill">{door.broken ? 'kırık' : door.open ? 'açık' : door.locked ? 'kilitli' : 'kapalı'}</span></div>
      <div className="data-row-desc">{door.description}</div>
    </div>) : <div className="empty-line">{wayOut ? `Çıkış: ${wayOut.name}` : 'Bu bölgede kapı veya geçit görünmüyor.'}</div>}</div>
    <Rule />
    <div className="mt-4"><Kicker>Çevredeki özellikler</Kicker><div className="mt-3">{features.length ? features.map((feature) => <div className="border-l border-[color-mix(in_srgb,var(--unw-accent-light)_55%,var(--unw-border))] pl-3" key={feature.id} data-testid={`feature-${feature.id}`}>
      <div className="font-serif text-[17px] text-(color:--unw-text)">{feature.name}</div><div className="subtle-text mt-1">{feature.description}</div>
    </div>) : <div className="empty-line">{state.exploration ? 'Bilinen keşif bulguları ve geçitler keşif panelinde gösterilir.' : 'Burada belirgin bir çevre ayrıntısı görünmüyor.'}</div>}</div></div>
  </section>;
}

export function LeftColumn({ state, catalog, decisionScope = '', conversionBlocked = true, onCommand }: { state: GameState; catalog?: unknown; decisionScope?: string; conversionBlocked?: boolean; onCommand?: (message: string, command: CombatActionInput) => void }) {
  return <aside className="state-column workspace-left" data-testid="panel-character-column"><CharacterPanel character={state.character} catalog={catalog} walletTotalCp={state.wallet?.total_cp ?? null} /><SpellcastingPanel spellcasting={state.spellcasting} decisionScope={JSON.stringify([decisionScope, state.combat?.combat_id, state.combat?.round, state.combat?.current_turn_index, state.combat?.current_actor_id, state.combat?.active])} conversionBlocked={conversionBlocked} onCommand={onCommand} /><InventoryPanel items={state.inventory} /></aside>;
}

const JOURNAL_ENVIRONMENT_LABELS: Record<string, string> = {
  tavern: 'Taverna',
  forest: 'Orman',
  city: 'Şehir',
  village: 'Köy',
  road: 'Yol',
  wilderness: 'Yabanıl alan',
  dungeon: 'Zindan',
  cave: 'Mağara',
  castle: 'Kale',
  temple: 'Tapınak',
  ruins: 'Harabeler',
  unknown: 'Türü bilinmiyor',
};

function JournalPanel({ state, sessionId, campaignId }: { state: GameState; sessionId: string; campaignId?: string }) {
  const queryClient = useQueryClient();
  const [commandNotice, setCommandNotice] = useState<string | null>(null);
  // Quest commands change the world too: they wait behind an unresolved play move or species action of this campaign.
  const questBlocked = () => {
    const reason = unresolvedElsewhere(currentAccountOwner() ?? LOCAL_OWNER, campaignId || sessionId);
    if (reason) setCommandNotice('Önceki işlem henüz doğrulanamadı. Önce onun sonucunu doğrula; görev komutu bundan sonra gönderilir.');
    return Boolean(reason);
  };
  const acceptQuest = useAcceptGameQuest({
    mutation: {
      // A reply is only as new as the moment its command was issued: a later turn or read must not be overwritten by it.
      onMutate: () => ({ issued: nextRevision() }),
      onSuccess: (result, _variables, context) => {
        applyGameState(queryClient, sessionId, result.state, { revision: context?.issued });
        setCommandNotice(result.outcome ? 'Görev kabul edildi.' : 'Görev durumu değişmedi.');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
    },
  });
  const cancelQuest = useCancelGameQuest({
    mutation: {
      // A reply is only as new as the moment its command was issued: a later turn or read must not be overwritten by it.
      onMutate: () => ({ issued: nextRevision() }),
      onSuccess: (result, _variables, context) => {
        applyGameState(queryClient, sessionId, result.state, { revision: context?.issued });
        setCommandNotice(result.outcome ? 'Görev iptal edildi.' : 'Görev durumu değişmedi.');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
    },
  });
  const { journal } = state;
  const events = [...journal.notable_events].sort(
    (left, right) => left.turn_index - right.turn_index || left.created_at.localeCompare(right.created_at),
  );

  return (
    <section className="state-panel" data-testid="panel-journal">
      <Kicker><BookOpen size={12} className="mr-1 inline" /> Yol boyunca birikenler</Kicker>
      <h2>Günlük</h2>
      <p className="subtle-text mt-3">Keşfettiğin yerler, tanıdığın kişiler ve yoluna çıkan önemli olaylar burada birikir.</p>

      <section className="journal-section" data-testid="section-journal-locations">
        <div className="journal-section-heading">
          <div><Kicker><MapPinned size={11} className="mr-1 inline" /> Keşifler</Kicker><h3>Yerler</h3></div>
          <span className="character-badge">{String(journal.discovered_locations.length).padStart(2, '0')}</span>
        </div>
        {journal.discovered_locations.length ? (
          <div className="mt-3">
            {journal.discovered_locations.map((location) => {
              const isCurrent = location.location_id === state.location;
              const turnsSinceVisit = Math.max(0, state.turn_index - location.last_visited_turn);
              const visitLabel = isCurrent
                ? 'Şu an buradasın'
                : turnsSinceVisit === 0
                  ? 'Son ziyaret: bu tur'
                  : `Son ziyaret: ${turnsSinceVisit} tur önce`;
              return (
                <div className="data-row journal-record" key={location.location_id} data-testid={`journal-location-${location.location_id}`}>
                  <div className="data-row-head"><span>{location.name}</span>{isCurrent && <span className="status-pill">Şu an</span>}</div>
                  <div className="data-row-meta">{JOURNAL_ENVIRONMENT_LABELS[location.environment] ?? 'Türü bilinmiyor'} · {visitLabel}</div>
                  <div className="journal-record-note">İlk keşif: Tur {location.first_discovered_turn} · {location.visit_count} ziyaret</div>
                </div>
              );
            })}
          </div>
        ) : <div className="empty-line mt-3" data-testid="empty-journal-locations">Henüz keşfedilmiş bir yer yok.</div>}
      </section>

      <section className="journal-section" data-testid="section-journal-npcs">
        <div className="journal-section-heading">
          <div><Kicker><Users size={11} className="mr-1 inline" /> Karşılaşmalar</Kicker><h3>Tanınan kişiler</h3></div>
          <span className="character-badge">{String(journal.known_npcs.length).padStart(2, '0')}</span>
        </div>
        {journal.known_npcs.length ? (
          <div className="mt-3">
            {journal.known_npcs.map((npc) => {
              const turnsSinceSeen = Math.max(0, state.turn_index - npc.last_seen_turn);
              const seenLabel = turnsSinceSeen === 0
                ? 'Bu tur görüldü'
                : `${turnsSinceSeen} tur önce görüldü`;
              return (
                <div className="data-row journal-record" key={npc.npc_id} data-testid={`journal-npc-${npc.npc_id}`}>
                  <div className="data-row-head"><span>{npc.name}</span>{npc.role && <span className="status-pill">{npc.role}</span>}</div>
                  <div className="data-row-meta">{seenLabel}{npc.last_known_location ? ` · ${npc.last_known_location}` : ''}</div>
                  <div className="journal-record-note">İlk karşılaşma: Tur {npc.first_met_turn}</div>
                </div>
              );
            })}
          </div>
        ) : <div className="empty-line mt-3" data-testid="empty-journal-npcs">Henüz tanınan kişi yok.</div>}
      </section>

      <section className="journal-section" data-testid="section-journal-events">
        <div className="journal-section-heading">
          <div><Kicker><ScrollText size={11} className="mr-1 inline" /> Kronoloji</Kicker><h3>Öne çıkan olaylar</h3></div>
          <span className="character-badge">{String(events.length).padStart(2, '0')}</span>
        </div>
        {events.length ? (
          <ol className="journal-chronicle mt-3" aria-label="Önemli olaylar">
            {events.map((event) => (
              <li className="journal-chronicle-entry" key={event.event_id} data-testid={`journal-event-${event.event_id}`}>
                <span>Tur {event.turn_index}{event.location_name ? ` · ${event.location_name}` : ''}</span>
                <p>{event.summary}</p>
              </li>
            ))}
          </ol>
        ) : <div className="empty-line mt-3" data-testid="empty-journal-events">Henüz kaydedilmiş bir olay yok.</div>}
      </section>

      <section className="journal-section" data-testid="section-journal-lore">
        <div className="journal-section-heading">
          <div><Kicker><ScrollText size={11} className="mr-1 inline" /> Bildiklerin</Kicker><h3>Öğrendiklerin</h3></div>
          <span className="character-badge">{String((state.known_lore ?? []).length).padStart(2, '0')}</span>
        </div>
        {(state.known_lore ?? []).length ? (
          <div className="mt-3">
            {state.known_lore.map((fact) => (
              <div className="data-row journal-record" key={fact.fact_id} data-testid={`journal-lore-${fact.fact_id}`}>
                <div className="data-row-head"><span>{fact.title}</span></div>
                <div className="journal-record-note">{fact.text}</div>
              </div>
            ))}
          </div>
        ) : <div className="empty-line mt-3" data-testid="empty-journal-lore">Henüz doğrulanmış bir bilgi yok.</div>}
        {(state.known_factions ?? []).length > 0 && (
          <div className="mt-3">
            {state.known_factions.map((faction) => (
              <div className="data-row journal-record" key={faction.faction_id} data-testid={`journal-faction-${faction.faction_id}`}>
                <div className="data-row-head"><span>{faction.title}</span></div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="journal-section" data-testid="section-journal-shops">
        <Kicker>Uğraklar</Kicker><h3>Dükkânlar</h3>
        {state.shops.length ? state.shops.map((shop) => (
          <div className="data-row journal-record" key={shop.id} data-testid={`journal-shop-${shop.id}`}>
            <div className="data-row-head">{shop.name}</div>
            <p className="data-row-desc">{shop.description}</p>
            <span className="data-row-meta">{state.locations[shop.location]?.name ?? shop.location}</span>
          </div>
        )) : <div className="empty-line mt-3">Henüz keşfedilmiş bir dükkân yok.</div>}
      </section>
      <QuestJournalSection
        quests={state.quests ?? []}
        offers={state.quest_offers ?? []}
        knownNpcs={journal.known_npcs}
        onAccept={(questId) => { if (!questBlocked()) acceptQuest.mutate({ sessionId, questId }); }}
        onCancel={(questId) => { if (!questBlocked()) cancelQuest.mutate({ sessionId, questId }); }}
        acceptPending={acceptQuest.isPending}
        cancelPending={cancelQuest.isPending}
        hasError={acceptQuest.isError || cancelQuest.isError}
        commandNotice={commandNotice}
        adventures={state.campaign_adventures}
        questLog={state.quest_log}
      />
      <AdventureJournalSection adventure={state.adventure} />
    </section>
  );
}

export function WorldTabs({ state, activeTab, setActiveTab, combatEntries, sessionId, campaignId, sending, onExplorationCommand, onDraft, onSetCombatTarget }: { state: GameState; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string; campaignId: string; sending: boolean; onExplorationCommand: (message: string) => void; onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void; onSetCombatTarget: (targetId: string) => void }) {
  const tabs: { id: WorldTab; label: string }[] = [{ id: 'world', label: 'DÜNYA' }, { id: 'npcs', label: 'KİŞİLER' }, { id: 'journal', label: 'GÜNLÜK' }, { id: 'combat', label: 'ÇATIŞMA' }];
  const tabRefs = useRef<Partial<Record<WorldTab, HTMLButtonElement>>>({});
  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | undefined;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = tabs.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    setActiveTab(nextTab.id);
    tabRefs.current[nextTab.id]?.focus();
  };

  return (
    <aside className="world-column" data-testid="panel-world-column">
      <div className="world-tabs" role="tablist" aria-label="Dünya panelleri">
        {tabs.map((tab, index) => (
          <button
            ref={(node) => { if (node) tabRefs.current[tab.id] = node; }}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls="world-panel-content"
            aria-selected={activeTab === tab.id}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={`${activeTab === tab.id ? 'active' : ''} ${tab.id === 'combat' && state.combat.active ? 'combat-live' : ''}`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
            data-testid={`tab-${tab.id}`}
            aria-label={tab.id === 'combat' && state.combat.active ? 'Çatışma sürüyor' : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="world-panel-content" aria-labelledby={`tab-${activeTab}`} tabIndex={0}>
        {activeTab === 'world' && <><WorldPanel state={state} /><ExperimentalWorldControls state={state} sending={sending} onExplorationCommand={onExplorationCommand} onDraft={onDraft} onSetCombatTarget={onSetCombatTarget} /><DetailsPanel state={state} /></>}
        {activeTab === 'npcs' && <PeoplePanel state={state} />}
         {activeTab === 'journal' && <JournalPanel state={state} sessionId={sessionId} campaignId={campaignId} />}
        {activeTab === 'combat' && <CombatPanel state={state} entries={combatEntries} sessionId={sessionId} campaignId={campaignId} onDeathMove={onExplorationCommand} sending={sending} />}
      </div>
    </aside>
  );
}
