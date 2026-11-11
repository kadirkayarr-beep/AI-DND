import { showsCounter } from '@/lib/play-panels';
import { createPrimalKnowledgeIntent, primalKnowledgeAvailable } from '@/lib/primal-knowledge';
import { tacticalMindAvailable } from '@/components/fighter-controls';
import { LevelUpControls, levelUpEarned, type LevelUpRequest } from '@/components/level-up-controls';
import { ECONOMIC_MESSAGES, EconomicOfferCard, EconomicPrepareControls, ShopControls, shopProbeKey } from '@/components/shop-panel';
import { reconcileState, useActionLifetime, RETRY_MESSAGE, ReconciliationError } from '@/lib/action-reconciliation';
import { closePending, createIntentKey, readPending, resumePending, speciesActionUnresolved } from '@/lib/pending-action';
import { askServer, findUnresolvedOnServer, RecoveryTimeoutError, settlePending, unresolvedActionFrom, type RecoveryApi, type ServerVerdict } from '@/lib/action-recovery';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { type CombatLogEntry } from '@/components/combat-panel';
import { mergeCombatHistory } from '@/lib/combat-history';
import { retainCombatTarget } from '@/lib/combat-ui-contract';
import { clippedControlOverflow, keyboardInset, transcriptFollowsBottom } from '@/lib/play-viewport';
import { removeAdvisoryCache, writeAdvisoryCache } from '@/lib/advisory-cache';
import {
  ambientFollowUpMove,
  createAmbientEventActionRequest,
  isActiveBlueAmbientEvent,
  type AmbientEventActionRequest,
} from '@/components/ambient-event-actions';
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  Heart,
  Map,
  RefreshCw,
  Shield,
  Swords,
  Users,
} from 'lucide-react';
import {
  getGetCampaignsQueryKey,
  getGetCampaignStartOptionsQueryKey,
  getGetCharacterOptionsQueryKey,
  getGetCharacterCreationCatalogQueryKey,
  getGetGameSessionStateQueryKey,
  getGameSessionState,
  useCreateCampaign,
  useGetCampaigns,
  useGetCampaignStartOptions,
  useGetCharacterOptions,
  useGetCharacterCreationCatalog,
  useGetGameSessionState,
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
import { type Notice, type RecoveryState } from '@/components/notice-banner';
import { historyToEntries } from '@/lib/transcript-history';
import { resumeComposerMode } from '@/lib/resume-mode';
import { accountWriteAllowed, currentAccountOwner } from '@/lib/account-session';
import { applyGameState, gameStateScope, nextRevision } from '@/lib/game-state-gate';
import { ActionDeadlineError, startDeadline, withActionDeadline } from '@/lib/action-deadline';
import { gatedStateRead, stateStructuralSharing } from '@/lib/state-envelope';
import type { AmbientEventActionInputAction, AmbientEventResult, CampaignDetail, CampaignStartSelection, CharacterCreateInput, GameState } from '@workspace/api-client-react';
import { type TranscriptEntry } from '@/components/campaign-transcript';
import { readReadingPreferences, writeReadingPreferences } from '@/lib/reading-preferences';
import { EnvironmentThemeProvider } from '@/components/environment-theme';
import { EnvironmentAtmosphere } from '@/components/environment-atmosphere';
import { CampaignLibrary } from '@/components/campaign-library';
import { CharacterCreationScreen } from '@/components/character-creation-screen';
import { playGateSound, primeGateSound } from '@/lib/gate-sound';
import '@/components/cinematic-gate.css';
import '@/components/unwritten-play.css';
import type { CombatActionInput } from '@workspace/api-client-react';
import { getTurnInteractionMetadata, type InteractionMode } from '@/lib/action-suggestions';
import { type Drawer, SessionHeader, DrawerSheet } from '@/pages/game/session-chrome';
import { LOCAL_OWNER, statusCode, friendlyError, OpeningScreen, StateSkeleton } from '@/pages/game/shell-parts';
import { StoryColumn } from '@/pages/game/story-column';
import { type WorldTab, type RailPanelId, RailSummary, DetailsPanel } from '@/pages/game/world-panels';
import { CharacterReveal } from '@/pages/game/character-reveal';

export { DetailsPanel } from '@/pages/game/world-panels';

const LAST_CAMPAIGN_KEY = 'ai-dnd-last-selected-campaign-id';
const TRANSCRIPT_KEY = 'ai-dnd-transcript-';

const RECOVERY_API: RecoveryApi = {
  status: getGameActionStatus, abandon: abandonGameAction, unresolved: getUnresolvedGameAction,
};
const PENDING_TURN_NOTICE: Notice = {
  tone: 'warning',
  title: 'Önceki hamle henüz doğrulanamadı',
  detail: 'Yeni hamle göndermeden önce önceki hamleyi aynı kimlikle yeniden dene. Yazdığın metin taslakta korunuyor.',
};

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
      enabled: phase === 'creation' || phase === 'reveal' || phase === 'adventure',
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
  const [lastTurn, setLastTurn] = useState<{ sessionId: string; actionId: string; outcome: TurnOutcome | null; label?: string | null; purseSpentCp?: number | null } | null>(null);
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
        if (!applyGameState(queryClient, sessionId, snapshot.state, { revision: readRevision, isCurrent })) throw new ReconciliationError();
        if (snapshot.history) {
          setEntries(historyToEntries(snapshot.history, { opening: snapshot.state.scene?.opening }));
        }
        if (snapshot.combat_history) setCombatEntries(mergeCombatHistory(snapshot.combat_history));
        // Undo invalidates an open quote even when the same vendor remains here.
        setPanelEpoch((epoch) => epoch + 1);
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
  const storyLayoutRef = useRef<{ width: number; height: number; contentHeight: number; top: number } | null>(null);
  const storyLayoutScrollTopRef = useRef<number | null>(null);
  const readStoryLayout = (node: HTMLDivElement) => ({
    width: node.clientWidth, height: node.clientHeight, contentHeight: node.scrollHeight, top: node.scrollTop,
  });
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
    storyLayoutRef.current = readStoryLayout(node);
    const observer = new ResizeObserver(() => {
      const previous = storyLayoutRef.current;
      const current = readStoryLayout(node);
      if (previous && (previous.width !== current.width || previous.height !== current.height
        || previous.contentHeight !== current.contentHeight)) {
        // A resize can clamp scrollTop and queue scroll after this callback.
        if (previous.top !== current.top) storyLayoutScrollTopRef.current = current.top;
      }
      storyLayoutRef.current = current;
      if (transcriptFollowsBottom(wasAtBottom.current)) scrollStoryToBottom(node);
    });
    // The reader can shrink without changing the transcript content box.
    observer.observe(node);
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

  const handleStoryScroll = (event?: { currentTarget: EventTarget | null }) => {
    const node = storyScrollRef.current;
    if (!node) return;
    // Moving the document does not express reading intent in this own scroller.
    if (event?.currentTarget === window && node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
    const previous = storyLayoutRef.current;
    const current = readStoryLayout(node);
    storyLayoutRef.current = current;
    const layoutScrollTop = storyLayoutScrollTopRef.current;
    storyLayoutScrollTopRef.current = null;
    // Layout can dispatch scroll before ResizeObserver. Keep the preference
    // from before that resize; genuine same-layout scrolling still updates it.
    if ((previous && (previous.width !== current.width || previous.height !== current.height
      || previous.contentHeight !== current.contentHeight)) || layoutScrollTop === node.scrollTop) {
      if (transcriptFollowsBottom(wasAtBottom.current)) scrollStoryToBottom(node);
      return;
    }
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
    // Görev 26: the purse before this move, for the undo confirmation; a retried stored move cannot know it.
    const purseBefore = stored ? null : state?.wallet?.total_cp ?? null;
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
        // Prepare/cancel and non-consuming confirm refusals retain the engine's previous undo checkpoint.
        // Other refusals consume the card and are turns, just like applied confirmations.
        const nonConsumingConfirm = result.turn_outcome?.action === 'economic_confirm'
          && receipt?.status === 'refused'
          && ['offer_not_prepared', 'digest_mismatch', 'stale'].includes(receipt.reason_code ?? '');
        const cardStepOnly = result.turn_outcome?.action === 'economic_prepare'
          || result.turn_outcome?.action === 'economic_cancel' || nonConsumingConfirm;
        if (stillVisible && !cardStepOnly) {
          const purseAfter = snapshot.state.wallet?.total_cp ?? null;
          setLastTurn({ sessionId, actionId, outcome: result.turn_outcome ?? null,
            // A card's fixed words name nothing: its engine summary names the turn instead.
            label: receipt?.public_summary ?? (request.economic_action ? null : trimmed),
            purseSpentCp: purseBefore !== null && purseAfter !== null ? purseBefore - purseAfter : null });
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
        <EnvironmentAtmosphere />
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
      <StoryColumn
                topControls={<>
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
                </>}
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
                turnLabel={visibleLastTurn?.label}
                purseSpentCp={visibleLastTurn?.purseSpentCp}
              />
            </>
          ) : <div className="empty-line" data-testid="empty-session-state">Bu günlük henüz bir durum döndürmedi.</div>}
          </main>
        </div>
        {state && <DrawerSheet drawer={drawer} state={state} catalog={characterCatalogQuery.data} decisionScope={JSON.stringify([currentAccountOwner() ?? LOCAL_OWNER, campaignId, sessionId])} conversionBlocked={turnSending || undoBusy || Boolean(blockingMutation())} onEconomyCommand={(text, command) => submitTurn(text, command, 'do')} returnFocus={panelOpener} focusAfterCloseRef={focusAfterDrawerCloseRef} onClose={() => setDrawer(null)} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} campaignId={campaignId} sending={turnSending} onExplorationCommand={(text) => submitTurn(text, undefined, 'do')} onSetCombatTarget={setCombatTargetId} onDraft={(text, mode = 'do', targetId) => { setInteractionMode(mode); setConversationTargetId(mode === 'say' ? targetId ?? '' : ''); if (state.combat.active && targetId) setCombatTargetId(targetId); setMessage(text); setComposerOpen(true); }} />}
        <div className="session-footnote" data-testid="text-session-label">
          {sessionLabel} · sahnenin izleri yol boyunca korunur
          {campaignId && <div data-testid="text-campaign-id">Defter numarası: {campaignId}</div>}
        </div>
        </div>
      </div>
    </EnvironmentThemeProvider>
  );
}
