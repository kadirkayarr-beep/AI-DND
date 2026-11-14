// Drawing taken as drawn from kaynak/Main.dc.html (first element of the writing line); see KAYNAK.md.
// Only the theme colour comes from a variable: --mum (pen nib), --sayfa (the slit).
export function KalemUcu({ boy = 38 }: { boy?: number }) {
  return (
    <svg width={boy} height={boy} viewBox="0 0 34 34" aria-hidden="true" focusable="false" className="kitap-kalem-ucu">
      <path d="M30 4L20.4 13.6" stroke="var(--mum)" strokeWidth="3.4" strokeLinecap="round" />
      <path d="M18.6 11.4L22.6 15.4C19.4 21.6 13.6 26 4.6 29.4C8 20.4 12.4 14.6 18.6 11.4Z" fill="var(--mum)" />
      <path d="M4.6 29.4L14.4 19.6" stroke="var(--sayfa)" strokeWidth="1.1" strokeLinecap="round" />
      <circle cx="15.2" cy="18.8" r="1.5" fill="var(--sayfa)" />
    </svg>
  );
}
