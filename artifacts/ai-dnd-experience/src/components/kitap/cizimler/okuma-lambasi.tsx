import { useId } from 'react';

// Reading lamp taken as drawn from kaynak/Main.dc.html (`class="fener"` with the uw-pirinc and uw-oz gradients); see
// KAYNAK.md. A brass clamp on the top edge of the book, an arm over the spine and a shade with a lit bulb. The colours
// inside are part of the drawing. The light it throws lives in src/index.css (--lamba-hale, --lamba-havuz, --isik-*).
export function OkumaLambasi() {
  const id = useId().replace(/:/g, '');
  const pirinc = `uw-pirinc-${id}`;
  const oz = `uw-oz-${id}`;
  return (
    <svg className="kitap-lamba-cizim" width="64" height="80" viewBox="0 0 80 100" role="img" aria-label="Okuma ışığı yanıyor">
      <defs>
        <linearGradient id={pirinc} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#C2A05C" />
          <stop offset=".5" stopColor="#7A5F2C" />
          <stop offset="1" stopColor="#33260F" />
        </linearGradient>
        <radialGradient id={oz} cx="50%" cy="40%" r="60%">
          <stop offset="0" stopColor="#FFF8DE" />
          <stop offset=".55" stopColor="#FFD271" />
          <stop offset="1" stopColor="#E0942A" />
        </radialGradient>
      </defs>
      <path d="M21 78H35V97C35 98.4 33.9 99.4 32.6 99.4H23.4C22.1 99.4 21 98.4 21 97Z" fill={`url(#${pirinc})`} />
      <path d="M21.8 78.6V96.6" stroke="#E3C98C" strokeWidth=".9" fill="none" opacity=".7" />
      <circle cx="28" cy="89" r="2.3" fill="#2E220E" />
      <path d="M26.6 89H29.4" stroke="#B89650" strokeWidth=".8" />
      <path d="M28 79C28 56 22 30 34 16C44 4.6 60 7 61 21" stroke="#3A2C12" strokeWidth="5" fill="none" strokeLinecap="round" />
      <path d="M28 79C28 56 22 30 34 16C44 4.6 60 7 61 21" stroke={`url(#${pirinc})`} strokeWidth="3.4" fill="none" strokeLinecap="round" />
      <path d="M26.9 70C26.4 52 22.6 31 33.4 17.4C39 11 46.4 9 52 10.4" stroke="#EBD49C" strokeWidth=".9" fill="none" strokeLinecap="round" opacity=".75" />
      <circle cx="28" cy="77" r="3.3" fill={`url(#${pirinc})`} />
      <circle cx="61" cy="24.6" r="2.6" fill="none" stroke="#8C6F36" strokeWidth="1.6" />
      <path d="M57.4 28.4H64.6L65.6 31.4H56.4Z" fill="#4A3916" />
      <path d="M46.4 47.4C46.4 37.4 52.4 31 61 31C69.6 31 75.6 37.4 75.6 47.4L77.6 50.6H44.4Z" fill={`url(#${pirinc})`} />
      <path d="M48.6 46.4C48.8 38.8 53.6 33.4 60 32.6" stroke="#F0DBA6" strokeWidth="1" fill="none" strokeLinecap="round" opacity=".8" />
      <path d="M44.4 50.6H77.6" stroke="#2E220E" strokeWidth="1.6" strokeLinecap="round" />
      <ellipse cx="61" cy="53.4" rx="8.4" ry="4.6" fill={`url(#${oz})`} />
    </svg>
  );
}
