import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Backpack,
  BookOpen,
  Check,
  CircleDot,
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
  getGetCharacterOptionsQueryKey,
  getGetGameHealthQueryKey,
  getGetGameSessionStateQueryKey,
  useCreateCampaign,
  useGetGameHealth,
  useGetCampaigns,
  useGetCharacterOptions,
  useGetGameSessionState,
  usePlayGameTurn,
  useResumeCampaign,
  useSaveCampaign,
} from '@workspace/api-client-react';
import type { CampaignHistoryEntry, CharacterCreateInput, GameCharacter, GameDoor, GameNpc, GameState } from '@workspace/api-client-react';
import { EnvironmentThemeProvider } from '@/components/environment-theme';
import { CampaignLibrary } from '@/components/campaign-library';
import { CharacterCreationScreen } from '@/components/character-creation-screen';

const LAST_CAMPAIGN_KEY = 'ai-dnd-last-selected-campaign-id';
const TRANSCRIPT_KEY = 'ai-dnd-transcript-';

type Notice = { tone: 'error' | 'success' | 'warning'; title: string; detail: string };
type TranscriptEntry = { kind: 'player' | 'narration'; text: string };
type Drawer = 'character' | 'world' | null;
type WorldTab = 'world' | 'npcs' | 'journal' | 'combat';

function statusCode(error: unknown) {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return candidate.status ?? candidate.statusCode ?? candidate.response?.status;
}

function friendlyError(error: unknown, fallback: string) {
  const code = statusCode(error);
  if (code === 404) return 'Bu macera kaydı bulunamadı.';
  if (code === 422) return 'Motor bu mesajı kabul etmedi. Bir iletinin 1–4000 karakter arasında olduğundan emin ol.';
  if (code === 503) return 'Dungeon Master’a şu anda ulaşılamıyor.';
  if (typeof navigator !== 'undefined' && !navigator.onLine) return 'Bağlantı yok. İnternet bağlantını kontrol edip tekrar dene.';
  return fallback;
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand" data-testid="brand-ai-dnd">
      <div className="brand-mark"><Compass size={17} strokeWidth={1.3} /></div>
      {!compact && <div><div className="brand-name">AI DUNGEON MASTER</div><div className="brand-subtitle">Solo campaign · Sword Coast</div></div>}
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
    <div className="tavern-frame dnd-enter dnd-delay-1" data-testid="artwork-tavern">
      <div className="tavern-scene">
        <div className="wood-planks" />
        <div className="tavern-glow" />
        <div className="candle" style={{ left: '24%', top: '16%' }} />
        <div className="candle" style={{ right: '23%', top: '24%', transform: 'scale(.8)' }} />
        <div className="hearth"><div className="hearth-fire" /></div>
        <div className="tavern-caption"><Kicker>Yolun başladığı yer</Kicker><div className="tavern-title">KÜL VE KUPA</div></div>
        <div className="tavern-seal"><Compass size={18} strokeWidth={1} /></div>
      </div>
      <div className="tavern-note"><Sparkles size={12} /> Yağmurun ardından, bir kapı aralanır</div>
    </div>
  );
}

function EngineHealth() {
  const health = useGetGameHealth({ query: { queryKey: getGetGameHealthQueryKey(), staleTime: 30_000, retry: 1 } });
  const ready = Boolean(health.data && ['ok', 'healthy', 'ready'].includes(health.data.status.toLowerCase()));
  return (
    <aside className="dnd-card dnd-texture p-5 md:p-7" data-testid="panel-engine-health">
      <div className="relative z-10">
        <div className="flex items-center gap-2"><Wifi size={14} /><Kicker>Motor bağlantısı</Kicker></div>
        <h2 className="dnd-display mt-3 text-xl tracking-wide text-[#decdaa]">{health.isLoading ? 'Kapı yoklanıyor.' : ready ? 'Kapı şu an açık.' : 'Kapı sessiz.'}</h2>
        <p className="dnd-serif mt-2 text-[17px] leading-6 text-[#94866e]">Python motoru mekanikleri doğrular; tarayıcı yalnızca senin sözlerini taşır.</p>
        {health.isLoading ? (
          <div className="mt-7 grid gap-2" data-testid="health-loading">{[1, 2].map((item) => <div className="dnd-skeleton h-10 rounded-sm" key={item} />)}</div>
        ) : health.isError ? (
          <div className="notice error mt-6" data-testid="error-health"><span>Sağlık bilgisi alınamadı.</span><button type="button" data-testid="button-retry-health" onClick={() => void health.refetch()}>Tekrar dene</button></div>
        ) : (
          <div className="mt-6" data-testid="status-health">
            {[['Durum', health.data?.status ?? 'bilinmiyor'], ['Motor', health.data?.engine ?? '—'], ['Model', health.data?.model ?? '—']].map(([label, value], index) => (
              <div className={`flex items-center justify-between py-3 text-sm ${index < 2 ? 'border-b border-[#4b3926]' : ''}`} key={label}>
                <span className="text-[#897b65]">{label}</span><span className="flex items-center gap-2 font-mono text-xs"><span className={`health-dot ${ready ? '' : 'bad'}`} />{value}</span>
              </div>
            ))}
          </div>
        )}
        <div className="mt-6 flex items-center gap-2 text-[10px] text-[#83745e]"><Shield size={13} /> Mekanik sonuçları istemci tarafından üretilmez.</div>
      </div>
    </aside>
  );
}

