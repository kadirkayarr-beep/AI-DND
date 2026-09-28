import './Experience.css';
import { ArrowLeft, ArrowRight, ChevronDown, Feather, ScrollText, Shield } from 'lucide-react';
import { BrandMark, Label, Rule } from './_shared';

const stats = [['STR', '11'], ['DEX', '15'], ['CON', '15'], ['INT', '10'], ['WIS', '14'], ['CHA', '14']];

function SampleField({ label, value, select = false }: { label: string; value: string; select?: boolean }) {
  return (
    <div className="relative border-b border-[#9b8158]/55 pb-2">
      <Label className="!text-[#7c6d52]">{label}</Label>
      <div className="dnd-literary mt-1 text-[22px] text-[#493d2b]">{value}</div>
      {select && <ChevronDown size={14} className="absolute bottom-3 right-1 text-[#89754f]" />}
    </div>
  );
}

export function CharacterCreation() {
  return (
    <main className="dnd-frame dnd-creation min-h-[100dvh] px-4 py-5 sm:px-7 md:px-10 md:py-7">
      <header className="mx-auto flex max-w-[1320px] items-center justify-between">
        <BrandMark />
        <div className="hidden items-center gap-2 md:flex"><span className="h-px w-8 bg-[#9a7b4b]/60" /><Label className="!text-[#76694f]">Gün ışığında karakter kaydı</Label></div>
        <button type="button" disabled className="inline-flex items-center gap-2 font-['DM_Sans'] text-[9px] uppercase tracking-[.14em] text-[#76694f] opacity-70"><ArrowLeft size={13} /> Geri dön</button>
      </header>
      <div className="mx-auto mt-8 max-w-[1170px]">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Label className="!text-[#826d48]">Yeni macera · Karakter kaydı</Label>
            <h1 className="dnd-display mt-2 text-[clamp(1.8rem,4vw,2.7rem)] tracking-[.02em] text-[#43382b]">Sayfayı aç.</h1>
            <p className="dnd-literary mt-1 text-[21px] text-[#74674f]">Bir yolcu, bir isim ve ilk adım.</p>
          </div>
          <div className="flex items-center gap-2 border-l border-[#a58a5b]/40 pl-4">
            <ScrollText size={15} className="text-[#92784d]" />
            <span className="dnd-sans text-[8px] uppercase tracking-[.14em] text-[#76694f]">Taslak görünümü</span>
          </div>
        </div>
        <div className="dnd-card-shadow grid overflow-hidden border border-[#947b55]/50 bg-[#eee4cc]/74 lg:grid-cols-[.72fr_1.28fr]">
          <aside className="relative min-h-[310px] overflow-hidden border-b border-[#947b55]/40 bg-[#d9caa8]/75 lg:border-b-0 lg:border-r">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_25%,rgba(255,252,231,.78),transparent_62%),linear-gradient(155deg,rgba(166,139,91,.12),rgba(97,79,52,.09))]" />
            <div className="absolute inset-4 border border-[#967d54]/35" />
            <div className="absolute inset-[8%_13%_20%] rounded-[48%_48%_3%_3%] border border-dashed border-[#92794f]/40 bg-[#e9dec2]/20" />
            <div className="absolute left-7 top-7 h-4 w-4 border-l border-t border-[#856e49]/70" />
            <div className="absolute right-7 top-7 h-4 w-4 border-r border-t border-[#856e49]/70" />
            <div className="absolute bottom-7 left-7 h-4 w-4 border-b border-l border-[#856e49]/70" />
            <div className="absolute bottom-7 right-7 h-4 w-4 border-b border-r border-[#856e49]/70" />
            <div className="absolute left-6 top-6 grid h-9 w-9 place-items-center border border-[#9c8051]/40 bg-[#eee4cd]/60 dnd-display text-[12px] text-[#866e46]">I</div>
            <div className="absolute inset-x-0 bottom-8 text-center">
              <Label className="!text-[#756649]">Portre alanı · boş</Label>
              <p className="dnd-literary mt-2 text-[18px] text-[#897a5e]">Bu sayfada portre bulunmaz</p>
            </div>
          </aside>
          <section className="p-5 sm:p-7 lg:p-9">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-2 border border-[#98794a]/60 bg-[#d8c7a2]/40 px-3.5 py-2.5 font-['DM_Sans'] text-[8px] uppercase tracking-[.14em] text-[#604e35]"><Feather size={13} /> Özel karakter</span>
                <span className="inline-flex items-center gap-2 border border-[#a79472]/35 px-3.5 py-2.5 font-['DM_Sans'] text-[8px] uppercase tracking-[.14em] text-[#83765d]"><span className="grid h-4 w-4 place-items-center border border-current dnd-display text-[8px]">20</span> Zarlarla örnekle</span>
              </div>
              <span className="dnd-sans text-[8px] uppercase tracking-[.13em] text-[#88795f]">Kontroller görsel · düzenleme kapalı</span>
            </div>
            <div className="mt-7 grid gap-x-7 gap-y-6 sm:grid-cols-2">
              <SampleField label="İsim · örnek" value="Cedric" />
              <SampleField label="Irk · örnek" value="Elf" select />
              <SampleField label="Sınıf · örnek" value="Wizard" select />
              <div className="border-b border-[#9b8158]/55 pb-2">
                <Label className="!text-[#7c6d52]">Yol seviyesi · örnek</Label>
                <div className="dnd-literary mt-1 flex items-center justify-between text-[22px] text-[#493d2b]">Level 1 <Shield size={15} className="mr-1 text-[#8d744c]" /></div>
              </div>
            </div>
            <Rule className="my-6 !bg-gradient-to-r !from-[#9f8357]/55 !via-[#ab9670]/35 !to-transparent" />
            <div className="grid gap-7 sm:grid-cols-[1fr_.8fr]">
              <div>
                <div className="flex items-center justify-between"><Label className="!text-[#786a50]">Özellikler</Label><span className="dnd-sans text-[8px] uppercase tracking-[.11em] text-[#927d58]">örnek değerler</span></div>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  {stats.map(([stat, value]) => <div key={stat} className="flex items-center justify-between border border-[#a58b5f]/35 bg-[#e6dbc0]/55 px-2.5 py-2"><span className="dnd-sans text-[8px] tracking-[.12em] text-[#83745a]">{stat}</span><span className="dnd-display text-[13px] text-[#544631]">{value}</span></div>)}
                </div>
              </div>
              <div>
                <Label className="!text-[#786a50]">Beceriler · örnek</Label>
                <div className="mt-3 flex flex-wrap gap-2">
                  {['Arcana', 'Perception', 'History'].map((skill) => <span key={skill} className="border border-[#9a8054]/45 bg-[#e8dcc0]/50 px-2.5 py-1.5 dnd-literary text-[15px] text-[#67563a]">{skill}</span>)}
                </div>
                <div className="mt-5 border-l border-[#a58a58] pl-3">
                  <Label className="!text-[#88734d]">Kayıt notu</Label>
                  <p className="dnd-literary mt-1 text-[15px] leading-5 text-[#7e7258]">Bu sayfa karakter kaydının görünümünü gösterir; değerler değiştirilemez.</p>
                </div>
              </div>
            </div>
            <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-[#9e8356]/40 pt-5">
              <span className="dnd-sans max-w-[350px] text-[9px] leading-4 text-[#786d57]">Örnek karakter bilgileri · oyun durumu ya da kaydedilebilir seçim değildir.</span>
              <button type="button" disabled className="dnd-entry inline-flex items-center gap-3 px-5 py-3 font-['DM_Sans'] text-[8px] font-semibold uppercase tracking-[.16em]">Macerayı aç <ArrowRight size={13} /></button>
            </div>
          </section>
        </div>
        <div className="dnd-sans mt-4 flex items-center gap-2 text-[8px] uppercase tracking-[.13em] text-[#776b52]"><ScrollText size={12} /> Karakter sayfası · görsel prototip</div>
      </div>
    </main>
  );
}