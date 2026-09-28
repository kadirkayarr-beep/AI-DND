import type { ReactNode } from 'react';
import {
  BookOpen,
  Compass,
  DoorOpen,
  Feather,
  Flame,
  MapPin,
  ScrollText,
  Shield,
  Sparkles,
  Swords,
  Users,
} from 'lucide-react';

export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`dnd-smallcap dnd-secondary ${className}`}>{children}</div>;
}

export function Rule({ className = '' }: { className?: string }) {
  return <div className={`dnd-rule ${className}`} />;
}

export function BrandMark({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className={`relative grid h-11 w-11 place-items-center border ${light ? 'border-[#c7aa78]/60 bg-[#242827]/55 text-[#e1c28a]' : 'border-[#927349]/65 bg-[#eee2c5]/65 text-[#8c7047]'}`}>
        <span className="absolute inset-[4px] border border-current opacity-30" />
        <Compass size={19} strokeWidth={1.25} />
      </div>
      <div>
        <div className={`dnd-display text-[12px] font-semibold tracking-[.17em] ${light ? 'text-[#f0e6d2]' : 'text-[#463b2d]'}`}>AI DUNGEON MASTER</div>
        <div className={`dnd-sans mt-1 text-[8px] uppercase tracking-[.22em] ${light ? 'text-[#c1b49d]' : 'text-[#796e5a]'}`}>Solo campaign · Sword Coast</div>
      </div>
    </div>
  );
}

export function TavernThreshold() {
  return (
    <div className="relative h-full min-h-[320px] overflow-hidden bg-[#555b56]">
      <div className="absolute inset-0 bg-[linear-gradient(125deg,rgba(205,212,202,.36),transparent_52%),linear-gradient(180deg,rgba(31,37,37,.08),rgba(25,25,22,.72))]" />
      <svg viewBox="0 0 760 620" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="threshold-sky" x1="380" y1="0" x2="380" y2="570" gradientUnits="userSpaceOnUse">
            <stop stopColor="#bdc8c2" /><stop offset=".52" stopColor="#d5c7a3" /><stop offset="1" stopColor="#5a5549" />
          </linearGradient>
          <linearGradient id="threshold-glow" x1="401" y1="280" x2="405" y2="520" gradientUnits="userSpaceOnUse">
            <stop stopColor="#edc77e" stopOpacity=".65" /><stop offset="1" stopColor="#d49a56" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path fill="url(#threshold-sky)" d="M0 0h760v620H0z" />
        <path d="M0 390c95-24 162-19 255 8 125 36 246 24 505-32v254H0V390Z" fill="#55584f" />
        <path d="M0 0h170v620H0zM590 0h170v620H590z" fill="#302d27" />
        <path d="M160 0h30v620h-30zM570 0h30v620h-30zM0 540h760v80H0z" fill="#443c31" />
        <path d="M190 16h380v465H190z" fill="#64706d" opacity=".32" />
        <path d="M213 28h335v420H213z" fill="url(#threshold-sky)" />
        <path d="M378 28v420M213 235h335" stroke="#665b49" strokeWidth="9" opacity=".75" />
        <path d="M230 30 290 447M277 30 335 447M478 30 420 447M525 30 462 447" stroke="#e1e2d5" strokeWidth="2" opacity=".3" />
        <path d="M214 330c69-39 117-42 164-14 60 34 107 40 170 6v127H214V330Z" fill="#77776a" opacity=".46" />
        <path d="M190 448h380l82 172H105l85-172Z" fill="#40382d" />
        <path d="M252 390c38-55 89-78 127-74 55 5 109 34 138 93v108H252V390Z" fill="#30251e" />
        <path d="M283 413c27-39 59-55 96-55 45 0 90 24 119 64v92H283v-101Z" fill="#aa7140" opacity=".68" />
        <path d="M327 451c12-25 32-46 47-69 16 20 16 37 36 55 14 12 17 31 14 77H327v-63Z" fill="#e2b66d" opacity=".74" />
        <path d="M0 540h760" stroke="#b99a67" strokeWidth="2" opacity=".36" />
        <path d="M86 23v196M112 23v251M632 27v240M659 27v188M44 48v133M711 68v216" stroke="#e4e7df" strokeWidth="2" opacity=".35" />
        <path d="M190 478h380" stroke="url(#threshold-glow)" strokeWidth="30" />
        <path d="M128 598h504" stroke="#a48b60" strokeWidth="2" opacity=".35" />
      </svg>
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(23,26,25,.25),transparent_50%,rgba(21,22,20,.28)),linear-gradient(0deg,rgba(20,19,17,.65),transparent_45%)]" />
      <div className="absolute left-[19%] top-[14%] h-[37%] w-px rotate-[10deg] bg-white/40" />
      <div className="absolute left-[27%] top-[20%] h-[29%] w-px rotate-[10deg] bg-white/30" />
      <div className="absolute right-[23%] top-[9%] h-[36%] w-px rotate-[10deg] bg-white/35" />
      <div className="absolute right-[17%] top-[18%] h-[24%] w-px rotate-[10deg] bg-white/30" />
      <div className="absolute bottom-7 left-7 flex items-end justify-between gap-5 right-7">
        <div>
          <Label className="!text-[#d4c19b]">Yolun başladığı yer</Label>
          <div className="dnd-display mt-2 text-[clamp(1rem,2vw,1.45rem)] tracking-[.13em] text-[#f2e4c6]">KÜL VE KUPA</div>
        </div>
        <Compass className="mb-1 text-[#d9bb80]" size={22} strokeWidth={1} />
      </div>
      <div className="absolute inset-[3%] border border-[#dfc69b]/30" />
      <div className="absolute left-3 top-3 h-5 w-5 border-l border-t border-[#e0c899]/75" />
      <div className="absolute right-3 top-3 h-5 w-5 border-r border-t border-[#e0c899]/75" />
    </div>
  );
}