function OpeningScreen({ onCreate, onContinue, creating, notice, loadingCampaigns, hasCampaigns, showNoCampaigns }: { onCreate: () => void; onContinue: () => void; creating: boolean; notice: Notice | null; loadingCampaigns: boolean; hasCampaigns: boolean; showNoCampaigns: boolean }) {
  return (
    <main className="opening" data-testid="app-start">
      <div className="dnd-shell">
        <header className="opening-header">
          <Brand />
          <span className="hidden font-mono text-[9px] uppercase tracking-[.2em] text-[#8f8069] md:block">Bir hikâye, yalnızca senin</span>
        </header>
        <div className="opening-grid">
          <section className="opening-copy dnd-enter">
            <div className="opening-eyebrow"><Kicker>Kapılar açılıyor · 1492 DR</Kicker></div>
            <h1 className="opening-title">Hikâyeni<br /><span>anlat.</span></h1>
            <p className="opening-lede dnd-serif">Dünya cevap versin.</p>
            <p className="opening-body">Yağmurun izini kapıda bırak. Dünya kendi kurallarını korurken ilk adımı kendi sözlerinle at.</p>
            <div className="opening-actions">
              <button className="dnd-button" type="button" data-testid="button-create-session" disabled={creating} onClick={onCreate}>
                {creating ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRight size={14} />} {creating ? 'Dünya kuruluyor' : 'Yeni macera'}
              </button>
              <button className="dnd-button secondary" type="button" data-testid="button-continue-session" disabled={loadingCampaigns} onClick={onContinue}>
                {loadingCampaigns ? <RefreshCw size={14} className="animate-spin" /> : <BookOpen size={14} />} Maceraya devam et
              </button>
            </div>
            {showNoCampaigns && !hasCampaigns && <div className="continue-note" data-testid="text-no-session">Henüz kayıtlı macera yok. Yeni maceranı sunucuya kaydedebilirsin.</div>}
            {notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}
            <div className="opening-meta"><span>TEK OYUNCU</span><span className="meta-dot" /><span>DOĞAL DİLLE</span><span className="meta-dot" /><span>SENİN SEÇİMİN</span></div>
          </section>
          <section className="opening-art"><TavernArtwork /></section>
        </div>
        <div className="mx-auto mt-8 w-full max-w-[1440px]"><EngineHealth /></div>
      </div>
    </main>
  );
}

