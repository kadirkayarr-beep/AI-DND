import { CombatStatusStrip, CombatTransitionBanner } from '@/components/combat-status-strip';
import { showsCounter } from '@/lib/play-panels';
import { runningQuestCount } from '@/lib/quest-counter';
import { PrimalKnowledgeControl } from '@/components/primal-knowledge-controls';
import { createPrimalKnowledgeIntent, primalKnowledgeAvailable } from '@/lib/primal-knowledge';
import { TacticalMindControl, tacticalMindAvailable } from '@/components/fighter-controls';
import { StartingEquipmentNotice } from '@/components/starting-equipment-notice';
import { CharacterPanel, InventoryPanel, PurseLine, StoredProgressionChoices } from '@/components/character-panel';
import { LevelUpControls, levelUpEarned, type LevelUpRequest } from '@/components/level-up-controls';
import { ECONOMIC_MESSAGES, EconomicOfferCard, EconomicPrepareControls, ShopControls, shopProbeKey } from '@/components/shop-panel';
import { reconcileState, useActionLifetime, RETRY_MESSAGE, ReconciliationError } from '@/lib/action-reconciliation';
import { closePending, createIntentKey, readPending, resumePending, speciesActionUnresolved, unresolvedElsewhere } from '@/lib/pending-action';
import { askServer, findUnresolvedOnServer, modelRefusalLine, RecoveryTimeoutError, settlePending, unresolvedActionFrom, type RecoveryApi, type ServerVerdict } from '@/lib/action-recovery';
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CombatPanel, type CombatLogEntry } from '@/components/combat-panel';
import { DeathEndNotice, DeathRecoveryControls } from '@/components/death-recovery-controls';
import { mergeCombatHistory } from '@/lib/combat-history';
import { combatErrorMessage, retainCombatTarget } from '@/lib/combat-ui-contract';
import { ExplorationControls } from '@/components/exploration-controls';
import { CourtyardHelp } from '@/components/courtyard-help';
import { clippedControlOverflow, focusReturnTarget, keyboardInset, transcriptFollowsBottom } from '@/lib/play-viewport';
import { removeAdvisoryCache, writeAdvisoryCache } from '@/lib/advisory-cache';
import {
  AmbientEventActionPanel,
  ambientFollowUpMove,
  createAmbientEventActionRequest,
  findPersistedAmbientEventResult,
  isActiveBlueAmbientEvent,
  type AmbientEventActionRequest,
} from '@/components/ambient-event-actions';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
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
  getGameSessionState,
  useCreateCampaign,
  useGetGameHealth,
  useGetCampaigns,
  useGetCampaignStartOptions,
  useGetCharacterOptions,
  useGetCharacterCreationCatalog,
  useGetGameSessionState,
  useAcceptGameQuest,
  useCancelGameQuest,
  playGameTurn,
  applyGameSessionLevelUp,
  undoGameTurn,
  getCampaign,
  getGameActionStatus,
  abandonGameAction,
  getUnresolvedGameAction,
  useResolveAmbientEventAction,
  useResumeCampaign,
  useSaveCampaign,
} from '@workspace/api-client-react';
import { ApiError, currentAuthEpoch } from '@workspace/api-client-react/custom-fetch';
import type { EconomicAction, TurnOutcome } from '@workspace/api-client-react';
import { summarizeTurnOutcome } from '@/lib/turn-outcome';
import { LastTurnBar } from '@/components/last-turn-bar';
import { NoticeBanner, type Notice, type RecoveryState } from '@/components/notice-banner';
import { historyToEntries } from '@/lib/transcript-history';
import { resumeComposerMode } from '@/lib/resume-mode';
import { accountWriteAllowed, currentAccountOwner } from '@/lib/account-session';
import { applyGameState, gameStateScope, nextRevision } from '@/lib/game-state-gate';
import { ActionDeadlineError, startDeadline, withActionDeadline } from '@/lib/action-deadline';
import { gatedStateRead, stateStructuralSharing } from '@/lib/state-envelope';
import { QuestJournalSection } from '@/components/quest-journal-section';
import { AdventureJournalSection } from '@/components/adventure-journal-section';
import type { AmbientEventActionInputAction, AmbientEventResult, CampaignDetail, CampaignStartSelection, CharacterCreateInput, GameCharacter, GameDoor, GameNpc, GameState } from '@workspace/api-client-react';
import { Transcript, type TranscriptEntry } from '@/components/campaign-transcript';
import { ReadingSettings } from '@/components/reading-settings';
import { readReadingPreferences, writeReadingPreferences, type ReadingPreferences } from '@/lib/reading-preferences';
import { EnvironmentThemeProvider } from '@/components/environment-theme';
import { CampaignLibrary } from '@/components/campaign-library';
import { CharacterCreationScreen } from '@/components/character-creation-screen';
import { ActionEconomyPanel } from '@/components/action-economy-panel';
import { SpellcastingPanel } from '@/components/spellcasting-panel';
import { CampaignContextPanel, CampaignDate } from '@/components/campaign-context-panel';
import { currentSceneContext, classLabel, speciesLabel } from '@/lib/campaign-presentation';
import { OuroborosMark } from '@/components/ouroboros-mark';
import { gateSoundMuted, gateSoundVolume, playGateSound, primeGateSound, setGateSoundMuted, setGateSoundVolume } from '@/lib/gate-sound';
import '@/components/cinematic-gate.css';
import '@/components/unwritten-play.css';
import type { CombatActionInput } from '@workspace/api-client-react';
import { getContextualActionSuggestions, getTurnInteractionMetadata, type InteractionMode } from '@/lib/action-suggestions';
import classPortraitSheet from '@assets/generated_images/ai-dnd-class-portraits.jpg';
import speciesPortraitSheet from '@assets/generated_images/ai-dnd-species-portraits.jpg';
import halfElfPortrait from '@assets/generated_images/ai-dnd-half-elf-portrait.png';

const LAST_CAMPAIGN_KEY = 'ai-dnd-last-selected-campaign-id';
const TRANSCRIPT_KEY = 'ai-dnd-transcript-';

const RECOVERY_API: RecoveryApi = {
  status: getGameActionStatus, abandon: abandonGameAction, unresolved: getUnresolvedGameAction,
};
// Without a resolved Clerk owner (local fixture) the slot still separates campaigns; the server decides access.
const LOCAL_OWNER = 'local';
const PENDING_TURN_NOTICE: Notice = {
  tone: 'warning',
  title: 'Önceki hamle henüz doğrulanamadı',
  detail: 'Yeni hamle göndermeden önce önceki hamleyi aynı kimlikle yeniden dene. Yazdığın metin taslakta korunuyor.',
};type Drawer = 'character' | 'world' | null;
type WorldTab = 'world' | 'npcs' | 'journal' | 'combat';

function statusCode(error: unknown) {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return candidate.status ?? candidate.statusCode ?? candidate.response?.status;
}

function friendlyError(error: unknown, fallback: string) {
  const combatMessage = combatErrorMessage(error);
  if (combatMessage) return combatMessage;
  const code = statusCode(error);
  if (code === 401) return 'Kimlik doğrulaması gerekli.';
  if (code === 404) return 'Bu macera bulunamadı.';
  if (code === 422) return 'Bu söz şimdilik yankı bulmadı. 1–4000 karakter arasında yeniden dene.';
  if (code === 503) return modelRefusalLine(error) ?? 'Dünya şu an sessiz.';
  if (typeof code === 'number' && code >= 500) return 'Sunucuda bir aksaklık oldu; yeniden dene.';
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
    <main className="design-preview unwritten-entry" data-testid="app-start">
      <div className="entry-ribbon"><span className="ribbon-dot" /><strong>GERÇEK OYUN</strong><span>/</span><span>{import.meta.env.VITE_AI_DND_LOCAL_PLAY === '1' ? 'Yerel oyun; kampanyaların bu bilgisayarda kayıtlı kalır' : 'Hesabınla giriş yap; kampanyaların kayıtlı kalır'}</span></div>
      <header className="entry-header">
        <div className="entry-brand"><span className="entry-brand-icon"><OuroborosMark /></span><span><strong>UNWRITTEN</strong><small>GERÇEK OYUN</small></span></div>
        <GateSoundControl />
      </header>
      <section className="entry-page">
        <div className="entry-main">
          <div className="entry-art">
            <img className="ouroboros-art" src={`${import.meta.env.BASE_URL}ouroboros-approved.jpg`} alt="UNWRITTEN amblemi: zümrüt ve altın renkli dairesel ejderha" data-testid="image-approved-ouroboros" />
          </div>
          <div className="entry-copy">
            <h1>UNWRITTEN</h1>
            <p className="entry-lede">Bir hikâyeye sessizce adım at.</p>
            <nav className="entry-actions" aria-label="Kampanya işlemleri">
              <button className="button-primary" type="button" data-testid="button-continue-session" disabled={loadingCampaigns} onClick={() => { primeGateSound(); playGateSound('menu'); onContinue(); }}>
                {loadingCampaigns ? <RefreshCw size={16} className="animate-spin" aria-hidden="true" /> : <BookOpen size={16} aria-hidden="true" />}
                Maceraya devam et <ArrowRight size={15} aria-hidden="true" />
              </button>
              <button className="button-quiet new-adventure-action" type="button" data-testid="button-create-session" disabled={creating} onClick={() => { primeGateSound(); playGateSound('menu'); onCreate(); }}>
                <Sparkles size={15} aria-hidden="true" />{creating ? 'Dünya kuruluyor' : 'Yeni macera'}
              </button>
            </nav>
            {showNoCampaigns && !hasCampaigns && <div className="continue-note" data-testid="text-no-session">Henüz bir macera yok. İlk yolculuğunu başlat.</div>}
            {notice && <div className="entry-notice"><NoticeBanner notice={notice} /></div>}
            <div className="entry-safety" role="note" data-testid="status-real-game-safety">
              <span className="safety-mark" aria-hidden="true">i</span>
              <p>Bu giriş ekranında kayıtlı kampanyanı sürdürebilir veya yeni macera oluşturabilirsin. İlerlemen hesabındaki kampanyaya kaydedilir.</p>
            </div>
          </div>
        </div>
        <aside className="real-entry-card">
          <div className="real-card-mark"><Shield size={17} aria-hidden="true" /></div>
          <div className="real-card-copy"><span className="eyebrow">HESABIN VE KAMPANYALARIN</span><strong>Gerçek oyun, güvenli oturumunla açılır.</strong></div>
          <span className="entry-health"><EngineHealth /></span>
        </aside>
      </section>
    </main>
  );
}

function WorldPanel({ state }: { state: GameState }) {
  return <CampaignContextPanel state={state} />;
}

