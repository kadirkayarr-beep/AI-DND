import { useState, type ReactNode } from 'react';
import './Experience.css';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  ChevronDown,
  Compass,
  DoorOpen,
  Feather,
  Flame,
  Map,
  Menu,
  MessageCircle,
  ScrollText,
  Shield,
  Sparkles,
  Swords,
  Users,
  X,
} from 'lucide-react';

type Screen = 'opening' | 'creation' | 'adventure';
type ContextTab = 'world' | 'npcs' | 'journal' | 'combat';

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-10 w-10 place-items-center border border-[#9b7946]/70 bg-[#17130f] text-[#d1b37c]">
        <span className="absolute inset-[4px] border border-[#9b7946]/35" />
        <Compass size={18} strokeWidth={1.35} />
      </div>
      {!compact && (
        <div>
          <div className="font-['Cinzel'] text-[13px] font-semibold tracking-[.2em] text-[#eee2c8]">AI DUNGEON MASTER</div>
          <div className="mt-0.5 font-['DM_Sans'] text-[9px] uppercase tracking-[.24em] text-[#8f8069]">Solo campaign · Sword Coast</div>
        </div>
      )}
    </div>
  );
}

function Candle({ className = '' }: { className?: string }) {
  return (
    <span className={`relative inline-flex h-8 w-[7px] items-end justify-center rounded-sm bg-[#a4865a] ${className}`}>
      <span className="absolute -top-[10px] h-3 w-2 rounded-[80%_0_80%_0] rotate-[-35deg] bg-[#e4bd73] shadow-[0_0_16px_5px_rgba(218,156,72,.26)]" />
      <span className="absolute -bottom-1 h-1.5 w-4 rounded-full bg-[#5b4831]" />
    </span>
  );
}

function TavernArtwork({ large = false }: { large?: boolean }) {
  return (
    <div className={`pointer-events-none relative overflow-hidden ${large ? 'h-full min-h-[430px]' : 'h-[260px]'}`}>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_55%_61%,rgba(169,93,36,.25),transparent_36%),linear-gradient(180deg,rgba(18,16,14,.08),rgba(14,12,11,.88))]" />
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 760 560" fill="none" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id="wood" x1="380" y1="0" x2="380" y2="560" gradientUnits="userSpaceOnUse">
            <stop stopColor="#45301e" />
            <stop offset="1" stopColor="#140f0c" />
          </linearGradient>
          <radialGradient id="hearth" cx="0" cy="0" r="1" gradientTransform="matrix(0 175 -255 0 386 350)" gradientUnits="userSpaceOnUse">
            <stop stopColor="#c87937" stopOpacity=".64" />
            <stop offset="1" stopColor="#6c351b" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="light" x1="404" y1="225" x2="425" y2="402" gradientUnits="userSpaceOnUse">
            <stop stopColor="#dc9c4a" stopOpacity=".72" />
            <stop offset="1" stopColor="#dc9c4a" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path fill="url(#wood)" d="M0 0h760v560H0z" />
        <path d="M0 0h760v44H0zM60 0v298M111 0v271M649 0v260M703 0v294" stroke="#725235" strokeOpacity=".28" strokeWidth="10" />
        <path d="M0 72h760M0 138h760M0 205h760" stroke="#a17a48" strokeOpacity=".18" strokeWidth="2" />
        <path d="M0 0h760v560H0z" fill="url(#hearth)" />
        <path d="M281 372c-24-69 2-145 36-183 29-34 78-45 128-31 48 13 89 63 98 114 8 48-17 85-5 134l-258-34Z" fill="#17110d" stroke="#946b3c" strokeOpacity=".48" strokeWidth="4" />
        <path d="M322 363c-12-59 0-113 36-145 22-20 55-24 83-11 37 17 55 53 58 92 2 30 13 45 6 80l-183-16Z" fill="#3b2013" />
        <path d="M344 365c16-31 10-66 36-87 13-10 19-21 26-39 17 17 16 32 34 47 17 14 33 40 24 84l-120-5Z" fill="#cf7936" opacity=".75" />
        <path d="M371 362c10-24 2-44 20-62 8-8 13-18 14-31 18 18 12 31 29 44 11 9 14 24 9 53l-72-4Z" fill="#e3b35e" opacity=".78" />
        <path d="M95 403c15-32 45-52 76-52s61 20 76 52v43H95v-43Z" fill="#19130f" stroke="#9b7849" strokeOpacity=".38" strokeWidth="2" />
        <path d="M76 447h205v14H76zM0 493c121-26 240-27 357-16 119 11 252 3 403-24v107H0v-67Z" fill="#120e0b" />
        <path d="M54 520h642M108 493v67M250 486v74M544 474v86M652 464v96" stroke="#755535" strokeOpacity=".3" strokeWidth="3" />
        <path d="m476 191 14-65 4 65M555 218l14-58 4 58" stroke="#d7aa64" strokeOpacity=".4" strokeWidth="2" />
        <circle cx="492" cy="121" r="8" fill="#e2b36a" opacity=".78" />
        <circle cx="573" cy="153" r="7" fill="#e2b36a" opacity=".65" />
        <path d="M443 198 325 365M516 198l78 170" stroke="url(#light)" strokeWidth="38" opacity=".19" />
        <path d="M18 42h720M18 478h720" stroke="#b18b55" strokeOpacity=".3" />
        <path d="M26 52h18M716 52h18M26 468h18M716 468h18" stroke="#d1b37c" strokeOpacity=".62" />
      </svg>
      <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-[#100d0a] to-transparent" />
      <div className="absolute left-[23%] top-[17%]"><Candle /></div>
      <div className="absolute right-[24%] top-[24%] scale-[.82]"><Candle /></div>
    </div>
  );
}