function CharacterPanel({ character, compact = false }: { character: GameCharacter; compact?: boolean }) {
  const abilities = [['KUV', character.strength], ['ÇEV', character.dexterity], ['DAY', character.constitution], ['ZEK', character.intelligence], ['BİL', character.wisdom], ['KAR', character.charisma]];
  const hp = character.max_hp > 0 ? Math.max(0, Math.min(100, character.current_hp / character.max_hp * 100)) : 0;
  return (
    <section className={`state-panel ${compact ? 'compact-character' : ''}`} data-testid="panel-character">
      <div className="character-top"><div><Kicker>Yolcu kaydı</Kicker><h2 data-testid="text-character-name">{character.name}</h2><div className="character-sub">{character.race} {character.class} · Seviye {character.level}</div></div><span className="character-badge">LVL {String(character.level).padStart(2, '0')}</span></div>
      <div className="health-row"><span className="flex items-center gap-2"><Heart size={13} /> Can durumu</span><span data-testid="text-character-hp">{character.current_hp} / {character.max_hp}</span></div>
      <div className="health-track"><div className="health-fill" style={{ width: `${hp}%` }} data-testid="meter-health" /></div>
      <div className="key-values"><div className="key-value"><Kicker>ZIRH</Kicker><span>{character.armor_class}</span></div><div className="key-value"><Kicker>USTALIK</Kicker><span>+{character.proficiency_bonus}</span></div></div>
      {!compact && <div className="mt-5"><Kicker>Özellikler · motor kaydı</Kicker><div className="stat-strip">{abilities.map(([label, value]) => <div className="stat-box" key={label}><Kicker>{label}</Kicker><div className="stat-value">{value}</div></div>)}</div></div>}
      {!compact && <div className="mt-5 border-t border-[#4b3926] pt-4"><Kicker>Usta olunan beceriler</Kicker><div className="mt-3 flex flex-wrap gap-2">{character.proficient_skills.length ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skill}</span>) : <span className="subtle-text">Motor henüz beceri kaydetmedi.</span>}</div></div>}
    </section>
  );
}

function InventoryPanel({ items }: { items: string[] }) {
  return <section className="state-panel" data-testid="panel-inventory"><div className="flex items-end justify-between"><div><Kicker>Üzerinde</Kicker><h2>Envanter</h2></div><span className="character-badge">{String(items.length).padStart(2, '0')}</span></div>{items.length ? <div className="list-stack">{items.map((item, index) => <div className="list-row" key={`${item}-${index}`} data-testid={`item-inventory-${index}`}><span className="list-icon"><Backpack size={14} /></span>{item}</div>)}</div> : <div className="empty-line mt-4">Çantada kaydedilmiş eşya yok.</div>}</section>;
}

function WorldPanel({ state }: { state: GameState }) {
  const locations = Object.values(state.locations);
  return <section className="state-panel" data-testid="panel-world"><div className="flex items-end justify-between"><div><Kicker><Map size={12} className="mr-1 inline" /> Kamuya açık dünya</Kicker><h2>Çevre</h2></div></div><div className="location-current" data-testid="text-current-location"><small><MapPinned size={11} className="mr-1 inline" /> Şu anki konum</small>{state.locations[state.location]?.name ?? state.location}</div><div className="mt-3 grid gap-2">{locations.length ? locations.map((location) => <div className="data-row" key={location.id} data-testid={`location-${location.id}`}><div className="data-row-head"><span>{location.name}</span>{location.id === state.location && <Check size={14} className="text-[#c09a61]" />}</div><div className="data-row-meta">{location.type}</div><div className="data-row-desc">{location.description}</div></div>) : <div className="empty-line">Motor konum kaydetmedi.</div>}</div></section>;
}

function PeoplePanel({ npcs }: { npcs: GameNpc[] }) {
  return <section className="state-panel" data-testid="panel-npcs"><div className="flex items-end justify-between"><div><Kicker><Users size={12} className="mr-1 inline" /> Karşılaşılanlar</Kicker><h2>Kişiler</h2></div><span className="character-badge">{String(npcs.length).padStart(2, '0')}</span></div><div className="mt-4">{npcs.length ? npcs.map((npc) => <div className="data-row" key={npc.id} data-testid={`npc-${npc.id}`}><div className="data-row-head"><span>{npc.name}</span>{npc.combat_status && <span className="status-pill">{npc.combat_status}</span>}</div><div className="data-row-meta">{npc.role} · {npc.location}</div>{npc.appearance && <div className="data-row-desc">{npc.appearance}</div>}{(npc.relationship || npc.current_hp !== null || npc.armor_class !== null) && <div className="mt-3 flex flex-wrap gap-3 border-t border-[#4b3926] pt-2 font-mono text-[9px] text-[#83745e]">{npc.relationship && <span>İlişki: {npc.relationship}</span>}{npc.current_hp !== null && npc.max_hp !== null && <span>Can: {npc.current_hp}/{npc.max_hp}</span>}{npc.armor_class !== null && <span>Zırh: {npc.armor_class}</span>}</div>}</div>) : <div className="empty-line">Bu bölgede tanınan kişi yok.</div>}</div></section>;
}

