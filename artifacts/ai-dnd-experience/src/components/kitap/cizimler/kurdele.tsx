import { useId, useLayoutEffect, useRef, useState } from 'react';

// Ribbon bookmark, redrawn for realism (Kadir, 14 Nov 2026: "gerekirse farklı bir tasarım kullan"; "çok düz, direk
// gibi olmasın"; screenshot: it broke where it left the page); see KAYNAK.md. One flat satin ribbon drawn at its
// measured height, so nothing is stretched: a clear S-curve down the gutter, one half twist, light along one edge,
// a soft shadow on the page; at the bottom it bends over the page block and the cover edge and lies on the desk,
// falling to the side, ending in a V cut with a lit rim. A thin thread headband sits at the top of the spine. The
// satin is drawn as bands that run along the ribbon, so its sheen follows the ribbon, and the half twist turns the
// sheen to the other edge (round 3). The phone shows only the tail, coming out from under the page.
// The colours inside are part of the drawing. Its width follows the book (--kurdele-en).

/** Swing of the S-curve, in units of a 40px-wide ribbon box (review: "kıvrımı 2-3 kat büyüt"). */
const GENLIK = 7;
/** Container height minus the page bottom: the container reaches 44px below the pages and starts 2px above. */
const SARKMA = 42;
/** Where the half twist turns (share of the body length). */
const BURGU = 0.675;
/** Satin bands across the ribbon: about one pixel each at 40px, so no step shows. */
const SERIT_SAYISI = 12;
/** Satin across the ribbon, lit edge first: [share across, red, green, blue]. */
const SATEN: [number, number, number, number][] = [
  [0, 0x5c, 0x15, 0x12], [0.14, 0xb0, 0x3c, 0x32], [0.3, 0x95, 0x2b, 0x24], [0.7, 0x7a, 0x1f, 0x1a], [1, 0x4a, 0x10, 0x0e],
];

interface Nokta { x: number; y: number; w: number; t: number }

function satenRengi(u: number) {
  let i = 0;
  while (i < SATEN.length - 2 && u > SATEN[i + 1][0]) i++;
  const [a0, r0, g0, b0] = SATEN[i];
  const [a1, r1, g1, b1] = SATEN[i + 1];
  const k = Math.min(1, Math.max(0, (u - a0) / (a1 - a0)));
  const ara = (p: number, q: number) => Math.round(p + (q - p) * k);
  return `rgb(${ara(r0, r1)}, ${ara(g0, g1)}, ${ara(b0, b1)})`;
}

function cizgi(en: number, boy: number): Nokta[] {
  const s = en / 40;
  const alt = boy - SARKMA;
  const orta = en / 2;
  const noktalar: Nokta[] = [];
  for (let y = 0; y <= alt; y += 6) {
    const t = y / alt;
    const burgu = Math.exp(-(((t - BURGU) / 0.075) ** 2));
    noktalar.push({ x: orta + GENLIK * s * Math.sin(t * Math.PI * 2) + 2.2 * s * Math.sin(t * Math.PI * 5), y, w: (11 - 7 * burgu) * s, t });
  }
  // Over the page block and the cover edge, then onto the desk: nearly straight, with a slight lean (Kadir's
  // screenshot, 14 Nov 2026: a tail swung to the side with a level cut left one fork as a loose sliver).
  const uc = boy - 1 - alt;
  for (let i = 1; i <= 14; i++) {
    const t = i / 14;
    noktalar.push({ x: orta + 2.5 * s * t, y: alt + uc * t, w: 11 * s, t: 1 + t });
  }
  return noktalar;
}

/** A strip between two shares across the ribbon (0 = left edge, 1 = right edge), over a run of points. */
function serit(n: Nokta[], a: number, b: number) {
  const sol = n.map((p) => `${(p.x - p.w / 2 + p.w * a).toFixed(2)} ${p.y.toFixed(2)}`);
  const sag = n.map((p) => `${(p.x - p.w / 2 + p.w * b).toFixed(2)} ${p.y.toFixed(2)}`).reverse();
  return `M${sol.join(' L')} L${sag.join(' L')} Z`;
}

