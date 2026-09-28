import './Experience.css';
import type { ReactNode } from 'react';
import {
  BookOpen,
  Compass,
  DoorOpen,
  Feather,
  Flame,
  MapPin,
  Moon,
  Shield,
  Sparkles,
  Users,
} from 'lucide-react';
import { BrandMark, CharacterRecord, Label, Rule } from './_shared';

function NightWindowScene() {
  return (
    <div className="relative isolate h-[148px] overflow-hidden border dnd-ornament sm:h-[178px]">
      <svg
        viewBox="0 0 820 320"
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="xMidYMid slice"
        role="img"
        aria-label="A moonlit view of the Sword Coast through a tavern window"
      >
        <defs>
          <linearGradient id="night-window-sky" x1="410" y1="0" x2="410" y2="320" gradientUnits="userSpaceOnUse">
            <stop stopColor="#172738" />
            <stop offset=".62" stopColor="#304454" />
            <stop offset="1" stopColor="#52616a" />
          </linearGradient>
          <linearGradient id="night-window-sea" x1="410" y1="178" x2="410" y2="320" gradientUnits="userSpaceOnUse">
            <stop stopColor="#344b59" />
            <stop offset="1" stopColor="#1c303e" />
          </linearGradient>
          <radialGradient id="night-moon-halo">
            <stop stopColor="#d8e0dc" stopOpacity=".27" />
            <stop offset="1" stopColor="#cbd7d7" stopOpacity="0" />
          </radialGradient>
          <clipPath id="night-window-arch">
            <path d="M128 274V107a282 282 0 0 1 564 0v167H128Z" />
          </clipPath>
        </defs>
        <path fill="#282923" d="M0 0h820v320H0z" />
        <path fill="#514535" d="M0 0h88v320H0zM732 0h88v320h-88zM0 277h820v43H0z" />
        <path fill="#927247" opacity=".6" d="M89 0h14v320H89zM717 0h14v320h-14zM0 271h820v7H0z" />
        <g clipPath="url(#night-window-arch)">
          <path fill="url(#night-window-sky)" d="M105 0h610v320H105z" />
          <circle cx="572" cy="77" r="88" fill="url(#night-moon-halo)" />
          <circle cx="572" cy="77" r="25" fill="#d7dfdc" opacity=".91" />
          <circle cx="582" cy="68" r="24" fill="#344555" />
          <g fill="#e1e5e1" opacity=".76">
            <circle cx="222" cy="55" r="1.5" /><circle cx="317" cy="87" r="1.2" />
            <circle cx="420" cy="41" r="1.3" /><circle cx="647" cy="131" r="1.4" />
            <circle cx="252" cy="137" r="1" /><circle cx="513" cy="145" r="1.2" />
          </g>
          <path d="M105 159c87-23 124-8 190 0 75 9 119-15 182-2 67 14 137 3 238-15v68H105v-51Z" fill="#65717a" opacity=".37" />
          <path d="M105 190c119-6 182 13 292 5 118-8 174-21 318-4v129H105V190Z" fill="url(#night-window-sea)" />
          <path d="M105 224c92-17 166 11 246 3 97-10 194-18 364 0M171 265c129-13 186 15 286 2 72-10 117-10 208 1" fill="none" stroke="#9aabb0" strokeWidth="2" opacity=".25" />
          <path d="M105 235c65-24 105-18 151-2l59 26 53 1 41-24 56-17 40 10 37 36h173v55H105v-85Z" fill="#263945" />
          <path d="m105 221 45-27 20 3 19-23 21 1 18-15 28 3 22-19 31 1 21-15 19 4 24-10 23 6 18-4 13 13 22 1 13 18 30-3 12 21 29 2 14 22 50 9v112H105v-99Z" fill="#1b2a36" />
          <path d="M122 217c48-25 76-40 122-53M204 202c63-24 92-53 138-66m-91 61c52-20 86-41 125-51" stroke="#91a0a3" strokeWidth="1.5" opacity=".22" />
          <path d="M210 191v-25l9-11 9 11v19M206 190h26" fill="#b99361" opacity=".78" />
          <path d="M571 154v44m-6-29h12" stroke="#aab5b5" strokeWidth="2" opacity=".55" />
          <path d="M410 4v272M128 181h564" stroke="#392f25" strokeWidth="12" opacity=".88" />
          <path d="M410 4v272M128 181h564" stroke="#ae9063" strokeWidth="2" opacity=".58" />
        </g>
        <path d="M128 274V107a282 282 0 0 1 564 0v167" fill="none" stroke="#342d24" strokeWidth="24" />
        <path d="M128 274V107a282 282 0 0 1 564 0v167" fill="none" stroke="#b29464" strokeWidth="2" opacity=".72" />
        <path d="M0 288h820" stroke="#c39a62" strokeWidth="2" opacity=".46" />
        <path d="M31 0v275M789 0v275" stroke="#161c20" strokeWidth="18" opacity=".6" />
      </svg>
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(12,19,27,.06)_35%,rgba(12,19,27,.66)_100%)]" />
      <div className="absolute bottom-3 left-4 flex items-end justify-between gap-4 right-4 sm:bottom-4 sm:left-5 sm:right-5">
        <div>
          <Label className="!text-[#c8d0d2]">Kılıç Sahili · gece</Label>
          <div className="dnd-display mt-1 text-[12px] tracking-[.14em] text-[#e8e2d1] sm:text-[13px]">AY IŞIĞINDA KIYI YOLU</div>
        </div>
        <Moon size={17} strokeWidth={1.2} className="mb-1 text-[#d2d8d4]" />
      </div>
      <div className="absolute inset-[3%] border border-[#d2d5ce]/25" />
    </div>
  );
}