function DetailsPanel({ state }: { state: GameState }) {
  return <section className="state-panel" data-testid="panel-details"><Kicker><DoorOpen size={12} className="mr-1 inline" /> İncelenebilir</Kicker><h2>Ayrıntılar</h2><div className="mt-4">{state.doors.length ? state.doors.map((door: GameDoor) => <div className="data-row" key={door.id} data-testid={`door-${door.id}`}><div className="data-row-head"><span className="flex items-center gap-2">{door.locked ? <LockKeyhole size={14} className="text-[#bc7062]" /> : <KeyRound size={14} className="text-[#c09a61]" />}{door.name}</span><span className="status-pill">{door.broken ? 'kırık' : door.open ? 'açık' : door.locked ? 'kilitli' : 'kapalı'}</span></div><div className="data-row-desc">{door.description}</div></div>) : <div className="empty-line">Kapı veya geçit kaydedilmedi.</div>}</div><Rule /><div className="mt-4"><Kicker>Çevredeki özellikler</Kicker><div className="mt-3">{state.features.length ? state.features.map((feature, index) => <div className="border-l border-[#866942] pl-3" key={`${feature.name}-${index}`} data-testid={`feature-${index}`}><div className="font-serif text-[17px] text-[#d1c2a6]">{feature.name}</div><div className="subtle-text mt-1">{feature.description}</div></div>) : <div className="empty-line">Motor çevre özelliği kaydetmedi.</div>}</div></div></section>;
}

function CombatPanel({ state }: { state: GameState }) {
  const combat = state.combat;
  const active = Boolean(combat.active);
  return <section className="state-panel" data-testid="panel-combat"><Kicker><Swords size={12} className="mr-1 inline" /> Motor durumu</Kicker><h2>Çatışma</h2><div className={`mt-4 border p-3 ${active ? 'border-[#9c5646] bg-[#5e2e26]/15' : 'border-[#4b3926] bg-[#211a14]'}`}><div className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><CircleDot size={13} className={active ? 'text-[#c66b56]' : 'text-[#817662]'} />{active ? 'Çatışma sürüyor' : 'Çatışma yok'}</span>{typeof combat.round === 'number' && <span className="font-mono text-[10px] text-[#83745e]">Tur {combat.round}</span>}</div>{active && combat.initiative_order?.length ? <div className="mt-3 border-t border-[#4b3926] pt-3"><Kicker>İnisiyatif</Kicker><div className="mt-2 flex flex-wrap gap-2">{combat.initiative_order.map((participant, index) => <span className="status-pill" key={`${participant}-${index}`}>{participant}</span>)}</div></div> : null}{active && typeof combat.current_turn_index === 'number' && <div className="mt-3 border-t border-[#4b3926] pt-3 text-sm text-[#b7a88c]">Sıra indeksi: {combat.current_turn_index}</div>}{state.player_combat_status && <div className="mt-3 border-t border-[#4b3926] pt-3 text-sm text-[#b7a88c]">{state.player_combat_status}</div>}</div></section>;
}

function LeftColumn({ state }: { state: GameState }) {
  return <aside className="state-column workspace-left" data-testid="panel-character-column"><CharacterPanel character={state.character} /><InventoryPanel items={state.inventory} /></aside>;
}

function JournalPanel({ entries }: { entries: TranscriptEntry[] }) {
  return (
    <section className="state-panel" data-testid="panel-journal">
      <Kicker><BookOpen size={12} className="mr-1 inline" /> Bu cihazdaki anlatı</Kicker>
      <h2>Günlük</h2>
      <p className="subtle-text mt-3">Bu geçmiş yalnızca bu tarayıcıya kaydedilir; kanonik kampanya kaydı sunucudadır.</p>
      {entries.length ? (
        <ol className="journal-entries" aria-label="Bu cihazdaki başarılı turlar">
          {entries.map((entry, index) => (
            <li className={entry.kind === 'player' ? 'journal-entry journal-entry-player' : 'journal-entry'} key={`${entry.kind}-${index}`} data-testid={`journal-entry-${index}`}>
              <span>{entry.kind === 'player' ? 'Sen · yerel kayıt' : 'Dungeon Master · sunucu anlatısı'}</span>
              <p>{entry.text}</p>
            </li>
          ))}
        </ol>
      ) : <div className="empty-line mt-4">Henüz bu tarayıcıda kaydedilmiş başarılı bir tur yok.</div>}
    </section>
  );
}

