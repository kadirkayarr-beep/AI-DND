import { useId } from 'react';

// Brass clip-on reading lamp, redrawn for realism (Kadir, 14 Nov 2026: the draft lamp looked "made in Paint");
// placement and idea from kaynak/Main.dc.html (`class="fener"`); see KAYNAK.md. A clamp bites the top edge of the
// cover near the spine (a back block on the desk side, a jaw pressed onto the cloth, a thumb screw), a short brass
// stem rises into a coiled gooseneck that arcs over, and a domed shade, tipped a little towards the reader, points
// the bulb down at the pages. The arc is kept low so the lamp stays inside the window at every width (round 3).
// Metal is shaded as round tube and polished dome (light from the bulb and the room), the shade's inside glows, the
// bulb is white-hot. The colours inside are part of the drawing; the light the lamp throws on the book lives in
// src/index.css (--lamba-hale, --lamba-huzme, --isik-cilt, --lamba-havuz, --isik-sol/sag).
export function OkumaLambasi() {
  const id = useId().replace(/:/g, '');
  const boru = `lamba-boru-${id}`;
  const kafa = `lamba-kafa-${id}`;
  const ic = `lamba-ic-${id}`;
  const ampul = `lamba-ampul-${id}`;
  const kiskac = `lamba-kiskac-${id}`;
  const cene = `lamba-cene-${id}`;
  const vida = `lamba-vida-${id}`;
  const kenar = `lamba-kenar-${id}`;
  const yansima = `lamba-yansima-${id}`;
  const boyun = 'M30 54C30 41 36 28.5 50 26.4C59 25.2 66 27.8 68.4 33.4';
  const dil = 'M23.4 78H36.6L35.8 92C35.7 93.4 34.6 94.4 33.2 94.4H26.8C25.4 94.4 24.3 93.4 24.2 92Z';
  return (
    <svg className="kitap-lamba-cizim" viewBox="0 0 100 110" role="img" aria-label="Okuma ışığı yanıyor">
      <defs>
        {/* Round brass tube: dark edges, a bright band off-centre, warm mid tone. */}
        <linearGradient id={boru} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#2E200B" />
          <stop offset=".22" stopColor="#7E5F27" />
          <stop offset=".42" stopColor="#F3DC9C" />
          <stop offset=".55" stopColor="#C29A4C" />
          <stop offset=".82" stopColor="#6A4E1E" />
          <stop offset="1" stopColor="#2A1D09" />
        </linearGradient>
        {/* Polished dome: a hot highlight high on the left, falling into deep brown at the far edge. */}
        <radialGradient id={kafa} cx="34%" cy="26%" r="80%">
          <stop offset="0" stopColor="#FFF4CF" />
          <stop offset=".12" stopColor="#E9C978" />
          <stop offset=".36" stopColor="#B88A3C" />
          <stop offset=".66" stopColor="#7A5822" />
          <stop offset="1" stopColor="#3A280C" />
        </radialGradient>
        <linearGradient id={kenar} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5E451A" />
          <stop offset=".3" stopColor="#E6C780" />
          <stop offset=".55" stopColor="#FFE9AE" />
          <stop offset=".8" stopColor="#B48A3F" />
          <stop offset="1" stopColor="#4E3812" />
        </linearGradient>
        {/* Inside of the shade, lit by the bulb. */}
        <radialGradient id={ic} cx="50%" cy="35%" r="65%">
          <stop offset="0" stopColor="#FFFBEA" />
          <stop offset=".35" stopColor="#FFE6A6" />
          <stop offset=".75" stopColor="#F0B654" />
          <stop offset="1" stopColor="#A86A1C" />
        </radialGradient>
        <radialGradient id={ampul} cx="50%" cy="40%" r="60%">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset=".45" stopColor="#FFF7DC" />
          <stop offset="1" stopColor="#FFD887" />
        </radialGradient>
        <linearGradient id={kiskac} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3B2A0E" />
          <stop offset=".25" stopColor="#B8924A" />
          <stop offset=".45" stopColor="#E8CD8A" />
          <stop offset=".7" stopColor="#8A6A2E" />
          <stop offset="1" stopColor="#33240B" />
        </linearGradient>
        {/* The jaw lies on the cloth: lit along its top lip, darker where it presses down. */}
        <linearGradient id={cene} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#E2C37E" />
          <stop offset=".18" stopColor="#A9843E" />
          <stop offset=".75" stopColor="#6E5222" />
          <stop offset="1" stopColor="#3E2C0E" />
        </linearGradient>
        <radialGradient id={vida} cx="38%" cy="32%" r="70%">
          <stop offset="0" stopColor="#F7E3A8" />
          <stop offset=".5" stopColor="#9C7A38" />
          <stop offset="1" stopColor="#3A2A0E" />
        </radialGradient>
        {/* Warm bulb light caught on the underside of the arm near the shade. */}
        <linearGradient id={yansima} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFE1A0" stopOpacity="0" />
          <stop offset="1" stopColor="#FFE1A0" stopOpacity=".75" />
        </linearGradient>
      </defs>

      {/* Shadows: the back block on the desk, the jaw on the cloth (offset down and right, away from the bulb). */}
      <ellipse cx="30.5" cy="80.6" rx="10.5" ry="1.8" fill="#000" opacity=".4" />
      <path d={dil} fill="#000" opacity=".32" transform="translate(1.4 2.2)" />
      <ellipse cx="31" cy="95.6" rx="8" ry="1.6" fill="#000" opacity=".3" />

      {/* Clamp: the back block, the jaw biting the cover edge (the dark seam is the cover between them), the screw. */}
      <rect x="21" y="64.6" width="18" height="15.6" rx="2.2" fill={`url(#${kiskac})`} />
      <path d="M22.6 66.2H37.4" stroke="#FFF0C4" strokeWidth=".6" opacity=".4" />
      <path d={dil} fill={`url(#${cene})`} />
      <path d="M22 79.3H38" stroke="#1E1406" strokeWidth="1.2" opacity=".7" />
      <path d="M24.6 79.9V92" stroke="#FFF0C4" strokeWidth=".6" opacity=".35" />
      <circle cx="30" cy="87.4" r="3.9" fill="#1E1406" opacity=".55" />
      <circle cx="30" cy="87" r="3.4" fill={`url(#${vida})`} />
      <path d="M28.1 87H31.9" stroke="#2A1D09" strokeWidth=".8" strokeLinecap="round" />

      {/* Stem collar and stem. */}
      <rect x="26.6" y="60" width="6.8" height="5.4" rx="1.3" fill={`url(#${kiskac})`} />
      <rect x="27.9" y="53" width="4.2" height="8" fill={`url(#${boru})`} />

      {/* Coiled gooseneck: a brown outline, the tube, wide coils, a highlight along the top. */}
      <path d={boyun} stroke="#4A3416" strokeWidth="5.4" fill="none" strokeLinecap="round" opacity=".9" />
      <path d={boyun} stroke="#A07C3A" strokeWidth="4.2" fill="none" strokeLinecap="round" />
      <path d={boyun} stroke="#3A2A0E" strokeWidth="4.2" fill="none" strokeDasharray="1.3 2" opacity=".5" />
      <path d={boyun} stroke="#F6DFA0" strokeWidth="1.1" fill="none" strokeLinecap="round" opacity=".75" transform="translate(-.8 -.8)" />
      <path d="M58 26C63.5 26 67.2 28.8 68.6 32.8" stroke={`url(#${yansima})`} strokeWidth="2" fill="none" strokeLinecap="round" />

      {/* Knuckle joint and the shade's neck. */}
      <circle cx="68.8" cy="35" r="3.4" fill={`url(#${vida})`} />
      <rect x="66.4" y="36.2" width="5" height="3.6" rx="1" fill={`url(#${kiskac})`} />

      {/* Domed shade with a rolled rim. */}
      <path d="M53.2 55.8C53.2 46 60.4 39.4 69.2 39.4C78 39.4 85.2 46 85.2 55.8Z" fill={`url(#${kafa})`} />
      <path d="M57.4 52.2C57.8 46.2 61.9 42 67.2 41.2" stroke="#FFF6D6" strokeWidth="1.3" fill="none" strokeLinecap="round" opacity=".85" />
      <path d="M80.6 46.6C82.4 49 83.5 51.6 83.8 54.6" stroke="#2E200B" strokeWidth="1" fill="none" opacity=".45" />
      <ellipse cx="69.2" cy="56" rx="16.9" ry="3.4" fill={`url(#${kenar})`} />
      {/* The lit inside of the shade and the bulb: the shade tips towards the reader, so more of its mouth shows. */}
      <ellipse cx="69.2" cy="56.9" rx="15.2" ry="3.9" fill={`url(#${ic})`} />
      <ellipse cx="69.2" cy="58.2" rx="5.8" ry="3.6" fill={`url(#${ampul})`} />
      <ellipse cx="68" cy="57.3" rx="1.9" ry="1.1" fill="#FFFFFF" opacity=".95" />
      <path d="M52.6 57.2C58 60.2 80.4 60.2 85.8 57.2" stroke="#FFE7A8" strokeWidth=".7" fill="none" opacity=".8" />
    </svg>
  );
}
