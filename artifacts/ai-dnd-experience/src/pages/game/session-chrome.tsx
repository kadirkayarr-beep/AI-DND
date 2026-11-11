import { useEffect, useRef } from 'react';
import { type CombatLogEntry } from '@/components/combat-panel';
import { focusReturnTarget } from '@/lib/play-viewport';
import {
  Feather,
  Heart,
  MapPinned,
  Menu,
  Palette,
  Plus,
  RefreshCw,
  Save,
  Shield,
  Swords,
  X,
} from 'lucide-react';
import type { GameState } from '@workspace/api-client-react';
import { CampaignDate } from '@/components/campaign-context-panel';
import type { CombatActionInput } from '@workspace/api-client-react';
import { type InteractionMode } from '@/lib/action-suggestions';
import { Kicker } from '@/pages/game/shell-parts';
import { AppearanceSettingsPanel } from '@/components/appearance-settings-panel';
import { type WorldTab, LeftColumn, WorldTabs } from '@/pages/game/world-panels';

export type Drawer = 'character' | 'world' | 'settings' | null;

export function SessionHeader({ state, campaignId, onSave, saving, onReset, onDrawer, onOpenCombat }: { state: GameState; campaignId: string; onSave: () => void; saving: boolean; onReset: () => void; onDrawer: (drawer: Exclude<Drawer, null>, opener: HTMLElement) => void; onOpenCombat: (opener: HTMLElement) => void }) {
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
          <button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-settings" onClick={(event) => onDrawer('settings', event.currentTarget)}><Palette size={14} /> Görünüm</button>
          <div className="session-chip" data-testid="status-session"><span className="health-dot" /> <span className="hidden sm:inline">MACERA</span></div>
          <button className="dnd-button secondary" type="button" onClick={onSave} disabled={saving} data-testid="button-save-campaign">{saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} <span>Kaydet</span></button>
          <button className="dnd-button secondary !px-3" type="button" onClick={onReset} data-testid="button-new-session"><Plus size={13} /> Ana ekrana dön</button>
        </div>
      </div>
    </header>
  );
}

export function DrawerSheet({ drawer, state, catalog, decisionScope, conversionBlocked, onEconomyCommand, onClose, returnFocus, focusAfterCloseRef, activeTab, setActiveTab, combatEntries, sessionId, campaignId, sending, onExplorationCommand, onDraft, onSetCombatTarget }: { drawer: Drawer; state: GameState; catalog?: unknown; decisionScope?: string; conversionBlocked?: boolean; onEconomyCommand?: (message: string, command: CombatActionInput) => void; onClose: () => void; returnFocus: HTMLElement | null; focusAfterCloseRef: React.MutableRefObject<'opener' | 'composer'>; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void; combatEntries: CombatLogEntry[]; sessionId: string; campaignId: string; sending: boolean; onExplorationCommand: (message: string) => void; onDraft: (message: string, mode?: InteractionMode, targetId?: string) => void; onSetCombatTarget: (targetId: string) => void }) {
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
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><section ref={dialogRef} className="drawer-sheet" role="dialog" aria-modal="true" aria-label={drawer === 'character' ? 'Karakter paneli' : drawer === 'settings' ? 'Görünüm ayarları' : 'Dünyanın çevresi'} tabIndex={-1} onClick={(event) => event.stopPropagation()}><div className="drawer-heading"><Kicker>{drawer === 'character' ? 'Yolcu' : drawer === 'settings' ? 'Görünüm' : 'Dünyanın çevresi'}</Kicker><button className="icon-button" type="button" aria-label="Paneli kapat" data-testid="button-close-drawer" onClick={onClose}><X size={16} /></button></div>{drawer === 'character' ? <LeftColumn state={state} catalog={catalog} decisionScope={decisionScope} conversionBlocked={conversionBlocked} onCommand={onEconomyCommand} /> : drawer === 'settings' ? <AppearanceSettingsPanel /> : <WorldTabs state={state} activeTab={activeTab} setActiveTab={setActiveTab} combatEntries={combatEntries} sessionId={sessionId} campaignId={campaignId} sending={sending} onExplorationCommand={onExplorationCommand} onDraft={(message, mode, targetId) => { focusAfterCloseRef.current = 'composer'; onDraft(message, mode, targetId); onClose(); }} onSetCombatTarget={onSetCombatTarget} />}</section></div>;
}
