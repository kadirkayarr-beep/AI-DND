import { useId, useLayoutEffect, useRef, useState } from 'react';

// Ribbon bookmark, redrawn for realism (Kadir, 14 Nov 2026: "gerekirse farklı bir tasarım kullan"; "çok düz, direk
// gibi olmasın"; screenshot: it broke where it left the page); see KAYNAK.md. One flat satin ribbon drawn at its
// measured height, so nothing is stretched: a clear S-curve down the gutter, one half twist, light along one edge,
// a soft shadow on the page; at the bottom it bends over the page block and the cover edge and hangs, falling to the
// side, ending in a V cut. A dark thread headband sits at the top of the spine. The phone shows only a short tail.
// The colours inside are part of the drawing. Its width follows the book (--kurdele-en).

/** Swing of the S-curve, in units of a 40px-wide ribbon box (review: "kıvrımı 2-3 kat büyüt"). */
const GENLIK = 7;
/** Container height minus the page bottom: the container reaches 40px below the pages and starts 2px above. */
const SARKMA = 38;

interface Nokta { x: number; y: number; w: number }

function cizgi(en: number, boy: number): Nokta[] {
  const s = en / 40;
  const alt = boy - SARKMA;
  const orta = en / 2;
  const noktalar: Nokta[] = [];
  for (let y = 0; y <= alt; y += 6) {
    const t = y / alt;
    const burgu = Math.exp(-(((t - 0.675) / 0.075) ** 2));
    noktalar.push({ x: orta + GENLIK * s * Math.sin(t * Math.PI * 2) + 2.2 * s * Math.sin(t * Math.PI * 5), y, w: (11 - 7 * burgu) * s });
  }
  // Over the page block and the cover edge, then hanging: the centre line leaves the vertical smoothly (t squared).
  const uc = boy - 1 - alt;
  for (let i = 1; i <= 12; i++) {
    const t = i / 12;
    noktalar.push({ x: orta + 9 * s * t * t, y: alt + uc * t, w: 11 * s });
  }
  return noktalar;
}

function yollar(en: number, boy: number) {
  const s = en / 40;
  const n = cizgi(en, boy);
  const sol = n.map((p) => `${(p.x - p.w / 2).toFixed(2)} ${p.y.toFixed(2)}`);
  const sag = n.map((p) => `${(p.x + p.w / 2).toFixed(2)} ${p.y.toFixed(2)}`).reverse();
  const son = n[n.length - 1];
  const centik = `${son.x.toFixed(2)} ${(son.y - 7 * s).toFixed(2)}`;
  const govde = `M${sol.join(' L')} L${centik} L${sag.join(' L')} Z`;
  const kaydir = (dx: number) => govde.replace(/(-?\d+\.\d+) (-?\d+\.\d+)/g, (_, x, y) => `${(Number(x) + dx).toFixed(2)} ${y}`);
  const parlak = `M${n.map((p) => `${(p.x - p.w * 0.3).toFixed(2)} ${p.y.toFixed(2)}`).join(' L')}`;
  return { govde, golge: kaydir(2.4 * s), golgeGenis: kaydir(4.4 * s), parlak, alt: boy - SARKMA };
}

