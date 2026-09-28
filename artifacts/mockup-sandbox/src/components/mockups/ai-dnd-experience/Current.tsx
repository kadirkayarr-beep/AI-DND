import './_group.css';
import { AlertTriangle, BookOpen, LoaderCircle, Plus, RefreshCw, ScrollText, Shield, Wifi, X } from 'lucide-react';

type Notice = { tone: 'amber' | 'red' | 'teal'; title: string; detail: string };

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

function NoticeBanner({ notice }: { notice: Notice }) {
  const colors = notice.tone === 'red'
    ? 'border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.08)] text-[hsl(var(--destructive))]'
    : notice.tone === 'teal'
      ? 'border-[hsl(var(--accent)/0.35)] bg-[hsl(var(--accent)/0.08)] text-[hsl(var(--accent))]'
      : 'border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.08)] text-[hsl(var(--primary))]';
  return (
    <div className={`mb-5 flex items-start gap-3 rounded-lg border px-4 py-3 ${colors}`} role="status">
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
    <main className="journal-shell flex min-h-[calc(100vh-88px)] items-center justify-center">
      <div className="grid w-full max-w-5xl gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="journal-card journal-texture relative overflow-hidden p-7 sm:p-12">
          <div className="relative z-10 max-w-xl">
            <div className="journal-kicker mb-4 flex items-center gap-2"><BookOpen className="h-3.5 w-3.5" /> Kişisel kampanya günlüğü</div>
            <h1 className="journal-title text-5xl leading-[0.98] sm:text-7xl">Perdenin<br /><span className="text-[hsl(var(--primary))]">ardında</span> bir dünya.</h1>
            <p className="mt-6 max-w-md text-base leading-relaxed text-[hsl(var(--muted-foreground))]">
              Python oyun motoruna doğal dilde seslen. Motorun onayladığı anlatıyı ve dünyada gerçekten var olanları gör.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-[hsl(var(--primary))] px-4 py-3 text-sm font-semibold text-[hsl(var(--primary-foreground))] transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
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
              <div className="mt-5 flex items-start gap-2 rounded-lg border border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.07)] p-3 text-sm text-[hsl(var(--destructive))]">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>Oturum oluşturulamadı. {errorText(createError, 'Sunucu yanıt vermedi.')}</span>
              </div>
            )}
          </div>
          <div className="pointer-events-none absolute -bottom-28 -right-10 h-72 w-72 rounded-full border-[18px] border-[hsl(var(--primary)/0.09)]" />
          <div className="pointer-events-none absolute -bottom-12 -right-24 h-56 w-56 rounded-full border border-[hsl(var(--accent)/0.22)]" />
        </section>

        <section className="journal-card p-6 sm:p-8">
          <div className="journal-kicker mb-3 flex items-center gap-2"><Wifi className="h-3.5 w-3.5" /> Motor bağlantısı</div>
          <h2 className="journal-title text-2xl">Kapı şu an {healthLoading ? 'yoklanıyor' : healthy ? 'açık' : 'sessiz'}.</h2>
          <p className="mt-2 text-sm leading-relaxed text-[hsl(var(--muted-foreground))]">Bu gösterge oyun API’sinin yanıtını kontrol eder. Model erişimi ilk turda ayrıca doğrulanır.</p>
          {healthLoading ? (
            <div className="mt-8 space-y-3">
              {[1, 2, 3].map((item) => <div className="h-12 animate-pulse rounded-lg bg-[hsl(var(--muted))]" key={item} />)}
            </div>
          ) : healthError ? (
            <div className="mt-8 rounded-lg border border-[hsl(var(--destructive)/0.3)] bg-[hsl(var(--destructive)/0.06)] p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-[hsl(var(--destructive))]"><X className="h-4 w-4" /> Sağlık bilgisi alınamadı</div>
              <p className="mt-2 text-xs leading-relaxed text-[hsl(var(--muted-foreground))]">Oturum yine de denenebilir; bağlantı sorununda tekrar kontrol et.</p>
              <button className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-[hsl(var(--primary))] hover:underline" onClick={onRetryHealth} type="button">
                <RefreshCw className="h-3.5 w-3.5" /> Tekrar dene
              </button>
            </div>
          ) : (
            <div className="mt-8 space-y-2">
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

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-primary))]"><ScrollText className="h-4 w-4" /></div>
      <div>
        <div className="font-serif text-lg font-semibold tracking-tight">AI-DND</div>
        <div className="font-mono text-[0.58rem] uppercase tracking-[0.16em] text-[hsl(var(--muted-foreground))]">browser / solo</div>
      </div>
    </div>
  );
}

export function Current() {
  return (
    <div className="journal-app" data-testid="app-start">
      <header className="journal-shell flex items-center justify-between gap-4 pb-2 pt-5">
        <Brand />
        <div className="hidden items-center gap-2 text-xs text-[hsl(var(--muted-foreground))] sm:flex">Kayıt defteri bekliyor</div>
      </header>
      <StartScreen
        createError={null}
        creating={false}
        health={{ status: 'healthy', engine: 'Python GameSession', model: 'qwen3:8b' }}
        healthError={null}
        healthLoading={false}
        notice={null}
        onCreate={() => undefined}
        onRetryHealth={() => undefined}
      />
    </div>
  );
}