function NightStoryEntry({ quote = false, children }: { quote?: boolean; children: ReactNode }) {
  return (
    <article className="relative pl-5 sm:pl-7">
      <span className="absolute bottom-0 left-0 top-1 w-px bg-gradient-to-b from-[var(--gold)]/70 via-[var(--gold)]/30 to-transparent" />
      <span className="absolute left-[-3px] top-1 h-[7px] w-[7px] rotate-45 border border-[var(--gold)] bg-[var(--story)]" />
      <p className={`dnd-literary text-[21px] leading-[1.52] sm:text-[23px] ${quote ? 'border-l border-[var(--gold)] pl-4 italic' : ''}`}>{children}</p>
    </article>
  );
}

function NightStory() {
  return (
    <div className="mx-auto w-full max-w-[760px] px-5 pb-7 pt-6 sm:px-8 sm:pt-7 lg:px-10">
      <div className="mb-5 flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center border dnd-ornament dnd-panel-deep dnd-accent"><Feather size={15} strokeWidth={1.25} /></div>
        <div>
          <Label>Dungeon Master · örnek anlatı</Label>
          <div className="dnd-sans dnd-secondary mt-1 text-[9px] uppercase tracking-[.14em]">1. bölüm · Kül ve Kupa</div>
        </div>
        <div className="dnd-sans dnd-secondary ml-auto text-right text-[9px] uppercase tracking-[.12em]">Gece vakti</div>
      </div>

      <NightWindowScene />

      <div className="mb-5 mt-6 flex items-center gap-2 dnd-sans dnd-secondary text-[9px] uppercase tracking-[.16em]">
        <Sparkles size={12} className="dnd-accent" /> Pencerede ay ışığı · şöminede köz
      </div>
      <NightStoryEntry>
        Kapıyı araladığında tavernanın sıcaklığı yüzüne vurur. Yağmurun sesi arkanda yavaşça kaybolurken içerideki şömine, koyu renk ahşap masaların üzerine titrek bir ışık yayıyor.
      </NightStoryEntry>
      <p className="dnd-literary mt-4 pl-5 text-[21px] leading-[1.52] sm:pl-7 sm:text-[23px]">
        Tezgâhın arkasında iri yapılı bir adam kupaları kuruluyor. Pelerininden süzülen son damlalar kapı eşiğinde küçük bir gölcük bırakıyor.
      </p>
      <div className="dnd-sans dnd-secondary mt-5 inline-flex items-center gap-2 border-l border-[var(--gold)] pl-3 text-[9px] uppercase tracking-[.16em]"><MapPin size={12} /> Kül ve Kupa · Taverna</div>

      <div className="my-7 flex items-center gap-3"><Rule className="flex-1" /><span className="dnd-display dnd-accent text-[12px]">❦</span><Rule className="flex-1 !bg-gradient-to-l" /></div>
      <div className="mb-2 flex items-center gap-2">
        <div className="grid h-6 w-6 place-items-center border dnd-ornament dnd-secondary"><Users size={12} /></div>
        <Label>Sen · örnek seçim</Label>
        <span className="dnd-sans dnd-secondary text-[9px]">az önce</span>
      </div>
      <p className="dnd-literary dnd-secondary ml-8 border-l dnd-ornament pl-4 text-[18px] italic leading-relaxed">Barmene doğru gidip selam veriyorum.</p>
      <div className="my-7 flex items-center gap-3"><Rule className="flex-1" /><span className="dnd-display dnd-accent text-[10px]">✦</span><Rule className="flex-1 !bg-gradient-to-l" /></div>
      <NightStoryEntry>
        Adam elindeki kupayı tezgâha bırakıp sana bakıyor. Yüzündeki çizgiler şömine ışığında daha derin görünüyor.
      </NightStoryEntry>
      <div className="mt-4 pl-5 sm:pl-7">
        <NightStoryEntry quote>“Yolcuya benziyorsun,” diyor. “İçki mi arıyorsun, yoksa bilgi mi?”</NightStoryEntry>
        <div className="dnd-sans dnd-secondary mt-4 inline-flex items-center gap-2 text-[9px] uppercase tracking-[.16em]"><Users size={12} className="dnd-accent" /> Kasım · Barmen</div>
      </div>
      <div className="mt-8 border-t dnd-ornament pt-4">
        <div className="dnd-smallcap dnd-accent">Anlatı örneği · sabit içerik</div>
        <div className="dnd-literary dnd-secondary mt-1 text-[14px]">Bu görünümde hiçbir seçim gönderilmez ve hikâye ilerlemez.</div>
      </div>
    </div>
  );
}