function WorldTabs({ state, entries, activeTab, setActiveTab }: { state: GameState; entries: TranscriptEntry[]; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void }) {
  const tabs: { id: WorldTab; label: string }[] = [{ id: 'world', label: 'DÜNYA' }, { id: 'npcs', label: 'NPC’LER' }, { id: 'journal', label: 'GÜNLÜK' }, { id: 'combat', label: 'ÇATIŞMA' }];
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
            className={activeTab === tab.id ? 'active' : ''}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
            data-testid={`tab-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="world-panel-content" aria-labelledby={`tab-${activeTab}`} tabIndex={0}>
        {activeTab === 'world' && <><WorldPanel state={state} /><DetailsPanel state={state} /></>}
        {activeTab === 'npcs' && <PeoplePanel npcs={state.npcs} />}
        {activeTab === 'journal' && <JournalPanel entries={entries} />}
        {activeTab === 'combat' && <CombatPanel state={state} />}
      </div>
    </aside>
  );
}

function Transcript({ entries, scrollRef, onScroll }: { entries: TranscriptEntry[]; scrollRef: RefObject<HTMLDivElement | null>; onScroll: () => void }) {
  if (!entries.length) return <div className="empty-line mt-4" data-testid="empty-transcript">İlk hamleni yaz. Dünya, sunucunun onayladığı bir yanıtla karşılık verecek.</div>;
  return <div className="transcript-scroll" ref={scrollRef} onScroll={onScroll} data-testid="transcript-scroll" tabIndex={0} aria-label="Hikâye akışı"><div className="mt-2" data-testid="transcript-local">{entries.map((entry, index) => entry.kind === 'player' ? <div className="player-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-player-${index}`}><div className="player-label"><MessageCircle size={12} /> Sen · yerel kayıt</div>{entry.text}</div> : <div className="story-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-narration-${index}`}><p className="story-text">{entry.text}</p></div>)}</div><div className="reader-note">Yerel anlatı kaydı · kanonik dünya durumu sağ panelde</div></div>;
}

function StoryColumn({ state, entries, message, setMessage, onSubmit, sending, notice, scrollRef, onScroll, locationChanged }: { state: GameState; entries: TranscriptEntry[]; message: string; setMessage: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; sending: boolean; notice: Notice | null; scrollRef: RefObject<HTMLDivElement | null>; onScroll: () => void; locationChanged: boolean }) {
  const location = state.locations[state.location];
  return <section className="story-column workspace-story" data-testid="panel-story"><div className="story-heading"><div className="story-icon"><Feather size={15} strokeWidth={1.25} /></div><div><Kicker>Dungeon Master · sunucu anlatısı</Kicker><div className="story-meta mt-1">Başarılı turlar yerel olarak gösterilir</div></div><div className="ml-auto story-meta hidden sm:block">Tur {state.turn_index}</div></div><div className={`location-ribbon ${locationChanged ? 'location-ribbon-new' : ''}`} data-testid="status-location"><MapPinned size={14} /><div><Kicker>Şu anki konum</Kicker><strong>{location?.name ?? state.location}</strong>{location?.type && <span>{location.type}</span>}</div></div><Transcript entries={entries} scrollRef={scrollRef} onScroll={onScroll} />{notice && <div className="mt-5"><NoticeBanner notice={notice} /></div>}<div className="command-box"><form className="command-form" onSubmit={onSubmit}><label className="sr-only" htmlFor="player-message">Hamleni anlat</label><textarea id="player-message" className="command-input" value={message} maxLength={4000} onChange={(event) => setMessage(event.target.value)} placeholder="Ne yapmak istiyorsun?" data-testid="input-player-message" disabled={sending} /><button className="dnd-button" type="submit" disabled={sending || !message.trim()} data-testid="button-send-turn">{sending ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}{sending ? 'Motor düşünüyor' : 'Gönder'}</button></form><div className="command-help"><span>Doğal dil · 1–4000 karakter · Python karar verir</span><span data-testid="text-message-count">{message.length} / 4000</span></div></div></section>;
}

