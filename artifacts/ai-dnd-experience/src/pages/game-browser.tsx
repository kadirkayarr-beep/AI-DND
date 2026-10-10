import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CombatPanel, type CombatLogEntry } from '@/components/combat-panel';
import { mergeCombatHistory } from '@/lib/combat-history';
import { ExplorationControls } from '@/components/exploration-controls';
import { explorationInputLabel } from '@/lib/exploration-input';
import {
  AmbientEventActionPanel,
  createAmbientEventActionRequest,
  findPersistedAmbientEventResult,
  isActiveBlueAmbientEvent,
  type AmbientEventActionRequest,
} from '@/components/ambient-event-actions';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Backpack,
  BookOpen,
  Check,
  Compass,
  DoorOpen,
  Feather,
  Heart,
  KeyRound,
  LockKeyhole,
  Map,
  MapPinned,
  Menu,
  MessageCircle,
  Plus,
  RefreshCw,
  Save,
  ScrollText,
  Send,
  Shield,
  Sparkles,
  Swords,
  Users,
  Wifi,
  X,
} from 'lucide-react';
import {
  getGetCampaignsQueryKey,
  getGetCampaignStartOptionsQueryKey,
  getGetCharacterOptionsQueryKey,
  getGetCharacterCreationCatalogQueryKey,
  getGetGameHealthQueryKey,
  getGetGameSessionStateQueryKey,
  useCreateCampaign,
  useGetGameHealth,
  useGetCampaigns,
  useGetCampaignStartOptions,
  useGetCharacterOptions,
  useGetCharacterCreationCatalog,
  useGetGameSessionState,
  useAcceptGameQuest,
  useCancelGameQuest,
  usePlayGameTurn,
  useResolveAmbientEventAction,
  useResumeCampaign,
  useSaveCampaign,
} from '@workspace/api-client-react';
import { QuestJournalSection } from '@/components/quest-journal-section';
import { AdventureJournalSection } from '@/components/adventure-journal-section';
import type { AmbientEventActionInputAction, AmbientEventResult, CampaignHistoryEntry, CampaignStartSelection, CharacterCreateInput, GameCharacter, GameDoor, GameNpc, GameState, SkillCheckResult } from '@workspace/api-client-react';
import { EnvironmentThemeProvider } from '@/components/environment-theme';
import { CampaignLibrary } from '@/components/campaign-library';
import { CharacterCreationScreen } from '@/components/character-creation-screen';
import { SkillCheckResultCard } from '@/components/skill-check-result';
import { ActionEconomyPanel } from '@/components/action-economy-panel';
import { SpellcastingPanel } from '@/components/spellcasting-panel';
import { CampaignContextPanel, CampaignDate } from '@/components/campaign-context-panel';
import { currentSceneContext, classLabel, speciesLabel } from '@/lib/campaign-presentation';
import { OuroborosMark } from '@/components/ouroboros-mark';
import { gateSoundMuted, gateSoundVolume, playGateSound, primeGateSound, setGateSoundMuted, setGateSoundVolume } from '@/lib/gate-sound';
import '@/components/cinematic-gate.css';
import type { CombatActionInput } from '@workspace/api-client-react';
import { getContextualActionSuggestions, getTurnInteractionMetadata, type InteractionMode } from '@/lib/action-suggestions';
import citadelArtwork from '@assets/generated_images/ai-dnd-citadel-gate.jpg';

const LAST_CAMPAIGN_KEY = 'ai-dnd-last-selected-campaign-id';
const TRANSCRIPT_KEY = 'ai-dnd-transcript-';

type Notice = { tone: 'error' | 'success' | 'warning'; title: string; detail: string };
type TranscriptEntry = { kind: 'player' | 'narration'; text: string; skillCheckResult?: SkillCheckResult };
type Drawer = 'character' | 'world' | null;
type WorldTab = 'world' | 'npcs' | 'journal' | 'combat';

function statusCode(error: unknown) {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return candidate.status ?? candidate.statusCode ?? candidate.response?.status;
}

function friendlyError(error: unknown, fallback: string) {
  const code = statusCode(error);
  if (code === 404) return 'Bu macera bulunamadı.';
  if (code === 422) return 'Bu söz şimdilik yankı bulmadı. 1–4000 karakter arasında yeniden dene.';
  if (code === 503) return 'Dünya şu an sessiz.';
  if (typeof navigator !== 'undefined' && !navigator.onLine) return 'Bağlantı yok. İnternet bağlantını kontrol edip tekrar dene.';
  return fallback;
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand" data-testid="brand-ai-dnd">
      <div className="brand-mark"><OuroborosMark /></div>
      {!compact && <div><div className="brand-name">AI DUNGEON MASTER</div><div className="brand-subtitle">Tek oyunculu macera · Forgotten Realms</div></div>}
    </div>
  );
}

function GateSoundControl() {
  const [muted, setMuted] = useState(gateSoundMuted);
  const [volume, setVolume] = useState(gateSoundVolume);
  return (
    <div className="gate-sound" data-testid="gate-sound-control">
      <button type="button" aria-pressed={muted} onClick={() => { primeGateSound(); const next = !muted; setMuted(next); setGateSoundMuted(next); }}>
        {muted ? 'Ses kapalı' : 'Ses açık'}
      </button>
      <label>
        Düzey
        <input aria-label="Ses düzeyi" type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => {
          const next = Number(event.target.value);
          setVolume(next);
          setGateSoundVolume(next);
          primeGateSound();
        }} />
      </label>
    </div>
  );
}

function Kicker({ children }: { children: ReactNode }) {
  return <div className="dnd-kicker">{children}</div>;
}

function Rule() {
  return <div className="dnd-rule" aria-hidden="true" />;
}

function NoticeBanner({ notice }: { notice: Notice }) {
  return (
    <div className={`notice ${notice.tone === 'error' ? 'error' : notice.tone === 'success' ? 'success' : ''}`} role="status" data-testid={`status-${notice.tone}`}>
      <AlertTriangle size={15} className="shrink-0" />
      <div><strong>{notice.title}</strong><div>{notice.detail}</div></div>
    </div>
  );
}

function TavernArtwork() {
  return (
    <div className="gate-scene" data-testid="artwork-tavern" role="img" aria-label="Sislerin ardındaki uzak kale ve ona uzanan taş köprü" style={{ backgroundImage: `url("${citadelArtwork}")` }}>
      <div className="gate-mist gate-mist-near" />
      <div className="gate-mist gate-mist-far" />
      <div className="gate-seal" aria-hidden="true">
        <span className="gate-seal-caption">Yol çağırıyor</span>
        <OuroborosMark awaken />
      </div>
      <span className="gate-art-caption" aria-hidden="true">UNUTULMUŞ DİYARLAR · FAERÛN</span>
    </div>
  );
}

function EngineHealth() {
  const health = useGetGameHealth({ query: { queryKey: getGetGameHealthQueryKey(), staleTime: 30_000, retry: 1 } });
  const ready = Boolean(health.data && ['ok', 'healthy', 'ready'].includes(health.data.status.toLowerCase()));
  return (
    <aside className="gate-health" data-testid="panel-engine-health">
      {health.isLoading ? <span data-testid="health-loading">Dünya uyanıyor.</span> : health.isError ? (
        <span data-testid="error-health">Dünyaya şu an ulaşılamıyor. <button type="button" data-testid="button-retry-health" onClick={() => void health.refetch()}>Tekrar dene</button></span>
      ) : <span data-testid="status-health">{ready ? 'Yol açık.' : 'Dünya sessiz.'}</span>}
    </aside>
  );
}

