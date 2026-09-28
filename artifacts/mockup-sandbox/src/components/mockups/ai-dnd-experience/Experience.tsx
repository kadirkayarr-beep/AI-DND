import './Experience.css';
import { ArrowRight, BookOpen, CloudRain, Feather } from 'lucide-react';
import { BrandMark, Label, Rule, TavernThreshold } from './_shared';

export function Experience() {
  return (
    <main className="dnd-frame dnd-opening min-h-[100dvh] overflow-hidden">
      <header className="relative z-10 mx-auto flex max-w-[1480px] items-center justify-between px-5 py-5 sm:px-8 md:px-12 md:py-7">
        <BrandMark light />
        <div className="hidden items-center gap-3 md:flex">
          <CloudRain size={15} className="text-[#d2bb90]" strokeWidth={1.3} />
          <span className="dnd-sans text-[9px] uppercase tracking-[.18em] text-[#d0c2a7]">Yağmurlu şafak · 1492 DR</span>
        </div>
      </header>
      <div className="relative mx-auto grid min-h-[calc(100dvh-84px)] max-w-[1480px] items-center gap-9 px-5 pb-14 pt-3 sm:px-8 md:grid-cols-[.92fr_1.08fr] md:px-12 lg:gap-16">
        <section className="dnd-reveal relative z-10 order-2 max-w-[610px] md:order-1">
          <div className="mb-7 flex items-center gap-3">
            <span className="h-px w-12 bg-[#c6a26a]" />
            <Label className="!text-[#d0c0a1]">Kapılar aralanıyor · 1492 DR</Label>
          </div>
          <h1 className="dnd-display text-[clamp(3.25rem,8.3vw,7.3rem)] font-medium leading-[.88] tracking-[-.055em] text-[#f1e7d3]">
            Hikâyeni<br /><span className="text-[#d8b780]">anlat.</span>
          </h1>
          <p className="dnd-literary mt-7 text-[27px] leading-tight text-[#e1d4bc] md:text-[31px]">Dünya cevap versin.</p>
          <p className="dnd-sans mt-4 max-w-[390px] text-[13px] leading-6 text-[#d0c5b0]">
            Yağmurun izini kapıda bırak. Bir karakterin sayfasını aç; Kılıç Sahili’nde seni bekleyen hikâyeye yaklaş.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <button type="button" disabled className="dnd-entry inline-flex items-center gap-3 px-5 py-4 font-['DM_Sans'] text-[9px] font-semibold uppercase tracking-[.18em]">
              Yeni macera <ArrowRight size={14} />
            </button>
            <button type="button" disabled className="inline-flex items-center gap-3 border border-[#d1bd96]/40 bg-[#272a27]/45 px-5 py-4 font-['DM_Sans'] text-[9px] font-semibold uppercase tracking-[.15em] text-[#e0d2b9]">
              <BookOpen size={14} strokeWidth={1.4} /> Maceraya devam et
            </button>
          </div>
          <div className="mt-3 dnd-sans text-[8px] uppercase tracking-[.12em] text-[#c2b49b]">Önizleme · bu görsel çağrılar gezinme başlatmaz</div>
          <div className="mt-10 flex flex-wrap items-center gap-x-3 gap-y-2 text-[#c9b99a]">
            <span className="dnd-display text-[8px] tracking-[.18em]">TEK OYUNCU</span><span className="h-1 w-1 rounded-full bg-[#c2a36e]" />
            <span className="dnd-display text-[8px] tracking-[.18em]">DOĞAL DİLLE</span><span className="h-1 w-1 rounded-full bg-[#c2a36e]" />
            <span className="dnd-display text-[8px] tracking-[.18em]">SENİN SEÇİMİN</span>
          </div>
        </section>
        <section className="dnd-reveal-delay relative order-1 mx-auto aspect-[1.18] w-full max-w-[760px] md:order-2 md:aspect-[.98]">
          <div className="absolute inset-[3%] border border-[#dac393]/26" />
          <div className="absolute inset-[5%] overflow-hidden border border-[#ceb17d]/50 bg-[#53564f] dnd-card-shadow">
            <TavernThreshold />
            <div className="absolute right-[8%] top-[8%] flex items-center gap-2 border border-[#e1c58f]/35 bg-[#242724]/55 px-3 py-2">
              <CloudRain size={12} className="text-[#dfc28c]" />
              <span className="dnd-sans text-[8px] uppercase tracking-[.13em] text-[#eadbbd]">Şafak yağmuru</span>
            </div>
            <div className="absolute left-[8%] top-[8%] grid h-11 w-11 place-items-center rounded-full border border-[#e0c797]/35 bg-[#252724]/55 text-[#ddbd81]">
              <Feather size={17} strokeWidth={1.15} />
            </div>
          </div>
          <div className="absolute -bottom-1 right-[9%] flex items-center gap-3 border border-[#c6a36c]/25 bg-[#272724]/90 px-4 py-3">
            <span className="h-1.5 w-1.5 rounded-full bg-[#d9b873]" />
            <span className="dnd-sans text-[8px] uppercase tracking-[.14em] text-[#d3c4a5]">Yağmurun ardından, bir kapı aralanır</span>
          </div>
        </section>
        <div className="pointer-events-none absolute bottom-0 left-0 h-px w-full bg-gradient-to-r from-transparent via-[#c2a06b]/50 to-transparent" />
      </div>
      <div className="absolute left-0 top-0 -z-10 h-full w-full bg-[radial-gradient(ellipse_at_12%_54%,rgba(16,21,22,.48),transparent_53%)]" />
      <Rule className="absolute left-8 top-[18%] hidden w-20 opacity-40 md:block" />
    </main>
  );
}