function yollar(en: number, boy: number) {
  const s = en / 40;
  const n = cizgi(en, boy);
  const sol = n.map((p) => `${(p.x - p.w / 2).toFixed(2)} ${p.y.toFixed(2)}`);
  const sag = n.map((p) => `${(p.x + p.w / 2).toFixed(2)} ${p.y.toFixed(2)}`).reverse();
  const son = n[n.length - 1];
  // A symmetric V cut: the tail is nearly straight, so a level cut meets it square and both forks are equal.
  const centik = `${son.x.toFixed(2)} ${(son.y - 6 * s).toFixed(2)}`;
  const govde = `M${sol.join(' L')} L${centik} L${sag.join(' L')} Z`;
  const kaydir = (dx: number) => govde.replace(/(-?\d+\.\d+) (-?\d+\.\d+)/g, (_, x, y) => `${(Number(x) + dx).toFixed(2)} ${y}`);
  // The sheen line sits near the lit edge; across the half twist it crosses to the other edge.
  const yan = (t: number) => {
    const k = Math.min(1, Math.max(0, (t - (BURGU - 0.06)) / 0.12));
    return -0.3 * Math.cos(Math.PI * k * k * (3 - 2 * k));
  };
  const parlak = `M${n.map((p) => `${(p.x + p.w * yan(p.t)).toFixed(2)} ${p.y.toFixed(2)}`).join(' L')}`;
  // Satin bands: lit edge on the left before the twist, on the right after it (the face has turned over).
  const donus = n.findIndex((p) => p.t >= BURGU);
  const once = n.slice(0, donus + 1);
  const sonra = n.slice(donus);
  const seritler: { d: string; renk: string }[] = [];
  for (let i = 0; i < SERIT_SAYISI; i++) {
    const a = i / SERIT_SAYISI;
    const b = (i + 1) / SERIT_SAYISI + 0.004;
    const u = (i + 0.5) / SERIT_SAYISI;
    seritler.push({ d: serit(once, a, b), renk: satenRengi(u) });
    seritler.push({ d: serit(sonra, a, b), renk: satenRengi(1 - u) });
  }
  // A faint lit rim along the V cut only, drawn inside the shape (Kadir's screenshot, 14 Nov 2026: a rim stroked on
  // the tail's side edges lay half outside the ribbon and showed as a dull pink line beside it on the dark desk,
  // so the tail read as another colour from the point where it left the page).
  const kenar = `M${sol[sol.length - 1]} L${centik} L${sag[0]}`;
  return { govde, golge: kaydir(2.4 * s), golgeGenis: kaydir(4.4 * s), parlak, seritler, kenar, alt: boy - SARKMA };
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
  const { govde, golge, golgeGenis, parlak, seritler, kenar, alt } = yollar(en, boy);
  const saten = `kurdele-saten-${id}`;
  const dokuma = `kurdele-dokuma-${id}`;
  const isik = `kurdele-isik-${id}`;
  const burgu = `kurdele-burgu-${id}`;
  const kivrim = `kurdele-kivrim-${id}`;
  const oran = (y: number) => Math.min(1, Math.max(0, y / boy)).toFixed(4);
  return (
    <span className="kitap-kurdele" role="img" aria-label={etiket} ref={kutu}>
      <svg className="kitap-kurdele-govde" width={en} height={boy} viewBox={`0 0 ${en.toFixed(2)} ${boy.toFixed(2)}`} aria-hidden="true" focusable="false">
        <defs>
          <clipPath id={saten}><path d={govde} /></clipPath>
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
          {/* The half twist: the satin turns edge-on (darker), then its other face catches the light. */}
          <linearGradient id={burgu} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2={boy}>
            <stop offset={oran(alt * 0.6)} stopColor="#000" stopOpacity="0" />
            <stop offset={oran(alt * 0.655)} stopColor="#000" stopOpacity=".42" />
            <stop offset={oran(alt * 0.69)} stopColor="#D9604F" stopOpacity=".2" />
            <stop offset={oran(alt * 0.72)} stopColor="#000" stopOpacity="0" />
          </linearGradient>
          {/* Where it bends: over the page block (a crease, then a ridge) and over the cover edge. Shade only, no pale
              highlight (Kadir's screenshot: near-white stops washed the red out to pink where it crossed the edge);
              a ridge is a band with less shadow, so the satin keeps its own red. */}
          <linearGradient id={kivrim} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2={boy}>
            <stop offset={oran(alt - 3)} stopColor="#000" stopOpacity="0" />
            <stop offset={oran(alt)} stopColor="#000" stopOpacity=".3" />
            <stop offset={oran(alt + 4)} stopColor="#000" stopOpacity=".02" />
            <stop offset={oran(alt + 10)} stopColor="#000" stopOpacity=".2" />
            <stop offset={oran(alt + 15)} stopColor="#000" stopOpacity=".05" />
            <stop offset={oran(alt + 19)} stopColor="#000" stopOpacity=".26" />
            <stop offset={oran(alt + 24)} stopColor="#000" stopOpacity=".12" />
            <stop offset="1" stopColor="#000" stopOpacity=".16" />
          </linearGradient>
        </defs>
        <path d={golgeGenis} fill="#000" opacity=".1" />
        <path d={golge} fill="#000" opacity=".24" />
        {/* Base colour under the bands (fills the V notch and any hairline between bands). */}
        <path d={govde} fill="#7A1F1A" />
        <g clipPath={`url(#${saten})`}>
          {seritler.map((s, i) => <path key={i} className="kitap-kurdele-serit" d={s.d} fill={s.renk} />)}
        </g>
        <path d={govde} fill={`url(#${dokuma})`} />
        <path d={govde} fill={`url(#${isik})`} />
        <path d={govde} fill={`url(#${burgu})`} />
        <path className="kitap-kurdele-uc" d={govde} fill={`url(#${kivrim})`} />
        {/* Lines are clipped to the ribbon shape, so no half of a line lies beside it; they are satin reds, not pale. */}
        <g clipPath={`url(#${saten})`}>
          <path d={parlak} stroke="#D2483A" strokeWidth=".8" fill="none" opacity=".3" />
          <path d={govde} stroke="#1E0504" strokeWidth=".7" fill="none" opacity=".5" />
          <path className="kitap-kurdele-uc-kenar" d={kenar} stroke="#B03C32" strokeWidth="1.4" fill="none" strokeLinejoin="round" opacity=".45" />
        </g>
      </svg>
      {/* Phone: the tail alone. Its top is under the page (z-index in kitap.css); it crosses the cover edge. */}
      <svg className="kitap-kurdele-kisa" width="22" height="44" viewBox="0 0 22 44" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${saten}-kisa`} x1="0" y1="0" x2="1" y2="0">
            {SATEN.map(([u, r, g, b]) => <stop key={u} offset={u} stopColor={`rgb(${r}, ${g}, ${b})`} />)}
          </linearGradient>
          <clipPath id={`${saten}-kisa-kirp`}><path d="M5.5 0H16.5L17.2 41.5L11.8 36.4L6.4 42.2Z" /></clipPath>
        </defs>
        <path d="M5.5 0H16.5L17.2 41.5L11.8 36.4L6.4 42.2Z" fill="#000" opacity=".24" transform="translate(1.4 1)" />
        <path d="M5.5 0H16.5L17.2 41.5L11.8 36.4L6.4 42.2Z" fill={`url(#${saten}-kisa)`} />
        <path d="M5.5 26H16.6V31H5.5Z" fill="#000" opacity=".18" />
        <g clipPath={`url(#${saten}-kisa-kirp)`}>
          <path d="M6.6 0L7.4 41" stroke="#D2483A" strokeWidth=".7" opacity=".3" />
          <path d="M6.4 42.2L11.8 36.4L17.2 41.5" stroke="#B03C32" strokeWidth="1.4" fill="none" strokeLinejoin="round" opacity=".45" />
        </g>
      </svg>
      <svg className="kitap-kapitalbant" width="26" height="5" viewBox="0 0 26 5" aria-hidden="true" focusable="false">
        <rect x="0" y="0" width="26" height="5" rx="1.6" fill="#24180D" />
        {[1, 4, 7, 10, 13, 16, 19, 22].map((x, i) => (
          <rect key={x} x={x} y=".7" width="2" height="3.6" rx=".9" fill={i % 2 ? '#4E3A24' : '#3A2A17'} />
        ))}
        <rect x="0" y="0" width="26" height="1.4" rx=".7" fill="#FFF" opacity=".07" />
      </svg>
    </span>
  );
}