function OpeningScreen({ onCreate, onContinue, creating, notice, loadingCampaigns, hasCampaigns, showNoCampaigns }: { onCreate: () => void; onContinue: () => void; creating: boolean; notice: Notice | null; loadingCampaigns: boolean; hasCampaigns: boolean; showNoCampaigns: boolean }) {
  return (
    <main className="opening cinematic-gate gate-fade" data-testid="app-start">
      <div className="dnd-shell">
        <header className="opening-header">
          <Brand />
          <GateSoundControl />
        </header>
        <div className="opening-grid">
          <section className="opening-copy" aria-labelledby="opening-title">
            <div className="opening-eyebrow"><Kicker>Kapılar açılıyor</Kicker></div>
            <h1 className="opening-title" id="opening-title">Hikâyeni<br /><span>anlat.</span></h1>
            <p className="opening-lede dnd-serif">Dünya cevap versin.</p>
            <p className="opening-body">Yağmurun izini kapıda bırak. Dünya kendi kurallarını korurken ilk adımı kendi sözlerinle at.</p>
            <div className="opening-actions gate-actions">
              <button className="dnd-button" type="button" data-testid="button-create-session" disabled={creating} onClick={() => { primeGateSound(); playGateSound('menu'); onCreate(); }}>
                {creating ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRight size={14} />} {creating ? 'Dünya kuruluyor' : 'Yeni macera'}
              </button>
              <button className="dnd-button secondary" type="button" data-testid="button-continue-session" disabled={loadingCampaigns} onClick={() => { primeGateSound(); playGateSound('menu'); onContinue(); }}>
                {loadingCampaigns ? <RefreshCw size={14} className="animate-spin" /> : <BookOpen size={14} />} Maceraya devam et
              </button>
            </div>
            {showNoCampaigns && !hasCampaigns && <div className="continue-note" data-testid="text-no-session">Henüz bir macera yok. İlk yolculuğunu başlat.</div>}
            {notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}
            <div className="opening-meta"><span>TEK OYUNCU</span><span className="meta-dot" /><span>DOĞAL DİLLE</span><span className="meta-dot" /><span>SENİN SEÇİMİN</span></div>
          </section>
          <section className="opening-art" aria-label="Macera kapısı"><TavernArtwork /></section>
        </div>
        <EngineHealth />
      </div>
    </main>
  );
}

function CharacterPanel({ character, compact = false }: { character: GameCharacter; compact?: boolean }) {
  const abilities = [['KUV', character.strength], ['ÇEV', character.dexterity], ['DAY', character.constitution], ['ZEK', character.intelligence], ['BİL', character.wisdom], ['KAR', character.charisma]];
  const hp = character.max_hp > 0 ? Math.max(0, Math.min(100, character.current_hp / character.max_hp * 100)) : 0;
  return (
    <section className={`state-panel ${compact ? 'compact-character' : ''}`} data-testid="panel-character">
      <div className="character-top"><div><Kicker>Yolcu kaydı</Kicker><h2 data-testid="text-character-name">{character.name}</h2><div className="character-sub">{speciesLabel(character.race)} {classLabel(character.class)} · Seviye {character.level}</div></div><span className="character-badge">LVL {String(character.level).padStart(2, '0')}</span></div>
      <div className="health-row"><span className="flex items-center gap-2"><Heart size={13} /> Can durumu</span><span data-testid="text-character-hp">{character.current_hp} / {character.max_hp}</span></div>
      <div className="health-track"><div className="health-fill" style={{ width: `${hp}%` }} data-testid="meter-health" /></div>
      <div className="key-values"><div className="key-value"><Kicker>ZIRH</Kicker><span>{character.armor_class}</span></div><div className="key-value"><Kicker>USTALIK</Kicker><span>+{character.proficiency_bonus}</span></div></div>
      {!compact && <div className="mt-5"><Kicker>Yetenekler</Kicker><div className="stat-strip">{abilities.map(([label, value]) => <div className="stat-box" key={label}><Kicker>{label}</Kicker><div className="stat-value">{value}</div></div>)}</div></div>}
      {!compact && <div className="mt-5 border-t border-[#4b3926] pt-4"><Kicker>Usta olunan beceriler</Kicker><div className="mt-3 flex flex-wrap gap-2">{character.proficient_skills.length ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skill}</span>) : <span className="subtle-text">Henüz bir beceride ustalaşmadın.</span>}</div></div>}
    </section>
  );
}

function InventoryPanel({ items }: { items: string[] }) {
  return <section className="state-panel" data-testid="panel-inventory"><div className="flex items-end justify-between"><div><Kicker>Üzerinde</Kicker><h2>Envanter</h2></div><span className="character-badge">{String(items.length).padStart(2, '0')}</span></div>{items.length ? <div className="list-stack">{items.map((item, index) => <div className="list-row" key={`${item}-${index}`} data-testid={`item-inventory-${index}`}><span className="list-icon"><Backpack size={14} /></span>{item}</div>)}</div> : <div className="empty-line mt-4">Çantada kaydedilmiş eşya yok.</div>}</section>;
}