function SessionHeader({ state, campaignId, onSave, saving, onReset, onDrawer }: { state: GameState; campaignId: string; onSave: () => void; saving: boolean; onReset: () => void; onDrawer: (drawer: Exclude<Drawer, null>) => void }) {
  return <header className="app-header"><div className="dnd-shell app-header-inner"><Brand /><div className="header-location"><MapPinned size={13} /><div className="header-location-copy"><span data-testid="header-location">{state.locations[state.location]?.name ?? state.location}</span><small data-testid="text-neutral-atmosphere">Otomatik kaydediliyor</small></div><span className="header-hp" data-testid="header-character-hp" aria-label={`Can ${state.character.current_hp} / ${state.character.max_hp}`}><Heart size={13} aria-hidden="true" />{state.character.current_hp} / {state.character.max_hp}</span></div><div className="header-actions"><button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-character" onClick={() => onDrawer('character')}><Shield size={14} /> Karakter</button><button className="drawer-trigger" type="button" aria-haspopup="dialog" data-testid="button-open-world" onClick={() => onDrawer('world')}><Menu size={14} /> Dünya</button><div className="session-chip" data-testid="status-session"><span className="health-dot" /> <span className="hidden sm:inline">MACERA</span> #{campaignId.slice(0, 8)}</div><button className="dnd-button secondary !min-h-[35px] !px-3 !text-[8px]" type="button" onClick={onSave} disabled={saving} data-testid="button-save-campaign">{saving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />} <span className="hidden sm:inline">Kaydet</span></button><button className="dnd-button secondary !min-h-[35px] !px-3 !text-[8px]" type="button" onClick={onReset} data-testid="button-new-session"><Plus size={13} /> Yeni</button></div></div></header>;
}

function DrawerSheet({ drawer, state, entries, onClose, activeTab, setActiveTab }: { drawer: Drawer; state: GameState; entries: TranscriptEntry[]; onClose: () => void; activeTab: WorldTab; setActiveTab: (tab: WorldTab) => void }) {
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
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><section ref={dialogRef} className="drawer-sheet" role="dialog" aria-modal="true" aria-label={drawer === 'character' ? 'Karakter paneli' : 'Dünya paneli'} tabIndex={-1} onClick={(event) => event.stopPropagation()}><div className="drawer-heading"><Kicker>{drawer === 'character' ? 'Kanonik kayıt' : 'Kanonik çevre'}</Kicker><button className="icon-button" type="button" aria-label="Paneli kapat" data-testid="button-close-drawer" onClick={onClose}><X size={16} /></button></div>{drawer === 'character' ? <><CharacterPanel character={state.character} /><InventoryPanel items={state.inventory} /></> : <WorldTabs state={state} entries={entries} activeTab={activeTab} setActiveTab={setActiveTab} />}</section></div>;
}