const sampleStats = [['STR', '11'], ['DEX', '15'], ['CON', '15'], ['INT', '10'], ['WIS', '14'], ['CHA', '14']];

export function CharacterRecord({ creation = false }: { creation?: boolean }) {
  const itemTone = creation ? 'border-[#93754c]/30 bg-[#e9dfc7]/70' : 'border-current/15 bg-current/[.035]';
  return (
    <aside className={`dnd-focus ${creation ? '' : 'dnd-surface border-r'} px-4 py-5 xl:px-5`}>
      <div className="flex items-center justify-between">
        <Label>Yolcu kaydı</Label>
        <span className="dnd-display dnd-accent border dnd-ornament px-2 py-1 text-[9px] tracking-[.12em]">LVL 01</span>
      </div>
      <div className={`relative mt-4 flex aspect-[.91] max-h-[245px] items-center justify-center overflow-hidden border dnd-ornament ${creation ? 'bg-[#e8ddc3]/65' : 'dnd-panel-deep'}`}>
        <div className="absolute inset-2 border dnd-ornament opacity-50" />
        <div className="absolute inset-4 border border-dashed dnd-ornament opacity-55" />
        <div className="absolute inset-[12%_15%_16%] rounded-[48%_48%_3%_3%] border dnd-ornament opacity-70" />
        <div className="absolute left-5 top-5 h-4 w-4 border-l border-t dnd-ornament" />
        <div className="absolute right-5 top-5 h-4 w-4 border-r border-t dnd-ornament" />
        <div className="absolute bottom-5 left-5 h-4 w-4 border-b border-l dnd-ornament" />
        <div className="absolute bottom-5 right-5 h-4 w-4 border-b border-r dnd-ornament" />
        <div className={`relative mt-20 dnd-sans text-[8px] uppercase tracking-[.2em] ${creation ? 'text-[#897956]' : 'dnd-secondary'}`}>Boş portre alanı</div>
        {!creation && <Compass size={15} strokeWidth={1} className="absolute bottom-3 right-3 dnd-accent" />}
      </div>
      <div className="mt-5 text-center">
        <h2 className="dnd-display text-[21px] tracking-[.13em]">CEDRIC</h2>
        <div className="dnd-literary dnd-secondary mt-1 text-[17px]">Elf Wizard <span className="mx-1 dnd-accent">·</span> Level 1</div>
      </div>
      <div className={`mt-5 border dnd-ornament p-3 ${creation ? 'bg-[#eee4ce]/65' : 'dnd-panel-deep'}`}>
        <div className="flex items-end justify-between">
          <div><Label>Hit points · örnek</Label><div className="dnd-display mt-1 text-[22px] leading-none">8 <span className="dnd-secondary text-[13px]">/ 10</span></div></div>
          <div className="dnd-sans dnd-accent mb-1 text-[9px]">İllüstratif</div>
        </div>
        <div className="mt-3 h-[4px] bg-[#9b896a]/25"><div className="h-full w-[80%] bg-[#a58250]" /></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className={`flex items-center justify-between border dnd-ornament px-2.5 py-2 ${itemTone}`}><Label>AC</Label><span className="dnd-display text-sm">12</span></div>
        <div className={`flex items-center justify-between border dnd-ornament px-2.5 py-2 ${itemTone}`}><Label>PB</Label><span className="dnd-display text-sm">+2</span></div>
      </div>
      <div className="mt-5">
        <Label>Özellikler · örnek değerler</Label>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {sampleStats.map(([stat, value]) => <div key={stat} className={`border dnd-ornament py-2 text-center ${itemTone}`}><div className="dnd-sans dnd-secondary text-[8px] tracking-[.12em]">{stat}</div><div className="dnd-display mt-0.5 text-sm">{value}</div></div>)}
        </div>
      </div>
      {!creation && <div className="mt-5">
        <Label>Üzerindekiler · örnek</Label>
        <div className="dnd-literary dnd-secondary mt-2 space-y-2 text-[16px]">
          <div className="flex items-center gap-2"><Swords size={13} className="dnd-accent" /> Kılıç</div>
          <div className="flex items-center gap-2"><ScrollText size={13} className="dnd-accent" /> Macera çantası</div>
        </div>
      </div>}
      <div className="mt-4 border-t dnd-ornament pt-3">
        <Label>Durum · örnek</Label>
        <div className="dnd-literary dnd-secondary mt-2 flex items-center gap-2 text-[15px]"><span className="h-1.5 w-1.5 rounded-full bg-[#82916a]" /> Etki yok</div>
      </div>
      <p className="dnd-sans dnd-secondary mt-4 text-[8px] leading-4">Bu kayıt yalnızca tasarım örneğidir; oyun durumu içermez.</p>
    </aside>
  );
}

