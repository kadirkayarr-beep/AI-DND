import { useId } from 'react';

// Ribbon bookmark, redrawn for realism (Kadir, 14 Nov 2026: "gerekirse farklı bir tasarım kullan"; "çok düz, direk
// gibi olmasın"); see KAYNAK.md. A satin grosgrain ribbon lying loose in the gutter: a gentle S-curve down the spine,
// one half twist where it narrows and catches the light, a soft shadow on the page, a striped headband at the top of
// the spine and a V-cut tail that falls a little to the side below the book. The colours inside are part of the drawing.

const YUKSEKLIK = 800;
const ORTA = 12;

/** Centre line and width of the ribbon at height y (viewBox units): an S-curve with one half twist. */
function kesit(y: number) {
  const t = y / YUKSEKLIK;
  const x = ORTA + 2.8 * Math.sin(t * Math.PI * 2) + 1.2 * Math.sin(t * Math.PI * 5);
  const burgu = Math.exp(-(((y - 540) / 60) ** 2));
  return { x, w: 11 - 7 * burgu };
}

function govdeYolu(kaydir = 0) {
  const sol: string[] = [];
  const sag: string[] = [];
  for (let y = 0; y <= YUKSEKLIK; y += 10) {
    const { x, w } = kesit(y);
    sol.push(`${(x - w / 2 + kaydir).toFixed(2)} ${y}`);
    sag.unshift(`${(x + w / 2 + kaydir).toFixed(2)} ${y}`);
  }
  return `M${sol.join(' L')} L${sag.join(' L')} Z`;
}

function parlakYol() {
  const nokta: string[] = [];
  for (let y = 0; y <= YUKSEKLIK; y += 10) {
    const { x, w } = kesit(y);
    nokta.push(`${(x - w * 0.12).toFixed(2)} ${y}`);
  }
  return `M${nokta.join(' L')}`;
}

const GOVDE = govdeYolu();
const GOLGE = govdeYolu(2.4);
const GOLGE_GENIS = govdeYolu(4.2);
const PARLAK = parlakYol();

export function Kurdele({ etiket = 'Kurdele ayraç' }: { etiket?: string }) {
  const id = useId().replace(/:/g, '');
  const saten = `kurdele-saten-${id}`;
  const dokuma = `kurdele-dokuma-${id}`;
  const isik = `kurdele-isik-${id}`;
  const burgu = `kurdele-burgu-${id}`;
  const kivrim = `kurdele-kivrim-${id}`;
  const satenDuraklari = (
    <>
      <stop offset="0" stopColor="#2A0706" />
      <stop offset=".16" stopColor="#5A1411" />
      <stop offset=".38" stopColor="#8C251F" />
      <stop offset=".5" stopColor="#A5342B" />
      <stop offset=".64" stopColor="#781D19" />
      <stop offset=".88" stopColor="#480F0D" />
      <stop offset="1" stopColor="#260605" />
    </>
  );
  return (
    <span className="kitap-kurdele" role="img" aria-label={etiket}>
      <svg className="kitap-kurdele-govde" width="28" height="100%" viewBox={`0 0 28 ${YUKSEKLIK}`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={saten} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
          <pattern id={dokuma} width="28" height="2.4" patternUnits="userSpaceOnUse">
            <rect x="0" y="0" width="28" height=".8" fill="#000" opacity=".14" />
            <rect x="0" y=".8" width="28" height=".5" fill="#FFF" opacity=".04" />
          </pattern>
          <linearGradient id={isik} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FFD9A8" stopOpacity=".2" />
            <stop offset=".1" stopColor="#FFD9A8" stopOpacity=".05" />
            <stop offset=".5" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".22" />
          </linearGradient>
          {/* The half twist: the satin turns its back (darker), then its face catches the light. */}
          <linearGradient id={burgu} x1="0" y1="0" x2="0" y2="1">
            <stop offset=".6" stopColor="#000" stopOpacity="0" />
            <stop offset=".645" stopColor="#000" stopOpacity=".38" />
            <stop offset=".675" stopColor="#FFC9B8" stopOpacity=".22" />
            <stop offset=".71" stopColor="#000" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={GOLGE_GENIS} fill="#000" opacity=".12" />
        <path d={GOLGE} fill="#000" opacity=".26" />
        <path d={GOVDE} fill={`url(#${saten})`} />
        <path d={GOVDE} fill={`url(#${dokuma})`} />
        <path d={GOVDE} fill={`url(#${isik})`} />
        <path d={GOVDE} fill={`url(#${burgu})`} />
        <path d={PARLAK} stroke="#E8907F" strokeWidth=".5" fill="none" opacity=".2" vectorEffect="non-scaling-stroke" />
        <path d={GOVDE} stroke="#1E0504" strokeWidth=".7" fill="none" opacity=".55" vectorEffect="non-scaling-stroke" />
      </svg>
      <svg className="kitap-kurdele-uc" width="28" height="36" viewBox="0 0 28 36" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${saten}-uc`} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
          <linearGradient id={kivrim} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#000" stopOpacity=".45" />
            <stop offset=".22" stopColor="#000" stopOpacity=".05" />
            <stop offset=".3" stopColor="#FFD9C8" stopOpacity=".12" />
            <stop offset=".5" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".25" />
          </linearGradient>
        </defs>
        {/* The tail falls a little to the side where it leaves the book. */}
        <g transform="rotate(7 12 0)">
          <path d="M17 2L22 4L22 29L19.4 27L17 32Z" fill="#000" opacity=".28" />
          <path d="M6.5 0H17.5V33L12 27L6.5 33Z" fill={`url(#${saten}-uc)`} />
          <path d="M6.5 0H17.5V33L12 27L6.5 33Z" fill={`url(#${dokuma})`} />
          <path d="M6.5 0H17.5V33L12 27L6.5 33Z" fill={`url(#${kivrim})`} />
          <path d="M6.5 33L12 27L17.5 33" stroke="#1E0504" strokeWidth=".6" fill="none" opacity=".6" />
          <path d="M7.7 31.8L7.2 33.6M9.8 29.6L9.4 31.1M14.3 29.7L14.8 31.2M16.4 31.9L16.9 33.5" stroke="#A5342B" strokeWidth=".4" opacity=".7" />
        </g>
      </svg>
      <svg className="kitap-kapitalbant" width="34" height="9" viewBox="0 0 34 9" aria-hidden="true" focusable="false">
        <rect x="0" y="0.5" width="34" height="8" rx="4" fill="#2B1D10" />
        {[2, 6, 10, 14, 18, 22, 26, 30].map((x, i) => (
          <rect key={x} x={x} y="1.4" width="2.4" height="6.2" rx="1.2" fill={i % 2 ? '#E8D9B5' : '#8E2A24'} />
        ))}
        <rect x="0" y="0.5" width="34" height="3" rx="1.5" fill="#FFF" opacity=".12" />
      </svg>
    </span>
  );
}
