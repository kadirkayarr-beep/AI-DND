import { CombatStatusStrip, CombatTransitionBanner } from '@/components/combat-status-strip';
import { PrimalKnowledgeControl } from '@/components/primal-knowledge-controls';
import { TacticalMindControl } from '@/components/fighter-controls';
import { useEffect, useRef, type FormEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { DeathEndNotice, DeathRecoveryControls } from '@/components/death-recovery-controls';
import { RestControls } from '@/components/rest-controls';
import {
  AmbientEventActionPanel,
  findPersistedAmbientEventResult,
  type AmbientEventActionRequest,
} from '@/components/ambient-event-actions';
import {
  ChevronLeft,
  ChevronRight,
  Feather,
  MessageCircle,
  RefreshCw,
  Send,
} from 'lucide-react';
import { NoticeBanner, type Notice } from '@/components/notice-banner';
import type { AmbientEventActionInputAction, AmbientEventResult, GameState } from '@workspace/api-client-react';
import { Transcript, type TranscriptEntry } from '@/components/campaign-transcript';
import { ReadingSettings } from '@/components/reading-settings';
import { type ReadingPreferences } from '@/lib/reading-preferences';
import { ActionEconomyPanel } from '@/components/action-economy-panel';
import { OuroborosMark } from '@/components/ouroboros-mark';
import type { CombatActionInput } from '@workspace/api-client-react';
import { getTurnInteractionMetadata, type InteractionMode } from '@/lib/action-suggestions';
import { Kicker } from '@/pages/game/shell-parts';
import { SceneIdeas } from '@/pages/game/world-panels';

const PREVIOUS_INTERACTION_MODE: Record<InteractionMode, InteractionMode> = { do: 'ask_dm', say: 'do', ask_dm: 'say' };

const NEXT_INTERACTION_MODE: Record<InteractionMode, InteractionMode> = { do: 'say', say: 'ask_dm', ask_dm: 'do' };

export function StoryColumn({
  topControls,
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
  topControls?: ReactNode;
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
  // Plan part L: once the character is dead the writing box closes; only the final call into the dark may still be written.
  const lastCall = state.death_state?.status === 'dead' && Boolean(state.death_state.last_call_open);
  const writingClosed = state.death_state?.status === 'dead' && !lastCall;
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
        {topControls}
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
      {notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}
      {state.conversation.active && state.conversation.interlocutor && (
          <div className="active-interlocutor" role="status" data-testid="active-interlocutor">
            <MessageCircle size={13} aria-hidden="true" />
            <span>Konuşuyorsun: <strong>{state.conversation.interlocutor.name}</strong></span>
            <button className="action-suggestion" type="button" disabled={sending} onClick={onEndConversation} data-testid="button-end-conversation">Konuşmayı bitir</button>
          </div>
      )}
      <DeathEndNotice state={state} onNewAdventure={onNewAdventure} />
      <RestControls state={state} onSend={onDeathMove} sending={sending} />
      {state.character.current_hp === 0 && <DeathRecoveryControls state={state} sessionId={sessionId} campaignId={campaignId} onSend={onDeathMove} sending={sending} />}
      <SceneIdeas state={state} recentText={entries.at(-1)?.text ?? ''} sending={sending} onDraft={(text, mode = 'do', targetId) => {
        setInteractionMode(mode);
        setConversationTargetId(mode === 'say' ? targetId ?? '' : '');
        if (state.combat.active && targetId) setCombatTargetId(targetId);
        setMessage(text);
        setComposerOpen(true);
        messageInputRef.current?.focus();
      }} />
      </div>
      <div className="story-reading-column">
      <Transcript entries={entries} scrollRef={scrollRef} onScroll={onScroll} readingPreferences={readingPreferences} resultCue={resultCue} newResponseEntryIndex={newResponseEntryIndex} onJumpToNewResponse={onJumpToNewResponse} />
      {!composerOpen && !writingClosed && <button ref={composerTriggerRef} className="dnd-button turn-open-button" type="button" disabled={sending} data-testid="button-open-composer" onClick={() => setComposerOpen(true)}><Send size={15} aria-hidden="true" /> {lastCall ? 'Karanlığa seslen' : 'Hamle yap'}</button>}
      {composerOpen && !writingClosed && <div className="command-box" data-testid="command-box">
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
      </div>
    </section>
  );
}