function TinyLabel({ children }: { children: ReactNode }) {
  return <div className="font-['DM_Sans'] text-[9px] font-semibold uppercase tracking-[.2em] text-[#9b8a70]">{children}</div>;
}

function Rule({ className = '' }: { className?: string }) {
  return <div className={`h-px bg-gradient-to-r from-[#997744]/70 via-[#624d33]/55 to-transparent ${className}`} />;
}

function OpeningScreen({ onCreate, onContinue }: { onCreate: () => void; onContinue: () => void }) {
  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[#100e0c] text-[#e6dcc8]">
      <div className="absolute inset-0 opacity-[.16]" style={{ backgroundImage: 'radial-gradient(ellipse at 50% 42%, #664629 0, transparent 57%), repeating-linear-gradient(0deg, transparent 0 47px, rgba(186,149,91,.08) 48px)' }} />
      <header className="relative z-10 mx-auto flex max-w-[1440px] items-center justify-between px-6 py-6 md:px-12">
        <BrandMark />
        <span className="hidden font-['DM_Sans'] text-[10px] uppercase tracking-[.2em] text-[#8f8069] md:block">Bir hikâye, yalnızca senin</span>
      </header>
      <div className="relative mx-auto grid min-h-[calc(100dvh-90px)] max-w-[1440px] items-center gap-8 px-6 pb-14 pt-4 md:grid-cols-[.94fr_1.06fr] md:px-12 lg:gap-16">
        <section className="relative z-10 order-2 max-w-[610px] md:order-1">
          <div className="mb-6 flex items-center gap-3">
            <span className="h-px w-12 bg-[#ae8752]" />
            <TinyLabel>Kapılar açılıyor · 1492 DR</TinyLabel>
          </div>
          <h1 className="font-['Cinzel'] text-[clamp(3.3rem,8vw,7.4rem)] font-medium leading-[.9] tracking-[-.045em] text-[#f1e6d0]">
            Hikâyeni<br /><span className="text-[#bd9a65]">anlat.</span>
          </h1>
          <p className="mt-7 max-w-[390px] font-['Cormorant_Garamond'] text-[25px] leading-[1.25] text-[#c8baa1] md:text-[29px]">
            Dünya cevap versin.
          </p>
          <p className="mt-4 max-w-[390px] font-['DM_Sans'] text-[13px] leading-6 text-[#938775]">
            Yağmurun izini kapıda bırak. Bir karakter seç, gerisini kendi sözlerinle keşfet.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <button onClick={onCreate} className="group inline-flex items-center gap-3 border border-[#b18b55] bg-[#6c3028] px-6 py-4 font-['DM_Sans'] text-[10px] font-semibold uppercase tracking-[.19em] text-[#f1e5cf] transition-colors hover:bg-[#813d32]" type="button">
              Yeni macera <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
            </button>
            <button onClick={onContinue} className="inline-flex items-center gap-3 border border-[#756147]/55 bg-[#211a14]/65 px-6 py-4 font-['DM_Sans'] text-[10px] font-semibold uppercase tracking-[.16em] text-[#c9b99e] transition-colors hover:border-[#ad8954]" type="button">
              <BookOpen size={14} strokeWidth={1.5} /> Maceraya devam et
            </button>
          </div>
          <div className="mt-12 flex items-center gap-4 text-[#786b58]">
            <span className="font-['Cinzel'] text-[9px] tracking-[.2em]">TEK OYUNCU</span><span className="h-1 w-1 rounded-full bg-[#8f7148]" /><span className="font-['Cinzel'] text-[9px] tracking-[.2em]">DOĞAL DİLLE</span><span className="h-1 w-1 rounded-full bg-[#8f7148]" /><span className="font-['Cinzel'] text-[9px] tracking-[.2em]">SENİN SEÇİMİN</span>
          </div>
        </section>
        <section className="relative order-1 mx-auto aspect-[1.19] w-full max-w-[740px] md:order-2 md:aspect-[.98]">
          <div className="absolute inset-[4%] border border-[#876741]/30" />
          <div className="absolute inset-[6%] overflow-hidden border border-[#8d6a3f]/55 bg-[#1c1510] shadow-[0_22px_80px_rgba(0,0,0,.5)]">
            <TavernArtwork large />
            <div className="absolute bottom-[8%] left-[8%] z-10">
              <TinyLabel>Yolun başladığı yer</TinyLabel>
              <div className="mt-2 font-['Cinzel'] text-[clamp(1rem,2vw,1.55rem)] tracking-[.14em] text-[#ead8b6]">KÜL VE KUPA</div>
            </div>
            <div className="absolute right-[10%] top-[9%] z-10 grid h-12 w-12 place-items-center rounded-full border border-[#c19c62]/35 bg-[#17110c]/50 text-[#c6a46d]">
              <Compass size={21} strokeWidth={1} />
            </div>
          </div>
          <div className="absolute -bottom-1 right-[12%] flex items-center gap-3 bg-[#17120e] px-4 py-3">
            <Flame size={13} className="text-[#c18d4e]" />
            <span className="font-['DM_Sans'] text-[9px] uppercase tracking-[.16em] text-[#93836b]">Yağmurun ardından, bir kapı aralanır</span>
          </div>
        </section>
      </div>
      <div className="pointer-events-none absolute bottom-0 left-0 h-px w-full bg-gradient-to-r from-transparent via-[#8e6d43]/50 to-transparent" />
    </main>
  );
}