function NightWorldPanel() {
  return (
    <aside className="dnd-focus dnd-surface border-l px-4 py-5 xl:px-5">
      <div className="relative overflow-hidden border dnd-ornament dnd-panel-deep">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_5%,rgba(169,190,203,.16),transparent_48%),radial-gradient(ellipse_at_0%_100%,rgba(185,126,76,.09),transparent_44%)]" />
        <div className="relative p-4">
          <Label>Şu an bulunduğun yer</Label>
          <div className="mt-2 flex items-end justify-between">
            <h3 className="dnd-display text-[19px] tracking-[.04em]">Taverna</h3>
            <Compass size={18} strokeWidth={1} className="mb-1 dnd-accent" />
          </div>
          <div className="dnd-sans dnd-secondary mt-3 flex items-center gap-2 text-[9px] uppercase tracking-[.12em]"><MapPin size={11} /> Kül ve Kupa</div>
        </div>
      </div>

      <section className="mt-6">
        <div className="flex items-center justify-between"><Label>Yakındaki kişiler · örnek</Label><span className="dnd-sans dnd-secondary text-[9px]">02</span></div>
        <div className="mt-3 space-y-3">
          <div className="flex items-center gap-3"><div className="grid h-8 w-8 place-items-center border dnd-ornament dnd-panel-deep dnd-display dnd-accent text-[11px]">K</div><div><div className="dnd-literary text-[17px]">Kasım</div><div className="dnd-sans dnd-secondary text-[9px]">Barmen · tezgâhın ardında</div></div></div>
          <div className="flex items-center gap-3"><div className="grid h-8 w-8 place-items-center border dnd-ornament dnd-panel-deep dnd-display dnd-accent text-[11px]">Y</div><div><div className="dnd-literary text-[17px]">Yaşlı Gezgin</div><div className="dnd-sans dnd-secondary text-[9px]">Büyük şömine yakınında</div></div></div>
        </div>
      </section>
      <section className="mt-6 border-t dnd-ornament pt-4">
        <Label>Çevre · atmosfer notları</Label>
        <div className="mt-3 space-y-3">
          <div className="flex items-start gap-2.5"><Flame size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Büyük Şömine</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">Azalan korların sıcaklığı</div></div></div>
          <div className="flex items-start gap-2.5"><Moon size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Kemerli Pencere</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">Ay ışığı · Kılıç Sahili</div></div></div>
          <div className="flex items-start gap-2.5"><DoorOpen size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Arka Kapı</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">Dar servis geçidi</div></div></div>
        </div>
      </section>
      <section className="mt-6 border-t dnd-ornament pt-4">
        <Label>Kayıt · statik önizleme</Label>
        <div className="mt-3 grid grid-cols-2 border dnd-ornament">
          <div className="border-r dnd-ornament p-3"><div className="dnd-sans dnd-secondary text-[8px] uppercase tracking-[.14em]">Bölüm</div><div className="dnd-display mt-1 text-[12px]">01</div></div>
          <div className="p-3"><div className="dnd-sans dnd-secondary text-[8px] uppercase tracking-[.14em]">Zaman</div><div className="dnd-literary mt-1 text-[14px]">Gece</div></div>
        </div>
      </section>
      <div className="dnd-sans dnd-secondary mt-5 flex items-start gap-2 border-t dnd-ornament pt-4 text-[8px] leading-4"><BookOpen size={12} className="dnd-accent mt-0.5 shrink-0" /> Tüm dünya ve karakter verileri örnek amaçlıdır.</div>
    </aside>
  );
}

