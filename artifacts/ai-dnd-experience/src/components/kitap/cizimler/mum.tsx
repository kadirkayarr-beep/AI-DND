import { useId } from 'react';

// Drawing taken as drawn from kaynak/Main.dc.html: <symbol id="uw-mum"> (lit) and <symbol id="uw-mum-sonuk"> (out),
// with the uw-fildisi, uw-alev and uw-hale gradients from the hidden <defs> of the same file; see KAYNAK.md. The
// colours inside are part of the drawing; the rim (--mum-cizgi), the smoke (--soluk) and the halo strength (--hale)
// come from the theme. Ids are made unique per candle, so many candles can sit on one page.
const GOVDE = 'M7 34C7 31.6 10.4 30.4 15 30.4C19.6 30.4 23 31.6 23 34L23 85C23 86.4 19.4 87.4 15 87.4C10.6 87.4 7 86.4 7 85Z';
const AKINTI = 'M22.6 34.6C23.6 39 23.8 45 23 51C22.5 54.4 20.2 54.2 20 51C19.7 46 20.4 40 19.6 35.6Z';

export function Mum({ yanan, en = 24 }: { yanan: boolean; en?: number }) {
  const id = useId().replace(/:/g, '');
  const govde = (
    <>
      <path d={GOVDE} fill={`url(#uw-fildisi-${id})`} stroke="var(--mum-cizgi)" strokeWidth=".7" />
      <path d={AKINTI} fill="#F7F1E0" stroke="var(--mum-cizgi)" strokeWidth=".5" />
      <ellipse cx="15" cy="33.8" rx="8" ry="2.7" fill="#FBF7EA" />
      <ellipse cx="15" cy="34.1" rx="4.4" ry="1.4" fill="#DDD1B2" />
    </>
  );
  return (
    <svg width={en} height={en * 3} viewBox="0 0 30 90" aria-hidden="true" className="kitap-mum" data-mum={yanan ? 'yanan' : 'sonuk'} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`uw-fildisi-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#CFC6AC" />
          <stop offset=".32" stopColor="#F4EEDC" />
          <stop offset=".62" stopColor="#E7DEC7" />
          <stop offset="1" stopColor="#B0A68C" />
        </linearGradient>
        {yanan ? (
          <>
            <linearGradient id={`uw-alev-${id}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0" stopColor="#E8892B" />
              <stop offset=".45" stopColor="#F7BE4A" />
              <stop offset="1" stopColor="#FFE9A8" />
            </linearGradient>
            <radialGradient id={`uw-hale-${id}`} cx="50%" cy="55%" r="50%">
              <stop offset="0" stopColor="#FFD27A" stopOpacity=".55" />
              <stop offset="1" stopColor="#FFD27A" stopOpacity="0" />
            </radialGradient>
          </>
        ) : null}
      </defs>
      {yanan ? (
        <>
          <ellipse cx="15" cy="86.4" rx="10.5" ry="2.4" fill="#000" opacity=".3" />
          {govde}
          <path d="M15 34C14.5 31 15.7 29 15 26" stroke="#2A2118" strokeWidth="1.3" fill="none" strokeLinecap="round" />
          <circle className="kitap-mum-hale" cx="15" cy="16" r="15" fill={`url(#uw-hale-${id})`} />
          <path d="M15 2.5C19.4 9.5 21.4 14.2 21.4 18.6C21.4 23 18.6 26.2 15 26.2C11.4 26.2 8.6 23 8.6 18.6C8.6 14.2 10.6 9.5 15 2.5Z" fill={`url(#uw-alev-${id})`} />
          <path d="M15 13C17 16.6 18 19 18 20.9C18 23.2 16.7 24.8 15 24.8C13.3 24.8 12 23.2 12 20.9C12 19 13 16.6 15 13Z" fill="#FFF7DC" opacity=".92" />
        </>
      ) : (
        <>
          <ellipse cx="15" cy="86.4" rx="10.5" ry="2.4" fill="#000" opacity=".22" />
          <g opacity=".5">{govde}</g>
          <path d="M15 34C14.5 31.4 15.6 29.6 15 27.4" stroke="#17120E" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          <path d="M15 24.5C12.2 20 17.8 16.6 15 12C13.2 9 16.4 6.4 15.4 3" stroke="var(--soluk)" strokeWidth="1" fill="none" strokeLinecap="round" opacity=".55" />
        </>
      )}
    </svg>
  );
}