function SceneIdeas({ state, recentText, sending, onDraft }: {
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

type RailPanelId = 'character' | 'world' | 'npcs' | 'journal' | 'combat';
const PREVIOUS_INTERACTION_MODE: Record<InteractionMode, InteractionMode> = { do: 'ask_dm', say: 'do', ask_dm: 'say' };
const NEXT_INTERACTION_MODE: Record<InteractionMode, InteractionMode> = { do: 'say', say: 'ask_dm', ask_dm: 'do' };

function RailSummary({ panel, state }: { panel: RailPanelId; state: GameState }) {
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
    <span>Süren görevler {runningQuestCount(state)}</span>
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

function LeftColumn({ state, decisionScope = '', conversionBlocked = true, onCommand }: { state: GameState; decisionScope?: string; conversionBlocked?: boolean; onCommand?: (message: string, command: CombatActionInput) => void }) {
  return <aside className="state-column workspace-left" data-testid="panel-character-column"><CharacterPanel character={state.character} walletTotalCp={state.wallet?.total_cp ?? null} /><SpellcastingPanel spellcasting={state.spellcasting} decisionScope={JSON.stringify([decisionScope, state.combat?.combat_id, state.combat?.round, state.combat?.current_turn_index, state.combat?.current_actor_id, state.combat?.active])} conversionBlocked={conversionBlocked} onCommand={onCommand} /><InventoryPanel items={state.inventory} /></aside>;
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
      />
      <AdventureJournalSection adventure={state.adventure} />
    </section>
  );
}

function WorldTabs({ state, activeTab, setActiveTab, combatEntries, sessionId, campaignId, sending, onExplorationCommand, onDraft, onSetCombatTarget }: { state: GameState; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string; campaignId: string; sending: boolean; onExplorationCommand: (message: string) => void; onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void; onSetCombatTarget: (targetId: string) => void }) {
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

function StoryColumn({
  state,
  entries,
  readingPreferences,
  setReadingPreferences,
  composerOpen,
  setComposerOpen,
  message,
  setMessage,
  interactionMode,
  setInteractionMode,
  conversationTargetId,
  setConversationTargetId,
  onEndConversation,
  onNewAdventure,
  onDeathMove,
  sessionId,
  campaignId,
  primalKnowledgeOptIn,
  onPrimalKnowledgeChange,
  tacticalMindOptIn,
  onTacticalMindChange,
  onSubmit,
  onKeyboardSubmit,
  onEconomyCommand,
  decisionScope,
  sending,
  notice,
  scrollRef,
  onScroll,
  resultCue,
  newResponseEntryIndex,
  onJumpToNewResponse,
  combatEndNotice,
  combatStartNotice,
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
  decisionScope: string;
  entries: TranscriptEntry[];
  readingPreferences: ReadingPreferences;
  setReadingPreferences: (next: ReadingPreferences) => void;
  composerOpen: boolean;
  setComposerOpen: (open: boolean) => void;
  message: string;
  setMessage: (value: string) => void;
  interactionMode: InteractionMode;
  setInteractionMode: (value: InteractionMode) => void;
  conversationTargetId: string;
  setConversationTargetId: (value: string) => void;
  onEndConversation: () => void;
  onNewAdventure: () => void;
  onDeathMove: (message: string) => void;
  sessionId: string;
  campaignId: string;
  primalKnowledgeOptIn: boolean;
  onPrimalKnowledgeChange: (checked: boolean) => void;
  tacticalMindOptIn: boolean;
  onTacticalMindChange: (checked: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onKeyboardSubmit: () => void;
  onEconomyCommand: (message: string, command: CombatActionInput) => void;
  sending: boolean;
  notice: Notice | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  resultCue: string;
  newResponseEntryIndex: number | null;
  onJumpToNewResponse: (focusTarget?: boolean) => void;
  combatEndNotice: string | null;
  combatStartNotice: string | null;
  combatTargetId: string;
  setCombatTargetId: (value: string) => void;
  ambientActionResult: AmbientEventResult | null;
  ambientActionRequest: AmbientEventActionRequest | null;
  ambientActionSending: boolean;
  ambientActionError: boolean;
  onAmbientAction: (action: AmbientEventActionInputAction) => void;
  onRetryAmbientAction: () => void;
}) {
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
  const conversationTargets = (state.scene?.npcs ?? []).filter(
    (npc) => typeof npc.id === 'string' && typeof npc.name === 'string' && npc.name.trim().length > 0,
  );
  const currentActor = state.combat.participant_records.find(
    (participant) => participant.id === state.combat.current_actor_id,
  );
  const modePrompt = interactionMode === 'say'
    ? 'Ne söylüyorsun?'
    : interactionMode === 'ask_dm'
      ? 'Anlatıcıya ne sormak istiyorsun?'
      : 'Ne yapmak istiyorsun?';
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const composerTriggerRef = useRef<HTMLButtonElement>(null);
  const wasComposerOpen = useRef(composerOpen);
  const desktopEnterSupported = typeof window !== 'undefined'
    && typeof navigator !== 'undefined'
    && !(window.matchMedia?.('(pointer: coarse)').matches
      || window.matchMedia?.('(max-width: 760px)').matches
      || navigator.maxTouchPoints > 0);
  useEffect(() => {
    if (composerOpen && !wasComposerOpen.current) messageInputRef.current?.focus();
    else if (wasComposerOpen.current) composerTriggerRef.current?.focus({ preventScroll: true });
    wasComposerOpen.current = composerOpen;
  }, [composerOpen]);
  const wasSending = useRef(sending);
  useEffect(() => {
    // The input is disabled while a move is sent, which drops focus; give it back on a keyboard device.
    if (wasSending.current && !sending && desktopEnterSupported && document.activeElement === document.body) {
      messageInputRef.current?.focus({ preventScroll: true });
    }
    wasSending.current = sending;
  }, [sending, desktopEnterSupported]);
  const handleMessageKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    if (window.matchMedia('(pointer: coarse)').matches || window.matchMedia('(max-width: 760px)').matches || navigator.maxTouchPoints > 0) return;
    event.preventDefault();
    if (event.repeat || sending || !message.trim()) return;
    onKeyboardSubmit();
  };
  return (
    <section className="story-column workspace-story" data-testid="panel-story">
      <div className="story-scene-context" role="region" aria-label="Sahne bilgileri" tabIndex={0}>
        <div className="story-heading">
          <div className="story-icon"><Feather size={15} strokeWidth={1.25} /></div>
          <div><Kicker>Anlatıcı</Kicker><div className="story-meta mt-1">Sahnenin sözü burada yankılanır</div></div>
          <div className="ml-auto story-meta hidden sm:block">Tur {state.turn_index}</div>
          <ReadingSettings value={readingPreferences} onChange={setReadingPreferences} />
        </div>
        <CombatStatusStrip combat={state.combat} />
        <ActionEconomyPanel decisionScope={decisionScope} state={state} targetId={combatTargetId} sending={sending} onCommand={onEconomyCommand} />
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
        {combatStartNotice && <CombatTransitionBanner kind="start" text={combatStartNotice} />}
        {combatEndNotice && <CombatTransitionBanner kind="end" text={combatEndNotice} />}
        {state.combat.active && currentActor && currentActor.id !== 'player' && (
          <div className="command-combat-turn-note" role="status" data-testid="status-combat-turn-owner">
            Sıra {currentActor.name}'de. Önce bu anı tamamlayacak bir söz gönder; ardından kendi hamleni anlat.
          </div>
        )}
      </div>
      <Transcript entries={entries} scrollRef={scrollRef} onScroll={onScroll} readingPreferences={readingPreferences} resultCue={resultCue} newResponseEntryIndex={newResponseEntryIndex} onJumpToNewResponse={onJumpToNewResponse} />
      {notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}
      {state.conversation.active && state.conversation.interlocutor && (
          <div className="active-interlocutor" role="status" data-testid="active-interlocutor">
            <MessageCircle size={13} aria-hidden="true" />
            <span>Konuşuyorsun: <strong>{state.conversation.interlocutor.name}</strong></span>
            <button className="action-suggestion" type="button" disabled={sending} onClick={onEndConversation} data-testid="button-end-conversation">Konuşmayı bitir</button>
          </div>
      )}
      <DeathEndNotice state={state} onNewAdventure={onNewAdventure} />
      {state.character.current_hp === 0 && <DeathRecoveryControls state={state} sessionId={sessionId} campaignId={campaignId} onSend={onDeathMove} sending={sending} />}
      <SceneIdeas state={state} recentText={entries.at(-1)?.text ?? ''} sending={sending} onDraft={(text, mode = 'do', targetId) => {
        setInteractionMode(mode);
        setConversationTargetId(mode === 'say' ? targetId ?? '' : '');
        if (state.combat.active && targetId) setCombatTargetId(targetId);
        setMessage(text);
        setComposerOpen(true);
        messageInputRef.current?.focus();
      }} />
      {!composerOpen && <button ref={composerTriggerRef} className="dnd-button turn-open-button" type="button" disabled={sending} data-testid="button-open-composer" onClick={() => setComposerOpen(true)}><Send size={15} aria-hidden="true" /> Hamle yap</button>}
      {composerOpen && <div className="command-box" data-testid="command-box">
        <div className="composer-heading">
          <span>Hamleni anlat</span>
          <button className="composer-close" type="button" disabled={sending} data-testid="button-close-composer" onClick={() => setComposerOpen(false)}>Kapat</button>
        </div>
        <form className="command-form" onSubmit={onSubmit}>
          <div className="command-toolbar">
            <div className="interaction-mode-picker" data-testid="interaction-mode-picker">
              <button type="button" aria-label="Önceki hamle türü" disabled={sending || state.combat.active} onClick={() => setInteractionMode(PREVIOUS_INTERACTION_MODE[interactionMode])}><ChevronLeft size={15} /></button>
              <label className="sr-only" htmlFor="interaction-mode">Hamle türü</label>
              <select id="interaction-mode" value={interactionMode} disabled={sending || state.combat.active} aria-label="Hamle türü" data-testid="select-interaction-mode" onChange={(event) => setInteractionMode(event.target.value as InteractionMode)}>
                <option value="do">Yap</option><option value="say">Söyle</option><option value="ask_dm">Anlatıcıya Sor</option>
              </select>
              <button type="button" aria-label="Sonraki hamle türü" disabled={sending || state.combat.active} onClick={() => setInteractionMode(NEXT_INTERACTION_MODE[interactionMode])}><ChevronRight size={15} /></button>
            </div>
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
            {interactionMode === 'say' && conversationTargets.length > 1 && (
              <label className="command-target-label compact-target" htmlFor="conversation-target-select">
                <span>Konuşma hedefi</span>
                <select id="conversation-target-select" className="command-target-select" value={conversationTargetId} onChange={(event) => setConversationTargetId(event.target.value)} disabled={sending} data-testid="select-conversation-target">
                  <option value="">Sözlerimde belirteceğim</option>
                  {conversationTargets.map((npc) => <option value={npc.id} key={npc.id}>{npc.name}</option>)}
                </select>
              </label>
            )}
            <PrimalKnowledgeControl state={state} mode={interactionMode} targetId={getTurnInteractionMetadata(state, interactionMode, conversationTargetId, combatTargetId).target_id} checked={primalKnowledgeOptIn} blocked={sending} onChange={onPrimalKnowledgeChange} />
            <TacticalMindControl state={state} mode={interactionMode} targetId={getTurnInteractionMetadata(state, interactionMode, conversationTargetId, combatTargetId).target_id} checked={tacticalMindOptIn} blocked={sending} onChange={onTacticalMindChange} />
          </div>
          <label className="sr-only" htmlFor="player-message">Hamleni anlat</label>
          <textarea ref={messageInputRef} id="player-message" className="command-input" value={message} maxLength={4000} onChange={(event) => setMessage(event.target.value)} onKeyDown={handleMessageKeyDown} placeholder={modePrompt} data-testid="input-player-message" aria-describedby="player-message-help" disabled={sending} />
          <button className="dnd-button" type="submit" disabled={sending || !message.trim()} data-testid="button-send-turn">
            {sending ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
            {sending ? 'İşleniyor' : 'Gönder'}
          </button>
        </form>
        {sending && <div className="pending-turn-status" data-testid="pending-turn-status" role="status" aria-live="polite" aria-atomic="true">
          <span className="pending-turn-mark"><OuroborosMark /></span>
          <span>Hamlen işleniyor</span>
        </div>}
        <div className="command-help" id="player-message-help"><span>Sözlerinle anlat · 1–4000 karakter</span>{desktopEnterSupported && <span className="desktop-enter-hint" data-testid="desktop-enter-hint"><kbd>Enter</kbd> gönder · <kbd>Shift+Enter</kbd> yeni satır</span>}<span data-testid="text-message-count">{message.length} / 4000</span></div>
      </div>}
    </section>
  );
}

function SessionHeader({ state, campaignId, onSave, saving, onReset, onDrawer, onOpenCombat }: { state: GameState; campaignId: string; onSave: () => void; saving: boolean; onReset: () => void; onDrawer: (drawer: Exclude<Drawer, null>, opener: HTMLElement) => void; onOpenCombat: (opener: HTMLElement) => void }) {
  return (
    <header className="preview-header app-header">
      <div className="preview-header-inner">
        <div className="preview-brand"><span className="preview-mark"><Feather size={17} /></span><span><strong>UNWRITTEN</strong><small>Bir hikâye, senin sözlerinle</small></span></div>
        <div className="header-location">
          <MapPinned size={13} />
          <div className="header-location-copy">
            <span data-testid="header-location">{state.locations[state.location]?.name ?? 'Konum ayrıntıları henüz görünmüyor.'}</span>
            <small data-testid="text-neutral-atmosphere"><CampaignDate state={state} /></small>
          </div>
          <span className="header-hp" data-testid="header-character-hp" aria-label={`Can ${state.character.current_hp} / ${state.character.max_hp}`}><Heart size={13} aria-hidden="true" />{state.character.current_hp} / {state.character.max_hp}</span>
        </div>
        {state.combat.active && (
          <button className="combat-quick-status" type="button" aria-haspopup="dialog" onClick={(event) => onOpenCombat(event.currentTarget)} data-testid="button-open-active-combat">
            <Swords size={14} aria-hidden="true" />
            <span className="combat-quick-status-label">ÇATIŞMA</span>
            {typeof state.combat.round === 'number' && <span>Tur {state.combat.round}</span>}
            <span className="combat-quick-hp">{state.character.current_hp}/{state.character.max_hp} CAN</span>
          </button>
        )}
        <div className="header-actions">
          <button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-character" onClick={(event) => onDrawer('character', event.currentTarget)}><Shield size={14} /> Karakter</button>
          <button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-world" onClick={(event) => onDrawer('world', event.currentTarget)}><Menu size={14} /> Dünya</button>
          <div className="session-chip" data-testid="status-session"><span className="health-dot" /> <span className="hidden sm:inline">MACERA</span></div>
          <button className="dnd-button secondary" type="button" onClick={onSave} disabled={saving} data-testid="button-save-campaign">{saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} <span>Kaydet</span></button>
          <button className="dnd-button secondary !px-3" type="button" onClick={onReset} data-testid="button-new-session"><Plus size={13} /> Ana ekrana dön</button>
        </div>
      </div>
    </header>
  );
}

function DrawerSheet({ drawer, state, decisionScope, conversionBlocked, onEconomyCommand, onClose, returnFocus, focusAfterCloseRef, activeTab, setActiveTab, combatEntries, sessionId, campaignId, sending, onExplorationCommand, onDraft, onSetCombatTarget }: { drawer: Drawer; state: GameState; decisionScope?: string; conversionBlocked?: boolean; onEconomyCommand?: (message: string, command: CombatActionInput) => void; onClose: () => void; returnFocus: HTMLElement | null; focusAfterCloseRef: React.MutableRefObject<'opener' | 'composer'>; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string; campaignId: string; sending: boolean; onExplorationCommand: (message: string) => void; onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void; onSetCombatTarget: (targetId: string) => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const returnFocusRef = useRef(returnFocus);
  closeRef.current = onClose;
  returnFocusRef.current = returnFocus;
  useEffect(() => {
    if (!drawer) return;
    focusAfterCloseRef.current = 'opener';
    const dialog = dialogRef.current;
    const root = document.documentElement;
    const body = document.body;
    const previousRootOverflow = root.style.overflow;
    const previousBodyOverflow = body.style.overflow;
    const previousRootOverscroll = root.style.overscrollBehavior;
    const previousBodyOverscroll = body.style.overscrollBehavior;
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    root.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    root.style.overscrollBehavior = 'none';
    body.style.overscrollBehavior = 'none';
    const stopBackgroundTouch = (event: TouchEvent) => {
      if (dialog && event.target instanceof Node && !dialog.contains(event.target)) event.preventDefault();
    };
    document.addEventListener('touchmove', stopBackgroundTouch, { capture: true, passive: false });
    const focusable = () => Array.from(dialog?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [tabindex]') ?? [])
      .filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden');
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
      document.removeEventListener('touchmove', stopBackgroundTouch, true);
      root.style.overflow = previousRootOverflow;
      body.style.overflow = previousBodyOverflow;
      root.style.overscrollBehavior = previousRootOverscroll;
      body.style.overscrollBehavior = previousBodyOverscroll;
      window.scrollTo(scrollX, scrollY);
      const focusAfterClose = focusAfterCloseRef.current;
      focusAfterCloseRef.current = 'opener';
      const opener = returnFocusRef.current;
      const target = focusReturnTarget(Boolean(opener?.isConnected));
      if (focusAfterClose === 'composer') document.getElementById('player-message')?.focus({ preventScroll: true });
      else if (target === 'opener') opener?.focus({ preventScroll: true });
      else document.getElementById('player-message')?.focus({ preventScroll: true });
    };
  }, [drawer, focusAfterCloseRef]);
  if (!drawer) return null;
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><section ref={dialogRef} className="drawer-sheet" role="dialog" aria-modal="true" aria-label={drawer === 'character' ? 'Karakter paneli' : 'Dünyanın çevresi'} tabIndex={-1} onClick={(event) => event.stopPropagation()}><div className="drawer-heading"><Kicker>{drawer === 'character' ? 'Yolcu' : 'Dünyanın çevresi'}</Kicker><button className="icon-button" type="button" aria-label="Paneli kapat" data-testid="button-close-drawer" onClick={onClose}><X size={16} /></button></div>{drawer === 'character' ? <LeftColumn state={state} decisionScope={decisionScope} conversionBlocked={conversionBlocked} onCommand={onEconomyCommand} /> : <WorldTabs state={state} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} campaignId={campaignId} sending={sending} onExplorationCommand={onExplorationCommand} onDraft={(message, mode, targetId) => { focusAfterCloseRef.current = 'composer'; onDraft(message, mode, targetId); onClose(); }} onSetCombatTarget={onSetCombatTarget} />}</section></div>;
}

function CharacterReveal({ state, catalog, onContinue, onBack }: { state: GameState; catalog?: unknown; onContinue: () => void; onBack: () => void }) {
  const character = state.character;
  const classPortraitCells: Record<string, number> = {
    fighter: 0, barbarian: 1, paladin: 2, ranger: 3, rogue: 4, monk: 5,
    bard: 6, cleric: 7, druid: 8, sorcerer: 9, wizard: 10, warlock: 11,
  };
  const speciesPortraitCells: Record<string, number> = {
    human: 0, elf: 1, dwarf: 2, halfling: 3, dragonborn: 4, gnome: 5,
    'half-orc': 6, tiefling: 7, goliath: 8, aasimar: 9, 'wood elf': 10, orc: 11,
  };
  const classCell = classPortraitCells[character.class.trim().toLowerCase()];
  const speciesCell = speciesPortraitCells[character.race.trim().toLowerCase()];
  const portraitCell = classCell ?? speciesCell;
  const portraitSheet = classCell !== undefined ? classPortraitSheet : speciesPortraitSheet;
  const portraitStyle = classCell === undefined && character.race.trim().toLowerCase() === 'half-elf'
    ? { backgroundImage: `url("${halfElfPortrait}")`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : portraitCell === undefined ? undefined : {
    backgroundImage: `url("${portraitSheet}")`,
    backgroundPosition: `${(portraitCell % 4) * 100 / 3}% ${Math.floor(portraitCell / 4) * 50}%`,
  };
  const abilities = [
    ['KUV', character.strength],
    ['ÇEV', character.dexterity],
    ['DAY', character.constitution],
    ['ZEK', character.intelligence],
    ['BİL', character.wisdom],
    ['KAR', character.charisma],
  ];
  return (
    <main className="reveal-screen gate-fade cinematic-reveal" data-testid="screen-character-reveal">
      <header className="dnd-shell reveal-header">
        <Brand />
        <button type="button" className="text-button reveal-back" onClick={() => { primeGateSound(); playGateSound('page'); onBack(); }} data-testid="button-back-opening">
          <ArrowLeft size={13} /> Geri dön
        </button>
      </header>
      <div className="reveal-wrap">
        <div className="reveal-heading">
          <Kicker>Yeni macera · Yolcu</Kicker>
          <h1 className="dnd-display">Adın artık<br /><em>bir hikâye.</em></h1>
          <p className="dnd-serif">Yolun belli. Dünya henüz seni tanımıyor.</p>
        </div>
        <div className="reveal-card">
          <div className={`reveal-portrait ${portraitStyle ? '' : 'reveal-portrait-neutral'}`} style={portraitStyle} role="img" aria-label={`${character.name} için ${speciesLabel(character.race)} ${classLabel(character.class)} temsili portre`}>
            <div className="portrait-vignette" />
            <div className="portrait-caption"><span>YOLCU PORTRESİ</span><strong>{character.name}</strong><small>Temsili görsel · karakter görünümünü belirlemez</small></div>
            <div className="portrait-insignia" aria-hidden="true"><OuroborosMark /></div>
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
            <StartingEquipmentNotice characterClass={character.class} catalog={catalog} />
            <PurseLine totalCp={state.wallet?.total_cp ?? null} />
            <StoredProgressionChoices character={character} />
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
              <button type="button" className="dnd-button" onClick={() => { primeGateSound(); playGateSound('success'); onContinue(); }} data-testid="button-continue-adventure">
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

export default function GameBrowser() {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState('');
  const [campaignId, setCampaignId] = useState('');
  const [phase, setPhase] = useState<'opening' | 'library' | 'creation' | 'reveal' | 'adventure'>('opening');
  const [creationReturnPhase, setCreationReturnPhase] = useState<'opening' | 'library'>('opening');
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [readingPreferences, setReadingPreferences] = useState(readReadingPreferences);
  useEffect(() => {
    writeReadingPreferences(readingPreferences);
  }, [readingPreferences]);
  const [combatEntries, setCombatEntries] = useState<CombatLogEntry[]>([]);
  const [combatEndNotice, setCombatEndNotice] = useState<string | null>(null);
  const [combatStartNotice, setCombatStartNotice] = useState<string | null>(null);
  const [combatTargetId, setCombatTargetId] = useState('');
  const [conversationTargetId, setConversationTargetId] = useState('');
  const [message, setMessage] = useState('');
  // The draft as it is when an async result lands (a retry must not clear text typed in the meantime).
  const messageRef = useRef(message);
  messageRef.current = message;
  const [composerOpen, setComposerOpen] = useState(true);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('do');
  const [notice, setNotice] = useState<Notice | null>(null);
  // Bumped when a recovery settles: the counter panel remounts and reads the server again instead of keeping a stale gate.
  const [panelEpoch, setPanelEpoch] = useState(0);
  const [drawer, setDrawer] = useState<Drawer>(null);
  const [expandedRailPanel, setExpandedRailPanel] = useState<RailPanelId | null>(null);
  const [panelOpener, setPanelOpener] = useState<HTMLElement | null>(null);
  const focusAfterDrawerCloseRef = useRef<'opener' | 'composer'>('opener');
  const [resultCue, setResultCue] = useState('');
  const [newResponseEntryIndex, setNewResponseEntryIndex] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<WorldTab>('world');
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
  const turnLifetime = useActionLifetime(sessionId);
  const inFlightSessionsRef = useRef(new Set<string>());
  const [inFlightSessions, setInFlightSessions] = useState<Set<string>>(new Set());
  useEffect(() => { setInFlightSessions(new Set(inFlightSessionsRef.current)); }, [sessionId]);
  const turnSending = inFlightSessions.has(sessionId);
  // LR00-P5/P7: the last completed turn's receipt summary and undo target.
  const [lastTurn, setLastTurn] = useState<{ sessionId: string; actionId: string; outcome: TurnOutcome | null } | null>(null);
  const lastTurnRef = useRef(lastTurn);
  lastTurnRef.current = lastTurn;
  // True right after a successful undo until the next turn reply (or a reset, a new campaign, a resume).
  const [undoneJustNow, setUndoneJustNow] = useState(false);
  const [undoPendingSessions, setUndoPendingSessions] = useState<Set<string>>(new Set());
  const undoPendingRef = useRef(new Set<string>());
  const undoRequestsRef = useRef(new globalThis.Map<string, {
    generation: number;
    scope: string;
    actionId: string;
    targetActionId: string;
  }>());
  const undoGenerationRef = useRef(0);
  const undoScope = `${campaignId ?? ''}:${sessionId}`;
  const undoScopeRef = useRef(undoScope);
  if (undoScopeRef.current !== undoScope) {
    undoScopeRef.current = undoScope;
    undoGenerationRef.current += 1;
  }
  const undoBusy = undoPendingSessions.has(sessionId);
  const visibleLastTurn = lastTurn && lastTurn.sessionId === sessionId ? lastTurn : null;
  const undoLastTurn = () => {
    const pendingRequest = undoRequestsRef.current.get(sessionId);
    if (!sessionId || (!visibleLastTurn && !pendingRequest) || undoPendingRef.current.has(sessionId) || inFlightSessionsRef.current.has(sessionId)) return;
    // An unresolved move may still commit; undoing around it would let a later retry land after the undo.
    const unresolved = blockingMutation();
    if (unresolved) {
      setNotice(unresolved);
      return;
    }
    const target = pendingRequest?.targetActionId ?? visibleLastTurn!.actionId;
    if (pendingRequest && visibleLastTurn && pendingRequest.targetActionId !== target) return;
    const startedOperation = turnLifetime.begin();
    if (!startedOperation) return;
    const operation = withActionDeadline(startedOperation, startDeadline());
    const recoveringRequest = Boolean(pendingRequest);
    const request = pendingRequest
      ? { ...pendingRequest, generation: undoGenerationRef.current, scope: undoScope }
      : {
        generation: undoGenerationRef.current,
        scope: undoScope,
        actionId: crypto.randomUUID(),
        targetActionId: target,
      };
    undoRequestsRef.current.set(sessionId, request);
    undoPendingRef.current.add(sessionId);
    setUndoPendingSessions(new Set(undoPendingRef.current));
    const isCurrent = () => activeSessionRef.current === sessionId
      && undoScopeRef.current === request.scope
      && undoGenerationRef.current === request.generation
      && undoRequestsRef.current.get(sessionId) === request
      && operation.isCurrent()
      && (recoveringRequest || (
        lastTurnRef.current?.sessionId === sessionId
        && lastTurnRef.current.actionId === target
      ));
    const stateKey = getGetGameSessionStateQueryKey(sessionId);
    let retainRequest = false;
    void undoGameTurn(sessionId, { action_id: request.actionId, target_action_id: target }, { signal: operation.signal })
      .then(async (result) => {
        if (!isCurrent() || operation.deadlineExpired()) return;
        let snapshot: {
          state: GameState;
          history: CampaignDetail['history'] | null;
          combat_history: CampaignDetail['combat_history'] | null;
        };
        const readRevision = nextRevision();
        try {
          snapshot = await reconcileState(queryClient, stateKey, operation, (signal) =>
            campaignId
              ? getCampaign(campaignId, { signal })
              : getGameSessionState(sessionId, { signal }).then((state) => ({
                state, history: null, combat_history: null,
              })),
          );
        } catch {
          if (!isCurrent()) return;
          retainRequest = true;
          void queryClient.invalidateQueries({ queryKey: stateKey });
          setNotice({
            tone: 'warning',
            title: 'Geri alma kaydı güncel durumla uzlaştırılamadı',
            detail: 'Aynı geri alma isteği korunuyor; güncel durum doğrulanana kadar yeni hamle gönderilemez.',
          });
          return;
        }
        if (!isCurrent()) return;
        applyGameState(queryClient, sessionId, snapshot.state, { revision: readRevision, isCurrent });
        if (snapshot.history) {
          setEntries(historyToEntries(snapshot.history, { opening: snapshot.state.scene?.opening }));
        }
        if (snapshot.combat_history) setCombatEntries(mergeCombatHistory(snapshot.combat_history));
        if (lastTurnRef.current?.sessionId === sessionId && lastTurnRef.current.actionId === target) setLastTurn(null);
        // One step only (the engine's rule): until a new turn lands the bar says why there is no second undo.
        setUndoneJustNow(true);
        setNotice({ tone: 'success', title: 'Son tur geri alındı', detail: 'Dünya o turdan önceki hâline döndü.' });
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      })
      .catch(async (error) => {
        if (!isCurrent()) return;
        const status = statusCode(error);
        const definitiveRejection = error instanceof ApiError && status !== undefined && status >= 400 && status < 500;
        if (definitiveRejection) {
          if (undoRequestsRef.current.get(sessionId) === request) undoRequestsRef.current.delete(sessionId);
          setNotice({ tone: 'error', title: 'Geri alınamadı', detail: friendlyError(error, 'Bu tur artık geri alınamıyor.') });
          return;
        }
        retainRequest = true;
        setNotice({
          tone: 'warning',
          title: 'Geri alma sonucu belirsiz',
          detail: 'Sunucu durumu yeniden okunuyor. Sonuç doğrulanana kadar yeni hamle gönderilemez.',
        });
        try {
          const statusReadUpdateCount = queryClient.getQueryState(stateKey)?.dataUpdateCount ?? 0;
          const readRevision = nextRevision();
          const canonicalState = await getGameSessionState(sessionId, { signal: operation.signal });
          if (!isCurrent()) return;
          if ((queryClient.getQueryState(stateKey)?.dataUpdateCount ?? 0) !== statusReadUpdateCount) {
            void queryClient.invalidateQueries({ queryKey: stateKey });
            setNotice({
              tone: 'warning',
              title: 'Geri alma sonucu doğrulanamadı',
              detail: 'Durum sorgusu sırasında daha yeni bilgi geldi. Aynı geri alma isteğini yeniden deneyin.',
            });
            return;
          }
          applyGameState(queryClient, sessionId, canonicalState, { revision: readRevision, isCurrent });
        } catch {
          if (!isCurrent()) return;
          void queryClient.invalidateQueries({ queryKey: stateKey });
          setNotice({
            tone: 'warning',
            title: 'Geri alma sonucu doğrulanamadı',
            detail: 'Aynı geri alma isteğini yeniden deneyin; yeni hamle gönderilemez.',
          });
        }
      })
      .finally(() => {
        if (!retainRequest && undoRequestsRef.current.get(sessionId) === request) {
          undoRequestsRef.current.delete(sessionId);
        }
        undoPendingRef.current.delete(sessionId);
        setUndoPendingSessions(new Set(undoPendingRef.current));
        operation.close();
      });
  };
  // The unresolved turn lives in pending-action storage (owner + campaign). Retry buttons sit in notice
  // state, so they reach the latest submitTurn through this ref instead of a stale render's closure.
  const submitTurnRef = useRef<(text: string, combatAction?: CombatActionInput, mode?: InteractionMode, retryPending?: boolean, economicAction?: EconomicAction) => void>(() => {});
  const submitLevelUpRef = useRef<(request?: LevelUpRequest) => void>(() => {});
  const retryPendingTurn = () => {
    const pending = readPending(currentAccountOwner() ?? LOCAL_OWNER, campaignId || sessionId);
    if (pending?.kind === 'level_up') submitLevelUpRef.current();
    else submitTurnRef.current('', undefined, undefined, true);
  };
  // Server-proven way out of an unresolved action (lost reply, damaged local request, second tab, re-login). The server's
  // stored receipt or durable refusal decides; a 404/503, a timeout or a missing receipt never closes anything, and nothing
  // here creates a new action id or resends a move.
  const serverRecoveryRef = useRef<(mode: 'check' | 'abandon', serverActionId?: string, boundSessionId?: string) => Promise<void>>(async () => {});
  // The handlers are bound to the session they were created for: a notice that outlives a session or campaign switch
  // must never ask (or close) an action id of another campaign.
  const recoveryHandlers = (serverActionId?: string) => {
    const boundSessionId = sessionId;
    return {
      check: () => { void serverRecoveryRef.current('check', serverActionId, boundSessionId); },
      abandon: () => { void serverRecoveryRef.current('abandon', serverActionId, boundSessionId); },
    };
  };
  const pendingTurnNotice = (serverActionId?: string): Notice => ({ ...PENDING_TURN_NOTICE, retry: retryPendingTurn, recover: recoveryHandlers(serverActionId) });
  // Any other unresolved mutation in this campaign (play move, species action, ambient action) blocks the rest:
  // one uncertain move must not be overtaken by another path. The server still decides; this is only the client guard.
  const blockingMutation = (ignoreAmbient = false): Notice | null => {
    const scope = campaignId || sessionId;
    if (readPending(currentAccountOwner() ?? LOCAL_OWNER, scope)) return pendingTurnNotice();
    // B3: a server-only open action (second tab, re-login) has no browser record; an unknown or unresolved server check
    // still locks this campaign until a later check or an explicit abandon settles it.
    if (notice?.recovery && !notice.recovery.mutationAllowed && notice.recovery.scope === scope) return notice;
    if (speciesActionUnresolved(scope)) {
      return { tone: 'warning', title: 'Tür yeteneği henüz doğrulanamadı', detail: 'Önce tür yeteneğinin sonucunu doğrula; başka bir işlem göndermeden önce aynı kimlikle yeniden denenmesi gerekiyor.' };
    }
    if (!ignoreAmbient && pendingAmbientActionRef.current) {
      return { tone: 'warning', title: 'Çevre olayı henüz doğrulanamadı', detail: 'Önce çevre olayı yanıtını yeniden dene; başka bir işlem göndermeden önce sonucu bekleniyor.' };
    }
    return null;
  };
  // The server's open action for this campaign (second tab, re-login, lost browser record) is offered for a server check
  // or a server-proven abandon. A failed lookup is not "nothing is open"; the server still refuses a conflicting move.
  // The lookup is bounded and ends with the screen that asked (`signal`), so a silent server leaves no hanging request.
  // A lookup that runs out of time is `unknown`, not "nothing is open": it locks this campaign and offers a manual re-check
  // that runs the same lookup again (`recheck`); when that re-check finds nothing open, the unknown notice is cleared.
  const showServerOpenAction = async (forSession: string, forCampaign: string, stillCurrent: () => boolean, signal?: AbortSignal, recheck = false) => {
    try {
      const open = await findUnresolvedOnServer(RECOVERY_API, forSession, { signal });
      if (!stillCurrent() || readPending(currentAccountOwner() ?? LOCAL_OWNER, forCampaign)) return;
      if (!open) {
        if (recheck) setNotice((current) => (current?.recheck ? null : current));
        return;
      }
      setNotice({
        tone: 'warning',
        title: 'Tamamlanmamış bir hamle var',
        detail: 'Sunucuda bu kampanya için henüz sonuçlanmamış bir hamle kayıtlı (başka bir sekme veya önceki oturum). Yeni hamle göndermeden önce durumunu sunucudan kontrol et ya da bilinçli olarak vazgeç.',
        recover: recoveryHandlers(open.actionId),
      });
    } catch (error) {
      // A failed lookup stays silent (see above); only a lookup that ran out of time is shown as unknown.
      if (!(error instanceof RecoveryTimeoutError) || !stillCurrent() || readPending(currentAccountOwner() ?? LOCAL_OWNER, forCampaign)) return;
      setNotice({
        tone: 'warning', title: 'Sonuç belirsiz',
        detail: 'Sunucu bu kampanyada açık bir hamle olup olmadığını belirlenen sürede söylemedi. Açık bir hamle olabilir; doğrulanana kadar yeni hamleler kilitli.',
        recheck: () => { void showServerOpenAction(forSession, forCampaign, stillCurrent, signal, true); },
        recovery: { status: 'unknown', loading: false, mutationAllowed: false, scope: forCampaign },
      });
    }
  };
  useEffect(() => {
    const unresolved = Boolean(readPending(currentAccountOwner() ?? LOCAL_OWNER, campaignId || sessionId));
    // A retry button from another session or campaign must not outlive the switch.
    setNotice((current) => (current?.retry || current?.recover || current?.recheck ? null : current));
    // After a reload the unresolved move is offered for a retry instead of being forgotten.
    if (unresolved) setNotice(pendingTurnNotice());
    // A second tab or a re-login has no browser record: the server's open action is read again, never assumed absent or closed.
    if (!sessionId || !campaignId) return undefined;
    let current = true;
    const lookup = new AbortController();
    void showServerOpenAction(sessionId, campaignId, () => current, lookup.signal);
    return () => { current = false; lookup.abort(); };
  }, [campaignId, sessionId]);
  const activeSessionRef = useRef(sessionId);
  activeSessionRef.current = sessionId;
  const resolveAmbientEventAction = useResolveAmbientEventAction();
  const stateQuery = useGetGameSessionState(sessionId, { query: {
    enabled: Boolean(sessionId), queryKey: getGetGameSessionStateQueryKey(sessionId), retry: false,
    // A refetch stamped with the moment it was issued cannot overwrite a newer mutation or reconciled state.
    queryFn: ({ signal }) => gatedStateRead(gameStateScope(sessionId))(() => getGameSessionState(sessionId, { signal })),
    structuralSharing: stateStructuralSharing(queryClient, getGetGameSessionStateQueryKey(sessionId)),
  } });
  const state = stateQuery.data;
  const primalKnowledgeRef = useRef<ReturnType<typeof createPrimalKnowledgeIntent> | null>(null);
  if (!primalKnowledgeRef.current) primalKnowledgeRef.current = createPrimalKnowledgeIntent();
  const primalKnowledgeIntent = primalKnowledgeRef.current;
  const tacticalMindRef = useRef<ReturnType<typeof createPrimalKnowledgeIntent> | null>(null);
  if (!tacticalMindRef.current) tacticalMindRef.current = createPrimalKnowledgeIntent();
  const tacticalMindIntent = tacticalMindRef.current;
  const [, redrawPrimalKnowledge] = useState(0);
  // Sync during render so no effect gap (or switch away and back) can resurrect consent.
  primalKnowledgeIntent.sync({
    key: JSON.stringify([currentAccountOwner() ?? LOCAL_OWNER, campaignId, sessionId, interactionMode]),
    available: primalKnowledgeAvailable(state, getTurnInteractionMetadata(state, interactionMode, conversationTargetId, combatTargetId)),
  });
  tacticalMindIntent.sync({
    key: JSON.stringify([currentAccountOwner() ?? LOCAL_OWNER, campaignId, sessionId, interactionMode]),
    available: tacticalMindAvailable(state, getTurnInteractionMetadata(state, interactionMode, conversationTargetId, combatTargetId)),
  });
  const [ambientActionResult, setAmbientActionResult] = useState<AmbientEventResult | null>(null);
  const [ambientActionRequest, setAmbientActionRequest] = useState<AmbientEventActionRequest | null>(null);
  const [ambientActionError, setAmbientActionError] = useState(false);
  const pendingAmbientActionRef = useRef<AmbientEventActionRequest | null>(null);
  const storyScrollRef = useRef<HTMLDivElement>(null);
  const wasAtBottom = useRef(true);
  const seenEntryCount = useRef(0);
  const isStoryNearBottom = (node: HTMLDivElement) => {
    const hasOwnScroll = node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY);
    return hasOwnScroll
      ? node.scrollHeight - node.scrollTop - node.clientHeight < 80
      : node.getBoundingClientRect().bottom <= window.innerHeight + 80;
  };
  const scrollStoryToBottom = (node: HTMLDivElement) => {
    const hasOwnScroll = node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY);
    if (hasOwnScroll) node.scrollTop = node.scrollHeight;
    else node.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'auto' });
  };
  const previousCombatActive = useRef<boolean | null>(null);

  useEffect(() => {
    pendingAmbientActionRef.current = null;
    setAmbientActionRequest(null);
    setAmbientActionResult(null);
    setAmbientActionError(false);
  }, [sessionId, state?.scene?.ambient_event?.instance_id]);

  useEffect(() => {
    setCombatStartNotice(null);
  }, [sessionId, campaignId]);

  useEffect(() => {
    setCombatEndNotice(null);
    setCombatTargetId('');
    if (!sessionId) { setEntries([]); return; }
    // Persisted campaigns restore their transcript from the authenticated API.
    // A local text-only cache must never replace a receipt-backed skill card.
    if (campaignId) return;
    try {
      const stored = JSON.parse(window.localStorage.getItem(`${TRANSCRIPT_KEY}${sessionId}`) ?? '[]') as unknown;
      const restored = Array.isArray(stored) ? stored.flatMap((entry): TranscriptEntry[] => {
        if (!entry || typeof entry !== 'object') return [];
        const candidate = entry as { kind?: unknown; text?: unknown; undone?: unknown; undoNote?: unknown; undoTargetUnknown?: unknown };
        if ((candidate.kind !== 'player' && candidate.kind !== 'narration') || typeof candidate.text !== 'string') return [];
        return [{ kind: candidate.kind, text: candidate.text,
          ...(candidate.undone === true ? { undone: true } : {}),
          ...(candidate.undoNote === true ? { undoNote: true } : {}),
          ...(candidate.undoTargetUnknown === true ? { undoTargetUnknown: true } : {}) }];
      }) : [];
      setEntries(restored);
    } catch { setEntries([]); }
  }, [sessionId, campaignId]);

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
    const node = storyScrollRef.current;
    const grew = entries.length > seenEntryCount.current;
    seenEntryCount.current = entries.length;
    if (!entries.length || !node) return;
    if (transcriptFollowsBottom(wasAtBottom.current)) {
      scrollStoryToBottom(node);
      return;
    }
    if (grew) setResultCue(`Yeni sonuç geldi. ${entries.length}`);
  }, [entries]);
  useEffect(() => {
    const node = storyScrollRef.current;
    const content = node?.querySelector('[data-testid="transcript-local"]');
    if (!node || !content || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      if (transcriptFollowsBottom(wasAtBottom.current)) scrollStoryToBottom(node);
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [entries.length]);
  useEffect(() => {
    if (phase !== 'adventure' || !sessionId) return;
    const shell = document.querySelector<HTMLElement>('.play-shell');
    const viewport = window.visualViewport;
    if (!shell || !viewport) return;
    const apply = () => {
      const inset = keyboardInset(window.innerHeight, viewport.height, viewport.offsetTop);
      shell.style.setProperty('--keyboard-inset', `${inset}px`);
      if (inset <= 0) {
        shell.scrollTop = 0;
        return;
      }
      window.requestAnimationFrame(() => {
        const send = shell.querySelector<HTMLElement>('[data-testid="button-send-turn"]');
        if (!send) return;
        const container = send.closest<HTMLElement>('.app-main') ?? shell;
        const overflow = clippedControlOverflow(
          send.getBoundingClientRect().bottom,
          container.getBoundingClientRect().bottom,
          window.innerHeight - inset,
        );
        if (overflow > 1) container.scrollTop += overflow;
      });
    };
    apply();
    viewport.addEventListener('resize', apply);
    viewport.addEventListener('scroll', apply);
    return () => {
      viewport.removeEventListener('resize', apply);
      viewport.removeEventListener('scroll', apply);
    };
  }, [phase, sessionId]);

  const handleStoryScroll = () => {
    const node = storyScrollRef.current;
    if (!node) return;
    wasAtBottom.current = isStoryNearBottom(node);
    if (wasAtBottom.current) {
      setNewResponseEntryIndex(null);
      setResultCue('');
    }
  };
  useEffect(() => {
    window.addEventListener('scroll', handleStoryScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleStoryScroll);
  }, [phase, sessionId]);

  const jumpToNewResponse = (focusTarget = false) => {
    if (newResponseEntryIndex === null) return;
    const target = storyScrollRef.current?.querySelector<HTMLElement>(
      `[data-testid="transcript-narration-${newResponseEntryIndex}"]`,
    );
    target?.scrollIntoView({
      block: 'end',
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
    if (focusTarget && target) {
      target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
    setNewResponseEntryIndex(null);
    setResultCue('');
  };

  const reset = () => {
    setSessionId('');
    setCampaignId('');
    setPhase('opening');
    setEntries([]);
    setCombatEntries([]);
    setCombatEndNotice(null);
    setCombatStartNotice(null);
    setConversationTargetId('');
    setInteractionMode('do');
    setUndoneJustNow(false);
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
    const epoch = currentAuthEpoch();
    createCampaign.mutate({
      data: { character, campaign_start: campaignStart, death_mode: deathMode },
    }, {
      onSuccess: (created) => {
        if (!accountWriteAllowed(epoch)) return;
        setCampaignId(created.campaign_id);
        writeAdvisoryCache(LAST_CAMPAIGN_KEY, created.campaign_id);
        applyGameState(queryClient, created.session_id, created.state);
        removeAdvisoryCache(`${TRANSCRIPT_KEY}${created.session_id}`);
        setEntries([]);
        setCombatEntries([]);
        setCombatEndNotice(null);
        setCombatStartNotice(null);
        setInteractionMode('do');
        setConversationTargetId('');
        setUndoneJustNow(false);
        setActiveTab('world');
        previousCombatActive.current = null;
        setSessionId(created.session_id);
        setPhase('reveal');
        primeGateSound();
        playGateSound('success');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => {
        if (!accountWriteAllowed(epoch)) return;
        setNotice({
        tone: 'error',
        title: 'Kampanya oluşturulamadı',
        detail: statusCode(error) === 422
          ? 'İsim, tür, sınıf, başlangıç seviyesi ve gerekli seviye seçimlerini yeniden gözden geçir. Taslağın korunuyor.'
          : friendlyError(error, 'Dünya şu an yanıt vermiyor.'),
      });
      },
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
        writeAdvisoryCache(
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
    const epoch = currentAuthEpoch();
    resumeCampaign.mutate({ campaignId: selectedCampaignId }, {
      onSuccess: (resumed) => {
        if (!accountWriteAllowed(epoch)) return;
        const transcript: TranscriptEntry[] = historyToEntries(resumed.history, { opening: resumed.state.scene?.opening });
        setCampaignId(resumed.campaign_id);
        writeAdvisoryCache(LAST_CAMPAIGN_KEY, resumed.campaign_id);
        writeAdvisoryCache(`${TRANSCRIPT_KEY}${resumed.session_id}`, JSON.stringify(transcript));
        setEntries(transcript);
        setCombatEntries(mergeCombatHistory(resumed.combat_history));
        setCombatEndNotice(null);
        setCombatStartNotice(null);
        // An open conversation (the engine's projection) stays in "Söyle" with that person; otherwise "Yap".
        const resumedMode = resumeComposerMode(resumed.state);
        setInteractionMode(resumedMode.mode);
        setConversationTargetId(resumedMode.targetId);
        setUndoneJustNow(false);
        setActiveTab('world');
        previousCombatActive.current = null;
        setSessionId(resumed.session_id);
        setMessage('');
        setPhase('adventure');
        setResumingCampaignId(null);
        applyGameState(queryClient, resumed.session_id, resumed.state);
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => {
        if (!accountWriteAllowed(epoch)) return;
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
    // Its own retry is allowed; a play move or species action that is still unresolved is not overtaken.
    const unresolved = blockingMutation(true);
    if (unresolved) {
      setNotice(unresolved);
      return;
    }
    pendingAmbientActionRef.current = request;
    setAmbientActionRequest(request);
    setAmbientActionError(false);
    const issued = nextRevision();
    resolveAmbientEventAction.mutate(
      {
        sessionId: request.sessionId,
        eventInstanceId: request.eventInstanceId,
        data: request.data,
      },
      {
        onSuccess: (response) => {
          applyGameState(queryClient, request.sessionId, response.state, { revision: issued });
          if (pendingAmbientActionRef.current === request) {
            pendingAmbientActionRef.current = null;
            setAmbientActionResult(response.result);
            setAmbientActionRequest(null);
            setAmbientActionError(false);
            const move = ambientFollowUpMove(request.data.action, response.result.status);
            if (move) submitTurnRef.current(move, undefined, 'do');
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
    retryPending = false,
    economicAction?: EconomicAction,
  ) => {
    const draft = text.trim();
    if (!sessionId || undoPendingRef.current.has(sessionId) || undoRequestsRef.current.has(sessionId) || inFlightSessionsRef.current.has(sessionId)) return;
    if (!retryPending && (draft.length < 1 || draft.length > 4000)) return;
    const actionScope = campaignId || sessionId;
    const ownerId = currentAccountOwner() ?? LOCAL_OWNER;
    const stored = readPending(ownerId, actionScope);
    if (retryPending ? !stored : stored) {
      // An earlier move is unresolved: no new move goes out, the typed draft stays as it is.
      if (stored) setNotice(pendingTurnNotice());
      return;
    }
    if (stored?.kind === 'level_up') { submitLevelUpRef.current(); return; }
    const elsewhere = retryPending ? null : blockingMutation();
    if (elsewhere) {
      setNotice(elsewhere);
      return;
    }
    const startedOperation = turnLifetime.begin();
    if (!startedOperation) return;
    // One absolute budget for the whole action (token read, mutation, reconciliation): it is never reset by a sub-step.
    const actionDeadline = startDeadline();
    const operation = withActionDeadline(startedOperation, actionDeadline);
    setResultCue('');
    setNotice(null);
    const fresh = stored ? null : getTurnInteractionMetadata(
      state, mode, conversationTargetId, combatTargetId, Boolean(combatAction),
    );
    // Fresh consent is scoped again at dispatch. A stored retry never consults current controls.
    if (!stored) tacticalMindIntent.sync({ key: JSON.stringify([ownerId, campaignId, sessionId, mode]), available: tacticalMindAvailable(state, fresh, combatAction) });
    if (!stored) primalKnowledgeIntent.sync({
      key: JSON.stringify([ownerId, campaignId, sessionId, mode]),
      available: primalKnowledgeAvailable(state, fresh, combatAction),
    });
    // The original request body is stored with the pending action, so a retry resends exactly that.
    // A card step is its own request: the fixed message and the economic action only, never the composer's draft.
    const cardStep: Record<string, unknown> | null = economicAction ? { message: draft, economic_action: economicAction } : null;
    const request: Record<string, unknown> = stored?.request ?? cardStep ?? {
      message: draft,
      interaction_mode: fresh?.interaction_mode,
      ...(combatAction ? { combat_action: combatAction } : {}),
      ...(state?.combat.active && state.combat.combat_id ? {
        combat_id: state.combat.combat_id, combat_round: state.combat.round,
        combat_turn_index: state.combat.current_turn_index,
      } : {}),
      ...(fresh?.target_id ? { target_id: fresh.target_id } : {}),
      ...(primalKnowledgeIntent.selected ? { check_feature: 'primal_knowledge' } : tacticalMindIntent.selected ? { check_feature: 'tactical_mind' } : {}),
    };
    let key: ReturnType<typeof createIntentKey>;
    try {
      key = stored ? resumePending(stored.key, currentAuthEpoch()).key : createIntentKey(ownerId, actionScope, request);
    } catch {
      // The move could not be recorded (no secure UUID, or an earlier move already holds the slot): say so, send nothing.
      operation.close();
      setNotice({ tone: 'error', title: 'Hamle kaydedilemedi', detail: 'Hamle güvenle kaydedilemediği için gönderilmedi. Sayfayı yenileyip tekrar dene; yazdığın metin taslakta duruyor.' });
      return;
    }
    // Consume only a newly recorded command. Unknown outcomes keep their original request in pending storage;
    // retry/refusal/recovery must not consume consent belonging to an unrelated later draft.
    if (!stored) { primalKnowledgeIntent.choose(false); tacticalMindIntent.choose(false); redrawPrimalKnowledge(value => value + 1); }
    const actionId = key.actionId;
    const trimmed = String(request.message ?? '');
    const metadata = { interaction_mode: request.interaction_mode as InteractionMode };
    inFlightSessionsRef.current.add(sessionId);
    setInFlightSessions(new Set(inFlightSessionsRef.current));
    const epoch = currentAuthEpoch();
    let receiptReceived = false;
    void playGameTurn(sessionId, {
        ...request,
        action_id: actionId,
    } as Parameters<typeof playGameTurn>[1], { signal: operation.signal }).then(async (result) => {
        // A reply that arrives after the deadline is never applied: the outcome was already declared unknown.
        if (!operation.isCurrent() || operation.deadlineExpired()) return;
        receiptReceived = true;
        const stateKey = getGetGameSessionStateQueryKey(sessionId);
        const readRevision = nextRevision();
        const snapshot = await reconcileState<{ state: GameState; history: CampaignDetail['history'] | null; combat_history: CampaignDetail['combat_history'] | null }>(queryClient, stateKey, operation, (signal) =>
          campaignId ? getCampaign(campaignId, { signal })
            : getGameSessionState(sessionId, { signal }).then(state => ({ state, history: null, combat_history: null })));
        if (!operation.isCurrent()) return;
        result = { ...result, state: snapshot.state };
        const stillVisible = activeSessionRef.current === sessionId;
        // Only a reconciled, committed result closes the pending action.
        closePending(key, 'confirmed');
        const next: TranscriptEntry[] = snapshot.history ? historyToEntries(snapshot.history, {
          opening: snapshot.state.scene?.opening, lastPlayerMode: metadata.interaction_mode,
        }) : [
          ...entries,
          { kind: 'player' as const, text: trimmed, mode: metadata.interaction_mode },
          {
            kind: 'narration' as const,
            text: result.narration,
            skillCheckResult: result.skill_check_result ?? undefined,
          },
        ];
        const wasFollowingResponse = transcriptFollowsBottom(wasAtBottom.current);
        if (stillVisible) {
          setEntries(next);
          setNewResponseEntryIndex(wasFollowingResponse ? null : next.length - 1);
        }
        writeAdvisoryCache(
          `${TRANSCRIPT_KEY}${sessionId}`,
          JSON.stringify(next.map(({ kind, text, skillCheckResult, mode, undone, undoNote, undoTargetUnknown }) => ({
            kind, text, ...(mode ? { mode } : {}), ...(skillCheckResult ? { skillCheckResult } : {}),
            ...(undone ? { undone } : {}), ...(undoNote ? { undoNote } : {}), ...(undoTargetUnknown ? { undoTargetUnknown } : {}),
          }))),
        );
        const combatResult = result.combat_result;
        const combatHistoryEntry = result.combat_history_entry;
        if (stillVisible && snapshot.combat_history) {
          setCombatEntries(mergeCombatHistory(snapshot.combat_history));
        } else if (stillVisible && combatHistoryEntry) {
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
          if (!retainCombatTarget(combatTargetId, result.state.combat, Boolean(combatResult.combat_ended))) {
            setCombatTargetId('');
          }
        } else if (stillVisible) {
          setCombatEndNotice(null);
        }
        if (stillVisible) {
          const actor = result.state.combat.participant_records?.find((participant) => participant.is_current_actor);
          setCombatStartNotice(combatResult?.combat_started === true ? `Sıra: ${actor?.name ?? result.state.combat.current_actor_id ?? ''}` : null);
        }
        applyGameState(queryClient, sessionId, result.state, { revision: readRevision, isCurrent: operation.isCurrent });
        if (stillVisible && !stored) setConversationTargetId('');
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
  // A retry resends the stored move; a draft that is still that same text is consumed with it, but text the
  // player changed or typed meanwhile belongs to a later, deliberate move and stays.
  // A card step never carried the composer's draft, so it leaves the draft as it is.
  if (stillVisible && !request.economic_action && (!stored || messageRef.current.trim() === trimmed)) {
    setMessage('');
  }
  // The engine's own receipt for a card step (same text as economicResolutionNotice; kept inline in this closure).
  const receipt = result.economic_resolution;
  if (stillVisible && receipt) {
    const changed = receipt.reason_code === 'stale';
    setNotice({ tone: receipt.status === 'applied' ? 'success' : 'warning', title: 'Teklif',
      detail: changed ? 'Teklif değişti; yeni kart gerekir.' : receipt.public_summary });
  }
        // A card prepare or cancel is not a turn: the engine keeps its undo checkpoint (main.py economic_step), so
        // the undo target and the one-step note stay on the turn before it. A confirm is the engine's to judge.
        const cardStepOnly = result.turn_outcome?.action === 'economic_prepare' || result.turn_outcome?.action === 'economic_cancel';
        if (stillVisible && !cardStepOnly) {
          setLastTurn({ sessionId, actionId, outcome: result.turn_outcome ?? null });
          setUndoneJustNow(false);
        }
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      }).catch((error) => {
        // A superseded or closed screen proves nothing about the server: the pending action stays.
        if (!operation.isCurrent()) return;
        if (activeSessionRef.current !== sessionId) return;
        const failure = statusCode(error) ?? 0;
        const refusal = (error as { data?: { detail?: { not_applied?: unknown; code?: unknown } } } | null)?.data?.detail;
        let evidence: Parameters<typeof closePending>[2];
        if (refusal?.not_applied === true && typeof refusal.code === 'string') evidence = { kind: 'server_not_applied', code: refusal.code };
        // A schema-invalid body proves nothing if the stored request itself was lost or damaged: the original body may have committed.
        else if (failure === 422 && typeof request.message === 'string') evidence = { kind: 'server_rejected', status: failure };
        if (!receiptReceived && evidence) {
          // After a reload the composer is empty and the text lived only in the pending record: give it back.
          // Only a move that came from the composer (it always carries an interaction mode) gives its text back;
          // a pending passive wait has no draft to restore.
          if (!messageRef.current.trim() && request.interaction_mode) setMessage(trimmed);
          // Only the server's own "never applied" answer (or a schema-invalid body) closes the move; the draft stays,
          // and the next Send is a new move with a new UUID. A bare 404/409/500 never gets here.
          closePending(key, 'cancelled', evidence);
          void queryClient.invalidateQueries({ queryKey: getGetGameSessionStateQueryKey(sessionId) });
        }
        const unresolved = Boolean(readPending(ownerId, actionScope));
        const blockedBy = unresolvedActionFrom(error);
        if (blockedBy) {
          // This NEW move was refused (and durably closed) because an earlier action of the campaign is still unresolved,
          // e.g. started in another tab or before a re-login. The draft stays; the player decides, with the server's help.
          setNotice({
            tone: 'warning', title: 'Tamamlanmamış bir hamle var',
            detail: 'Bu kampanyada sonucu henüz kesinleşmemiş bir hamle var (başka bir sekme veya önceki oturum). Yeni hamle uygulanmadı; yazdığın metin taslakta duruyor. Önce o hamlenin durumunu sunucudan kontrol et ya da bilinçli olarak vazgeç.',
            recover: recoveryHandlers(blockedBy.actionId),
          });
          return;
        }
        // An expired budget is an UNKNOWN outcome: the server may have committed it. The draft and the key stay, and only
        // the player's own retry (same id) or the server's verdict can settle it.
        const deadlineExpired = error instanceof ActionDeadlineError || operation.deadlineExpired();
        setNotice({
          tone: deadlineExpired ? 'warning' : 'error',
          title: deadlineExpired ? 'Hamlenin sonucu belirsiz' : statusCode(error) === 503 ? 'Dünya şu an sessiz' : Number(statusCode(error)) >= 500 ? 'Bir aksaklık oldu' : 'Hamle sonuçlanamadı',
          detail: deadlineExpired
            ? 'Süre doldu ve sunucudan yanıt alınamadı; hamle uygulanmış olabilir. Aynı hamleyi yeniden dene: kayıtlı işlem kimliği korunuyor, yazdığın metin taslakta duruyor.'
            : error instanceof ReconciliationError ? RETRY_MESSAGE : friendlyError(error, 'Bu hamleyi şu haliyle gerçekleştiremiyorsun.'),
          ...(unresolved ? { retry: retryPendingTurn, recover: recoveryHandlers() } : {}),
        });
      }).finally(() => {
        inFlightSessionsRef.current.delete(sessionId);
        if (operation.isCurrent()) setInFlightSessions(new Set(inFlightSessionsRef.current));
        operation.close();
    });
  };
  submitTurnRef.current = submitTurn;

  const submitLevelUp = (fresh?: LevelUpRequest) => {
    if (!sessionId || !campaignId || !accountWriteAllowed(currentAuthEpoch()) || inFlightSessionsRef.current.has(sessionId)
      || undoPendingRef.current.has(sessionId) || undoRequestsRef.current.has(sessionId)) return;
    const owner = currentAccountOwner() ?? LOCAL_OWNER;
    const stored = readPending(owner, campaignId);
    if (fresh ? Boolean(stored) : stored?.kind !== 'level_up') { setNotice(pendingTurnNotice()); return; }
    if (fresh) { const blocked = blockingMutation(); if (blocked) { setNotice(blocked); return; } }
    const started = turnLifetime.begin(); if (!started) return;
    const operation = withActionDeadline(started, startDeadline());
    const request = stored ? stored.request as LevelUpRequest : fresh!;
    if (request.campaign_id !== campaignId) { operation.close(); return; }
    let key: ReturnType<typeof createIntentKey>;
    try { key = stored ? resumePending(stored.key, currentAuthEpoch()).key : createIntentKey(owner, campaignId, request, 'level_up'); }
    catch { operation.close(); setNotice(pendingTurnNotice()); return; }
    inFlightSessionsRef.current.add(sessionId);
    setInFlightSessions(new Set(inFlightSessionsRef.current)); setNotice(null);
    void (async () => {
      const response = await applyGameSessionLevelUp(sessionId, { ...request, action_id: key.actionId }, { signal: operation.signal });
      if (!operation.isCurrent()) return;
      if (operation.deadlineExpired()) throw new ActionDeadlineError();
      if (response.action_id !== key.actionId || response.session_id !== sessionId || response.result.status !== 'applied') throw new ReconciliationError();
      await settlePending(key, { kind: 'applied', response }, async () => {
        const revision = nextRevision();
        const snapshot = await reconcileState(queryClient, getGetGameSessionStateQueryKey(sessionId), operation,
          signal => getCampaign(campaignId, { signal }));
        if (!operation.isCurrent() || operation.deadlineExpired()) throw new ReconciliationError();
        if (!applyGameState(queryClient, sessionId, snapshot.state, { revision, isCurrent: operation.isCurrent })) throw new ReconciliationError();
      });
      if (!operation.isCurrent()) return;
      setLastTurn(null);
      setNotice({ tone: 'success', title: `${request.target_level}. seviye seçimleri kaydedildi`, detail: 'Seviye seçimleri sunucudan doğrulandı. Desteklenmeyen etkiler karakter kaydında ayrıca gösterilir.' });
      void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
    })().catch(error => {
      if (!operation.isCurrent()) return;
      if (statusCode(error) === 422) closePending(key, 'cancelled', { kind: 'server_rejected', status: 422 });
      setNotice({ tone: 'warning', title: 'Seviye işlemi doğrulanamadı', detail: error instanceof ReconciliationError ? RETRY_MESSAGE : friendlyError(error, 'İşlem uygulanmış olabilir. Aynı kimlikle yeniden dene veya sunucudan durumunu kontrol et.'),
        ...(readPending(owner, campaignId) ? { retry: retryPendingTurn, recover: recoveryHandlers() } : {}) });
    }).finally(() => {
      inFlightSessionsRef.current.delete(sessionId);
      if (operation.isCurrent()) setInFlightSessions(new Set(inFlightSessionsRef.current));
      operation.close();
    });
  };
  submitLevelUpRef.current = submitLevelUp;


  // Asks the server what it recorded for the unresolved action (or closes it for good on `abandon`). The browser record is
  // only a convenience: a verdict comes from the server's stored receipt or durable refusal, never from a timeout or a 404/503.
  const serverRecovery = async (mode: 'check' | 'abandon', serverActionId?: string, boundSessionId?: string) => {
    // A notice created for another session or campaign must not ask or close an id of this one.
    if (boundSessionId !== undefined && boundSessionId !== sessionId) {
      setNotice((current) => (current?.recover ? null : current));
      return;
    }
    const scope = campaignId || sessionId;
    const storedAny = readPending(currentAccountOwner() ?? LOCAL_OWNER, scope);
    const actionId = serverActionId ?? storedAny?.key.actionId;
    // The local record is settled only when it is the very id being asked about.
    const stored = storedAny && storedAny.key.actionId === actionId ? storedAny : null;
    if (!sessionId || !actionId || inFlightSessionsRef.current.has(sessionId)) return;
    const operation = turnLifetime.begin();
    if (!operation) return;
    inFlightSessionsRef.current.add(sessionId);
    setInFlightSessions(new Set(inFlightSessionsRef.current));
    const reconcileFromServer = async () => {
      const stateKey = getGetGameSessionStateQueryKey(sessionId);
      const readRevision = nextRevision();
      const snapshot = await reconcileState<{ state: GameState; history: CampaignDetail['history'] | null; combat_history: CampaignDetail['combat_history'] | null }>(
        queryClient, stateKey, operation,
        async (signal) => (campaignId
          ? getCampaign(campaignId, { signal })
          : { state: await getGameSessionState(sessionId, { signal }), history: null, combat_history: null }));
      if (!operation.isCurrent()) throw new ReconciliationError();
      const accepted = applyGameState(queryClient, sessionId, snapshot.state, { revision: readRevision, isCurrent: operation.isCurrent });
      if (!accepted) throw new ReconciliationError();
      setCombatStartNotice(null);
      if (snapshot.history) {
        const next: TranscriptEntry[] = historyToEntries(snapshot.history, { opening: snapshot.state.scene?.opening });
        setEntries(next);
        writeAdvisoryCache(`${TRANSCRIPT_KEY}${sessionId}`, JSON.stringify(next.map(({ kind, text, skillCheckResult, undone, undoNote, undoTargetUnknown }) => ({
          kind, text, ...(skillCheckResult ? { skillCheckResult } : {}),
          ...(undone ? { undone } : {}), ...(undoNote ? { undoNote } : {}), ...(undoTargetUnknown ? { undoTargetUnknown } : {}),
        }))));
      }
      if (snapshot.combat_history) setCombatEntries(mergeCombatHistory(snapshot.combat_history));
      void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
    };
    // B3: a settled verdict unlocks only when no unresolved local record is left; anything else stays locked.
    const settled = (status: 'applied' | 'not_applied'): RecoveryState => ({
      status, loading: false, mutationAllowed: !readPending(currentAccountOwner() ?? LOCAL_OWNER, scope), scope,
    });
    const unknownNotice = (detail: string, title = 'Sonuç belirsiz'): Notice => ({
      tone: 'warning', title, detail,
      ...(stored ? { retry: retryPendingTurn } : {}),
      recover: recoveryHandlers(serverActionId), checkLabel: 'Tekrar kontrol et',
      recovery: { status: 'unknown', loading: false, mutationAllowed: false, scope },
    });
    const noticeFor = (verdict: ServerVerdict): Notice => {
      if (verdict.kind === 'applied') {
        // The stored answer may be historical (the move was undone later): the screen shows the server's present, never the old receipt.
        return { tone: 'success', title: 'Hamle sonucu sunucudan alındı', recovery: settled('applied'),
          detail: 'Sunucu bu hamlenin kaydını doğruladı; hamle yeniden gönderilmedi. Ekran sunucudaki güncel durumu gösteriyor: hamle sonradan geri alındıysa geri alınmış hâli görünür. Yeni bir hamle gönderebilirsin.' };
      }
      if (verdict.kind === 'unresolved' && verdict.timedOut) {
        return unknownNotice('Sunucu belirlenen sürede yanıt vermedi. Hamle kaydedilmiş de olabilir, kaydedilmemiş de; ödeme yeniden gönderilmedi. Sonuç doğrulanana kadar yeni hamleler kilitli.');
      }
      if (verdict.kind === 'not_applied') {
        return {
          tone: 'warning', title: 'Hamle uygulanmadı', recovery: settled('not_applied'),
          detail: stored
            ? 'Sunucu bu hamlenin hiç uygulanmadığını ve sonradan da uygulanamayacağını doğruladı. Yazdığın metin taslakta duruyor; istersen yeniden gönderebilirsin.'
            : 'Sunucu bu hamlenin hiç uygulanmadığını ve sonradan da uygulanamayacağını doğruladı. Hamle başka bir sekmeden veya önceki oturumdan kalmıştı; istersen yeni bir hamle gönderebilirsin.',
        };
      }
      return {
        tone: 'warning',
        title: verdict.processing ? 'Hamle şu anda işleniyor' : 'Sunucuda henüz sonuç yok',
        detail: verdict.processing
          ? 'Sunucu bu hamleyi hâlâ işliyor. Biraz sonra durumu yeniden kontrol et; kimlik korunuyor.'
          : 'Sunucu bu hamle için bir sonuç kaydetmedi, ama bu hamlenin hiç uygulanmayacağı anlamına gelmez. Aynı hamleyi yeniden deneyebilir ya da bilinçli olarak vazgeçebilirsin.',
        ...(stored ? { retry: retryPendingTurn } : {}),
        recover: recoveryHandlers(serverActionId),
        recovery: { status: verdict.state === 'unknown' ? 'unknown' : 'unresolved', loading: false, mutationAllowed: false, scope },
      };
    };
    try {
      // Bounded (B3): a silent server ends as `unknown`; the switch to another campaign aborts the wait (operation.signal).
      const verdict = await askServer(RECOVERY_API, mode, sessionId, actionId, { signal: operation.signal });
      if (!operation.isCurrent()) return;
      if (stored) await settlePending(stored.key, verdict, reconcileFromServer);
      else if (verdict.kind === 'applied') await reconcileFromServer();
      // State, story and the last-turn slot come from the same server read: an earlier turn's outcome or undo target is
      // dropped, and a historical answer (an undone move) is never put back as the last turn.
      // A recovered applied move is a turn reply too: the "only the last turn" line no longer applies.
      if (verdict.kind === 'applied') { setLastTurn(null); setUndoneJustNow(false); }
      // A settled verdict also resets the counter panel (its waiting gate and old quote/seq) from the same server read.
      if (verdict.kind === 'applied' || verdict.kind === 'not_applied') setPanelEpoch((epoch) => epoch + 1);
      if (verdict.kind === 'not_applied' && stored && typeof stored.request.message === 'string' && stored.request.interaction_mode && !messageRef.current.trim()) {
        setMessage(stored.request.message);
      }
      setNotice(noticeFor(verdict));
    } catch (error) {
      if (!operation.isCurrent()) return;
      setNotice({
        tone: 'error', title: 'Sunucudan yanıt alınamadı',
        detail: error instanceof ReconciliationError ? RETRY_MESSAGE : friendlyError(error, 'Sunucu bu hamle hakkında bir şey söylemedi. Bu bir iptal kanıtı değildir; hamlenin kimliği korunuyor.'),
        ...(stored ? { retry: retryPendingTurn } : {}),
        recover: recoveryHandlers(serverActionId), checkLabel: 'Tekrar kontrol et',
        recovery: { status: 'unknown', loading: false, mutationAllowed: false, scope },
      });
    } finally {
      inFlightSessionsRef.current.delete(sessionId);
      if (operation.isCurrent()) setInFlightSessions(new Set(inFlightSessionsRef.current));
      operation.close();
    }
  };
  serverRecoveryRef.current = serverRecovery;

  const sessionLabel = useMemo(() => campaignId ? 'Yolculuk sürüyor' : 'Yeni yolculuk', [campaignId]);
  const submitCurrentTurn = () => submitTurn(message, undefined, interactionMode);
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitCurrentTurn();
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
  if (phase === 'reveal' && state) return <CharacterReveal state={state} catalog={characterCatalogQuery.data} onContinue={handleRevealContinue} onBack={() => { setPhase('opening'); setSessionId(''); }} />;
  return (
    <EnvironmentThemeProvider state={state}>
      <div className="design-preview dnd-app play-shell" data-testid="app-session">
        <div className="preview-background">
        <div className="preview-banner"><span>GERÇEK KAMPANYA</span><span>{sessionLabel} · Defter numarası: {campaignId}</span></div>
        {state && <SessionHeader state={state} campaignId={campaignId} onSave={handleSave} saving={saveCampaign.isPending} onReset={reset} onDrawer={(next, opener) => { setPanelOpener(opener); setDrawer(next); }} onOpenCombat={(opener) => { setPanelOpener(opener); setActiveTab('combat'); setDrawer('world'); }} />}
        <div className="preview-layout">
          <nav className="preview-rail" aria-label="Kampanya panelleri">
            <span className="preview-rail-label">YANINDA</span>
            {[
              { id: 'character', label: 'Karakter', icon: Shield },
              { id: 'world', label: 'Dünya', icon: Map },
              { id: 'npcs', label: 'Kişiler', icon: Users },
              { id: 'journal', label: 'Günlük', icon: BookOpen },
              { id: 'combat', label: 'Çatışma', icon: Swords },
            ].map(({ id, label, icon: Icon }) => (
              <div className="preview-rail-item" key={id}>
                <button type="button" aria-controls={`rail-summary-${id}`} aria-expanded={expandedRailPanel === id} onClick={() => setExpandedRailPanel(expandedRailPanel === id ? null : id as RailPanelId)} data-testid={`button-open-panel-${id}`}><Icon size={16} /><span>{label}</span><ChevronDown size={13} /></button>
                {expandedRailPanel === id && state && <div id={`rail-summary-${id}`}><RailSummary panel={id as RailPanelId} state={state} /></div>}
              </div>
            ))}
            {state && <div className="preview-rail-note"><Heart size={14} /><span>Can<br /><strong>{state.character.current_hp} / {state.character.max_hp}</strong></span></div>}
          </nav>
          <main className="preview-play app-main workspace-grid" aria-label="Kampanya hikâyesi">
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
      {campaignId && levelUpEarned(state.character) && <LevelUpControls key={`${currentAccountOwner() ?? LOCAL_OWNER}:${campaignId}:${sessionId}`} sessionId={sessionId} campaignId={campaignId}
        disabled={turnSending || undoBusy || Boolean(blockingMutation())} onConfirm={submitLevelUp} />}
      {state.economic_offer && <EconomicOfferCard key={state.economic_offer.offer_id} offer={state.economic_offer}
        disabled={turnSending || undoBusy || Boolean(blockingMutation())}
        onConfirm={async (offerId, digest) => { submitTurn(ECONOMIC_MESSAGES.confirm, undefined, 'do', false, { kind: 'confirm', offer_id: offerId, confirmation_digest: digest }); }}
        onCancel={async (offerId) => { submitTurn(ECONOMIC_MESSAGES.cancel, undefined, 'do', false, { kind: 'cancel', offer_id: offerId }); }} />}
      {!state.combat.active && <details className="economic-prepare-drawer" data-testid="economic-prepare-drawer">
        <summary>Para ver ya da teklif hazırla</summary>
        <EconomicPrepareControls
        counterparties={(state.npcs ?? []).filter(npc => npc.location === state.location).map(npc => ({ id: npc.id, label: npc.name }))}
        disabled={Boolean(state.economic_offer) || turnSending || undoBusy || Boolean(blockingMutation())}
        onPrepare={async (proposal) => { submitTurn(ECONOMIC_MESSAGES.prepare, undefined, 'do', false, { kind: 'prepare', proposal }); }} />
      </details>}
      {showsCounter(state, campaignId) && <ShopControls key={`${currentAccountOwner() ?? LOCAL_OWNER}:${campaignId}:${sessionId}:${panelEpoch}`} sessionId={sessionId} campaignId={campaignId}
        disabled={turnSending || undoBusy || Boolean(blockingMutation())} outcome={visibleLastTurn?.outcome ?? null} outcomeKey={visibleLastTurn?.actionId ?? null}
        probeKey={shopProbeKey(state)} onTrade={(text) => submitTurn(text, undefined, 'do')} />}
      <StoryColumn
                decisionScope={JSON.stringify([currentAccountOwner() ?? LOCAL_OWNER, campaignId, sessionId])}
                state={state}
                entries={entries}
                readingPreferences={readingPreferences}
                setReadingPreferences={setReadingPreferences}
                composerOpen={composerOpen}
                setComposerOpen={(open) => { if (!open) { primalKnowledgeIntent.choose(false); tacticalMindIntent.choose(false); redrawPrimalKnowledge(value => value + 1); } setComposerOpen(open); }}
                message={message}
                setMessage={setMessage}
                tacticalMindOptIn={tacticalMindIntent.selected}
                onTacticalMindChange={(checked) => { tacticalMindIntent.choose(checked); redrawPrimalKnowledge(value => value + 1); }}
                primalKnowledgeOptIn={primalKnowledgeIntent.selected}
                onPrimalKnowledgeChange={(checked) => { primalKnowledgeIntent.choose(checked); redrawPrimalKnowledge(value => value + 1); }}
                interactionMode={interactionMode}
                setInteractionMode={setInteractionMode}
                conversationTargetId={conversationTargetId}
                setConversationTargetId={setConversationTargetId}
                onEndConversation={() => submitTurn('Konuşmayı bitiriyorum.', undefined, 'do')}
                onNewAdventure={reset}
                onDeathMove={(text) => submitTurn(text, undefined, 'do')}
                sessionId={sessionId}
                campaignId={campaignId}
                onSubmit={handleSubmit}
                onKeyboardSubmit={submitCurrentTurn}
                onEconomyCommand={(text, command) => submitTurn(text, command, 'do')}
                sending={turnSending}
                notice={notice}
                scrollRef={storyScrollRef}
                onScroll={handleStoryScroll}
                resultCue={resultCue}
                newResponseEntryIndex={newResponseEntryIndex}
                onJumpToNewResponse={jumpToNewResponse}
                combatEndNotice={combatEndNotice}
                combatStartNotice={combatStartNotice}
                combatTargetId={combatTargetId}
                setCombatTargetId={setCombatTargetId}
                ambientActionResult={ambientActionResult}
                ambientActionRequest={ambientActionRequest}
                ambientActionSending={resolveAmbientEventAction.isPending}
                ambientActionError={ambientActionError}
                onAmbientAction={handleAmbientAction}
                onRetryAmbientAction={retryAmbientAction}
              />
              <LastTurnBar
                summary={summarizeTurnOutcome(visibleLastTurn?.outcome)}
                canUndo={Boolean(visibleLastTurn) && !state.combat.active}
                recoveringUndo={undoRequestsRef.current.has(sessionId)}
                busy={undoBusy || turnSending}
                onUndo={undoLastTurn}
                combatActive={Boolean(visibleLastTurn) && state.combat.active}
                justUndone={undoneJustNow}
              />
            </>
          ) : <div className="empty-line" data-testid="empty-session-state">Bu günlük henüz bir durum döndürmedi.</div>}
          </main>
        </div>
        {state && <DrawerSheet drawer={drawer} state={state} decisionScope={JSON.stringify([currentAccountOwner() ?? LOCAL_OWNER, campaignId, sessionId])} conversionBlocked={turnSending || undoBusy || Boolean(blockingMutation())} onEconomyCommand={(text, command) => submitTurn(text, command, 'do')} returnFocus={panelOpener} focusAfterCloseRef={focusAfterDrawerCloseRef} onClose={() => setDrawer(null)} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} campaignId={campaignId} sending={turnSending} onExplorationCommand={(text) => submitTurn(text, undefined, 'do')} onSetCombatTarget={setCombatTargetId} onDraft={(text, mode = 'do', targetId) => { setInteractionMode(mode); setConversationTargetId(mode === 'say' ? targetId ?? '' : ''); if (state.combat.active && targetId) setCombatTargetId(targetId); setMessage(text); setComposerOpen(true); }} />}
        <div className="session-footnote" data-testid="text-session-label">
          {sessionLabel} · sahnenin izleri yol boyunca korunur
          {campaignId && <div data-testid="text-campaign-id">Defter numarası: {campaignId}</div>}
        </div>
        </div>
      </div>
    </EnvironmentThemeProvider>
  );
}
