import { useId } from 'react';

// Drawing taken as drawn from kaynak/KurulumGece.dc.html (aria-label "Seçildi"), with the uw-balmumu filter and the
// uw-mum-kirmizi and uw-cukur gradients from the same file; see KAYNAK.md. The wax filter applies to this 30px stamp
// only, never to a page. The colours inside are part of the drawing and stay as drawn.
const KENAR = 'M109.7 60.0 C108.7 62.6 106.9 64.8 106.2 67.3 C105.6 69.8 106.0 72.3 105.7 74.9 C105.5 77.4 105.4 80.3 104.7 82.8 C104.0 85.3 102.7 87.7 101.4 90.1 C100.1 92.4 98.7 94.9 96.9 96.9 C95.1 98.9 92.9 100.7 90.7 102.2 C88.4 103.8 86.0 105.0 83.5 106.2 C81.1 107.4 78.7 109.0 76.1 109.5 C73.4 109.9 70.4 109.6 67.7 108.9 C65.1 108.2 62.5 106.1 60.0 105.3 C57.5 104.6 55.4 104.4 53.0 104.5 C50.5 104.5 47.8 105.5 45.1 105.7 C42.4 105.9 39.5 106.1 36.7 105.7 C34.0 105.3 30.9 104.7 28.6 103.3 C26.2 101.9 24.3 99.5 22.8 97.2 C21.4 94.8 20.9 91.7 19.7 89.2 C18.6 86.8 17.1 84.8 15.8 82.5 C14.5 80.3 12.7 78.1 11.9 75.6 C11.2 73.1 11.3 70.3 11.1 67.7 C10.9 65.1 10.9 62.6 10.8 60.0 C10.7 57.4 10.3 54.8 10.4 52.1 C10.5 49.5 10.8 46.8 11.3 44.2 C11.8 41.5 12.2 38.6 13.4 36.2 C14.6 33.9 16.4 31.5 18.6 29.9 C20.9 28.4 24.5 28.0 27.0 27.0 C29.5 25.9 31.7 25.3 33.6 23.7 C35.6 22.2 36.7 19.7 38.5 17.8 C40.3 15.8 42.2 13.6 44.4 12.0 C46.6 10.3 49.1 8.8 51.7 7.8 C54.3 6.9 57.3 6.3 60.0 6.4 C62.7 6.6 65.5 7.8 68.1 8.7 C70.8 9.5 73.3 10.4 75.8 11.3 C78.3 12.3 81.1 12.8 83.3 14.3 C85.4 15.8 87.1 18.3 88.7 20.5 C90.3 22.6 91.2 25.3 92.8 27.2 C94.4 29.2 96.3 30.5 98.2 32.2 C100.1 33.9 102.4 35.5 104.2 37.5 C106.1 39.4 108.1 41.5 109.5 43.9 C110.8 46.3 112.1 49.1 112.1 51.7 C112.2 54.4 110.7 57.4 109.7 60.0Z';

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
