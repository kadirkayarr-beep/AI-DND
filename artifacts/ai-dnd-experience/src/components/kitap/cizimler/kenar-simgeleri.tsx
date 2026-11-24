import type { ReactNode } from 'react';

// Drawings taken as drawn from kaynak/Main.dc.html: the 16px <svg>s inside class="kenar" (para: "Kesenden 4 bakır
// çıktı", iş: "Yeni iş", geri: "Geri alındı", zar: "Algı zarı", kural: "Yol tarifi günlüğe yazıldı"); see KAYNAK.md.
// Line drawings in currentColor, so they take the colour of their margin note.
const KENAR_SIMGELERI = {
  para: <><circle cx="8" cy="8" r="6.2" /><circle cx="8" cy="8" r="3.2" /></>,
  is: <path d="M4 1.8H12V14.2L8 11.2L4 14.2Z" />,
  geri: <><path d="M6 3.2L2.6 6.4L6 9.6" /><path d="M2.8 6.4H9.4C11.8 6.4 13.4 8 13.4 10.2C13.4 12.4 11.8 13.8 9.6 13.8H7" /></>,
  zar: <><path d="M8 1.4L14 4.8V11.2L8 14.6L2 11.2V4.8Z" /><path d="M8 1.4V5.6M2 11.2L5.2 9.6M14 11.2L10.8 9.6M5.2 9.6L8 5.6L10.8 9.6Z" /></>,
  kural: <><path d="M3 2.2H13V13.8H3Z" /><path d="M5.6 5.4H10.4M5.6 8H10.4M5.6 10.6H8.6" /></>,
} satisfies Record<string, ReactNode>;

export type KenarSimgesi = keyof typeof KENAR_SIMGELERI;

export function KenarSimge({ ad }: { ad: KenarSimgesi }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="kitap-kenar-simge">
      {KENAR_SIMGELERI[ad]}
    </svg>
  );
}
