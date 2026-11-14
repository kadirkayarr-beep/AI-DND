/*
 * Book UI (A1): which of the three book themes a page shows. The values live in src/index.css under
 * [data-kitap-tema]; old screens never carry that attribute, so they keep the --unw reading tokens.
 */
export type KitapTemasi = 'gunduz' | 'gece' | 'karanlik';
export type GorunumSecimi = 'saat' | KitapTemasi;
export type HikayeSaati = 'gunduz' | 'gece';
export type ElYazisi = 'a' | 'b' | 'c';
export type YaziBoyu = 'normal' | 'buyuk';
export type SayfaDuzeni = 'iki-sayfa' | 'karakter-acik';

/** Four options, the story clock first (Kadir, 13 Nov 2026); there is no "follow the device" option. */
export const GORUNUM_SECENEKLERI: ReadonlyArray<{ deger: GorunumSecimi; etiket: string }> = [
  { deger: 'saat', etiket: 'Hikâyedeki saati izle' },
  { deger: 'gunduz', etiket: 'Gündüz' },
  { deger: 'gece', etiket: 'Gece' },
  { deger: 'karanlik', etiket: 'Karanlık' },
];
export const VARSAYILAN_GORUNUM: GorunumSecimi = 'saat';

/** Shown A, B, C as in the target image; B (Kalam) is the default (decision T10). */
export const EL_YAZISI_SECENEKLERI: ReadonlyArray<{ deger: ElYazisi; etiket: string; ad: string }> = [
  { deger: 'a', etiket: 'A', ad: 'Charm' },
  { deger: 'b', etiket: 'B', ad: 'Kalam' },
  { deger: 'c', etiket: 'C', ad: 'Bad Script' },
];
export const VARSAYILAN_EL: ElYazisi = 'b';

export const SAYFA_DUZENI_SECENEKLERI: ReadonlyArray<{ deger: SayfaDuzeni; etiket: string }> = [
  { deger: 'iki-sayfa', etiket: 'İki sayfa hikâye' },
  { deger: 'karakter-acik', etiket: 'Karakter açık' },
];

export const YAZI_BOYU_SECENEKLERI: ReadonlyArray<{ deger: YaziBoyu; etiket: string }> = [
  { deger: 'normal', etiket: 'Normal' },
  { deger: 'buyuk', etiket: 'Büyük' },
];

/**
 * T5: no story line is lost. With another bookmark open, or on a phone (one page), the story runs as one flow on the
 * left page, ending in its last lines and the writing field; only the two-page story spreads it over both pages.
 */
export function hikayeTekAkista(ayrac: string, darEkran: boolean): boolean {
  return darEkran || ayrac !== 'hikaye';
}

export function kitapTemasi(secim: GorunumSecimi, saat: HikayeSaati): KitapTemasi {
  return secim === 'saat' ? saat : secim;
}