function NightHeader() {
  return (
    <header className="relative z-10 flex min-h-[58px] items-center justify-between gap-4 border-b dnd-ornament px-4 sm:px-6">
      <BrandMark light />
      <div className="hidden items-center gap-3 md:flex">
        <span className="dnd-sans dnd-secondary text-[9px] uppercase tracking-[.14em]">Faerûn</span>
        <span className="h-1 w-1 rounded-full bg-[var(--gold)]" />
        <span className="dnd-sans dnd-secondary text-[9px] uppercase tracking-[.14em]">Kılıç Sahili</span>
      </div>
      <div className="flex items-center gap-2 border-l dnd-ornament pl-3 sm:pl-5">
        <div className="hidden text-right sm:block"><Label>Ortam</Label><div className="dnd-literary dnd-focus text-[15px]">Moonlight</div></div>
        <div className="grid h-8 w-8 place-items-center border dnd-ornament dnd-panel-deep dnd-accent"><Moon size={14} /></div>
      </div>
    </header>
  );
}

export function AdventureNight() {
  return (
    <main className="dnd-frame dnd-night min-h-[100dvh] overflow-hidden">
      <style>{`
        .dnd-night {
          --ink: #e5e8e9;
          --muted: #aeb9c0;
          --line: rgba(164, 184, 196, .25);
          --gold: #c6b58e;
          --accent: #c18a64;
          --panel: rgba(24, 34, 46, .96);
          --panel-deep: rgba(19, 29, 40, .98);
          --story: rgba(27, 38, 51, .985);
          background:
            radial-gradient(ellipse at 50% -5%, rgba(144, 166, 180, .2), transparent 36%),
            radial-gradient(ellipse at 95% 56%, rgba(164, 112, 70, .10), transparent 25%),
            linear-gradient(145deg, #1a2632 0%, #293744 48%, #1b252f 100%);
        }
        .dnd-night .dnd-card-shadow {
          box-shadow: 0 24px 70px rgba(8, 14, 20, .42), 0 1px 0 rgba(202, 192, 169, .06) inset;
        }
        .dnd-night::after {
          content: "";
          position: fixed;
          z-index: -1;
          inset: 0;
          pointer-events: none;
          opacity: .23;
          background: repeating-linear-gradient(0deg, transparent 0 5px, rgba(205, 215, 215, .025) 6px);
        }
      `}</style>
      <NightHeader />
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 xl:grid-cols-[250px_minmax(450px,1fr)_270px]">
        <div className="order-2 xl:order-1"><CharacterRecord /></div>
        <section className="dnd-story-surface order-1 min-w-0 border-b dnd-ornament dnd-card-shadow xl:order-2 xl:border-b-0">
          <NightStory />
          <div className="mx-auto max-w-[760px] px-5 pb-8 sm:px-8 lg:px-10">
            <div className="border dnd-ornament dnd-panel-deep p-4 sm:p-5">
              <div className="mb-3 flex items-center justify-between gap-3"><Label>Hikâyeye verilecek söz · görsel alan</Label><span className="dnd-sans dnd-secondary text-[8px] uppercase tracking-[.12em]">Devre dışı</span></div>
              <div className="flex min-h-[78px] items-end justify-between gap-3 border-b dnd-ornament pb-3">
                <div className="dnd-literary dnd-secondary text-[17px] italic">Örnek eylem alanı — bu prototipte gönderim kapalı.</div>
                <button type="button" disabled aria-label="Prototipte gönderim devre dışı" className="grid h-9 w-10 shrink-0 cursor-not-allowed place-items-center border dnd-ornament dnd-focus opacity-50"><Feather size={14} /></button>
              </div>
              <div className="dnd-sans dnd-secondary mt-3 flex items-center gap-2 text-[8px] leading-4"><Shield size={11} /> Görsel prototip · oyun turu veya karakter değişikliği yoktur.</div>
            </div>
          </div>
        </section>
        <div className="order-3"><NightWorldPanel /></div>
      </div>
      <footer className="dnd-sans dnd-secondary border-t dnd-ornament px-5 py-3 text-center text-[8px] uppercase tracking-[.14em]">Faerûn günlüğü · örnek içerik · yalnızca görsel prototip</footer>
    </main>
  );
}