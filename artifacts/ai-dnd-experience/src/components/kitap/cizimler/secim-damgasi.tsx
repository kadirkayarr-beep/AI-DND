import { useId } from 'react';
import { MUHUR_KENAR as KENAR } from '@/components/kitap/cizimler/can-muhuru';

// Drawing taken as drawn from kaynak/KurulumGece.dc.html (aria-label "Seçildi"), with the uw-balmumu filter and the
// uw-mum-kirmizi and uw-cukur gradients from the same file; see KAYNAK.md. The wax filter applies to this 30px stamp
// only, never to a page. The colours inside are part of the drawing and stay as drawn.

export function SecimDamgasi({ boy = 30 }: { boy?: number }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg width={boy} height={boy} viewBox="0 0 120 120" role="img" aria-label="Seçildi" className="kitap-damga" style={{ overflow: 'visible' }}>
      <defs>
        <filter id={`uw-balmumu-${id}`} x="-12%" y="-12%" width="124%" height="124%">
          <feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves={2} seed={7} result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale={3} xChannelSelector="R" yChannelSelector="G" result="d" />
          <feGaussianBlur in="d" stdDeviation={2.4} result="b" />
          <feSpecularLighting in="b" surfaceScale={5} specularConstant={0.75} specularExponent={16} lightingColor="#FFD6CF" result="s">
            <feDistantLight azimuth={225} elevation={46} />
          </feSpecularLighting>
          <feComposite in="s" in2="d" operator="in" result="s2" />
          <feComposite in="d" in2="s2" operator="arithmetic" k1={0} k2={1} k3={0.6} k4={0} />
        </filter>
        <radialGradient id={`uw-mum-kirmizi-${id}`} cx="38%" cy="30%" r="78%">
          <stop offset="0" stopColor="#C9483F" />
          <stop offset=".5" stopColor="#A8332E" />
          <stop offset="1" stopColor="#701A18" />
        </radialGradient>
        <radialGradient id={`uw-cukur-${id}`} cx="62%" cy="68%" r="75%">
          <stop offset="0" stopColor="#B13A34" />
          <stop offset="1" stopColor="#8A2622" />
        </radialGradient>
      </defs>
      <g filter={`url(#uw-balmumu-${id})`}>
        <path d={KENAR} fill={`url(#uw-mum-kirmizi-${id})`} />
      </g>
      <circle cx="60" cy="60" r="30" fill={`url(#uw-cukur-${id})`} />
      <path d="M38.8 38.8A30 30 0 0 1 81.2 38.8" stroke="#4F110F" strokeWidth="4" fill="none" strokeLinecap="round" opacity=".7" />
      <path d="M81.2 81.2A30 30 0 0 1 38.8 81.2" stroke="#EE8E86" strokeWidth="3.4" fill="none" strokeLinecap="round" opacity=".55" />
    </svg>
  );
}
