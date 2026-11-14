import { useId, type ReactNode } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Minus, Plus, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button, type ButtonProps } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogOverlay, DialogPortal, DialogTitle } from '@/components/ui/dialog';
import { Empty } from '@/components/ui/empty';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Spinner } from '@/components/ui/spinner';
import { Switch } from '@/components/ui/switch';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { SecimDamgasi } from '@/components/kitap/cizimler/secim-damgasi';
import './kitap.css';

/** ana: filled ink; ikinci: ruled outline; kare: 44px square icon button; masa: on the desk beside the book. */
export function KitapDugme({ tur = 'ikinci', className = '', ...props }: ButtonProps & { tur?: 'ana' | 'ikinci' | 'kare' | 'masa' }) {
  return <Button variant="ghost" className={`kitap-dugme kitap-dugme-${tur} ${className}`.trim()} {...props} />;
}

export interface Secenek<T extends string = string> { deger: T; etiket: ReactNode; ad?: string }

/** Row of choices where exactly one is on (appearance, layout, hand, size, writing mode); toggle-group.tsx. */
export function SeciciGrup<T extends string>({ etiket, deger, degisince, secenekler, className = '', tur = 'kutu', disabled }: {
  etiket: string; deger: T; degisince: (deger: T) => void; secenekler: ReadonlyArray<Secenek<T>>; className?: string; tur?: 'kutu' | 'cizgi'; disabled?: boolean;
}) {
  return (
    <ToggleGroup type="single" aria-label={etiket} value={deger} disabled={disabled} onValueChange={(v) => { if (v) degisince(v as T); }}
      className={`kitap-secici kitap-secici-${tur} ${className}`.trim()}>
      {secenekler.map((s) => (
        <ToggleGroupItem key={s.deger} value={s.deger} aria-label={s.ad} className="kitap-secenek">{s.etiket}</ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

export function AcilirListe({ etiket, deger, degisince, secenekler, disabled }: {
  etiket: string; deger?: string; degisince: (deger: string) => void; secenekler: ReadonlyArray<{ deger: string; etiket: string }>; disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="kitap-alan">
      <label className="kitap-etiket" htmlFor={id}>{etiket}</label>
      <Select value={deger} onValueChange={degisince} disabled={disabled}>
        <SelectTrigger id={id} className="kitap-liste">
          <SelectValue placeholder="Seç" />
        </SelectTrigger>
        <SelectContent className="kitap-liste-icerik">
          {secenekler.map((s) => <SelectItem key={s.deger} value={s.deger} className="kitap-liste-oge">{s.etiket}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

export function OnayKutusu({ etiket, isaretli, degisince, disabled }: { etiket: string; isaretli: boolean; degisince: (v: boolean) => void; disabled?: boolean }) {
  const id = useId();
  return (
    <label className="kitap-onay" htmlFor={id}>
      <Checkbox id={id} checked={isaretli} onCheckedChange={(v) => degisince(v === true)} disabled={disabled} className="kitap-onay-kutu" />
      <span>{etiket}</span>
    </label>
  );
}

export function Anahtar({ etiket, acik, degisince, disabled }: { etiket: string; acik: boolean; degisince: (v: boolean) => void; disabled?: boolean }) {
  const id = useId();
  return (
    <label className="kitap-onay" htmlFor={id}>
      <Switch id={id} checked={acik} onCheckedChange={degisince} disabled={disabled} className="kitap-anahtar" />
      <span>{etiket}</span>
    </label>
  );
}

/** Choice cards (setup species list): the chosen card wears the wax stamp drawing (A0-4). */
export function SecimKartlari({ etiket, deger, degisince, secenekler, disabled }: {
  etiket: string; deger?: string; degisince: (deger: string) => void; disabled?: boolean;
  secenekler: ReadonlyArray<{ deger: string; baslik: string; aciklama: string; ayrinti?: ReactNode }>;
}) {
  return (
    <RadioGroup aria-label={etiket} value={deger} onValueChange={degisince} disabled={disabled} className="kitap-kartlar">
      {secenekler.map((s) => {
        const secili = s.deger === deger;
        return (
          <label key={s.deger} className={`kitap-kart${secili ? ' kitap-kart-secili' : ''}`}>
            <RadioGroupItem value={s.deger} className="kitap-kart-radyo" />
            <span className="kitap-kart-damga">{secili ? <SecimDamgasi /> : null}</span>
            <span className="kitap-kart-metin">
              <span className="kitap-kart-baslik">{s.baslik}</span>
              <span className="kitap-kart-aciklama">{s.aciklama}</span>
              {secili && s.ayrinti ? <span className="kitap-kart-ayrinti">{s.ayrinti}</span> : null}
            </span>
          </label>
        );
      })}
    </RadioGroup>
  );
}

/** Small counter (button.tsx + a live number); the buttons stop at the limits. */
export function Sayac({ etiket, deger, min = 0, max = 99, degisince, disabled }: {
  etiket: string; deger: number; min?: number; max?: number; degisince: (v: number) => void; disabled?: boolean;
}) {
  return (
    <div className="kitap-sayac" role="group" aria-label={etiket}>
      <span className="kitap-etiket">{etiket}</span>
      <KitapDugme tur="kare" aria-label={`${etiket} azalt`} disabled={disabled || deger <= min} onClick={() => degisince(deger - 1)}><Minus aria-hidden="true" /></KitapDugme>
      <output className="kitap-sayac-deger" aria-live="polite">{deger}</output>
      <KitapDugme tur="kare" aria-label={`${etiket} artır`} disabled={disabled || deger >= max} onClick={() => degisince(deger + 1)}><Plus aria-hidden="true" /></KitapDugme>
    </div>
  );
}

export function Rozet({ children, tur = 'duz' }: { children: ReactNode; tur?: 'duz' | 'yeni' | 'hakem' }) {
  return <Badge variant="outline" className={`kitap-rozet kitap-rozet-${tur}`}>{children}</Badge>;
}

/** Page or section heading: italic Literata over a double rule; level 3 is the small quiet label. */
export function BolumBasligi({ duzey = 2, yan, children }: { duzey?: 2 | 3; yan?: ReactNode; children: ReactNode }) {
  const Etiket = duzey === 2 ? 'h2' : 'h3';
  return (
    <div className={`kitap-bolum kitap-bolum-${duzey}`}>
      <Etiket className="kitap-bolum-baslik">{children}</Etiket>
      {yan ? <p className="kitap-bolum-yan">{yan}</p> : null}
    </div>
  );
}

/** Number field (input.tsx); the error is written beside it and tied to it for screen readers. */
export function SayiKutusu({ etiket, deger, degisince, hata, disabled, yerTutucu }: {
  etiket: string; deger: string; degisince: (v: string) => void; hata?: string; disabled?: boolean; yerTutucu?: string;
}) {
  const id = useId();
  const hataId = `${id}-hata`;
  return (
    <div className="kitap-alan kitap-sayi">
      <Input id={id} inputMode="numeric" value={deger} placeholder={yerTutucu} disabled={disabled}
        aria-invalid={hata ? true : undefined} aria-describedby={hata ? hataId : undefined}
        onChange={(e) => degisince(e.target.value)} className="kitap-sayi-girdi" />
      <label className="kitap-etiket" htmlFor={id}>{etiket}</label>
      {hata ? <p id={hataId} className="kitap-alan-hata">{hata}</p> : null}
    </div>
  );
}

/** What is not written yet is a ruled empty line (draft principle 2), empty.tsx underneath. */
export function BosSatirlar({ satir = 3, etiket }: { satir?: number; etiket: string }) {
  return (
    <Empty className="kitap-bos" role="group" aria-label={etiket}>
      <p className="kitap-etiket">{etiket}</p>
      <div className="kitap-cizgili" style={{ ['--satir' as string]: satir }} aria-hidden="true" />
    </Empty>
  );
}

export function Yukleniyor({ etiket }: { etiket: string }) {
  return (
    <div className="kitap-yukleniyor" role="status" aria-live="polite">
      <Spinner aria-hidden="true" className="kitap-yukleniyor-isaret" />
      <span>{etiket}</span>
    </div>
  );
}

/** Hover and focus hint (tooltip.tsx); needs a TooltipProvider above it. */
export function Ipucu({ metin, children }: { metin: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent className="kitap-ipucu">{metin}</TooltipContent>
    </Tooltip>
  );
}

/** Window with a close button that stays in sight while the body scrolls (dialog.tsx, scroll-area.tsx). */
export function Pencere({ acik, degisince, baslik, children }: { acik: boolean; degisince: (v: boolean) => void; baslik: string; children: ReactNode }) {
  return (
    <Dialog open={acik} onOpenChange={degisince}>
      <DialogPortal>
        <DialogOverlay className="kitap-perde" />
        <DialogPrimitive.Content className="kitap-pencere" aria-describedby={undefined}>
          <div className="kitap-pencere-bas">
            <DialogTitle className="kitap-pencere-baslik">{baslik}</DialogTitle>
            <DialogPrimitive.Close asChild>
              <KitapDugme tur="kare" aria-label="Kapat"><X aria-hidden="true" /></KitapDugme>
            </DialogPrimitive.Close>
          </div>
          <ScrollArea className="kitap-pencere-govde">{children}</ScrollArea>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}

/** Self-closing notice, small, top right (sonner.tsx). */
export function BildirimAlani() {
  return <Toaster position="top-right" duration={4000} className="kitap-bildirimler" toastOptions={{ classNames: { toast: 'kitap-bildirim' } }} />;
}