export function Kurdele({ etiket = 'Kurdele ayraç' }: { etiket?: string }) {
  const id = useId().replace(/:/g, '');
  const kutu = useRef<HTMLSpanElement>(null);
  const [olcu, setOlcu] = useState({ en: 40, boy: 820 });
  useLayoutEffect(() => {
    const el = kutu.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const olc = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setOlcu({ en: r.width, boy: r.height });
    };
    olc();
    const izle = new ResizeObserver(olc);
    izle.observe(el);
    return () => izle.disconnect();
  }, []);
  const { en, boy } = olcu;
  const { govde, golge, golgeGenis, parlak, alt } = yollar(en, boy);
  const saten = `kurdele-saten-${id}`;
  const dokuma = `kurdele-dokuma-${id}`;
  const isik = `kurdele-isik-${id}`;
  const burgu = `kurdele-burgu-${id}`;
  const kivrim = `kurdele-kivrim-${id}`;
  const oran = (y: number) => Math.min(1, Math.max(0, y / boy)).toFixed(4);
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
    <span className="kitap-kurdele" role="img" aria-label={etiket} ref={kutu}>
      <svg className="kitap-kurdele-govde" width={en} height={boy} viewBox={`0 0 ${en.toFixed(2)} ${boy.toFixed(2)}`} aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={saten} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
          <pattern id={dokuma} width={en} height="2.4" patternUnits="userSpaceOnUse">
            <rect x="0" y="0" width={en} height=".8" fill="#000" opacity=".07" />
            <rect x="0" y=".8" width={en} height=".5" fill="#FFF" opacity=".03" />
          </pattern>
          <linearGradient id={isik} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FFD9A8" stopOpacity=".2" />
            <stop offset=".1" stopColor="#FFD9A8" stopOpacity=".05" />
            <stop offset=".5" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity=".1" />
          </linearGradient>
          {/* The half twist: the satin turns its back (darker), then its face catches the light. */}
          <linearGradient id={burgu} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2={boy}>
            <stop offset={oran(alt * 0.6)} stopColor="#000" stopOpacity="0" />
            <stop offset={oran(alt * 0.645)} stopColor="#000" stopOpacity=".38" />
            <stop offset={oran(alt * 0.675)} stopColor="#FFC9B8" stopOpacity=".24" />
            <stop offset={oran(alt * 0.71)} stopColor="#000" stopOpacity="0" />
          </linearGradient>
          {/* Where it bends: over the page block (a crease, then a lit ridge) and over the cover edge. */}
          <linearGradient id={kivrim} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2={boy}>
            <stop offset={oran(alt - 3)} stopColor="#000" stopOpacity="0" />
            <stop offset={oran(alt)} stopColor="#000" stopOpacity=".32" />
            <stop offset={oran(alt + 4)} stopColor="#FFD9C8" stopOpacity=".16" />
            <stop offset={oran(alt + 10)} stopColor="#000" stopOpacity=".18" />
            <stop offset={oran(alt + 15)} stopColor="#FFD9C8" stopOpacity=".1" />
            <stop offset={oran(alt + 19)} stopColor="#000" stopOpacity=".28" />
            <stop offset={oran(alt + 24)} stopColor="#000" stopOpacity=".06" />
            <stop offset="1" stopColor="#000" stopOpacity=".14" />
          </linearGradient>
        </defs>
        <path d={golgeGenis} fill="#000" opacity=".1" />
        <path d={golge} fill="#000" opacity=".24" />
        <path d={govde} fill={`url(#${saten})`} />
        <path d={govde} fill={`url(#${dokuma})`} />
        <path d={govde} fill={`url(#${isik})`} />
        <path d={govde} fill={`url(#${burgu})`} />
        <path className="kitap-kurdele-uc" d={govde} fill={`url(#${kivrim})`} />
        <path d={parlak} stroke="#F2A898" strokeWidth=".8" fill="none" opacity=".28" />
        <path d={govde} stroke="#1E0504" strokeWidth=".7" fill="none" opacity=".5" />
      </svg>
      <svg className="kitap-kurdele-kisa" width="28" height="50" viewBox="0 0 28 50" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${saten}-kisa`} x1="0" y1="0" x2="1" y2="0">{satenDuraklari}</linearGradient>
        </defs>
        <g transform="rotate(10 14 0)">
          <path d="M8.5 0H19.5V47L14 40L8.5 47Z" fill={`url(#${saten}-kisa)`} />
          <path d="M9.6 0V45.6" stroke="#F2A898" strokeWidth=".7" opacity=".3" />
          <path d="M8.5 47L14 40L19.5 47" stroke="#1E0504" strokeWidth=".6" fill="none" opacity=".55" />
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