function CharacterReveal({ state, onContinue, onBack }: { state: GameState; onContinue: () => void; onBack: () => void }) {
  const character = state.character;
  const abilities = [['KUV', character.strength], ['ÇEV', character.dexterity], ['DAY', character.constitution], ['ZEK', character.intelligence], ['BİL', character.wisdom], ['KAR', character.charisma]];
  return <main className="reveal-screen" data-testid="screen-character-reveal"><header className="dnd-shell reveal-header"><Brand /><button type="button" className="text-button" onClick={onBack} data-testid="button-back-opening"><ArrowLeft size={13} /> Geri dön</button></header><div className="reveal-wrap"><div className="reveal-heading"><Kicker>Yeni macera · Kanonik karakter kaydı</Kicker><h1 className="dnd-display">Yolcu ortaya çıktı.</h1><p className="dnd-serif">Motorun ürettiği kayıtla yola çıkıyorsun. Bu sayfa bir seçim ekranı değil; dünya durumunun okunabilir yüzü.</p></div><div className="reveal-card"><div className="portrait-empty" aria-label="Portre alanı boş"><ScrollText size={25} /><Kicker>Portre alanı · boş</Kicker><span>Motor portre verisi sağlamadı</span></div><div className="reveal-data"><div className="reveal-top"><div><Kicker>Karakter</Kicker><h2 data-testid="reveal-character-name">{character.name}</h2><div className="character-sub">{character.race} {character.class} · Seviye {character.level}</div></div><span className="character-badge">LVL {String(character.level).padStart(2, '0')}</span></div><Rule /><div className="reveal-metrics"><div><Kicker>Can</Kicker><strong>{character.current_hp} / {character.max_hp}</strong></div><div><Kicker>Zırh</Kicker><strong>{character.armor_class}</strong></div><div><Kicker>Ustalık</Kicker><strong>+{character.proficiency_bonus}</strong></div></div><div className="reveal-stats"><Kicker>Özellikler · motor kaydı</Kicker><div className="stat-strip">{abilities.map(([label, value]) => <div className="stat-box" key={label}><Kicker>{label}</Kicker><div className="stat-value">{value}</div></div>)}</div></div><div className="reveal-skills"><Kicker>Usta olunan beceriler</Kicker><div className="mt-3 flex flex-wrap gap-2">{character.proficient_skills.length ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skill}</span>) : <span className="subtle-text">Motor henüz beceri kaydetmedi.</span>}</div></div><div className="reveal-actions"><span>İsim, ırk, sınıf ve değerler sunucunun kaydıdır.</span><button type="button" className="dnd-button" onClick={onContinue} data-testid="button-continue-adventure">Macerayı aç <ArrowRight size={14} /></button></div></div></div></div></main>;
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
  const [message, setMessage] = useState('');
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
  const playTurn = usePlayGameTurn();
  const stateQuery = useGetGameSessionState(sessionId, { query: { enabled: Boolean(sessionId), queryKey: getGetGameSessionStateQueryKey(sessionId), retry: false } });
  const state = stateQuery.data;
  const storyScrollRef = useRef<HTMLDivElement>(null);
  const wasAtBottom = useRef(true);
  const previousLocation = useRef<string>('');

  useEffect(() => {
    if (!sessionId) { setEntries([]); return; }
    try {
      const stored = JSON.parse(window.localStorage.getItem(`${TRANSCRIPT_KEY}${sessionId}`) ?? '[]') as unknown;
      setEntries(Array.isArray(stored) ? stored.filter((entry): entry is TranscriptEntry => Boolean(entry) && typeof entry === 'object' && ((entry as TranscriptEntry).kind === 'player' || (entry as TranscriptEntry).kind === 'narration') && typeof (entry as TranscriptEntry).text === 'string') : []);
    } catch { setEntries([]); }
  }, [sessionId]);

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
    setMessage('');
    setNotice(null);
    setResumingCampaignId(null);
    setDrawer(null);
  };

  const handleCreate = () => {
    setNotice(null);
    setCreationReturnPhase(phase === 'library' ? 'library' : 'opening');
    setPhase('creation');
  };

  const handleCreateCharacter = (character: CharacterCreateInput) => {
    setNotice(null);
    createCampaign.mutate({ data: { character } }, {
      onSuccess: (created) => {
        setCampaignId(created.campaign_id);
        window.localStorage.setItem(LAST_CAMPAIGN_KEY, created.campaign_id);
        queryClient.setQueryData(getGetGameSessionStateQueryKey(created.session_id), created.state);
        window.localStorage.removeItem(`${TRANSCRIPT_KEY}${created.session_id}`);
        setEntries([]);
        setSessionId(created.session_id);
        setPhase('reveal');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => setNotice({
        tone: 'error',
        title: 'Karakter oluşturulamadı',
        detail: statusCode(error) === 422
          ? 'İsim, ırk veya sınıfı kontrol et; motor yalnızca listelenen seçenekleri kabul eder.'
          : friendlyError(error, 'Sunucu yanıt vermedi.'),
      }),
    });
  };

  const handleContinue = () => {
    setNotice(null);
    setPhase('library');
    void campaignsQuery.refetch();
  };

  const handleResume = (selectedCampaignId: string) => {
    setNotice(null);
    setResumingCampaignId(selectedCampaignId);
    resumeCampaign.mutate({ campaignId: selectedCampaignId }, {
      onSuccess: (resumed) => {
        const transcript = resumed.history.flatMap((entry: CampaignHistoryEntry) => [
          { kind: 'player' as const, text: entry.player_message },
          { kind: 'narration' as const, text: entry.narration },
        ]);
        setCampaignId(resumed.campaign_id);
        window.localStorage.setItem(LAST_CAMPAIGN_KEY, resumed.campaign_id);
        window.localStorage.setItem(`${TRANSCRIPT_KEY}${resumed.session_id}`, JSON.stringify(transcript));
        setEntries(transcript);
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
        setNotice({ tone: 'success', title: 'Macera kaydedildi', detail: 'Kanonik dünya durumu sunucudaki kayıt defterine yazıldı.' });
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => setNotice({ tone: 'error', title: 'Kayıt tamamlanamadı', detail: friendlyError(error, 'Macera güvenli biçimde kaydedilemedi.') }),
    });
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!sessionId || playTurn.isPending || trimmed.length < 1 || trimmed.length > 4000) return;
    setNotice(null);
    playTurn.mutate({ sessionId, data: { message: trimmed } }, {
      onSuccess: (result) => {
        const next = [...entries, { kind: 'player' as const, text: trimmed }, { kind: 'narration' as const, text: result.narration }];
        setEntries(next);
        window.localStorage.setItem(`${TRANSCRIPT_KEY}${sessionId}`, JSON.stringify(next));
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
        setMessage('');
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
      },
      onError: (error) => setNotice({ tone: 'error', title: statusCode(error) === 503 ? 'Motor şu an meşgul' : 'Hamle işlenemedi', detail: friendlyError(error, 'Python motoru bu hamleyi kabul etmedi.') }),
    });
  };

  const sessionLabel = useMemo(() => campaignId ? `#${campaignId.slice(0, 8)}` : 'yeni macera', [campaignId]);
  if (phase === 'library') return <CampaignLibrary campaigns={campaignsQuery.data} loading={campaignsQuery.isLoading} error={campaignsQuery.error} resuming={resumeCampaign.isPending} resumingCampaignId={resumingCampaignId} notice={notice} onBack={() => { setPhase('opening'); setNotice(null); }} onNew={handleCreate} onResume={handleResume} onRetry={() => void campaignsQuery.refetch()} />;
  if (phase === 'creation') return (
    <CharacterCreationScreen
      options={characterOptionsQuery.data}
      loadingOptions={characterOptionsQuery.isLoading}
      optionsError={characterOptionsQuery.error}
      creating={createCampaign.isPending}
      notice={notice}
      onBack={() => { setPhase(creationReturnPhase); setNotice(null); }}
      onCreate={handleCreateCharacter}
      onRetryOptions={() => void characterOptionsQuery.refetch()}
    />
  );
  if (!sessionId || phase === 'opening') return <OpeningScreen onCreate={handleCreate} onContinue={handleContinue} creating={createCampaign.isPending} notice={notice} loadingCampaigns={campaignsQuery.isLoading} hasCampaigns={Boolean(campaignsQuery.data?.length)} showNoCampaigns={!campaignsQuery.isLoading && !campaignsQuery.error} />;
  if (phase === 'reveal' && state) return <CharacterReveal state={state} onContinue={() => setPhase('adventure')} onBack={() => { setPhase('opening'); setSessionId(''); }} />;
  return (
    <EnvironmentThemeProvider state={state}>
      <div className="dnd-app" data-testid="app-session">
        {state && <SessionHeader state={state} campaignId={campaignId} onSave={handleSave} saving={saveCampaign.isPending} onReset={reset} onDrawer={setDrawer} />}
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
                <AlertTriangle size={16} /> {statusCode(stateQuery.error) === 503 ? 'Motor şu an kullanılamıyor.' : 'Günlük yüklenemedi.'}
              </div>
              <p className="dnd-serif mt-3 text-lg text-[#a99a80]">{friendlyError(stateQuery.error, 'Kanonik durum alınamadı.')}</p>
              <button className="dnd-button secondary mt-5" type="button" data-testid="button-retry-session-state" onClick={() => void stateQuery.refetch()}>
                <RefreshCw size={14} /> Tekrar dene
              </button>
            </div>
          ) : state ? (
            <>
              <LeftColumn state={state} />
              <StoryColumn state={state} entries={entries} message={message} setMessage={setMessage} onSubmit={handleSubmit} sending={playTurn.isPending} notice={notice} scrollRef={storyScrollRef} onScroll={handleStoryScroll} locationChanged={locationChanged} />
              <WorldTabs state={state} entries={entries} activeTab={activeTab} setActiveTab={setActiveTab} />
            </>
          ) : <div className="empty-line" data-testid="empty-session-state">Bu günlük henüz bir durum döndürmedi.</div>}
        </main>
        {state && <DrawerSheet drawer={drawer} state={state} entries={entries} onClose={() => setDrawer(null)} activeTab={activeTab} setActiveTab={setActiveTab} />}
        <div className="dnd-shell pb-8 text-right font-mono text-[9px] tracking-[.1em] text-[#695b48]" data-testid="text-session-label">
          {sessionLabel} · yalnızca başarılı sunucu turları saklanır
        </div>
      </div>
    </EnvironmentThemeProvider>
  );
}