function StoryEntry({ quote = false, children }: { quote?: boolean; children: ReactNode }) {
  return (
    <article className="relative pl-5 sm:pl-7">
      <span className="absolute bottom-0 left-0 top-1 w-px bg-gradient-to-b from-[var(--gold)]/70 via-[var(--gold)]/30 to-transparent" />
      <span className="absolute left-[-3px] top-1 h-[7px] w-[7px] rotate-45 border border-[var(--gold)] bg-[var(--story)]" />
      <p className={`dnd-literary text-[21px] leading-[1.52] sm:text-[23px] ${quote ? 'border-l border-[var(--gold)] pl-4 italic' : ''}`}>{children}</p>
    </article>
  );
}

export function StoryFeed({ evening = false }: { evening?: boolean }) {
  return (
    <div className="mx-auto w-full max-w-[760px] px-5 pb-7 pt-7 sm:px-8 lg:px-10">
      <div className="mb-7 flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center border dnd-ornament dnd-panel-deep dnd-accent"><Feather size={15} strokeWidth={1.25} /></div>
        <div><Label>Dungeon Master · örnek anlatı</Label><div className="dnd-sans dnd-secondary mt-1 text-[9px] uppercase tracking-[.14em]">1. bölüm · Kül ve Kupa</div></div>
        <div className="dnd-sans dnd-secondary ml-auto text-right text-[9px] uppercase tracking-[.12em]">{evening ? 'Akşam vakti' : 'Gün ortası'}</div>
      </div>
      <StoryEntry>
        Kapıyı araladığında tavernanın sıcaklığı yüzüne vurur. Yağmurun sesi arkanda yavaşça kaybolurken içerideki şömine, koyu renk ahşap masaların üzerine titrek bir ışık yayıyor.
      </StoryEntry>
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
      <StoryEntry>
        Adam elindeki kupayı tezgâha bırakıp sana bakıyor. Yüzündeki çizgiler şömine ışığında daha derin görünüyor.
      </StoryEntry>
      <div className="mt-4 pl-5 sm:pl-7">
        <StoryEntry quote>“Yolcuya benziyorsun,” diyor. “İçki mi arıyorsun, yoksa bilgi mi?”</StoryEntry>
        <div className="dnd-sans dnd-secondary mt-4 inline-flex items-center gap-2 text-[9px] uppercase tracking-[.16em]"><Users size={12} className="dnd-accent" /> Kasım · Barmen</div>
      </div>
      <div className="mt-8 border-t dnd-ornament pt-4">
        <div className="dnd-smallcap dnd-accent">Anlatı örneği · sabit içerik</div>
        <div className="dnd-literary dnd-secondary mt-1 text-[14px]">Bu görünümde hiçbir seçim gönderilmez ve hikâye ilerlemez.</div>
      </div>
    </div>
  );
}