function CreationScreen({ onBack, onBegin }: { onBack: () => void; onBegin: () => void }) {
  const [name, setName] = useState('Cedric');
  const [race, setRace] = useState('Elf');
  const [characterClass, setCharacterClass] = useState('Wizard');
  const [mode, setMode] = useState<'custom' | 'dice'>('custom');
  return (
    <main className="min-h-[100dvh] bg-[#100e0c] px-4 py-5 text-[#e6dcc8] md:px-8 md:py-8">
      <header className="mx-auto flex max-w-[1280px] items-center justify-between">
        <BrandMark />
        <button onClick={onBack} type="button" className="inline-flex items-center gap-2 font-['DM_Sans'] text-[10px] uppercase tracking-[.15em] text-[#aa9a80] hover:text-[#e6dcc8]"><ArrowLeft size={14} /> Geri dön</button>
      </header>
      <div className="mx-auto mt-8 max-w-[1120px]">
        <div className="mb-6">
          <TinyLabel>Yeni macera · Karakter kaydı</TinyLabel>
          <h1 className="mt-2 font-['Cinzel'] text-3xl tracking-[.03em] text-[#eddfc5] md:text-4xl">Sayfayı aç.</h1>
          <p className="mt-2 font-['Cormorant_Garamond'] text-xl text-[#a99a80]">Bir yolcu, bir isim ve ilk adım.</p>
        </div>
        <div className="grid overflow-hidden border border-[#6e5638]/70 bg-[#1a1511] lg:grid-cols-[.78fr_1.22fr]">
          <aside className="relative min-h-[250px] overflow-hidden border-b border-[#6e5638]/50 bg-[#1d1711] lg:border-b-0 lg:border-r">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_38%,rgba(155,119,67,.18),transparent_57%),linear-gradient(180deg,#241b13,#15110d)]" />
            <div className="absolute inset-4 border border-[#9b7946]/45" />
            <div className="absolute inset-[9%_14%_18%] rounded-[48%_48%_3%_3%] border border-dashed border-[#9b7946]/35 bg-[radial-gradient(ellipse_at_50%_36%,rgba(187,148,85,.08),transparent_68%)]" />
            <div className="absolute left-7 top-7 h-4 w-4 border-l border-t border-[#c0a16c]/65" />
            <div className="absolute right-7 top-7 h-4 w-4 border-r border-t border-[#c0a16c]/65" />
            <div className="absolute bottom-7 left-7 h-4 w-4 border-b border-l border-[#c0a16c]/65" />
            <div className="absolute bottom-7 right-7 h-4 w-4 border-b border-r border-[#c0a16c]/65" />
            <div className="absolute inset-x-0 bottom-7 text-center">
              <TinyLabel>Boş portre alanı</TinyLabel>
              <p className="mt-2 font-['Cormorant_Garamond'] text-[18px] text-[#9e8b6d]">Portre daha sonra eklenecek</p>
            </div>
            <div className="absolute left-5 top-5 flex h-10 w-10 items-center justify-center border border-[#c09a5e]/45 bg-[#16110c]/75 text-[#c7a469]">
              <span className="font-['Cinzel'] text-sm">I</span>
            </div>
          </aside>
          <section className="p-5 md:p-8">
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setMode('custom')} type="button" className={`border px-4 py-2.5 font-['DM_Sans'] text-[9px] uppercase tracking-[.16em] transition-colors ${mode === 'custom' ? 'border-[#b28d57] bg-[#30251a] text-[#e4d1ae]' : 'border-[#51412c] text-[#93846c] hover:border-[#876b42]'}`}>
                <span className="inline-flex items-center gap-2"><Feather size={13} /> Özel karakter</span>
              </button>
              <button onClick={() => setMode('dice')} type="button" className={`border px-4 py-2.5 font-['DM_Sans'] text-[9px] uppercase tracking-[.16em] transition-colors ${mode === 'dice' ? 'border-[#b28d57] bg-[#30251a] text-[#e4d1ae]' : 'border-[#51412c] text-[#93846c] hover:border-[#876b42]'}`}>
                <span className="inline-flex items-center gap-2"><span className="grid h-4 w-4 place-items-center border border-current font-['Cinzel'] text-[9px]">20</span> Zarlarla örnekle</span>
              </button>
            </div>
            {mode === 'dice' && <p className="mt-3 border-l border-[#9a7749] pl-3 font-['Cormorant_Garamond'] text-base text-[#ae9a79]">Zarlar burada yalnızca bir tasarım daveti. Değerler değişmeden kalır.</p>}
            <div className="mt-7 grid gap-x-5 gap-y-5 sm:grid-cols-2">
              <label className="block">
                <TinyLabel>İsim</TinyLabel>
                <input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 w-full border-b border-[#766044] bg-transparent px-0 py-2 font-['Cormorant_Garamond'] text-[22px] text-[#e8dcc5] outline-none placeholder:text-[#766b5b] focus:border-[#c6a06a]" />
              </label>
              <label className="block">
                <TinyLabel>Irk</TinyLabel>
                <div className="relative mt-2">
                  <select value={race} onChange={(event) => setRace(event.target.value)} className="w-full appearance-none border-b border-[#766044] bg-[#1a1511] py-2 font-['Cormorant_Garamond'] text-[22px] text-[#e8dcc5] outline-none focus:border-[#c6a06a]">
                    <option>Elf</option><option>İnsan</option><option>Cüce</option><option>Halfling</option>
                  </select><ChevronDown className="pointer-events-none absolute right-1 top-3 text-[#9d8969]" size={14} />
                </div>
              </label>
              <label className="block">
                <TinyLabel>Sınıf</TinyLabel>
                <div className="relative mt-2">
                  <select value={characterClass} onChange={(event) => setCharacterClass(event.target.value)} className="w-full appearance-none border-b border-[#766044] bg-[#1a1511] py-2 font-['Cormorant_Garamond'] text-[22px] text-[#e8dcc5] outline-none focus:border-[#c6a06a]">
                    <option>Wizard</option><option>Fighter</option><option>Rogue</option><option>Cleric</option>
                  </select><ChevronDown className="pointer-events-none absolute right-1 top-3 text-[#9d8969]" size={14} />
                </div>
              </label>
              <div className="block">
                <TinyLabel>Yol seviyesi</TinyLabel>
                <div className="mt-2 flex items-center justify-between border-b border-[#766044] py-2 font-['Cormorant_Garamond'] text-[22px] text-[#e8dcc5]"><span>Level 1</span><Shield size={15} className="text-[#aa8958]" /></div>
              </div>
            </div>
            <Rule className="my-6" />
            <div className="grid gap-6 sm:grid-cols-[1fr_1fr]">
              <div>
                <TinyLabel>Özellikler · örnek değerler</TinyLabel>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {[['STR', '11'], ['DEX', '15'], ['CON', '15'], ['INT', '10'], ['WIS', '14'], ['CHA', '14']].map(([stat, value]) => (
                    <div key={stat} className="flex items-center justify-between border border-[#493a29] bg-[#211a14] px-2.5 py-2">
                      <span className="font-['DM_Sans'] text-[9px] tracking-[.14em] text-[#897b65]">{stat}</span><span className="font-['Cinzel'] text-sm text-[#d5c4a3]">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <TinyLabel>Beceriler</TinyLabel>
                <div className="mt-3 flex flex-wrap gap-2">
                  {['Arcana', 'Perception', 'History'].map((skill) => <span key={skill} className="border border-[#604a30] px-2.5 py-1.5 font-['Cormorant_Garamond'] text-[15px] text-[#c5b18e]">{skill}</span>)}
                </div>
              </div>
            </div>
            <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-[#604b32]/70 pt-5">
              <span className="font-['DM_Sans'] text-[10px] text-[#897b67]">Değerler örnek amaçlıdır · oyun durumu değildir.</span>
              <button onClick={onBegin} type="button" className="group inline-flex items-center gap-3 border border-[#b18b55] bg-[#6c3028] px-5 py-3 font-['DM_Sans'] text-[9px] font-semibold uppercase tracking-[.17em] text-[#f1e5cf] hover:bg-[#813d32]">
                Macerayı aç <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
              </button>
            </div>
          </section>
        </div>
        <div className="mt-4 flex items-center gap-2 text-[9px] font-['DM_Sans'] uppercase tracking-[.14em] text-[#6f6555]"><ScrollText size={12} /> Karakter sayfası · taslak görünümü</div>
      </div>
    </main>
  );
}

function CharacterPanel() {
  const stats = [['STR', '11'], ['DEX', '15'], ['CON', '15'], ['INT', '10'], ['WIS', '14'], ['CHA', '14']];
  return (
    <aside className="border-r border-[#4d3b28] bg-[#17130f] px-4 py-5 xl:px-5">
      <div className="flex items-center justify-between">
        <TinyLabel>Yolcu kaydı</TinyLabel>
        <span className="border border-[#876d44]/55 px-2 py-1 font-['Cinzel'] text-[9px] tracking-[.12em] text-[#c6a36b]">LVL 01</span>
      </div>
      <div className="relative mt-4 flex aspect-[.91] max-h-[245px] items-center justify-center overflow-hidden border border-[#866b43]/60 bg-[radial-gradient(ellipse_at_center,rgba(140,105,60,.17),transparent_60%),#201912]">
        <div className="absolute inset-2 border border-[#8f744b]/25" />
        <div className="absolute inset-4 border border-dashed border-[#9a7a4b]/30" />
        <div className="absolute inset-[12%_15%_16%] rounded-[48%_48%_3%_3%] border border-[#9a7a4b]/35" />
        <div className="relative mt-20 font-['DM_Sans'] text-[8px] uppercase tracking-[.2em] text-[#83745c]">Boş portre alanı</div>
        <span className="absolute bottom-2 right-2 text-[#92764a]"><Compass size={15} strokeWidth={1} /></span>
      </div>
      <div className="mt-5 text-center">
        <h2 className="font-['Cinzel'] text-[22px] tracking-[.13em] text-[#e6d7bb]">CEDRIC</h2>
        <div className="mt-1 font-['Cormorant_Garamond'] text-[17px] text-[#aa9a7f]">Elf Wizard <span className="mx-1 text-[#785f3b]">·</span> Level 1</div>
      </div>
      <div className="mt-5 border border-[#5e482e]/75 bg-[#1f1913] p-3">
        <div className="flex items-end justify-between">
          <div><TinyLabel>Hit points</TinyLabel><div className="mt-1 font-['Cinzel'] text-[23px] leading-none text-[#dfc9a1]">8 <span className="text-[13px] text-[#8b7a61]">/ 10</span></div></div>
          <div className="mb-1 flex items-center gap-1.5 text-[10px] text-[#b69b71]"><Flame size={12} /> Sağlam</div>
        </div>
        <div className="mt-3 h-[5px] bg-[#3b3022]"><div className="h-full w-[80%] bg-gradient-to-r from-[#795039] to-[#ba8b5a]" /></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="flex items-center justify-between border border-[#473725] px-2.5 py-2"><TinyLabel>AC</TinyLabel><span className="font-['Cinzel'] text-sm text-[#d3c2a2]">12</span></div>
        <div className="flex items-center justify-between border border-[#473725] px-2.5 py-2"><TinyLabel>PB</TinyLabel><span className="font-['Cinzel'] text-sm text-[#d3c2a2]">+2</span></div>
      </div>
      <div className="mt-5">
        <TinyLabel>Özellikler</TinyLabel>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {stats.map(([stat, value]) => <div key={stat} className="border border-[#473725]/90 bg-[#1e1913] py-2 text-center"><div className="font-['DM_Sans'] text-[8px] tracking-[.12em] text-[#8d806a]">{stat}</div><div className="mt-0.5 font-['Cinzel'] text-sm text-[#d0bea0]">{value}</div></div>)}
        </div>
      </div>
      <div className="mt-5">
        <TinyLabel>Üzerindekiler</TinyLabel>
        <div className="mt-2 space-y-2 font-['Cormorant_Garamond'] text-[16px] text-[#c5b697]">
          <div className="flex items-center gap-2"><Swords size={13} className="text-[#a98958]" /> Kılıç</div>
          <div className="flex items-center gap-2"><ScrollText size={13} className="text-[#a98958]" /> Macera Çantası</div>
        </div>
      </div>
      <div className="mt-4 border-t border-[#4b3926] pt-3">
        <TinyLabel>Durum</TinyLabel>
        <div className="mt-2 flex items-center gap-2 font-['Cormorant_Garamond'] text-[15px] text-[#97876e]"><span className="h-1.5 w-1.5 rounded-full bg-[#82916a]" /> Etki yok</div>
      </div>
    </aside>
  );
}

function StoryFeed() {
  return (
    <div className="mx-auto w-full max-w-[720px] px-5 pb-8 pt-7 sm:px-8 lg:px-10">
      <div className="mb-7 flex items-center gap-3">
        <div className="grid h-8 w-8 place-items-center border border-[#80633c]/65 bg-[#241c14] text-[#b8965f]"><Feather size={15} strokeWidth={1.25} /></div>
        <div><TinyLabel>Dungeon Master</TinyLabel><div className="mt-1 font-['DM_Sans'] text-[9px] uppercase tracking-[.15em] text-[#716754]">1. bölüm · Kül ve Kupa</div></div>
        <div className="ml-auto font-['DM_Sans'] text-[9px] uppercase tracking-[.12em] text-[#716754]">Akşam vakti</div>
      </div>
      <article className="relative pl-5 sm:pl-7">
        <span className="absolute bottom-0 left-0 top-1 w-px bg-gradient-to-b from-[#a27b48]/60 via-[#695032]/45 to-transparent" />
        <span className="absolute left-[-3px] top-1 h-[7px] w-[7px] rotate-45 border border-[#c09a61] bg-[#241c14]" />
        <p className="font-['Cormorant_Garamond'] text-[21px] leading-[1.53] text-[#ded2ba] sm:text-[23px]">
          Kapıyı araladığında tavernanın sıcaklığı yüzüne vurur. Yağmurun sesi arkanda yavaşça kaybolurken içerideki şömine, koyu renk ahşap masaların üzerine titrek bir ışık yayıyor.
        </p>
        <p className="mt-4 font-['Cormorant_Garamond'] text-[21px] leading-[1.53] text-[#ded2ba] sm:text-[23px]">
          Tezgâhın arkasında iri yapılı bir adam kupaları kuruluyor. Pelerininden süzülen son damlalar kapı eşiğinde küçük bir gölcük bırakıyor.
        </p>
        <div className="mt-5 inline-flex items-center gap-2 border-l border-[#866942] pl-3 font-['DM_Sans'] text-[9px] uppercase tracking-[.17em] text-[#927a58]"><Map size={12} /> Kül ve Kupa · Taverna</div>
      </article>
      <div className="my-7 flex items-center gap-3">
        <Rule className="flex-1" /><span className="font-['Cinzel'] text-[9px] tracking-[.25em] text-[#7d6748]">❦</span><Rule className="flex-1 !bg-gradient-to-l" />
      </div>
      <div className="mb-2 flex items-center gap-2">
        <div className="grid h-6 w-6 place-items-center border border-[#55432e] text-[#9f8b6a]"><MessageCircle size={12} /></div>
        <TinyLabel>Sen</TinyLabel>
        <span className="font-['DM_Sans'] text-[9px] text-[#756a58]">az önce</span>
      </div>
      <p className="ml-8 border-l border-[#4b3b2b] pl-4 font-['Cormorant_Garamond'] text-[18px] italic leading-relaxed text-[#b7a88c]">Barmene doğru gidip selam veriyorum.</p>
      <div className="my-7 flex items-center gap-3"><Rule className="flex-1" /><span className="font-['Cinzel'] text-[9px] tracking-[.25em] text-[#7d6748]">✦</span><Rule className="flex-1 !bg-gradient-to-l" /></div>
      <article className="relative pl-5 sm:pl-7">
        <span className="absolute bottom-0 left-0 top-1 w-px bg-gradient-to-b from-[#a27b48]/60 via-[#695032]/45 to-transparent" />
        <span className="absolute left-[-3px] top-1 h-[7px] w-[7px] rotate-45 border border-[#c09a61] bg-[#241c14]" />
        <p className="font-['Cormorant_Garamond'] text-[21px] leading-[1.53] text-[#ded2ba] sm:text-[23px]">
          Adam elindeki kupayı tezgâha bırakıp sana bakıyor. Yüzündeki çizgiler şömine ışığında daha derin görünüyor.
        </p>
        <p className="mt-4 border-l border-[#775d3a] pl-4 font-['Cormorant_Garamond'] text-[21px] italic leading-[1.45] text-[#d1bc96] sm:text-[23px]">
          “Yolcuya benziyorsun,” diyor. “İçki mi arıyorsun, yoksa bilgi mi?”
        </p>
        <div className="mt-5 inline-flex items-center gap-2 font-['DM_Sans'] text-[9px] uppercase tracking-[.17em] text-[#887351]"><Users size={12} /> Kasım · Barmen</div>
      </article>
    </div>
  );
}

function LoadingNarration() {
  return (
    <div className="mx-auto mb-3 flex max-w-[720px] items-center gap-3 border-l border-[#a98752] bg-[#211a14] px-3 py-2.5" role="status">
      <Feather size={15} className="shrink-0 animate-pulse text-[#c4a36d]" strokeWidth={1.3} />
      <div><TinyLabel>Yükleme örneği</TinyLabel><div className="mt-1 font-['Cormorant_Garamond'] text-[17px] text-[#c7b99f]">Dungeon Master düşünüyor...</div></div>
      <span className="ml-auto font-['DM_Sans'] text-[8px] uppercase tracking-[.12em] text-[#786d5b]">Görsel durum</span>
    </div>
  );
}

function WorldContext({ tab }: { tab: ContextTab }) {
  if (tab === 'npcs') {
    return <div className="p-5">
      <TinyLabel>Kişiler ve karşılaşmalar</TinyLabel>
      <h3 className="mt-3 font-['Cinzel'] text-[17px] tracking-[.04em] text-[#decdaa]">Bu akşam burada</h3>
      <div className="mt-5 space-y-4">
        <div className="flex items-start gap-3 border-b border-[#4b3926] pb-4">
          <div className="grid h-9 w-9 shrink-0 place-items-center border border-[#604a30] bg-[#211a14] font-['Cinzel'] text-[11px] text-[#c09e68]">K</div>
          <div><div className="font-['Cormorant_Garamond'] text-[18px] text-[#d1c2a6]">Kasım</div><div className="mt-0.5 font-['DM_Sans'] text-[9px] text-[#83745e]">Barmen · tezgâhın ardında</div></div>
        </div>
        <div className="flex items-start gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center border border-[#604a30] bg-[#211a14] font-['Cinzel'] text-[11px] text-[#c09e68]">Y</div>
          <div><div className="font-['Cormorant_Garamond'] text-[18px] text-[#d1c2a6]">Yaşlı Gezgin</div><div className="mt-0.5 font-['DM_Sans'] text-[9px] text-[#83745e]">Büyük Şömine yakınında</div></div>
        </div>
      </div>
      <div className="mt-6 border-t border-[#4b3926] pt-4"><TinyLabel>Yakında · 02 kişi</TinyLabel><p className="mt-2 font-['Cormorant_Garamond'] text-[16px] leading-5 text-[#8c7d65]">Bu liste yalnızca örnek bağlamı gösterir.</p></div>
    </div>;
  }
  if (tab === 'journal') {
    return <div className="p-5">
      <TinyLabel>Kampanya günlüğü</TinyLabel>
      <h3 className="mt-3 font-['Cinzel'] text-[17px] tracking-[.04em] text-[#decdaa]">İlk izler</h3>
      <div className="mt-5 border-l border-[#80633c] pl-4">
        <TinyLabel>Bu akşam · Taverna</TinyLabel>
        <p className="mt-2 font-['Cormorant_Garamond'] text-[18px] leading-6 text-[#b9aa8d]">Yağmurdan sığınmak için Kül ve Kupa’ya girdin. Kasım, seni bilgi arayan bir yolcuya benzetti.</p>
      </div>
      <div className="mt-6 border-t border-[#4b3926] pt-4">
        <TinyLabel>Not defteri</TinyLabel><p className="mt-2 font-['Cormorant_Garamond'] text-base text-[#837762]">Henüz kişisel not yok.</p>
      </div>
    </div>;
  }
  if (tab === 'combat') {
    return <div className="p-5">
      <div className="flex items-center gap-2 text-[#c4a36d]"><Swords size={14} /><TinyLabel>Çatışma kaydı</TinyLabel></div>
      <h3 className="mt-3 font-['Cinzel'] text-[17px] tracking-[.04em] text-[#decdaa]">Masa görünümü</h3>
      <p className="mt-2 font-['Cormorant_Garamond'] text-[16px] leading-5 text-[#94866e]">Bu kampanya anında çatışma etkin değil.</p>
      <div className="mt-5 border border-[#5a432d] bg-[#211a14] p-4">
        <div className="flex items-center justify-between"><TinyLabel>Örnek kayıt · 2. tur</TinyLabel><span className="border border-[#715033] px-2 py-1 font-['DM_Sans'] text-[8px] uppercase tracking-[.12em] text-[#a78b60]">İllüstratif</span></div>
        <div className="mt-4 flex items-center justify-between">
          <div><div className="font-['Cinzel'] text-[11px] tracking-[.1em] text-[#d8c5a0]">CEDRIC</div><div className="mt-1 font-['DM_Sans'] text-[9px] text-[#8e806a]">HP 7 / 8 · AC 12</div></div>
          <span className="font-['Cormorant_Garamond'] text-[14px] italic text-[#83745f]">versus</span>
          <div className="text-right"><div className="font-['Cinzel'] text-[11px] tracking-[.1em] text-[#d8c5a0]">BANDIT</div><div className="mt-1 font-['DM_Sans'] text-[9px] text-[#8e806a]">HP 6 / 10 · AC 11</div></div>
        </div>
        <Rule className="my-4" />
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 rotate-45 place-items-center border border-[#a5824c] bg-[#2b2117]"><span className="-rotate-45 font-['Cinzel'] text-[15px] text-[#d2b174]">d20</span></div>
          <div><TinyLabel>Attack roll</TinyLabel><div className="mt-1 font-['Cinzel'] text-[14px] text-[#d9c6a4]">17 + 2 = 19 <span className="ml-1 text-[#a37d4e]">· HIT</span></div></div>
          <div className="ml-auto text-right"><TinyLabel>Damage</TinyLabel><div className="mt-1 font-['Cinzel'] text-sm text-[#d9c6a4]">6</div></div>
        </div>
      </div>
      <p className="mt-3 font-['DM_Sans'] text-[9px] leading-4 text-[#746957]">Sabit örnek veridir; zar atımı veya oyun mantığı çalıştırılmaz.</p>
    </div>;
  }
  return (
    <div className="p-5">
      <div className="relative overflow-hidden border border-[#59442d]/80 bg-[#201910]">
        <div className="absolute inset-0 opacity-[.2]" style={{ backgroundImage: 'radial-gradient(ellipse at 50% 50%, transparent 0 22%, #9a7c4e 23%, transparent 24%), repeating-linear-gradient(145deg, transparent 0 22px, rgba(159,129,78,.28) 23px, transparent 24px)' }} />
        <div className="relative p-4">
          <TinyLabel>Şu an bulunduğun yer</TinyLabel>
          <div className="mt-2 flex items-end justify-between">
            <h3 className="font-['Cinzel'] text-[21px] tracking-[.05em] text-[#e0cfad]">Taverna</h3>
            <Compass size={19} strokeWidth={1} className="mb-1 text-[#a78856]" />
          </div>
          <div className="mt-3 flex items-center gap-2 font-['DM_Sans'] text-[9px] uppercase tracking-[.12em] text-[#897b65]"><Map size={11} /> Kül ve Kupa</div>
        </div>
      </div>
      <section className="mt-6">
        <div className="flex items-center justify-between"><TinyLabel>Yakındaki kişiler</TinyLabel><span className="font-['DM_Sans'] text-[9px] text-[#716652]">02</span></div>
        <div className="mt-3 space-y-3">
          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center border border-[#604a30] bg-[#211a14] font-['Cinzel'] text-[11px] text-[#c09e68]">K</div>
            <div><div className="font-['Cormorant_Garamond'] text-[17px] text-[#d1c2a6]">Kasım</div><div className="font-['DM_Sans'] text-[9px] text-[#83745e]">Barmen · tezgâhın ardında</div></div>
          </div>
          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center border border-[#604a30] bg-[#211a14] font-['Cinzel'] text-[11px] text-[#c09e68]">Y</div>
            <div><div className="font-['Cormorant_Garamond'] text-[17px] text-[#d1c2a6]">Yaşlı Gezgin</div><div className="font-['DM_Sans'] text-[9px] text-[#83745e]">Büyük Şömine yakınında</div></div>
          </div>
        </div>
      </section>
      <section className="mt-6 border-t border-[#4b3926] pt-4">
        <TinyLabel>Çevre</TinyLabel>
        <div className="mt-3 space-y-2.5">
          {[
            [Flame, 'Büyük Şömine', 'Çıtırdayan odunlar'],
            [Compass, 'Kemerli Pencere', 'Yağmurla kaplı cam'],
            [DoorOpen, 'Arka Kapı', 'Dar servis geçidi'],
          ].map(([Icon, title, detail]) => {
            const ItemIcon = Icon as typeof Flame;
            return <div className="flex items-start gap-2.5" key={title as string}><ItemIcon size={13} className="mt-1 text-[#a58755]" /><div><div className="font-['Cormorant_Garamond'] text-[16px] leading-4 text-[#c1b292]">{title as string}</div><div className="mt-1 font-['DM_Sans'] text-[9px] text-[#756b59]">{detail as string}</div></div></div>;
          })}
        </div>
      </section>
      <div className="mt-6 border-t border-[#4b3926] pt-4">
        <TinyLabel>Hava</TinyLabel>
        <div className="mt-2 font-['Cormorant_Garamond'] text-[16px] text-[#9d8f75]">Dışarıda ince, soğuk yağmur.</div>
      </div>
    </div>
  );
}

function AdventureScreen({ onHome, onCreation }: { onHome: () => void; onCreation: () => void }) {
  const [tab, setTab] = useState<ContextTab>('world');
  const [drawer, setDrawer] = useState<'character' | 'context' | null>(null);
  const [draft, setDraft] = useState('');
  const [showNote, setShowNote] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const tabs: { id: ContextTab; label: string; icon: typeof Map }[] = [
    { id: 'world', label: 'Dünya', icon: Compass },
    { id: 'npcs', label: 'NPC’ler', icon: Users },
    { id: 'journal', label: 'Günlük', icon: BookOpen },
    { id: 'combat', label: 'Çatışma', icon: Swords },
  ];
  return (
    <main className="flex h-[100dvh] min-h-[600px] flex-col bg-[#100e0c] text-[#e8ddc8]">
      <header className="sticky top-0 z-30 flex h-[62px] items-center justify-between border-b border-[#4b3926] bg-[#15110e]/95 px-4 backdrop-blur-sm md:px-6">
        <div className="flex items-center gap-3">
          <BrandMark compact />
          <div className="ml-1 hidden sm:block"><div className="font-['Cinzel'] text-[12px] tracking-[.11em] text-[#d8c7a5]">Kül ve Kupa</div><div className="mt-0.5 font-['DM_Sans'] text-[8px] uppercase tracking-[.16em] text-[#756b5a]">Kampanya · İlk bölüm</div></div>
        </div>
        <div className="hidden items-center gap-2 md:flex"><span className="h-1.5 w-1.5 rounded-full bg-[#8b926d]" /><span className="font-['DM_Sans'] text-[9px] uppercase tracking-[.14em] text-[#8e826d]">Örnek kampanya görünümü</span></div>
        <div className="flex items-center gap-2">
          <button onClick={() => setDrawer(drawer === 'character' ? null : 'character')} type="button" className="inline-flex items-center gap-2 border border-[#4c3b28] px-3 py-2 font-['DM_Sans'] text-[9px] uppercase tracking-[.13em] text-[#b5a486] hover:border-[#9b7949] lg:hidden"><Shield size={12} /> Cedric</button>
          <button onClick={() => setDrawer(drawer === 'context' ? null : 'context')} type="button" aria-label="Dünya bağlamını aç" className="inline-flex h-8 w-8 items-center justify-center border border-[#4c3b28] text-[#b5a486] hover:border-[#9b7949] xl:hidden"><Menu size={15} /></button>
          <button onClick={onHome} type="button" className="hidden border-l border-[#4c3b28] pl-3 font-['DM_Sans'] text-[9px] uppercase tracking-[.14em] text-[#93846c] hover:text-[#d9c8a7] sm:block">Ana sayfa</button>
        </div>
      </header>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[230px_minmax(420px,1fr)] xl:grid-cols-[240px_minmax(460px,1fr)_286px]">
        <div className="hidden min-h-0 overflow-y-auto lg:block"><CharacterPanel /></div>
        <section className="flex min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-[#3f3223] px-5 py-3 sm:px-8">
            <div className="flex items-center gap-2 font-['DM_Sans'] text-[9px] uppercase tracking-[.14em] text-[#82745d]"><Map size={12} className="text-[#a48655]" /> Taverna <span className="text-[#64543b]">/</span> Akşam</div>
            <button onClick={onCreation} type="button" className="font-['DM_Sans'] text-[9px] uppercase tracking-[.12em] text-[#81735d] hover:text-[#d1bf9c]">Karakter sayfası</button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <StoryFeed />
          </div>
          <div className="relative z-20 shrink-0 border-t border-[#5a452d] bg-[#17130f]/95 px-4 pb-4 pt-3 sm:px-8">
            <div className="mx-auto max-w-[720px]">
              <div className="mb-2 flex items-center justify-between">
                <TinyLabel>Ne yapmak istiyorsun?</TinyLabel>
                <button type="button" aria-pressed={showThinking} onClick={() => setShowThinking(!showThinking)} className="inline-flex items-center gap-1.5 font-['DM_Sans'] text-[8px] uppercase tracking-[.12em] text-[#82745d] hover:text-[#c8ad7d]"><Feather size={11} /> {showThinking ? 'Yükleme gizle' : 'Yükleme örneği'}</button>
              </div>
              {showThinking && <LoadingNarration />}
              <div className="relative border border-[#665033] bg-[#211a14] focus-within:border-[#a17d4b]">
                <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={2} placeholder="Örn. şöminenin yanındaki adama doğru gidiyorum…" className="min-h-[68px] w-full resize-none bg-transparent py-3 pl-4 pr-16 font-['Cormorant_Garamond'] text-[18px] leading-6 text-[#ded0b6] outline-none placeholder:text-[#756a57]" />
                <button type="button" aria-label="Gönderim prototipte devre dışı" onClick={() => setShowNote(!showNote)} className="absolute bottom-2 right-2 flex h-9 w-10 items-center justify-center border border-[#705534] bg-[#38271b] text-[#c6a46a] hover:bg-[#4a3220]"><ArrowRight size={15} /></button>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 font-['DM_Sans'] text-[8px] text-[#736954]"><span className="grid h-4 w-4 place-items-center border border-[#51402a] font-['Cinzel'] text-[7px] text-[#a58a5c]">d20</span> Sözlerin hikâyeyi yönlendirir.</div>
                <span className="font-['DM_Sans'] text-[8px] uppercase tracking-[.1em] text-[#746957]">Yalnızca tasarım · gönderim kapalı</span>
              </div>
              {showNote && <div className="mt-2 border-l border-[#a38250] pl-3 font-['DM_Sans'] text-[10px] text-[#b49a71]">Bu prototipte eylemler gönderilmez; anlatı örneği sabit kalır.</div>}
            </div>
          </div>
        </section>
        <aside className="hidden min-h-0 overflow-y-auto border-l border-[#4d3b28] bg-[#17130f] xl:block">
          <div className="flex h-[49px] items-stretch border-b border-[#4b3926]">
            {tabs.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} type="button" className={`relative flex flex-1 items-center justify-center gap-1.5 font-['DM_Sans'] text-[8px] uppercase tracking-[.12em] ${tab === id ? 'text-[#d2b47e]' : 'text-[#81745e] hover:text-[#c2af8c]'}`}><Icon size={12} />{label}{tab === id && <span className="absolute inset-x-2 bottom-0 h-px bg-[#ad8952]" />}</button>)}
          </div>
          <WorldContext tab={tab} />
        </aside>
      </div>
      {drawer && <div className="fixed inset-0 z-50 lg:hidden">
        <button aria-label="Paneli kapat" onClick={() => setDrawer(null)} className="absolute inset-0 bg-black/65" />
        <div className={`absolute inset-y-0 ${drawer === 'character' ? 'left-0' : 'right-0'} w-[min(88vw,340px)] overflow-y-auto border-[#6c5232] bg-[#17130f] shadow-2xl ${drawer === 'character' ? 'border-r' : 'border-l'}`}>
          <div className="flex items-center justify-between border-b border-[#4b3926] px-4 py-3"><TinyLabel>{drawer === 'character' ? 'Yolcu kaydı' : 'Dünya bağlamı'}</TinyLabel><button onClick={() => setDrawer(null)} aria-label="Kapat" className="text-[#b8a37e]"><X size={17} /></button></div>
          {drawer === 'character' ? <CharacterPanel /> : <><div className="flex border-b border-[#4b3926]">{tabs.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} className={`flex flex-1 items-center justify-center gap-1 py-3 font-['DM_Sans'] text-[8px] uppercase tracking-[.1em] ${tab === id ? 'text-[#d2b47e]' : 'text-[#81745e]'}`}><Icon size={12} />{label}</button>)}</div><WorldContext tab={tab} /></>}
        </div>
      </div>}
    </main>
  );
}

export function Experience() {
  const [screen, setScreen] = useState<Screen>(() => {
    const requestedScreen = new URLSearchParams(window.location.search).get('screen');
    return requestedScreen === 'creation' || requestedScreen === 'adventure' ? requestedScreen : 'opening';
  });
  if (screen === 'creation') return <CreationScreen onBack={() => setScreen('opening')} onBegin={() => setScreen('adventure')} />;
  if (screen === 'adventure') return <AdventureScreen onHome={() => setScreen('opening')} onCreation={() => setScreen('creation')} />;
  return <OpeningScreen onCreate={() => setScreen('creation')} onContinue={() => setScreen('adventure')} />;
}