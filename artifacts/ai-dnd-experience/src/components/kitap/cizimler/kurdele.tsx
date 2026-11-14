import { useId } from 'react';

// Ribbon bookmark, redrawn for realism (Kadir, 14 Nov 2026: "gerekirse farklı bir tasarım kullan"; "çok düz, direk
// gibi olmasın"); see KAYNAK.md. A flat satin ribbon lying loose in the gutter: a clear S-curve down the spine, one
// half twist where it narrows and catches the light, light along one edge (flat cloth, not a round rod), a soft shadow
// on the page, a dark thread headband at the top of the spine and a V-cut tail that falls to the side below the book.
// The colours inside are part of the drawing. Its width follows the book (--kurdele-en).

const YUKSEKLIK = 800;
const EN = 40;
const ORTA = 20;
/** Swing of the S-curve in viewBox units (review: "kıvrımı 2-3 kat büyüt"). */
const GENLIK = 7;

/** Centre line and width of the ribbon at height y: an S-curve with a smaller ripple and one half twist. */
function kesit(y: number) {
  const t = y / YUKSEKLIK;
  const x = ORTA + GENLIK * Math.sin(t * Math.PI * 2) + 2.2 * Math.sin(t * Math.PI * 5);
  const burgu = Math.exp(-(((y - 540) / 60) ** 2));
  return { x, w: 11 - 7 * burgu };
}

function govdeYolu(kaydir = 0) {
  const sol: string[] = [];
  const sag: string[] = [];
  for (let y = 0; y <= YUKSEKLIK; y += 8) {
    const { x, w } = kesit(y);
    sol.push(`${(x - w / 2 + kaydir).toFixed(2)} ${y}`);
    sag.unshift(`${(x + w / 2 + kaydir).toFixed(2)} ${y}`);
  }
  return `M${sol.join(' L')} L${sag.join(' L')} Z`;
}

/** The light runs along the left edge of the satin, as on flat cloth. */
function parlakYol() {
  const nokta: string[] = [];
  for (let y = 0; y <= YUKSEKLIK; y += 8) {
    const { x, w } = kesit(y);
    nokta.push(`${(x - w * 0.3).toFixed(2)} ${y}`);
  }
  return `M${nokta.join(' L')}`;
}

const GOVDE = govdeYolu();
const GOLGE = govdeYolu(2.4);
const GOLGE_GENIS = govdeYolu(4.4);
const PARLAK = parlakYol();

export function Kurdele({ etiket = 'Kurdele ayraç' }: { etiket?: string }) {
  const id = useId().replace(/:/g, '');
  const saten = `kurdele-saten-${id}`;
  const dokuma = `kurdele-dokuma-${id}`;
  const isik = `kurdele-isik-${id}`;
  const burgu = `kurdele-burgu-${id}`;
  const uc = `kurdele-uc-${id}`;
  // Flat satin: bright near one edge, a long even middle, a darker far edge.
  const satenDuraklari = (
    <>
      <stop offset="0" stopColor="#5C1512" />
      <stop offset=".14" stopColor="#B03C32" />
      <stop offset=".3" stopColor="#952B24" />
      <stop offset=".7" stopColor="#7A1F1A" />
      <stop offset="1" stopColor="#4A100E" />
    </>
  );
  return (
    <span className="kitap-kurdele" role="img" aria-label={etiket}>
      <svg className="kitap-kurdele-govde" viewBox={`0 0 ${EN} ${YUKSEKLIK}`} preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={saten} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
          <pattern id={dokuma} width={EN} height="2.4" patternUnits="userSpaceOnUse">
            <rect x="0" y="0" width={EN} height=".8" fill="#000" opacity=".07" />
            <rect x="0" y=".8" width={EN} height=".5" fill="#FFF" opacity=".03" />
          </pattern>
          <linearGradient id={isik} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FFD9A8" stopOpacity=".2" />
            <stop offset=".1" stopColor="#FFD9A8" stopOpacity=".05" />
            <stop offset=".5" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".12" />
          </linearGradient>
          {/* The half twist: the satin turns its back (darker), then its face catches the light. */}
          <linearGradient id={burgu} x1="0" y1="0" x2="0" y2="1">
            <stop offset=".6" stopColor="#000" stopOpacity="0" />
            <stop offset=".645" stopColor="#000" stopOpacity=".38" />
            <stop offset=".675" stopColor="#FFC9B8" stopOpacity=".24" />
            <stop offset=".71" stopColor="#000" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={GOLGE_GENIS} fill="#000" opacity=".1" />
        <path d={GOLGE} fill="#000" opacity=".24" />
        <path d={GOVDE} fill={`url(#${saten})`} />
        <path d={GOVDE} fill={`url(#${dokuma})`} />
        <path d={GOVDE} fill={`url(#${isik})`} />
        <path d={GOVDE} fill={`url(#${burgu})`} />
        <path d={PARLAK} stroke="#F2A898" strokeWidth=".8" fill="none" opacity=".28" vectorEffect="non-scaling-stroke" />
        <path d={GOVDE} stroke="#1E0504" strokeWidth=".7" fill="none" opacity=".5" vectorEffect="non-scaling-stroke" />
      </svg>
      <svg className="kitap-kurdele-uc" viewBox={`0 0 ${EN} 46`} aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${saten}-uc`} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
          {/* Same light as the body's bottom end at the top (no seam), a crease where it bends, a lit edge below. */}
          <linearGradient id={uc} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#000" stopOpacity=".12" />
            <stop offset=".18" stopColor="#000" stopOpacity=".3" />
            <stop offset=".3" stopColor="#FFD9C8" stopOpacity=".16" />
            <stop offset=".55" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".12" />
          </linearGradient>
        </defs>
        {/* The tail falls clearly to the side where it leaves the book. */}
        <g transform="rotate(16 20 0)">
          <path d="M25 2L31 4L31 39L27.6 36L25 42Z" fill="#000" opacity=".3" />
          <path d="M14.5 0H25.5V43L20 36L14.5 43Z" fill={`url(#${saten}-uc)`} />
          <path d="M14.5 0H25.5V43L20 36L14.5 43Z" fill={`url(#${dokuma})`} />
          <path d="M14.5 0H25.5V43L20 36L14.5 43Z" fill={`url(#${uc})`} />
          <path d="M15.6 0V41.6" stroke="#F2A898" strokeWidth=".7" opacity=".3" />
          <path d="M14.5 43L20 36L25.5 43" stroke="#1E0504" strokeWidth=".6" fill="none" opacity=".55" />
          <path d="M15.7 41.8L15.2 43.6M17.8 39.6L17.4 41.1M22.3 39.7L22.8 41.2M24.4 41.9L24.9 43.5" stroke="#B03C32" strokeWidth=".4" opacity=".7" />
        </g>
      </svg>
      <svg className="kitap-kapitalbant" width="34" height="9" viewBox="0 0 34 9" aria-hidden="true" focusable="false">
        <rect x="0" y="0.5" width="34" height="8" rx="4" fill="#24180D" />
        {[2, 6, 10, 14, 18, 22, 26, 30].map((x, i) => (
          <rect key={x} x={x} y="1.4" width="2.4" height="6.2" rx="1.2" fill={i % 2 ? '#6B5134' : '#3E2C18'} />
        ))}
        <rect x="0" y="0.5" width="34" height="3" rx="1.5" fill="#FFF" opacity=".1" />
      </svg>
    </span>
  );
}
