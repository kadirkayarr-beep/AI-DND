import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Backpack,
  BookOpen,
  Check,
  ChevronRight,
  Circle,
  Clock3,
  DoorOpen,
  Heart,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Map,
  MapPinned,
  MessageCircle,
  Plus,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Send,
  Shield,
  Swords,
  Users,
  Wifi,
  X,
} from 'lucide-react';
import {
  getGetGameHealthQueryKey,
  getGetGameSessionStateQueryKey,
  useCreateGameSession,
  useGetGameHealth,
  useGetGameSessionState,
  usePlayGameTurn,
} from '@workspace/api-client-react';
import type {
  GameCharacter,
  GameDoor,
  GameNpc,
  GameState,
} from '@workspace/api-client-react';

const SESSION_STORAGE_KEY = 'ai-dnd-session-id';

type Notice = { tone: 'amber' | 'red' | 'teal'; title: string; detail: string };

function isMissingSession(error: unknown) {
  if (!error || typeof error !== 'object') return false;
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return candidate.status === 404 || candidate.statusCode === 404 || candidate.response?.status === 404;
}

function errorText(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function HealthMark({ healthy }: { healthy: boolean }) {
  return (
    <span
      className={`inline-flex h-2 w-2 rounded-full ${healthy ? 'bg-[hsl(var(--accent))]' : 'bg-[hsl(var(--destructive))]'} ${healthy ? 'journal-pulse' : ''}`}
      aria-hidden="true"
    />
  );
}

function SectionHeading({
  icon: Icon,
  eyebrow,
  title,
  count,
}: {
  icon: typeof BookOpen;
  eyebrow: string;
  title: string;
  count?: number;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-3">
      <div>
        <div className="journal-kicker mb-1 flex items-center gap-2">
          <Icon className="h-3.5 w-3.5" />
          {eyebrow}
        </div>
        <h2 className="journal-title text-2xl">{title}</h2>
      </div>
      {typeof count === 'number' && (
        <span className="rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.48)] px-2 py-1 font-mono text-[0.65rem] text-[hsl(var(--muted-foreground))]">
          {count.toString().padStart(2, '0')}
        </span>
      )}
    </div>
  );
}

function EmptyLine({ children }: { children: string }) {
  return (
    <p className="rounded-lg border border-dashed border-[hsl(var(--border))] bg-[hsl(var(--muted)/0.32)] px-3 py-3 text-sm italic text-[hsl(var(--muted-foreground))]">
      {children}
    </p>
  );
}

function CharacterSheet({ character }: { character: GameCharacter }) {
  const abilities = [
    ['KUV', character.strength],
    ['ÇEV', character.dexterity],
    ['DAY', character.constitution],
    ['ZEK', character.intelligence],
    ['BİL', character.wisdom],
    ['KAR', character.charisma],
  ];
  const hpPercent = character.max_hp > 0 ? Math.max(0, Math.min(100, (character.current_hp / character.max_hp) * 100)) : 0;

  return (
    <section className="journal-card journal-texture p-5" data-testid="panel-character">
      <div className="relative z-10">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="journal-kicker mb-1">Oyuncu karakteri</div>
            <h2 className="journal-title text-3xl">{character.name}</h2>
            <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">
              Seviye {character.level} {character.race} {character.class}
            </p>
            <p className="mt-1 font-mono text-xs text-[hsl(var(--muted-foreground))]" data-testid="text-xp">
              {character.xp} XP
            </p>
          </div>
          <div className="flex h-11 w-11 items-center justify-center rounded-full border border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]">
            <Shield className="h-5 w-5" />
          </div>
        </div>

        <div className="mb-5 grid grid-cols-3 gap-2">
          <div className="rounded-lg bg-[hsl(var(--muted)/0.58)] p-3">
            <div className="journal-kicker">Zırh</div>
            <div className="mt-1 font-mono text-lg font-medium">{character.armor_class}</div>
          </div>
          <div className="rounded-lg bg-[hsl(var(--muted)/0.58)] p-3">
            <div className="journal-kicker">Ustalık</div>
            <div className="mt-1 font-mono text-lg font-medium">+{character.proficiency_bonus}</div>
          </div>
          <div className="rounded-lg bg-[hsl(var(--muted)/0.58)] p-3">
            <div className="journal-kicker">Can</div>
            <div className="mt-1 font-mono text-lg font-medium">{character.current_hp}/{character.max_hp}</div>
          </div>
        </div>

        <div className="mb-5">
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-[hsl(var(--muted-foreground))]">
              <Heart className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" /> Can durumu
            </span>
            <span className="font-mono text-[hsl(var(--foreground))]">{Math.round(hpPercent)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[hsl(var(--muted))]">
            <div
              className="h-full rounded-full bg-[hsl(var(--destructive))] transition-[width] duration-500"
              style={{ width: `${hpPercent}%` }}
              data-testid="meter-health"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {abilities.map(([label, value]) => (
            <div className="border-t border-[hsl(var(--border))] pt-2" key={label}>
              <div className="font-mono text-[0.63rem] tracking-[0.12em] text-[hsl(var(--muted-foreground))]">{label}</div>
              <div className="mt-0.5 font-mono text-base">{value}</div>
            </div>
          ))}
        </div>

        <div className="mt-5 border-t border-[hsl(var(--border))] pt-4">
          <div className="mb-2 text-xs font-medium text-[hsl(var(--muted-foreground))]">Usta olunan beceriler</div>
          {character.proficient_skills.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {character.proficient_skills.map((skill) => (
                <span className="rounded-md bg-[hsl(var(--secondary))] px-2 py-1 text-xs text-[hsl(var(--secondary-foreground))]" key={skill}>
                  {skill}
                </span>
              ))}
            </div>
          ) : (
            <EmptyLine>Motor henüz beceri kaydetmedi.</EmptyLine>
          )}
        </div>
      </div>
    </section>
  );
}

function InventoryPanel({ inventory }: { inventory: string[] }) {
  return (
    <section className="journal-card p-5" data-testid="panel-inventory">
      <SectionHeading icon={Backpack} eyebrow="Üzerinde" title="Envanter" count={inventory.length} />
      {inventory.length > 0 ? (
        <ul className="space-y-2">
          {inventory.map((item, index) => (
            <li className="flex items-center gap-3 border-b border-[hsl(var(--border)/0.7)] pb-2 text-sm last:border-0 last:pb-0" key={`${item}-${index}`} data-testid={`item-inventory-${index}`}>
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[hsl(var(--secondary))] font-mono text-xs text-[hsl(var(--secondary-foreground))]">{index + 1}</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyLine>Çantada kaydedilmiş eşya yok.</EmptyLine>
      )}
    </section>
  );
}

function WorldPanel({ state }: { state: GameState }) {
  return (
    <section className="journal-card p-5" data-testid="panel-world">
      <SectionHeading icon={Map} eyebrow="Kamuya açık dünya" title="Çevre" />
      <div className="mb-5 rounded-lg border border-[hsl(var(--primary)/0.25)] bg-[hsl(var(--primary)/0.07)] p-3">
        <div className="mb-1 flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
          <MapPinned className="h-3.5 w-3.5 text-[hsl(var(--primary))]" /> Şu anki konum
        </div>
        <div className="font-medium" data-testid="text-current-location">{state.location}</div>
      </div>
      <div className="space-y-3">
        {Object.values(state.locations).length > 0 ? Object.values(state.locations).map((location) => (
          <div className="rounded-lg border border-[hsl(var(--border))] p-3" key={location.id} data-testid={`location-${location.id}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-medium">{location.name}</div>
                <div className="mt-0.5 font-mono text-[0.62rem] uppercase tracking-[0.12em] text-[hsl(var(--muted-foreground))]">{location.type}</div>
              </div>
              {location.name === state.location && <Check className="h-4 w-4 text-[hsl(var(--accent))]" />}
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">{location.description}</p>
          </div>
        )) : <EmptyLine>Motor konum kaydetmedi.</EmptyLine>}
      </div>
    </section>
  );
}

function PeoplePanel({ npcs }: { npcs: GameNpc[] }) {
  return (
    <section className="journal-card p-5" data-testid="panel-npcs">
      <SectionHeading icon={Users} eyebrow="Karşılaşılanlar" title="Kişiler" count={npcs.length} />
      {npcs.length > 0 ? (
        <div className="space-y-3">
          {npcs.map((npc) => (
            <div className="rounded-lg border border-[hsl(var(--border))] p-3" key={npc.id} data-testid={`npc-${npc.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{npc.name}</div>
                  <div className="mt-0.5 text-xs text-[hsl(var(--muted-foreground))]">{npc.role} · {npc.location}</div>
                </div>
                {npc.combat_status && <span className="rounded-full bg-[hsl(var(--destructive)/0.12)] px-2 py-1 text-[0.65rem] text-[hsl(var(--destructive))]">{npc.combat_status}</span>}
              </div>
              {npc.appearance && <p className="mt-2 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">{npc.appearance}</p>}
              {(npc.relationship || npc.current_hp !== null) && (
                <div className="mt-3 flex flex-wrap gap-2 border-t border-[hsl(var(--border))] pt-2 font-mono text-[0.65rem] text-[hsl(var(--muted-foreground))]">
                  {npc.relationship && <span>İlişki: {npc.relationship}</span>}
                  {npc.current_hp !== null && npc.max_hp !== null && <span>Can: {npc.current_hp}/{npc.max_hp}</span>}
                  {npc.armor_class !== null && <span>Zırh: {npc.armor_class}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : <EmptyLine>Bu bölgede tanınan kişi yok.</EmptyLine>}
    </section>
  );
}

function DoorsAndFeatures({ state }: { state: GameState }) {
  return (
    <section className="journal-card p-5" data-testid="panel-details">
      <SectionHeading icon={DoorOpen} eyebrow="İncelenebilir" title="Ayrıntılar" />
      <div className="space-y-2">
        {state.doors.length > 0 ? state.doors.map((door: GameDoor) => (
          <div className="flex items-center justify-between gap-3 rounded-lg bg-[hsl(var(--muted)/0.5)] px-3 py-2.5" key={door.id} data-testid={`door-${door.id}`}>
            <div className="flex min-w-0 items-center gap-2">
              {door.locked ? <LockKeyhole className="h-4 w-4 shrink-0 text-[hsl(var(--destructive))]" /> : <KeyRound className="h-4 w-4 shrink-0 text-[hsl(var(--primary))]" />}
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{door.name}</div>
                <div className="truncate text-xs text-[hsl(var(--muted-foreground))]">{door.description}</div>
              </div>
            </div>
            <span className="shrink-0 font-mono text-[0.62rem] uppercase text-[hsl(var(--muted-foreground))]">
              {door.broken ? 'kırık' : door.open ? 'açık' : door.locked ? 'kilitli' : 'kapalı'}
            </span>
          </div>
        )) : <EmptyLine>Kapı veya geçit kaydedilmedi.</EmptyLine>}
      </div>
      <div className="my-5 journal-rule" />
      <div className="mb-2 text-xs font-medium text-[hsl(var(--muted-foreground))]">Çevredeki özellikler</div>
      {state.features.length > 0 ? (
        <div className="space-y-2">
          {state.features.map((feature, index) => (
            <div className="border-l-2 border-[hsl(var(--primary)/0.5)] pl-3" key={`${feature.name}-${index}`} data-testid={`feature-${index}`}>
              <div className="text-sm font-medium">{feature.name}</div>
              <div className="mt-0.5 text-xs text-[hsl(var(--muted-foreground))]">{feature.description}</div>
            </div>
          ))}
        </div>
      ) : <EmptyLine>Motor çevre özelliği kaydetmedi.</EmptyLine>}
    </section>
  );
}

function CombatPanel({ state }: { state: GameState }) {
  const combat = state.combat;
  const active = Boolean(combat.active);
  return (
    <section className={`journal-card p-5 ${active ? 'border-[hsl(var(--destructive)/0.4)]' : ''}`} data-testid="panel-combat">
      <SectionHeading icon={Swords} eyebrow="Motor durumu" title="Çatışma" />
      <div className={`rounded-lg p-3 ${active ? 'bg-[hsl(var(--destructive)/0.09)]' : 'bg-[hsl(var(--muted)/0.5)]'}`}>
        <div className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 text-sm font-medium">
            <span className={`h-2 w-2 rounded-full ${active ? 'bg-[hsl(var(--destructive))] journal-pulse' : 'bg-[hsl(var(--muted-foreground))]'}`} />
            {active ? 'Çatışma sürüyor' : 'Çatışma yok'}
          </span>
          {typeof combat.round === 'number' && <span className="font-mono text-xs text-[hsl(var(--muted-foreground))]">Tur {combat.round}</span>}
        </div>
        {active && combat.initiative_order && combat.initiative_order.length > 0 && (
          <div className="mt-3 border-t border-[hsl(var(--border)/0.7)] pt-3">
            <div className="mb-2 text-[0.65rem] uppercase tracking-[0.12em] text-[hsl(var(--muted-foreground))]">İnisiyatif</div>
            <div className="flex flex-wrap gap-1.5">
              {combat.initiative_order.map((participant, index) => (
                <span className="rounded-md border border-[hsl(var(--border))] px-2 py-1 font-mono text-xs" key={`${participant}-${index}`}>{participant}</span>
              ))}
            </div>
          </div>
        )}
        {state.player_combat_status && (
          <div className="mt-3 flex items-start gap-2 border-t border-[hsl(var(--border)/0.7)] pt-3 text-sm text-[hsl(var(--muted-foreground))]">
            <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--primary))]" /> {state.player_combat_status}
          </div>
        )}
      </div>
    </section>
  );
}

function StateColumn({ state }: { state: GameState }) {
  return (
    <aside className="space-y-4">
      <CharacterSheet character={state.character} />
      <InventoryPanel inventory={state.inventory} />
      <WorldPanel state={state} />
      <PeoplePanel npcs={state.npcs} />
      <DoorsAndFeatures state={state} />
      <CombatPanel state={state} />
    </aside>
  );
}

function StateSkeleton() {
  return (
    <div className="space-y-4" data-testid="state-loading">
      <div className="journal-card p-5">
        <div className="journal-skeleton h-3 w-24 rounded" />
        <div className="journal-skeleton mt-3 h-9 w-48 rounded" />
        <div className="journal-skeleton mt-2 h-4 w-36 rounded" />
        <div className="mt-6 grid grid-cols-3 gap-2">
          {[1, 2, 3].map((item) => <div className="journal-skeleton h-16 rounded-lg" key={item} />)}
        </div>
        <div className="journal-skeleton mt-6 h-24 rounded" />
      </div>
      <div className="journal-card p-5">
        <div className="journal-skeleton h-4 w-32 rounded" />
        <div className="mt-5 space-y-3">
          {[1, 2, 3].map((item) => <div className="journal-skeleton h-10 rounded-lg" key={item} />)}
        </div>
      </div>
    </div>
  );
}

function NoticeBanner({ notice }: { notice: Notice }) {
  const colors = notice.tone === 'red'
    ? 'border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.08)] text-[hsl(var(--destructive))]'
    : notice.tone === 'teal'
      ? 'border-[hsl(var(--accent)/0.35)] bg-[hsl(var(--accent)/0.08)] text-[hsl(var(--accent))]'
      : 'border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.08)] text-[hsl(var(--primary))]';
  return (
    <div className={`mb-5 flex items-start gap-3 rounded-lg border px-4 py-3 ${colors}`} role="status" data-testid="status-notice">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <div className="text-sm font-semibold">{notice.title}</div>
        <div className="mt-0.5 text-xs opacity-80">{notice.detail}</div>
      </div>
    </div>
  );
}

function StartScreen({
  health,
  healthLoading,
  healthError,
  onRetryHealth,
  onCreate,
  creating,
  notice,
  createError,
}: {
  health?: { status: string; engine: string; model: string };
  healthLoading: boolean;
  healthError: unknown;
  onRetryHealth: () => void;
  onCreate: () => void;
  creating: boolean;
  notice: Notice | null;
  createError: unknown;
}) {
  const healthy = Boolean(health && ['ok', 'healthy', 'ready'].includes(health.status.toLowerCase()));
  return (
    <main className="journal-shell flex min-h-[calc(100dvh-88px)] items-center justify-center">
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="journal-card journal-texture relative overflow-hidden p-7 sm:p-12" data-testid="panel-start">
          <div className="relative z-10 max-w-xl">
            <div className="journal-kicker mb-4 flex items-center gap-2"><BookOpen className="h-3.5 w-3.5" /> Kişisel kampanya günlüğü</div>
            <h1 className="journal-title text-5xl leading-[0.98] sm:text-7xl">Perdenin<br /><span className="text-[hsl(var(--primary))]">ardında</span> bir dünya.</h1>
            <p className="mt-6 max-w-md text-base leading-relaxed text-[hsl(var(--muted-foreground))]">
              Python oyun motoruna doğal dilde seslen. Motorun onayladığı anlatıyı ve dünyada gerçekten var olanları gör.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-3 text-sm font-semibold text-[hsl(var(--primary-foreground))] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
                data-testid="button-create-session"
                disabled={creating}
                onClick={onCreate}
                type="button"
              >
                {creating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {creating ? 'Oda hazırlanıyor' : 'Yeni oturum başlat'}
              </button>
              <span className="text-xs text-[hsl(var(--muted-foreground))]">Tek oyuncu · motor kontrollü</span>
            </div>
            {Boolean(createError) && (
              <div className="mt-5 flex items-start gap-2 rounded-lg border border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.07)] p-3 text-sm text-[hsl(var(--destructive))]" data-testid="error-create-session">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>Oturum oluşturulamadı. {errorText(createError, 'Sunucu yanıt vermedi.')}</span>
              </div>
            )}
          </div>
          <div className="pointer-events-none absolute -bottom-28 -right-10 h-72 w-72 rounded-full border-[18px] border-[hsl(var(--primary)/0.09)]" />
          <div className="pointer-events-none absolute -bottom-12 -right-24 h-56 w-56 rounded-full border border-[hsl(var(--accent)/0.22)]" />
        </section>

        <section className="journal-card p-6 sm:p-8" data-testid="panel-engine-health">
          <div className="journal-kicker mb-3 flex items-center gap-2"><Wifi className="h-3.5 w-3.5" /> Motor bağlantısı</div>
          <h2 className="journal-title text-2xl">Kapı şu an {healthLoading ? 'yoklanıyor' : healthy ? 'açık' : 'sessiz'}.</h2>
          <p className="mt-2 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Bu gösterge oyun API’sinin yanıtını kontrol eder. Model erişimi ilk turda ayrıca doğrulanır.</p>
          {healthLoading ? (
            <div className="mt-8 space-y-3" data-testid="health-loading">
              {[1, 2, 3].map((item) => <div className="journal-skeleton h-12 rounded-lg" key={item} />)}
            </div>
          ) : healthError ? (
            <div className="mt-8 rounded-lg border border-[hsl(var(--destructive)/0.3)] bg-[hsl(var(--destructive)/0.06)] p-4" data-testid="error-health">
              <div className="flex items-center gap-2 text-sm font-medium text-[hsl(var(--destructive))]"><X className="h-4 w-4" /> Sağlık bilgisi alınamadı</div>
              <p className="mt-2 text-xs leading-relaxed text-[hsl(var(--muted-foreground))]">Oturum yine de denenebilir; bağlantı sorununda tekrar kontrol et.</p>
              <button className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-[hsl(var(--primary))] hover:underline" data-testid="button-retry-health" onClick={onRetryHealth} type="button">
                <RefreshCw className="h-3.5 w-3.5" /> Tekrar dene
              </button>
            </div>
          ) : (
            <div className="mt-8 space-y-2" data-testid="status-health">
              <div className="flex items-center justify-between border-b border-[hsl(var(--border))] py-3 text-sm">
                <span className="text-[hsl(var(--muted-foreground))]">Durum</span>
                <span className="flex items-center gap-2 font-medium"><HealthMark healthy={healthy} /> {health?.status ?? 'bilinmiyor'}</span>
              </div>
              <div className="flex items-center justify-between border-b border-[hsl(var(--border))] py-3 text-sm">
                <span className="text-[hsl(var(--muted-foreground))]">Motor</span>
                <span className="font-mono text-xs">{health?.engine ?? '—'}</span>
              </div>
              <div className="flex items-center justify-between py-3 text-sm">
                <span className="text-[hsl(var(--muted-foreground))]">Model</span>
                <span className="font-mono text-xs">{health?.model ?? '—'}</span>
              </div>
            </div>
          )}
          {notice && <div className="mt-6"><NoticeBanner notice={notice} /></div>}
          <div className="mt-7 flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
            <Shield className="h-3.5 w-3.5" /> Tarayıcı yalnızca oyuncu mesajını gönderir.
          </div>
        </section>
      </div>
    </main>
  );
}

function actionFingerprint(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
  }
  return (hash >>> 0).toString(36);
}

function stableTurnActionId(scope: string, signature: string) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  const fingerprint = actionFingerprint(signature);
  try {
    const pending = JSON.parse(window.sessionStorage.getItem(storageKey) ?? '{}') as Record<string, unknown>;
    const existing = pending[fingerprint];
    if (typeof existing === 'string') return existing;
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    const actionId = window.crypto.randomUUID();
    pending[fingerprint] = actionId;
    window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
    return actionId;
  } catch {
    if (!window.crypto?.randomUUID) throw new Error('Secure UUID generation is unavailable.');
    return window.crypto.randomUUID();
  }
}

function clearPendingTurnAction(scope: string, actionId: string) {
  const storageKey = `ai-dnd-pending-turns:${scope}`;
  try {
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
  const [sessionId, setSessionId] = useState(() => window.localStorage.getItem(SESSION_STORAGE_KEY) ?? '');
  const [narration, setNarration] = useState('');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [staleSession, setStaleSession] = useState(false);

  const healthQuery = useGetGameHealth({
    query: { queryKey: getGetGameHealthQueryKey(), staleTime: 30_000, retry: 1 },
  });
  const stateQuery = useGetGameSessionState(sessionId, {
    query: {
      enabled: Boolean(sessionId),
      queryKey: getGetGameSessionStateQueryKey(sessionId),
      retry: false,
    },
  });
  const createSession = useCreateGameSession();
  const playTurn = usePlayGameTurn();
  const pendingTurnRef = useRef<{ signature: string; actionId: string } | null>(null);

  useEffect(() => {
    if (!sessionId || !stateQuery.isError) return;
    if (isMissingSession(stateQuery.error)) {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      setSessionId('');
      setNarration('');
      setStaleSession(true);
      setNotice({
        tone: 'amber',
        title: 'Eski oturum bulunamadı',
        detail: 'Sunucu bu günlükte kayıtlı bir oturum bulamadı. Yeni bir oturum açabilirsin.',
      });
    }
  }, [sessionId, stateQuery.error, stateQuery.isError]);

  const state = stateQuery.data;
  const isSending = playTurn.isPending;
  const sessionLabel = useMemo(() => sessionId ? `${sessionId.slice(0, 8)}…` : 'yeni günlük', [sessionId]);

  const resetToStart = () => {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    setSessionId('');
    setNarration('');
    setMessage('');
    setStaleSession(false);
    setNotice(null);
  };

  const handleCreate = () => {
    setNotice(null);
    createSession.mutate(undefined, {
      onSuccess: (created) => {
        window.localStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
        setSessionId(created.session_id);
        setNarration('');
        setStaleSession(false);
        setNotice({ tone: 'teal', title: 'Günlük hazır', detail: 'Dünya kuruldu. İlk hamleni doğal dilde yaz.' });
      },
      onError: (error) => {
        setNotice({ tone: 'red', title: 'Yeni günlük açılamadı', detail: errorText(error, 'Sunucu yanıt vermedi.') });
      },
    });
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!message.trim() || !sessionId || isSending) return;
    setNotice(null);
    const turnMessage = message.trim();
    const signature = JSON.stringify([sessionId, turnMessage, null]);
    const actionId = pendingTurnRef.current?.signature === signature
      ? pendingTurnRef.current.actionId
      : stableTurnActionId(sessionId, signature);
    pendingTurnRef.current = { signature, actionId };
    playTurn.mutate({ sessionId, data: { message: turnMessage, action_id: actionId } }, {
      onSuccess: (result) => {
        if (pendingTurnRef.current?.actionId === actionId) pendingTurnRef.current = null;
        clearPendingTurnAction(sessionId, actionId);
        setNarration(result.narration);
        setMessage('');
        queryClient.setQueryData(getGetGameSessionStateQueryKey(sessionId), result.state);
        const levelUp = result.level_up;
        if (levelUp && levelUp.new_level > levelUp.previous_level) {
          setNotice({
            tone: 'teal',
            title: 'Seviye atlandı',
            detail: `Seviye ${levelUp.previous_level} → ${levelUp.new_level}. +${levelUp.hit_points_gained} can, +${levelUp.xp_gained} deneyim.`,
          });
        }
      },
      onError: (error) => {
        setNotice({ tone: 'red', title: 'Hamle işlenemedi', detail: errorText(error, 'Motor bu hamleyi kabul etmedi.') });
      },
    });
  };

  if (!sessionId && !staleSession) {
    return (
      <div className="journal-app" data-testid="app-start">
        <header className="journal-shell flex items-center justify-between gap-4 pb-2 pt-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-primary))]"><ScrollText className="h-4 w-4" /></div>
            <div>
              <div className="font-serif text-lg font-semibold tracking-tight">AI-DND</div>
              <div className="font-mono text-[0.58rem] uppercase tracking-[0.16em] text-[hsl(var(--muted-foreground))]">browser / solo</div>
            </div>
          </div>
          <div className="hidden items-center gap-2 text-xs text-[hsl(var(--muted-foreground))] sm:flex"><Clock3 className="h-3.5 w-3.5" /> Kayıt defteri bekliyor</div>
        </header>
        <StartScreen
          createError={createSession.error}
          creating={createSession.isPending}
          health={healthQuery.data}
          healthError={healthQuery.error}
          healthLoading={healthQuery.isLoading}
          notice={notice}
          onCreate={handleCreate}
          onRetryHealth={() => void healthQuery.refetch()}
        />
      </div>
    );
  }

  if (staleSession) {
    return (
      <div className="journal-app min-h-[100dvh]" data-testid="app-stale-session">
        <header className="journal-shell flex items-center justify-between gap-4 pb-2 pt-5">
          <Brand />
        </header>
        <main className="journal-shell flex min-h-[calc(100dvh-88px)] items-center justify-center">
          <div className="journal-card max-w-lg p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]"><RotateCcw className="h-5 w-5" /></div>
            <h1 className="journal-title mt-5 text-3xl">Bu sayfa artık boş.</h1>
            <p className="mt-3 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Sunucu eski oturumu unutmuş. Yeni bir günlük açarak yeniden başlayabilirsin.</p>
            <button className="mt-6 inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-3 text-sm font-semibold text-[hsl(var(--primary-foreground))]" data-testid="button-start-after-stale" onClick={() => { setStaleSession(false); setNotice(null); }} type="button">
              <Plus className="h-4 w-4" /> Yeni günlük aç
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="journal-app min-h-[100dvh]" data-testid="app-session">
      <header className="journal-shell pb-5 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Brand />
          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--card)/0.7)] px-3 py-1.5 text-xs text-[hsl(var(--muted-foreground))] sm:flex" data-testid="status-session">
              <HealthMark healthy={!healthQuery.isError} /> <span className="font-mono">#{sessionLabel}</span>
            </div>
            <button className="inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card)/0.75)] px-3 py-2 text-xs font-medium text-[hsl(var(--foreground))] transition-colors hover:bg-[hsl(var(--muted))]" data-testid="button-new-session" onClick={resetToStart} type="button">
              <Plus className="h-3.5 w-3.5" /> Yeni günlük
            </button>
          </div>
        </div>
        <div className="mt-5 flex items-end justify-between gap-5">
          <div>
            <div className="journal-kicker mb-1">Oturum günlüğü</div>
            <h1 className="journal-title text-3xl sm:text-4xl">Gecenin ilk sayfası</h1>
          </div>
          <div className="hidden text-right sm:block">
            <div className="font-mono text-[0.62rem] uppercase tracking-[0.15em] text-[hsl(var(--muted-foreground))]">Motor turu</div>
            <div className="mt-1 font-mono text-lg" data-testid="text-turn-index">{state?.turn_index ?? '—'}</div>
          </div>
        </div>
      </header>

      <main className="journal-shell pt-0">
        {notice && <NoticeBanner notice={notice} />}
        {stateQuery.isLoading ? (
          <StateSkeleton />
        ) : stateQuery.isError ? (
          <div className="journal-card mx-auto max-w-xl p-8 text-center" data-testid="error-session-state">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[hsl(var(--destructive)/0.1)] text-[hsl(var(--destructive))]"><AlertTriangle className="h-5 w-5" /></div>
            <h2 className="journal-title mt-5 text-3xl">Sayfa okunamadı.</h2>
            <p className="mt-3 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Kamuya açık oyun durumu alınamadı. Oturumu sıfırlamadan önce bağlantıyı yeniden dene.</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              <button className="inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-2.5 text-sm font-semibold text-[hsl(var(--primary-foreground))]" data-testid="button-retry-session-state" onClick={() => void stateQuery.refetch()} type="button">
                <RefreshCw className="h-4 w-4" /> Tekrar dene
              </button>
              <button className="inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] px-4 py-2.5 text-sm font-medium" data-testid="button-clear-session-error" onClick={resetToStart} type="button">
                <X className="h-4 w-4" /> Yeni günlük
              </button>
            </div>
          </div>
        ) : !state ? (
          <div className="journal-card mx-auto max-w-xl p-8 text-center" data-testid="empty-session-state">
            <MessageCircle className="mx-auto h-8 w-8 text-[hsl(var(--primary))]" />
            <h2 className="journal-title mt-4 text-2xl">Dünya henüz görünmüyor.</h2>
            <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">Motor kamuya açık bir durum döndürmedi. Yenilemeyi dene.</p>
            <button className="mt-5 inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--border))] px-4 py-2.5 text-sm font-medium" data-testid="button-retry-empty-state" onClick={() => void stateQuery.refetch()} type="button">
              <RefreshCw className="h-4 w-4" /> Durumu yenile
            </button>
          </div>
        ) : (
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.08fr)_minmax(330px,0.92fr)]">
            <section className="space-y-5">
              <div className="journal-card journal-reveal journal-texture min-h-[410px] p-6 sm:p-8" data-testid="panel-narration">
                <div className="relative z-10">
                  <div className="flex items-start justify-between gap-4">
                    <SectionHeading icon={BookOpen} eyebrow="Motorun kaydı" title="Anlatı" />
                    <span className="rounded-full border border-[hsl(var(--accent)/0.28)] bg-[hsl(var(--accent)/0.08)] px-2 py-1 font-mono text-[0.6rem] uppercase tracking-[0.1em] text-[hsl(var(--accent))]">onaylı</span>
                  </div>
                  <div className="journal-rule mb-7 mt-1" />
                  {narration ? (
                    <div className="max-w-2xl whitespace-pre-wrap font-serif text-xl leading-[1.65] text-[hsl(var(--foreground))]" data-testid="text-narration">{narration}</div>
                  ) : (
                    <div className="max-w-md py-10" data-testid="empty-narration">
                      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]"><ChevronRight className="h-5 w-5" /></div>
                      <p className="font-serif text-2xl leading-tight">İlk cümleni bekleyen bir dünya var.</p>
                      <p className="mt-3 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Oyuncu mesajını gönderdiğinde yalnızca motorun doğruladığı son anlatı burada görünecek. Eski sohbet geçmişi tarayıcıya geri yüklenmez.</p>
                    </div>
                  )}
                  <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[hsl(var(--border))] pt-4 text-xs text-[hsl(var(--muted-foreground))]">
                    <span className="flex items-center gap-1.5"><Shield className="h-3.5 w-3.5 text-[hsl(var(--accent))]" /> Yalnızca motor çıktısı</span>
                    <span className="flex items-center gap-1.5"><MapPinned className="h-3.5 w-3.5" /> {state.location}</span>
                  </div>
                </div>
              </div>

              <form className="journal-card journal-reveal journal-reveal-delay-1 p-5 sm:p-6" data-testid="form-player-turn" onSubmit={handleSubmit}>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <label className="journal-kicker flex items-center gap-2" htmlFor="player-message"><Send className="h-3.5 w-3.5" /> Senin hamlen</label>
                  <span className="font-mono text-[0.65rem] text-[hsl(var(--muted-foreground))]">{message.length}/4000</span>
                </div>
                <textarea
                  className="min-h-28 w-full resize-y rounded-lg border border-[hsl(var(--input))] bg-[hsl(var(--background)/0.72)] p-4 text-sm leading-relaxed text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]"
                  data-testid="input-player-message"
                  disabled={isSending}
                  id="player-message"
                  maxLength={4000}
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder="Ne yapmak istiyorsun? Örn. Kapıyı inceleyip içeriden bir ses gelip gelmediğini dinliyorum."
                  value={message}
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">Göndermek için Enter · yeni satır için Shift + Enter</span>
                  <button className="inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-2.5 text-sm font-semibold text-[hsl(var(--primary-foreground))] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50" data-testid="button-submit-turn" disabled={!message.trim() || isSending} type="submit">
                    {isSending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    {isSending ? 'Motor düşünüyor' : 'Hamleyi gönder'}
                  </button>
                </div>
                {playTurn.isError && <p className="mt-3 text-xs text-[hsl(var(--destructive))]" data-testid="error-submit-turn">{errorText(playTurn.error, 'Hamle gönderilemedi.')}</p>}
              </form>
            </section>
            <div className="journal-reveal journal-reveal-delay-2">
              <StateColumn state={state} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3" data-testid="brand-ai-dnd">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-primary))]"><ScrollText className="h-4 w-4" /></div>
      <div>
        <div className="font-serif text-lg font-semibold tracking-tight">AI-DND</div>
        <div className="font-mono text-[0.58rem] uppercase tracking-[0.16em] text-[hsl(var(--muted-foreground))]">browser / solo</div>
      </div>
    </div>
  );
}