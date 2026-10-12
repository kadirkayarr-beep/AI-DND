import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  MapPinned,
  Plus,
  RefreshCw,
  ScrollText,
} from 'lucide-react';
import type { CampaignSummary, CampaignStartOptionsResponse } from '@workspace/api-client-react';
import { campaignLocationLabel, classLabel, speciesLabel } from '@/lib/campaign-presentation';
import { playGateSound, primeGateSound } from '@/lib/gate-sound';
import '@/components/cinematic-gate.css';
import { getGetCampaignsQueryKey, useDeleteCampaign } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

function statusOf(error: unknown) {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { status?: number };
  return candidate.status;
}

function formatPlayedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Zaman bilinmiyor';
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

type CampaignLibraryProps = {
  campaigns?: CampaignSummary[];
  locationCatalog?: CampaignStartOptionsResponse;
  loading: boolean;
  error: unknown;
  resuming: boolean;
  resumingCampaignId: string | null;
  notice: { tone: 'error' | 'success' | 'warning'; title: string; detail: string } | null;
  onBack: () => void;
  onNew: () => void;
  onResume: (campaignId: string) => void;
  onRetry: () => void;
  onDeleted?: (campaignId: string) => void;
};

export function CampaignLibrary({
  campaigns,
  locationCatalog,
  loading,
  error,
  resuming,
  resumingCampaignId,
  notice,
  onBack,
  onNew,
  onResume,
  onRetry,
  onDeleted,
}: CampaignLibraryProps) {
  const deletion = useDeleteCampaign();
  const queryClient = useQueryClient();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [removed, setRemoved] = useState<Set<string>>(() => new Set());
  const deleteSelected = (campaign: CampaignSummary) => {
    if (!window.confirm(`“${campaign.name}” macerasını kalıcı olarak silmek istiyor musun? Bu maceranın tüm geçmişi silinecek. Geri alınamaz.`)) return;
    setDeleteError(null);
    deletion.mutate({ campaignId: campaign.campaign_id }, {
      onSuccess: () => {
        setRemoved(previous => new Set(previous).add(campaign.campaign_id));
        void queryClient.invalidateQueries({ queryKey: getGetCampaignsQueryKey() });
        onDeleted?.(campaign.campaign_id);
      },
      onError: () => setDeleteError('Macera silinemedi. Kaydın listede korunuyor; yeniden deneyebilirsin.'),
    });
  };
  campaigns = campaigns?.filter(campaign => !removed.has(campaign.campaign_id));
  return (
    <main className="opening cinematic-gate gate-fade" data-testid="screen-campaign-library">
      <div className="dnd-shell">
        <header className="opening-header">
          <button className="text-button" type="button" onClick={onBack} data-testid="button-back-opening">
            <ArrowLeft size={13} /> Geri dön
          </button>
          <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[.18em] text-[#8f8069]">
            <ScrollText size={14} /> Macera defteri
          </div>
        </header>

        <section className="gate-library mx-auto max-w-4xl py-8 md:py-14">
          <div className="mb-8 max-w-2xl">
            <div className="opening-eyebrow"><span className="dnd-kicker">Kayıtlı yolculuklar</span></div>
            <h1 className="dnd-display mt-4 text-4xl text-[#eddfc5] sm:text-5xl">Karakterler<br /><span className="text-[#c09a61]">ve kayıtlar.</span></h1>
            <p className="dnd-serif mt-4 max-w-xl text-lg leading-7 text-[#a99a80]">
              Her macera, bıraktığın dünyaya açılır. Bir yolculuğu seç ya da yeni bir sayfa başlat.
            </p>
          </div>

          {notice && (
            <div className={`notice ${notice.tone === 'error' ? 'error' : notice.tone === 'success' ? 'success' : ''} mb-6`} role="status">
              <AlertTriangle size={15} className="shrink-0" />
              <div><strong>{notice.title}</strong><div>{notice.detail}</div></div>
            </div>
          )}

          {loading ? (
            <div className="grid gap-4" data-testid="campaign-list-loading">
              {[1, 2].map((item) => (
                <div className="dnd-card p-6" key={item}>
                  <div className="dnd-skeleton h-3 w-32" />
                  <div className="dnd-skeleton mt-4 h-7 w-56" />
                  <div className="dnd-skeleton mt-4 h-4 w-48" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="dnd-card dnd-texture p-7" data-testid="campaign-list-error">
              <div className="relative z-10">
                <div className="flex items-center gap-2 text-[#dca49b]"><AlertTriangle size={16} /> {statusOf(error) === 401 ? 'Kimlik doğrulaması gerekli.' : 'Kayıt defteri açılamadı.'}</div>
                <p className="dnd-serif mt-3 text-lg text-[#a99a80]">{statusOf(error) === 401 ? 'Oturum doğrulanmadan maceralar açılmaz.' : 'Dungeon Master’a şu anda ulaşılamıyor.'}</p>
                <button className="dnd-button secondary mt-5" type="button" onClick={onRetry} data-testid="button-retry-campaigns">
                  <RefreshCw size={14} /> Yeniden dene
                </button>
              </div>
            </div>
          ) : campaigns?.length ? (
            <div className="grid gap-4" data-testid="campaign-list">
              {campaigns.map((campaign) => {
                const isResuming = resuming && resumingCampaignId === campaign.campaign_id;
                return (
                  <article
                    className="dnd-card dnd-texture p-5 sm:p-7"
                    key={campaign.campaign_id}
                    data-testid={`campaign-card-${campaign.campaign_id}`}
                  >
                    <div className="relative z-10">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <div className="dnd-kicker">Kayıtlı macera · Seviye {campaign.character_level}</div>
                          <h2 className="dnd-display mt-2 text-2xl text-[#eddfc5] sm:text-3xl">{campaign.name}</h2>
                          <p className="mt-2 font-serif text-base text-[#c09a61]">
                            {speciesLabel(campaign.character_race)} {classLabel(campaign.character_class)} · {campaign.character_name}
                          </p>
                        </div>
                        <BookOpen className="mt-1 text-[#9b7946]" size={20} aria-hidden="true" />
                      </div>

                      <div className="my-5 border-t border-[#4b3926]" />
                      <div className="flex flex-col gap-3 text-sm text-[#a99a80] sm:flex-row sm:items-center sm:gap-8">
                        <div className="flex items-center gap-2" data-testid="campaign-location">
                          <MapPinned size={14} className="text-[#c09a61]" />
                          <span><span className="text-[#83745e]">Son konum:</span> {campaignLocationLabel(campaign.location, locationCatalog)}</span>
                        </div>
                        <div className="flex items-center gap-2" data-testid="campaign-last-played">
                          <CalendarDays size={14} className="text-[#c09a61]" />
                          <span><span className="text-[#83745e]">Son oynanma:</span> {formatPlayedAt(campaign.last_played_at)}</span>
                        </div>
                      </div>

                      <div className="mt-6 flex justify-end gap-3">
                        <button type="button" className="text-button" disabled={resuming || deletion.isPending}
                          data-testid={`button-delete-${campaign.campaign_id}`}
                          onClick={() => deleteSelected(campaign)}>Macerayı sil</button>
                        <button
                          className="dnd-button"
                          type="button"
                          disabled={resuming || deletion.isPending}
                          onClick={() => { primeGateSound(); playGateSound('menu'); onResume(campaign.campaign_id); }}
                          data-testid={`button-resume-${campaign.campaign_id}`}
                        >
                          {isResuming ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                          {isResuming ? 'Kayıt açılıyor' : 'Maceraya devam et'}
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="dnd-card dnd-texture p-7 text-center sm:p-10" data-testid="campaign-list-empty">
              <div className="relative z-10">
                <div className="mx-auto grid h-12 w-12 place-items-center border border-[#9b7946]/60 text-[#c6a46d]">
                  <ScrollText size={20} />
                </div>
                <h2 className="dnd-display mt-5 text-2xl text-[#eddfc5]">Henüz kayıtlı macera yok.</h2>
                <p className="dnd-serif mx-auto mt-3 max-w-md text-lg text-[#a99a80]">
                  Yeni yolculuğunu daha sonra buradan kaldığın yerden sürdürebilirsin.
                </p>
                <button className="dnd-button mt-6" type="button" onClick={onNew} data-testid="button-create-from-library">
                  <Plus size={14} /> Yeni macera
                </button>
              </div>
            </div>
          )}

          {deleteError && <p role="alert" className="mt-5 text-red-300">{deleteError}</p>}
          <div className="mt-7 flex justify-between">
            <button className="text-button" type="button" onClick={onBack}><ArrowLeft size={13} /> Ana kapıya dön</button>
            {campaigns?.length ? (
              <button className="text-button" type="button" onClick={onNew} data-testid="button-new-from-library">
                <Plus size={13} /> Yeni macera
              </button>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}