export function WorldPanel({ evening = false }: { evening?: boolean }) {
  return (
    <aside className="dnd-focus dnd-surface border-l px-4 py-5 xl:px-5">
      <div className="relative overflow-hidden border dnd-ornament dnd-panel-deep">
        <div className={`absolute inset-0 ${evening ? 'bg-[radial-gradient(ellipse_at_68%_15%,rgba(217,156,85,.18),transparent_45%)]' : 'bg-[radial-gradient(ellipse_at_72%_0%,rgba(233,224,198,.58),transparent_50%)]'}`} />
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
          <div className="flex items-start gap-2.5"><Flame size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Büyük Şömine</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">Çıtırdayan odunlar</div></div></div>
          <div className="flex items-start gap-2.5"><Sparkles size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Kemerli Pencere</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">{evening ? 'Bakır rengi alacakaranlık' : 'Bulutların ardından yumuşak ışık'}</div></div></div>
          <div className="flex items-start gap-2.5"><DoorOpen size={13} className="dnd-accent mt-1" /><div><div className="dnd-literary text-[16px] leading-4">Arka Kapı</div><div className="dnd-sans dnd-secondary mt-1 text-[9px]">Dar servis geçidi</div></div></div>
        </div>
      </section>
      <section className="mt-6 border-t dnd-ornament pt-4">
        <Label>Kayıt · statik önizleme</Label>
        <div className="mt-3 grid grid-cols-2 border dnd-ornament">
          <div className="border-r dnd-ornament p-3"><div className="dnd-sans dnd-secondary text-[8px] uppercase tracking-[.14em]">Bölüm</div><div className="dnd-display mt-1 text-[12px]">01</div></div>
          <div className="p-3"><div className="dnd-sans dnd-secondary text-[8px] uppercase tracking-[.14em]">Zaman</div><div className="dnd-literary mt-1 text-[14px]">{evening ? 'Akşam' : 'Gündüz'}</div></div>
        </div>
      </section>
      <div className="dnd-sans dnd-secondary mt-5 flex items-start gap-2 border-t dnd-ornament pt-4 text-[8px] leading-4"><BookOpen size={12} className="dnd-accent mt-0.5 shrink-0" /> Tüm dünya ve karakter verileri örnek amaçlıdır.</div>
    </aside>
  );
}

export function WorkspaceHeader({ evening = false }: { evening?: boolean }) {
  return (
    <header className="relative z-10 flex min-h-[58px] items-center justify-between gap-4 border-b dnd-ornament px-4 sm:px-6">
      <BrandMark light={evening} />
      <div className="hidden items-center gap-3 md:flex">
        <span className="dnd-sans dnd-secondary text-[9px] uppercase tracking-[.14em]">Faerûn</span>
        <span className="h-1 w-1 rounded-full bg-[var(--gold)]" />
        <span className="dnd-sans dnd-secondary text-[9px] uppercase tracking-[.14em]">Kılıç Sahili</span>
      </div>
      <div className="flex items-center gap-2 border-l dnd-ornament pl-3 sm:pl-5">
        <div className="hidden text-right sm:block"><Label>Ortam</Label><div className="dnd-literary dnd-focus text-[15px]">{evening ? 'Hearthlight' : 'Windowlight'}</div></div>
        <div className="grid h-8 w-8 place-items-center border dnd-ornament dnd-panel-deep dnd-accent">{evening ? <Flame size={14} /> : <Sparkles size={14} />}</div>
      </div>
    </header>
  );
}

export function AdventureWorkspace({ evening = false }: { evening?: boolean }) {
  return (
    <main className={`dnd-frame ${evening ? 'dnd-evening' : 'dnd-day'} min-h-[100dvh] overflow-hidden`}>
      <WorkspaceHeader evening={evening} />
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 xl:grid-cols-[250px_minmax(450px,1fr)_270px]">
        <div className="order-2 xl:order-1"><CharacterRecord /></div>
        <section className="dnd-story-surface order-1 min-w-0 border-b dnd-ornament dnd-card-shadow xl:order-2 xl:border-b-0">
          <StoryFeed evening={evening} />
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
        <div className="order-3"><WorldPanel evening={evening} /></div>
      </div>
      <footer className="dnd-sans dnd-secondary border-t dnd-ornament px-5 py-3 text-center text-[8px] uppercase tracking-[.14em]">Faerûn günlüğü · örnek içerik · yalnızca görsel prototip</footer>
    </main>
  );
}