function WorldPanel({ state }: { state: GameState }) {
  return <CampaignContextPanel state={state} />;
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

function DetailsPanel({ state }: { state: GameState }) {
  const { features, doors } = currentSceneContext(state);
  return <section className="state-panel" data-testid="panel-details">
    <Kicker><DoorOpen size={12} className="mr-1 inline" /> İncelenebilir</Kicker><h2>Ayrıntılar</h2>
    <div className="mt-4">{doors.length ? doors.map((door: GameDoor) => <div className="data-row" key={door.id} data-testid={`door-${door.id}`}>
      <div className="data-row-head"><span className="flex items-center gap-2">{door.locked ? <LockKeyhole size={14} className="text-[#bc7062]" /> : <KeyRound size={14} className="text-[#c09a61]" />}{door.name}</span><span className="status-pill">{door.broken ? 'kırık' : door.open ? 'açık' : door.locked ? 'kilitli' : 'kapalı'}</span></div>
      <div className="data-row-desc">{door.description}</div>
    </div>) : <div className="empty-line">Bu bölgede kapı veya geçit görünmüyor.</div>}</div>
    <Rule />
    <div className="mt-4"><Kicker>Çevredeki özellikler</Kicker><div className="mt-3">{features.length ? features.map((feature) => <div className="border-l border-[#866942] pl-3" key={feature.id} data-testid={`feature-${feature.id}`}>
      <div className="font-serif text-[17px] text-[#d1c2a6]">{feature.name}</div><div className="subtle-text mt-1">{feature.description}</div>
    </div>) : <div className="empty-line">{state.exploration ? 'Bilinen keşif bulguları ve geçitler keşif panelinde gösterilir.' : 'Burada belirgin bir çevre ayrıntısı görünmüyor.'}</div>}</div></div>
  </section>;
}

function LeftColumn({ state }: { state: GameState }) {
  return <aside className="state-column workspace-left" data-testid="panel-character-column"><CharacterPanel character={state.character} /><SpellcastingPanel spellcasting={state.spellcasting} /><InventoryPanel items={state.inventory} /></aside>;
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

function JournalPanel({ state, sessionId }: { state: GameState; sessionId: string }) {
  const queryClient = useQueryClient();
  const [commandNotice, setCommandNotice] = useState<string | null>(null);
  const acceptQuest = useAcceptGameQuest({
    mutation: {
      onSuccess: (result) => {
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
        setCommandNotice(result.outcome ? 'Görev kabul edildi.' : 'Görev durumu değişmedi.');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
    },
  });
  const cancelQuest = useCancelGameQuest({
    mutation: {
      onSuccess: (result) => {
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
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

      <QuestJournalSection
        quests={state.quests ?? []}
        offers={state.quest_offers ?? []}
        knownNpcs={journal.known_npcs}
        onAccept={(questId) => acceptQuest.mutate({ sessionId, questId })}
        onCancel={(questId) => cancelQuest.mutate({ sessionId, questId })}
        acceptPending={acceptQuest.isPending}
        cancelPending={cancelQuest.isPending}
        hasError={acceptQuest.isError || cancelQuest.isError}
        commandNotice={commandNotice}
        adventures={state.campaign_adventures}
      />
      <AdventureJournalSection adventure={state.adventure} />
    </section>
  );
}

function WorldTabs({ state, activeTab, setActiveTab, combatEntries, sessionId }: { state: GameState; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string }) {
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
        {activeTab === 'world' && <><WorldPanel state={state} /><DetailsPanel state={state} /></>}
  {activeTab === 'npcs' && <PeoplePanel state={state} />}
         {activeTab === 'journal' && <JournalPanel state={state} sessionId={sessionId} />}
        {activeTab === 'combat' && <CombatPanel state={state} entries={combatEntries} sessionId={sessionId} />}
      </div>
    </aside>
  );
}

function Transcript({ entries, scrollRef, onScroll }: { entries: TranscriptEntry[]; scrollRef: RefObject<HTMLDivElement | null>; onScroll: () => void }) {
  if (!entries.length) return <div className="empty-line mt-4" data-testid="empty-transcript">İlk hamleni yaz. Dünya seçiminin ardından karşılık verecek.</div>;
  return <div className="transcript-scroll" ref={scrollRef} onScroll={onScroll} data-testid="transcript-scroll" tabIndex={0} aria-label="Hikâye akışı"><div className="mt-2" data-testid="transcript-local">{entries.map((entry, index) => entry.kind === 'player' ? <div className="player-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-player-${index}`}><div className="player-label"><MessageCircle size={12} /> Sen</div>{entry.text}</div> : <div className="story-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-narration-${index}`}><p className="story-text">{entry.text}</p>{entry.skillCheckResult && <SkillCheckResultCard result={entry.skillCheckResult} />}</div>)}</div><div className="reader-note">Sahne, kişiler ve öykü notları sağ panelde</div></div>;
}

function StoryColumn({
  state,
  entries,
  message,
  setMessage,
  interactionMode,
  setInteractionMode,
  conversationTargetId,
  setConversationTargetId,
  onEndConversation,
  onSubmit,
  onExplorationCommand,
  onEconomyCommand,
  sending,
  notice,
  scrollRef,
  onScroll,
  locationChanged,
  combatEndNotice,
  combatTargetId,
  setCombatTargetId,
  ambientActionResult,
  ambientActionRequest,
  ambientActionSending,
  ambientActionError,
  onAmbientAction,
  onRetryAmbientAction,
}: {
  state: GameState;
  entries: TranscriptEntry[];
  message: string;
  setMessage: (value: string) => void;
  interactionMode: InteractionMode;
  setInteractionMode: (value: InteractionMode) => void;
  conversationTargetId: string;
  setConversationTargetId: (value: string) => void;
  onEndConversation: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onExplorationCommand: (message: string) => void;
  onEconomyCommand: (message: string, command: CombatActionInput) => void;
  sending: boolean;
  notice: Notice | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  locationChanged: boolean;
  combatEndNotice: string | null;
  combatTargetId: string;
  setCombatTargetId: (value: string) => void;
  ambientActionResult: AmbientEventResult | null;
  ambientActionRequest: AmbientEventActionRequest | null;
  ambientActionSending: boolean;
  ambientActionError: boolean;
  onAmbientAction: (action: AmbientEventActionInputAction) => void;
  onRetryAmbientAction: () => void;
}) {
  const location = state.locations[state.location];
  const ambientEvent = state.scene?.ambient_event ?? null;
  const currentAmbientResult = ambientActionResult?.event_instance_id === ambientEvent?.instance_id
    ? ambientActionResult
    : ambientEvent
      ? findPersistedAmbientEventResult(state, ambientEvent.instance_id)
      : null;
  const combatTargets = state.combat.participant_records.filter(
    (participant) => participant.kind === 'npc'
      && participant.status === 'active'
      && participant.current_hp > 0,
  );
  const actionSuggestions = [
    ...getContextualActionSuggestions(state),
    ...(state.campaign_adventures?.affordances ?? []).map((label: string) => ({
      id: `adventure-${label}`,
      label,
      message: label,
      mode: 'do' as const,
    })),
  ];
  const conversationTargets = (state.scene?.npcs ?? []).filter(
    (npc) => typeof npc.id === 'string' && typeof npc.name === 'string' && npc.name.trim().length > 0,
  );
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const currentActor = state.combat.participant_records.find(
    (participant) => participant.id === state.combat.current_actor_id,
  );
  const modePrompt = interactionMode === 'say'
    ? 'Ne söylüyorsun?'
    : interactionMode === 'ask_dm'
      ? 'Anlatıcıya ne sormak istiyorsun?'
      : 'Ne yapmak istiyorsun?';
  return (
    <section className="story-column workspace-story" data-testid="panel-story">
      <div className="story-heading">
        <div className="story-icon"><Feather size={15} strokeWidth={1.25} /></div>
        <div><Kicker>Anlatıcı</Kicker><div className="story-meta mt-1">Sahnenin sözü burada yankılanır</div></div>
        <div className="ml-auto story-meta hidden sm:block">Tur {state.turn_index}</div>
      </div>
      <ActionEconomyPanel state={state} targetId={combatTargetId} sending={sending} onCommand={onEconomyCommand} />
      <div className={`location-ribbon ${locationChanged ? 'location-ribbon-new' : ''}`} data-testid="status-location">
        <MapPinned size={14} /><div><Kicker>Şu anki konum</Kicker><strong>{location?.name ?? 'Konum ayrıntıları henüz görünmüyor.'}</strong>{location?.type && JOURNAL_ENVIRONMENT_LABELS[location.type] && <span>{JOURNAL_ENVIRONMENT_LABELS[location.type]}</span>}</div>
      </div>
      <AmbientEventActionPanel
        event={ambientEvent}
        referents={state.scene?.referents ?? []}
        result={currentAmbientResult}
        retryRequest={ambientActionRequest}
        sending={ambientActionSending}
        hasError={ambientActionError}
        onAction={onAmbientAction}
        onRetry={onRetryAmbientAction}
      />
      {combatEndNotice && (
        <div className="combat-transition-banner" role="status" data-testid="status-combat-ended">
          <Swords size={14} aria-hidden="true" />
          <div><strong>ÇATIŞMA SONA ERDİ</strong><span>{combatEndNotice}</span></div>
        </div>
      )}
      {state.combat.active && currentActor && currentActor.id !== 'player' && (
        <div className="command-combat-turn-note" role="status" data-testid="status-combat-turn-owner">
          Sıra {currentActor.name}'de. Önce bu anı tamamlayacak bir söz gönder; ardından kendi hamleni anlat.
        </div>
      )}
      <Transcript entries={entries.map((entry) => entry.kind === 'player'
        ? { ...entry, text: explorationInputLabel(entry.text) } : entry)} scrollRef={scrollRef} onScroll={onScroll} />
      {notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}
      <div className="command-box">
        <details className="data-row mb-3" open={!state.exploration} data-testid="exploration-disclosure">
          <summary className="cursor-pointer">Keşif ve yolculuk</summary>
          <div className="mt-3 overflow-y-auto" style={{ maxHeight: '35vh' }}>
            <ExplorationControls state={state}
              disabled={sending || state.combat.active || state.character.current_hp <= 0 || !!state.pending_event_decisions?.length}
              onCommand={onExplorationCommand} />
          </div>
        </details>
        <div className="action-suggestions" role="group" aria-label="Bu sahne için önerilen hamleler" data-testid="action-suggestions">
          <div className="action-suggestions-heading">
            <span><Sparkles size={12} aria-hidden="true" /> Bu sahnede deneyebilirsin</span>
            <small>Seçim metin kutusuna aktarılır; gönderilmez.</small>
          </div>
          <div className="action-suggestion-list">
            {actionSuggestions.map((suggestion) => (
              <button
                className="action-suggestion"
                data-testid={`button-suggestion-${suggestion.id}`}
                disabled={sending}
                key={suggestion.id}
                onClick={() => {
                  const targetId = "targetId" in suggestion ? suggestion.targetId : undefined;
                  setInteractionMode(suggestion.mode);
                  setConversationTargetId(suggestion.mode === 'say' ? (targetId ?? '') : '');
                  if (state.combat.active && targetId) setCombatTargetId(targetId);
                  setMessage(suggestion.message);
                  messageInputRef.current?.focus();
                }}
                type="button"
              >
                {suggestion.label}
              </button>
            ))}
          </div>
        </div>
        {state.conversation.active && state.conversation.interlocutor && (
          <div className="data-row mb-3" role="status" data-testid="active-interlocutor">
            <div className="flex items-center gap-2">
              <MessageCircle size={13} aria-hidden="true" />
              <span>Konuşuyorsun: <strong>{state.conversation.interlocutor.name}</strong></span>
              <button
                className="action-suggestion ml-auto"
                type="button"
                disabled={sending}
                onClick={onEndConversation}
                data-testid="button-end-conversation"
              >
                Konuşmayı bitir
              </button>
            </div>
          </div>
        )}
        <div className="action-suggestion-list mb-3" role="group" aria-label="Etkileşim biçimi" data-testid="interaction-mode-selector">
          {([
            ['say', 'SÖYLE'],
            ['do', 'YAP'],
            ['ask_dm', 'ANLATICIYA SOR'],
          ] as const).map(([mode, label]) => (
            <button
              key={mode}
              className="action-suggestion"
              type="button"
              aria-pressed={interactionMode === mode}
              data-testid={`button-mode-${mode}`}
              disabled={sending || (state.combat.active && mode !== 'do')}
              onClick={() => {
                setInteractionMode(mode);
                if (mode !== 'say') setConversationTargetId('');
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {interactionMode === 'say' && conversationTargets.length > 1 && (
          <label className="command-target-label mb-3" htmlFor="conversation-target-select">
            <span>Kiminle konuşuyorsun? <small>— isteğe bağlı</small></span>
            <select
              id="conversation-target-select"
              className="command-target-select"
              value={conversationTargetId}
              onChange={(event) => setConversationTargetId(event.target.value)}
              disabled={sending}
              data-testid="select-conversation-target"
            >
              <option value="">Sözlerimde belirteceğim</option>
              {conversationTargets.map((npc) => (
                <option value={npc.id} key={npc.id}>{npc.name}</option>
              ))}
            </select>
          </label>
        )}
        <form className="command-form" onSubmit={onSubmit}>
          {state.pending_event_decisions?.map((event, index) => <div className="data-row mb-3" data-testid="scheduled-event-decision" key={index}>
            <p>{event.summary}</p>
            <small>{event.in_combat ? 'Çatışma sonrasında sonraki kararını sen vereceksin.' : event.forced ? 'Fiziksel engel: başka bir kayıtlı konum veya rota seçebilirsin.' : 'Kararın bekleniyor; zaman kendiliğinden ilerlemiyor.'}</small>
            {!event.in_combat && <div className="action-suggestion-list">
              {[
                ...(!event.forced ? [['Devam etmeyi seç', 'Karşılaşmada devam etmeyi seçiyorum.'], ['Konuş', 'Karşılaşmada konuşmayı seçiyorum.']] : []),
                ...(event.can_fight ? [['Savaş', 'Karşılaşmada savaşmayı seçiyorum.']] : []),
                ...(state.journey ? [['Geri dön', 'Geri dönüyorum.']] : []),
              ].map(([label, intent]) => <button key={label} className="action-suggestion" type="button" disabled={sending || state.combat.active} onClick={() => {
                if (state.exploration) {
                  const choice = label === 'Savaş' ? 'fight' : label === 'Geri dön' ? 'return'
                    : label === 'Konuş' ? 'talk' : 'continue';
                  onExplorationCommand('/explore decision ' + choice);
                } else {
                  setMessage(`Karşılaşma: ${event.summary}\nKararım: ${intent}`);
                  messageInputRef.current?.focus();
                }
              }}>{label}</button>)}
            </div>}
          </div>)}
          {state.journey && <div className="data-row mb-3" data-testid="journey-decision">
            <p>{state.locations[state.journey.destination]?.name ?? state.journey.destination} yolunda · {state.journey.stage} / {state.journey.stage_count}</p>
            {state.journey.encounter && <p>{state.journey.encounter}</p>}
            <div className="action-suggestion-list">
              {[
                ['Yola devam', 'Yolculuğa devam ediyorum.'],
                ['Dur', 'Yolculuğu durduruyorum.'],
                ['Geri dön', 'Geri dönüyorum.'],
              ].map(([label, intent]) => <button key={label} className="action-suggestion" type="button" disabled={sending || state.combat.active || !!state.pending_event_decisions?.length} onClick={() => {
                if (state.exploration) onExplorationCommand('/travel ' + (label === 'Yola devam' ? 'continue' : label === 'Dur' ? 'stop' : 'return'));
                else { setMessage(intent); messageInputRef.current?.focus(); }
              }}>{label}</button>)}
            </div>
          </div>}
          {state.combat.active && combatTargets.length > 0 && (
            <label className="command-target-label" htmlFor="combat-target-select">
              <span>Hedef seç <small>· isteğe bağlı</small></span>
              <select
                id="combat-target-select"
                className="command-target-select"
                value={combatTargetId}
                onChange={(event) => setCombatTargetId(event.target.value)}
                disabled={sending}
                data-testid="select-combat-target"
              >
                <option value="">Hamlemde belirteceğim</option>
                {combatTargets.map((participant) => (
                  <option value={participant.id} key={participant.id}>{participant.name}</option>
                ))}
              </select>
            </label>
          )}
          <label className="sr-only" htmlFor="player-message">Hamleni anlat</label>
          <textarea ref={messageInputRef} id="player-message" className="command-input" value={message} maxLength={4000} onChange={(event) => setMessage(event.target.value)} placeholder={modePrompt} data-testid="input-player-message" disabled={sending} />
          <button className="dnd-button" type="submit" disabled={sending || !message.trim()} data-testid="button-send-turn">
            {sending ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
            {sending ? 'Dünya yanıt veriyor' : 'Gönder'}
          </button>
        </form>
        <div className="command-help"><span>Sözlerinle anlat · 1–4000 karakter</span><span data-testid="text-message-count">{message.length} / 4000</span></div>
      </div>
    </section>
  );
}

function SessionHeader({ state, campaignId, onSave, saving, onReset, onDrawer, onOpenCombat }: { state: GameState; campaignId: string; onSave: () => void; saving: boolean; onReset: () => void; onDrawer: (drawer: Exclude<Drawer, null>) => void; onOpenCombat: () => void }) {
  return (
    <header className="app-header">
      <div className="dnd-shell app-header-inner">
        <Brand />
        <div className="header-location">
          <MapPinned size={13} />
          <div className="header-location-copy">
            <span data-testid="header-location">{state.locations[state.location]?.name ?? 'Konum ayrıntıları henüz görünmüyor.'}</span>
            <small data-testid="text-neutral-atmosphere"><CampaignDate state={state} /></small>
          </div>
          <span className="header-hp" data-testid="header-character-hp" aria-label={`Can ${state.character.current_hp} / ${state.character.max_hp}`}><Heart size={13} aria-hidden="true" />{state.character.current_hp} / {state.character.max_hp}</span>
        </div>
        {state.combat.active && (
          <button className="combat-quick-status" type="button" aria-haspopup="dialog" onClick={onOpenCombat} data-testid="button-open-active-combat">
            <Swords size={14} aria-hidden="true" />
            <span className="combat-quick-status-label">ÇATIŞMA</span>
            {typeof state.combat.round === 'number' && <span>Tur {state.combat.round}</span>}
            <span className="combat-quick-hp">{state.character.current_hp}/{state.character.max_hp} CAN</span>
          </button>
        )}
        <div className="header-actions">
          <button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-character" onClick={() => onDrawer('character')}><Shield size={14} /> Karakter</button>
          <button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-world" onClick={() => onDrawer('world')}><Menu size={14} /> Dünya</button>
          <div className="session-chip" data-testid="status-session"><span className="health-dot" /> <span className="hidden sm:inline">MACERA</span></div>
          <button className="dnd-button secondary !min-h-[35px] !px-3 !text-[8px]" type="button" onClick={onSave} disabled={saving} data-testid="button-save-campaign">{saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} <span className="hidden sm:inline">Kaydet</span></button>
          <button className="dnd-button secondary !min-h-[35px] !px-3 !text-[8px]" type="button" onClick={onReset} data-testid="button-new-session"><Plus size={13} /> Yeni</button>
        </div>
      </div>
    </header>
  );
}

function DrawerSheet({ drawer, state, onClose, activeTab, setActiveTab, combatEntries, sessionId }: { drawer: Drawer; state: GameState; onClose: () => void; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string }) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!drawer) return;
    const dialog = dialogRef.current;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => dialog?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? [];
    focusable()[0]?.focus();
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const elements = focusable();
      if (!elements.length) { event.preventDefault(); return; }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [drawer]);
  if (!drawer) return null;
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><section ref={dialogRef} className="drawer-sheet" role="dialog" aria-modal="true" aria-label={drawer === 'character' ? 'Karakter paneli' : 'Dünyanın çevresi'} tabIndex={-1} onClick={(event) => event.stopPropagation()}><div className="drawer-heading"><Kicker>{drawer === 'character' ? 'Yolcu' : 'Dünyanın çevresi'}</Kicker><button className="icon-button" type="button" aria-label="Paneli kapat" data-testid="button-close-drawer" onClick={onClose}><X size={16} /></button></div>{drawer === 'character' ? <><CharacterPanel character={state.character} /><SpellcastingPanel spellcasting={state.spellcasting} /><InventoryPanel items={state.inventory} /></> : <WorldTabs state={state} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} />}</section></div>;
}

function CharacterReveal({ state, onContinue, onBack }: { state: GameState; onContinue: () => void; onBack: () => void }) {
  const character = state.character;
  const abilities = [
    ['KUV', character.strength],
    ['ÇEV', character.dexterity],
    ['DAY', character.constitution],
    ['ZEK', character.intelligence],
    ['BİL', character.wisdom],
    ['KAR', character.charisma],
  ];
  return (
    <main className="reveal-screen gate-fade" data-testid="screen-character-reveal">
      <header className="dnd-shell reveal-header">
        <Brand />
        <button type="button" className="text-button" onClick={onBack} data-testid="button-back-opening">
          <ArrowLeft size={13} /> Geri dön
        </button>
      </header>
      <div className="reveal-wrap">
        <div className="reveal-heading">
          <Kicker>Yeni macera · Yolcu</Kicker>
          <h1 className="dnd-display">Yolcu ortaya çıktı.</h1>
          <p className="dnd-serif">Seçtiğin nitelikler, beceriler ve ekipmanlar kurallara göre mühürlendi. Dünya ilk sözünü bekliyor.</p>
        </div>
        <div className="reveal-card">
          <div className="portrait-empty" aria-label="Portre alanı boş">
            <ScrollText size={25} />
            <Kicker>Henüz bir suret yok</Kicker>
            <span>Yol boyunca yüzün hatırlanacak.</span>
          </div>
          <div className="reveal-data">
            <div className="reveal-top">
              <div>
                <Kicker>Karakter</Kicker>
                <h2 data-testid="reveal-character-name">{character.name}</h2>
                <div className="character-sub">{speciesLabel(character.race)} {classLabel(character.class)} · Seviye {character.level}</div>
              </div>
              <span className="character-badge">LVL {String(character.level).padStart(2, '0')}</span>
            </div>
            {character.origin && (
              <div className="reveal-origin" data-testid="reveal-character-origin">
                <Kicker>Kişisel köken</Kicker>
                <span>{character.origin}</span>
              </div>
            )}
            {(character.origin_feat || character.species_bonus_feat) && (
              <div className="reveal-origin" data-testid="reveal-character-origin-feats">
                <Kicker>Başlangıç hünerleri</Kicker>
                <div className="mt-2 flex flex-wrap gap-2">
                  {character.origin_feat && (
                    <span className="status-pill" data-testid="reveal-background-origin-feat">
                      Geçmiş: {character.origin_feat}
                    </span>
                  )}
                  {character.species_bonus_feat && (
                    <span className="status-pill" data-testid="reveal-species-bonus-feat">
                      Tür: {character.species_bonus_feat}
                    </span>
                  )}
                </div>
              </div>
            )}
            <Rule />
            <div className="reveal-metrics">
              <div><Kicker>Can</Kicker><strong>{character.current_hp} / {character.max_hp}</strong></div>
              <div><Kicker>Zırh</Kicker><strong>{character.armor_class}</strong></div>
              <div><Kicker>Ustalık</Kicker><strong>+{character.proficiency_bonus}</strong></div>
            </div>
            <p className="subtle-text mt-3"><CampaignDate state={state} /></p>
            <div className="reveal-stats">
              <Kicker>Yetenekler</Kicker>
              <div className="stat-strip">
                {abilities.map(([label, value]) => (
                  <div className="stat-box" key={label}>
                    <Kicker>{label}</Kicker>
                    <div className="stat-value">{value}</div>
                  </div>
                ))}
              </div>
            </div>
            <SpellcastingPanel spellcasting={state.spellcasting} />
            <div className="reveal-skills">
              <Kicker>Usta olunan beceriler</Kicker>
              <div className="mt-3 flex flex-wrap gap-2">
                {character.proficient_skills.length
                  ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skill}</span>)
                  : <span className="subtle-text">Henüz bir beceride ustalaşmadın.</span>}
              </div>
            </div>
            {character.species_bonus_skills?.length ? (
              <div className="reveal-skills" data-testid="reveal-species-bonus-skills">
                <Kicker>Tür becerileri</Kicker>
                <div className="mt-3 flex flex-wrap gap-2">
                  {character.species_bonus_skills.map((skill) => (
                    <span className="status-pill" key={skill}>{skill}</span>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="reveal-actions">
              <span>Bu yolculukta sana adın, geçmişin ve yeteneklerin eşlik edecek.</span>
              <button type="button" className="dnd-button" onClick={onContinue} data-testid="button-continue-adventure">
                Macerayı aç <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

function StateSkeleton() {
  return <div className="state-column" data-testid="state-loading">{[1, 2].map((panel) => <div className="state-panel" key={panel}><div className="dnd-skeleton h-3 w-24" /><div className="dnd-skeleton mt-4 h-7 w-40" /><div className="dnd-skeleton mt-3 h-16 w-full" /><div className="dnd-skeleton mt-3 h-8 w-full" /></div>)}</div>;
}

function actionFingerprint(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return (hash >>> 0).toString(36);
}

type CombatRequestContext = { combat_id?: string; combat_round?: number; combat_turn_index?: number };

function stableTurnActionId(scope: string, signature: string, context: CombatRequestContext = {}) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  const fingerprint = actionFingerprint(signature);
  try {
    const pending = JSON.parse(window.sessionStorage.getItem(storageKey) ?? '{}') as Record<string, unknown>;
    const existing = pending[fingerprint];
    if (typeof existing === 'string') return existing;
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    const actionId = window.crypto.randomUUID();
    pending[fingerprint] = actionId;
    window.sessionStorage.setItem(`ai-dnd-turn-context:${scope}:${actionId}`, JSON.stringify(context));
    window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
    return actionId;
  } catch {
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    return window.crypto.randomUUID();
  }
}

function storedTurnContext(scope: string, actionId: string): CombatRequestContext {
  try {
    return JSON.parse(window.sessionStorage.getItem(`ai-dnd-turn-context:${scope}:${actionId}`) ?? '{}');
  } catch {
    return {};
  }
}

function clearPendingTurnAction(scope: string, actionId: string) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  try {
    window.sessionStorage.removeItem(`ai-dnd-turn-context:${scope}:${actionId}`);
    const pending = JSON.parse(window.sessionStorage.getItem(storageKey) ?? '{}') as Record<string, unknown>;
    for (const [fingerprint, pendingId] of Object.entries(pending)) {
      if (pendingId === actionId) delete pending[fingerprint];
    }
    if (Object.keys(pending).length) {
      window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
    } else {
      window.sessionStorage.removeItem(storageKey);
    }
  } catch {
    // The server receipt remains authoritative if browser storage is unavailable.
  }
}

export default function GameBrowser() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState('');
  const [campaignId, setCampaignId] = useState('');
  const [phase, setPhase] = useState<'opening' | 'library' | 'creation' | 'reveal' | 'adventure'>('opening');
  const [creationReturnPhase, setCreationReturnPhase] = useState<'opening' | 'library'>('opening');
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [combatEntries, setCombatEntries] = useState<CombatLogEntry[]>([]);
  const [combatEndNotice, setCombatEndNotice] = useState<string | null>(null);
  const [combatTargetId, setCombatTargetId] = useState('');
  const [conversationTargetId, setConversationTargetId] = useState('');
  const [message, setMessage] = useState('');
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('do');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [activeTab, setActiveTab] = useState<WorldTab>('world');
  const [locationChanged, setLocationChanged] = useState(false);
  const [resumingCampaignId, setResumingCampaignId] = useState<string | null>(null);
  const createCampaign = useCreateCampaign();
  const resumeCampaign = useResumeCampaign();
  const saveCampaign = useSaveCampaign();
  const campaignsQuery = useGetCampaigns({
    query: {
      queryKey: getGetCampaignsQueryKey(),
      retry: false,
      refetchOnWindowFocus: true,
    },
  });
  const characterOptionsQuery = useGetCharacterOptions({
    query: {
      queryKey: getGetCharacterOptionsQueryKey(),
      enabled: phase === 'creation',
      retry: false,
    },
  });
  const characterCatalogQuery = useGetCharacterCreationCatalog({
    query: {
      queryKey: getGetCharacterCreationCatalogQueryKey(),
      enabled: phase === 'creation',
      retry: false,
    },
  });
  const campaignStartOptionsQuery = useGetCampaignStartOptions({
    query: {
      queryKey: getGetCampaignStartOptionsQueryKey(),
      enabled: phase === 'creation' || phase === 'library',
      retry: false,
    },
  });
  const playTurn = usePlayGameTurn();
  const pendingTurnRef = useRef<{ signature: string; actionId: string } | null>(null);
  const activeSessionRef = useRef(sessionId);
  activeSessionRef.current = sessionId;
  const resolveAmbientEventAction = useResolveAmbientEventAction();
  const stateQuery = useGetGameSessionState(sessionId, { query: { enabled: Boolean(sessionId), queryKey: getGetGameSessionStateQueryKey(sessionId), retry: false } });
  const state = stateQuery.data;
  const [ambientActionResult, setAmbientActionResult] = useState<AmbientEventResult | null>(null);
  const [ambientActionRequest, setAmbientActionRequest] = useState<AmbientEventActionRequest | null>(null);
  const [ambientActionError, setAmbientActionError] = useState(false);
  const pendingAmbientActionRef = useRef<AmbientEventActionRequest | null>(null);
  const storyScrollRef = useRef<HTMLDivElement>(null);
  const wasAtBottom = useRef(true);
  const previousLocation = useRef<string>('');
  const previousCombatActive = useRef<boolean | null>(null);

  useEffect(() => {
    pendingAmbientActionRef.current = null;
    setAmbientActionRequest(null);
    setAmbientActionResult(null);
    setAmbientActionError(false);
  }, [sessionId, state?.scene?.ambient_event?.instance_id]);

  useEffect(() => {
    setCombatEndNotice(null);
    setCombatTargetId('');
    if (!sessionId) { setEntries([]); return; }
    try {
      const stored = JSON.parse(window.localStorage.getItem(`${TRANSCRIPT_KEY}${sessionId}`) ?? '[]') as unknown;
      const restored = Array.isArray(stored) ? stored.flatMap((entry): TranscriptEntry[] => {
        if (!entry || typeof entry !== 'object') return [];
        const candidate = entry as { kind?: unknown; text?: unknown };
        if ((candidate.kind !== 'player' && candidate.kind !== 'narration') || typeof candidate.text !== 'string') return [];
        return [{ kind: candidate.kind, text: candidate.text }];
      }) : [];
      setEntries(restored);
    } catch { setEntries([]); }
  }, [sessionId]);

  useEffect(() => {
    if (!state) return;
    const active = Boolean(state.combat.active);
    if (active) {
      setActiveTab('combat');
      setInteractionMode('do');
      setConversationTargetId('');
    }
    else if (previousCombatActive.current === true) setActiveTab('world');
    previousCombatActive.current = active;
  }, [state?.combat.active]);

  useEffect(() => {
    setConversationTargetId((current) => (
      state?.scene?.npcs.some((npc) => npc.id === current) ? current : ''
    ));
  }, [state?.scene]);

  useEffect(() => {
    if (!state || previousLocation.current === '') { if (state) previousLocation.current = state.location; return; }
    if (previousLocation.current !== state.location) {
      previousLocation.current = state.location;
      setLocationChanged(true);
      const timer = window.setTimeout(() => setLocationChanged(false), 1200);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [state]);

  useEffect(() => {
    if (!sessionId || !stateQuery.isError) return;
    if (statusCode(stateQuery.error) === 404) {
      setSessionId('');
      setConversationTargetId('');
      setInteractionMode('do');
      setPhase('library');
      setNotice({ tone: 'warning', title: 'Oturum yeniden açılmalı', detail: 'Kayıtlı macerayı defterden seçerek güvenli biçimde sürdürebilirsin.' });
    }
  }, [sessionId, stateQuery.error, stateQuery.isError]);

  useEffect(() => {
    if (!entries.length || !storyScrollRef.current || !wasAtBottom.current) return;
    storyScrollRef.current.scrollTop = storyScrollRef.current.scrollHeight;
  }, [entries]);

  const handleStoryScroll = () => {
    const node = storyScrollRef.current;
    if (!node) return;
    wasAtBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
  };

  const reset = () => {
    setSessionId('');
    setCampaignId('');
    setPhase('opening');
    setEntries([]);
    setCombatEntries([]);
    setCombatEndNotice(null);
    setConversationTargetId('');
    setInteractionMode('do');
    setMessage('');
    setNotice(null);
    setResumingCampaignId(null);
    setDrawer(null);
    setActiveTab('world');
    previousCombatActive.current = null;
  };

  const handleCreate = () => {
    setNotice(null);
    setCreationReturnPhase(phase === 'library' ? 'library' : 'opening');
    setPhase('creation');
  };

  const handleCreateCharacter = (
    character: CharacterCreateInput,
    campaignStart: CampaignStartSelection,
    deathMode: 'NORMAL' | 'PERMADEATH' | 'IRONMAN',
  ) => {
    setNotice(null);
    createCampaign.mutate({
      data: { character, campaign_start: campaignStart, death_mode: deathMode },
    }, {
      onSuccess: (created) => {
        setCampaignId(created.campaign_id);
        window.localStorage.setItem(LAST_CAMPAIGN_KEY, created.campaign_id);
        queryClient.setQueryData(getGetGameSessionStateQueryKey(created.session_id), created.state);
        window.localStorage.removeItem(`${TRANSCRIPT_KEY}${created.session_id}`);
        setEntries([]);
        setCombatEntries([]);
        setCombatEndNotice(null);
        setInteractionMode('do');
        setConversationTargetId('');
        setActiveTab('world');
        previousCombatActive.current = null;
        setSessionId(created.session_id);
        setPhase('reveal');
        primeGateSound();
        playGateSound('success');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => setNotice({
        tone: 'error',
        title: 'Kampanya oluşturulamadı',
        detail: statusCode(error) === 422
          ? 'İsim, ırk ya da sınıfını yeniden gözden geçir.'
          : friendlyError(error, 'Dünya şu an yanıt vermiyor.'),
      }),
    });
  };

  const handleContinue = () => {
    setNotice(null);
    setPhase('library');
    void campaignsQuery.refetch();
  };

  const handleRevealContinue = () => {
    const opening = state?.scene?.opening;
    if (typeof opening === 'string' && opening.trim()) {
      const transcript: TranscriptEntry[] = [{ kind: 'narration', text: opening }];
      setEntries(transcript);
      if (sessionId) {
        window.localStorage.setItem(
          `${TRANSCRIPT_KEY}${sessionId}`,
          JSON.stringify(transcript),
        );
      }
    }
    setPhase('adventure');
  };

  const handleResume = (selectedCampaignId: string) => {
    setNotice(null);
    setResumingCampaignId(selectedCampaignId);
    resumeCampaign.mutate({ campaignId: selectedCampaignId }, {
      onSuccess: (resumed) => {
        const opening = resumed.state.scene?.opening;
        const transcript: TranscriptEntry[] = [
          ...(typeof opening === 'string' && opening.trim()
            ? [{ kind: 'narration' as const, text: opening }]
            : []),
          ...resumed.history.flatMap((entry: CampaignHistoryEntry) => [
          { kind: 'player' as const, text: entry.player_message },
          { kind: 'narration' as const, text: entry.narration },
          ]),
        ];
        setCampaignId(resumed.campaign_id);
        window.localStorage.setItem(LAST_CAMPAIGN_KEY, resumed.campaign_id);
        window.localStorage.setItem(`${TRANSCRIPT_KEY}${resumed.session_id}`, JSON.stringify(transcript));
        setEntries(transcript);
        setCombatEntries(mergeCombatHistory(resumed.combat_history));
        setCombatEndNotice(null);
        setInteractionMode('do');
        setConversationTargetId('');
        setActiveTab('world');
        previousCombatActive.current = null;
        setSessionId(resumed.session_id);
        setMessage('');
        setPhase('adventure');
        setResumingCampaignId(null);
        queryClient.setQueryData(getGetGameSessionStateQueryKey(resumed.session_id), resumed.state);
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => {
        setResumingCampaignId(null);
        setNotice({ tone: 'error', title: 'Macera açılamadı', detail: friendlyError(error, 'Bu macera güvenli biçimde yüklenemedi.') });
      },
    });
  };

  const handleSave = () => {
    if (!campaignId || saveCampaign.isPending) return;
    saveCampaign.mutate({ campaignId }, {
      onSuccess: () => {
        setNotice({ tone: 'success', title: 'Macera kaydedildi', detail: 'Yolculuğunun izleri güvenle saklandı.' });
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => setNotice({ tone: 'error', title: 'Kayıt tamamlanamadı', detail: friendlyError(error, 'Macera güvenli biçimde kaydedilemedi.') }),
    });
  };

  const submitAmbientEventAction = (request: AmbientEventActionRequest) => {
    pendingAmbientActionRef.current = request;
    setAmbientActionRequest(request);
    setAmbientActionError(false);
    resolveAmbientEventAction.mutate(
      {
        sessionId: request.sessionId,
        eventInstanceId: request.eventInstanceId,
        data: request.data,
      },
      {
        onSuccess: (response) => {
          queryClient.setQueryData(
            getGetGameSessionStateQueryKey(request.sessionId),
            response.state,
          );
          if (pendingAmbientActionRef.current === request) {
            pendingAmbientActionRef.current = null;
            setAmbientActionResult(response.result);
            setAmbientActionRequest(null);
            setAmbientActionError(false);
          }
        },
        onError: () => {
          if (pendingAmbientActionRef.current === request) {
            setAmbientActionError(true);
          }
        },
      },
    );
  };

  const handleAmbientAction = (action: AmbientEventActionInputAction) => {
    const event = state?.scene?.ambient_event;
    if (
      !sessionId
      || !event
      || !state?.scene
      || pendingAmbientActionRef.current
      || !isActiveBlueAmbientEvent(event, state.scene.referents)
    ) {
      return;
    }

    const request = createAmbientEventActionRequest(
      sessionId,
      event.instance_id,
      action,
    );
    setAmbientActionResult(null);
    submitAmbientEventAction(request);
  };

  const retryAmbientAction = () => {
    const request = pendingAmbientActionRef.current;
    if (!request || resolveAmbientEventAction.isPending) return;
    submitAmbientEventAction(request);
  };

  const submitTurn = (
    text: string,
    combatAction?: CombatActionInput,
    mode: InteractionMode = interactionMode,
  ) => {
    const trimmed = text.trim();
    if (!sessionId || playTurn.isPending || trimmed.length < 1 || trimmed.length > 4000) return;
    setNotice(null);
    const metadata = getTurnInteractionMetadata(
      state, mode, conversationTargetId, combatTargetId, Boolean(combatAction),
    );
    const targetId = metadata.target_id;
    const actionScope = campaignId || sessionId;
    const signature = JSON.stringify([actionScope, trimmed, metadata.interaction_mode, targetId, combatAction ?? null]);
    const actionId = pendingTurnRef.current?.signature === signature
      ? pendingTurnRef.current.actionId
      : stableTurnActionId(actionScope, signature, state?.combat.active && state.combat.combat_id ? {
        combat_id: state.combat.combat_id, combat_round: state.combat.round,
        combat_turn_index: state.combat.current_turn_index,
      } : {});
    pendingTurnRef.current = { signature, actionId };
    playTurn.mutate({
      sessionId,
      data: {
        message: trimmed,
        interaction_mode: metadata.interaction_mode,
        action_id: actionId,
        ...(combatAction ? { combat_action: combatAction } : {}),
        ...storedTurnContext(actionScope, actionId),
        ...(targetId ? { target_id: targetId } : {}),
      },
    }, {
      onSuccess: (result) => {
        const stillVisible = activeSessionRef.current === sessionId;
        if (pendingTurnRef.current?.actionId === actionId) pendingTurnRef.current = null;
        clearPendingTurnAction(actionScope, actionId);
        const next = [
          ...entries,
          { kind: 'player' as const, text: trimmed },
          {
            kind: 'narration' as const,
            text: result.narration,
            skillCheckResult: result.skill_check_result ?? undefined,
          },
        ];
        if (stillVisible) setEntries(next);
        window.localStorage.setItem(
          `${TRANSCRIPT_KEY}${sessionId}`,
          JSON.stringify(next.map(({ kind, text }) => ({ kind, text }))),
        );
        const combatResult = result.combat_result;
        const combatHistoryEntry = result.combat_history_entry;
        if (stillVisible && combatHistoryEntry) {
          setCombatEntries((current) => mergeCombatHistory(
            [combatHistoryEntry],
            current,
          ));
        }
        if (stillVisible && combatResult) {
          if (combatResult.combat_ended) {
            const endReason = combatResult.end_reason;
            setCombatEndNotice(
              endReason === 'target_defeated'
                ? 'Rakip etkisiz hale getirildi.'
                : endReason === 'player_defeated'
                  ? 'Karakter bilinç kaybetti.'
                  : 'Çatışma sona erdi.',
            );
          } else {
            setCombatEndNotice(null);
          }
          if (combatResult.outcome !== 'enemy_turn_resolved' || combatResult.combat_ended) {
            setCombatTargetId('');
          }
        } else if (stillVisible) {
          setCombatEndNotice(null);
        }
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
        if (stillVisible) setConversationTargetId('');
        const outcomeMessages = (result.quest_outcomes ?? []).map((outcome) => {
          const quest = result.state.quests.find((item) => item.quest_id === outcome.quest_id);
          const objective = quest?.objectives.find((item) => item.objective_id === outcome.objective_id);
          const transition = {
            accepted: 'görev kabul edildi',
            objective_progress: 'görev hedefinde ilerleme kaydedildi',
            objective_completed: 'görev hedefi tamamlandı',
            completed: 'görev tamamlandı',
            cancelled: 'görev iptal edildi',
          }[outcome.transition] ?? 'görev durumu güncellendi';
          return `${quest?.title ?? 'Görev'}: ${transition}${objective ? ` — ${objective.description}` : ''}.`;
        });
        if (stillVisible && outcomeMessages.length) {
          setNotice({
            tone: 'success',
            title: 'Görev güncellendi',
            detail: outcomeMessages.join(' '),
          });
        }
        if (stillVisible) setMessage('');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => {
        if (activeSessionRef.current !== sessionId) {
          if (pendingTurnRef.current?.actionId === actionId) pendingTurnRef.current = null;
          return;
        }
        if ([400, 409, 422].includes(statusCode(error) ?? 0)) {
          pendingTurnRef.current = null;
          clearPendingTurnAction(actionScope, actionId);
          void queryClient.invalidateQueries({ queryKey: getGetGameSessionStateQueryKey(sessionId) });
        }
        setNotice({ tone: 'error', title: statusCode(error) === 503 ? 'Dünya şu an sessiz' : 'Hamle sonuçlanamadı', detail: friendlyError(error, 'Bu hamleyi şu haliyle gerçekleştiremiyorsun.') });
      },
    });
  };

  const sessionLabel = useMemo(() => campaignId ? 'Yolculuk sürüyor' : 'Yeni yolculuk', [campaignId]);
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitTurn(message, undefined, interactionMode);
  };
  if (phase === 'library') return <CampaignLibrary campaigns={campaignsQuery.data} locationCatalog={campaignStartOptionsQuery.data} loading={campaignsQuery.isLoading} error={campaignsQuery.error} resuming={resumeCampaign.isPending} resumingCampaignId={resumingCampaignId} notice={notice} onBack={() => { setPhase('opening'); setNotice(null); }} onNew={handleCreate} onResume={handleResume} onRetry={() => void campaignsQuery.refetch()} onDeleted={deletedId => { if (deletedId === campaignId) { setSessionId(''); setCampaignId(''); setEntries([]); setCombatEntries([]); } }} />;
  if (phase === 'creation') return (
    <CharacterCreationScreen
      options={characterOptionsQuery.data}
      catalog={characterCatalogQuery.data}
      startOptions={campaignStartOptionsQuery.data}
      loadingOptions={characterOptionsQuery.isLoading || characterCatalogQuery.isLoading}
      loadingStartOptions={campaignStartOptionsQuery.isLoading}
      optionsError={characterOptionsQuery.error || characterCatalogQuery.error}
      startOptionsError={campaignStartOptionsQuery.error}
      creating={createCampaign.isPending}
      notice={notice}
      onBack={() => { setPhase(creationReturnPhase); setNotice(null); }}
      onCreate={handleCreateCharacter}
      onRetryOptions={() => {
        void characterOptionsQuery.refetch();
        void characterCatalogQuery.refetch();
      }}
      onRetryStartOptions={() => void campaignStartOptionsQuery.refetch()}
    />
  );
  if (!sessionId || phase === 'opening') return <OpeningScreen onCreate={handleCreate} onContinue={handleContinue} creating={createCampaign.isPending} notice={notice} loadingCampaigns={campaignsQuery.isLoading} hasCampaigns={Boolean(campaignsQuery.data?.length)} showNoCampaigns={!campaignsQuery.isLoading && !campaignsQuery.error} />;
  if (phase === 'reveal' && state) return <CharacterReveal state={state} onContinue={handleRevealContinue} onBack={() => { setPhase('opening'); setSessionId(''); }} />;
  return (
    <EnvironmentThemeProvider state={state}>
      <div className="dnd-app" data-testid="app-session">
        {state && <SessionHeader state={state} campaignId={campaignId} onSave={handleSave} saving={saveCampaign.isPending} onReset={reset} onDrawer={setDrawer} onOpenCombat={() => { setActiveTab('combat'); setDrawer('world'); }} />}
        <main className="app-main workspace-grid">
          {stateQuery.isLoading ? (
            <>
              <div className="workspace-story">
                <div className="dnd-card p-7" data-testid="story-loading">
                  <div className="dnd-skeleton h-4 w-36" />
                  <div className="dnd-skeleton mt-6 h-28 w-full" />
                  <div className="dnd-skeleton mt-4 h-24 w-4/5" />
                </div>
              </div>
              <StateSkeleton />
              <StateSkeleton />
            </>
          ) : stateQuery.isError ? (
            <div className="dnd-card p-7 workspace-error" data-testid="error-session-state">
              <div className="flex items-center gap-2 text-[#dca49b]">
                <AlertTriangle size={16} /> {statusCode(stateQuery.error) === 503 ? 'Dünya şu an sessiz.' : 'Yolculuğun izleri görünmüyor.'}
              </div>
              <p className="dnd-serif mt-3 text-lg text-[#a99a80]">{friendlyError(stateQuery.error, 'Dünya şu an görünmüyor.')}</p>
              <button className="dnd-button secondary mt-5" type="button" data-testid="button-retry-session-state" onClick={() => void stateQuery.refetch()}>
                <RefreshCw size={14} /> Tekrar dene
              </button>
            </div>
          ) : state ? (
            <>
              <LeftColumn state={state} />
              <StoryColumn
                state={state}
                entries={entries}
                message={message}
                setMessage={setMessage}
                interactionMode={interactionMode}
                setInteractionMode={setInteractionMode}
                conversationTargetId={conversationTargetId}
                setConversationTargetId={setConversationTargetId}
                onEndConversation={() => submitTurn('Konuşmayı bitiriyorum.', undefined, 'do')}
                onSubmit={handleSubmit}
                onExplorationCommand={(text) => submitTurn(text, undefined, 'do')}
                onEconomyCommand={(text, command) => submitTurn(text, command, 'do')}
                sending={playTurn.isPending}
                notice={notice}
                scrollRef={storyScrollRef}
                onScroll={handleStoryScroll}
                locationChanged={locationChanged}
                combatEndNotice={combatEndNotice}
                combatTargetId={combatTargetId}
                setCombatTargetId={setCombatTargetId}
                ambientActionResult={ambientActionResult}
                ambientActionRequest={ambientActionRequest}
                ambientActionSending={resolveAmbientEventAction.isPending}
                ambientActionError={ambientActionError}
                onAmbientAction={handleAmbientAction}
                onRetryAmbientAction={retryAmbientAction}
              />
              <WorldTabs state={state} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} />
            </>
          ) : <div className="empty-line" data-testid="empty-session-state">Bu günlük henüz bir durum döndürmedi.</div>}
        </main>
        {state && <DrawerSheet drawer={drawer} state={state} onClose={() => setDrawer(null)} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} />}
        <div className="dnd-shell pb-8 text-right font-mono text-[9px] tracking-[.1em] text-[#695b48]" data-testid="text-session-label">
          {sessionLabel} · sahnenin izleri yol boyunca korunur
        </div>
      </div>
    </EnvironmentThemeProvider>
  );
}