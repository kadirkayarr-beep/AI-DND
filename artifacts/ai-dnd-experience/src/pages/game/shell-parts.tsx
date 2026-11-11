import { modelRefusalLine } from '@/lib/action-recovery';
import { useState, type ReactNode } from 'react';
import { combatErrorMessage } from '@/lib/combat-ui-contract';
import {
  ArrowRight,
  BookOpen,
  RefreshCw,
  Shield,
  Sparkles,
} from 'lucide-react';
import {
  getGetGameHealthQueryKey,
  useGetGameHealth,
} from '@workspace/api-client-react';
import { NoticeBanner, type Notice } from '@/components/notice-banner';
import { OuroborosMark } from '@/components/ouroboros-mark';
import { gateSoundMuted, gateSoundVolume, playGateSound, primeGateSound, setGateSoundMuted, setGateSoundVolume } from '@/lib/gate-sound';

// Without a resolved Clerk owner (local fixture) the slot still separates campaigns; the server decides access.
export const LOCAL_OWNER = 'local';

export function statusCode(error: unknown) {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { status?: number; statusCode?: number; response?: { status?: number } };
  return candidate.status ?? candidate.statusCode ?? candidate.response?.status;
}

export function friendlyError(error: unknown, fallback: string) {
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

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand" data-testid="brand-ai-dnd">
      <div className="brand-mark"><OuroborosMark /></div>
      {!compact && <div><div className="brand-name">Unwritten</div><div className="brand-subtitle">Tek oyunculu macera · Forgotten Realms</div></div>}
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

export function Kicker({ children }: { children: ReactNode }) {
  return <div className="dnd-kicker">{children}</div>;
}

export function Rule() {
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

export function OpeningScreen({ onCreate, onContinue, creating, notice, loadingCampaigns, hasCampaigns, showNoCampaigns }: { onCreate: () => void; onContinue: () => void; creating: boolean; notice: Notice | null; loadingCampaigns: boolean; hasCampaigns: boolean; showNoCampaigns: boolean }) {
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
          <div className="real-card-copy"><span className="eyebrow">HESABIN VE KAMPANYALARIN</span>{' '}<strong>Gerçek oyun, güvenli oturumunla açılır.</strong></div>
          <span className="entry-health"><EngineHealth /></span>
        </aside>
      </section>
    </main>
  );
}

export function StateSkeleton() {
  return <div className="state-column" data-testid="state-loading">{[1, 2].map((panel) => <div className="state-panel" key={panel}><div className="dnd-skeleton h-3 w-24" /><div className="dnd-skeleton mt-4 h-7 w-40" /><div className="dnd-skeleton mt-3 h-16 w-full" /><div className="dnd-skeleton mt-3 h-8 w-full" /></div>)}</div>;
}
