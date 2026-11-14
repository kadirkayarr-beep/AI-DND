import { useId } from 'react';

// Brass clip-on reading lamp, redrawn for realism (Kadir, 14 Nov 2026: the draft lamp looked "made in Paint");
// placement and idea from kaynak/Main.dc.html (`class="fener"`); see KAYNAK.md. A clamp grips the top edge of the
// cover near the spine, a short brass stem rises into a coiled gooseneck that arcs over, and a domed shade points the
// bulb down at the pages. Metal is shaded as round tube and polished dome (light from the bulb and the room), the
// shade's inside glows, the bulb is white-hot. The colours inside are part of the drawing; the light the lamp throws
// on the book lives in src/index.css (--lamba-hale, --lamba-huzme, --isik-cilt, --lamba-havuz, --isik-sol/sag).
export function OkumaLambasi() {
  const id = useId().replace(/:/g, '');
  const boru = `lamba-boru-${id}`;
  const kafa = `lamba-kafa-${id}`;
  const ic = `lamba-ic-${id}`;
  const ampul = `lamba-ampul-${id}`;
  const kiskac = `lamba-kiskac-${id}`;
  const vida = `lamba-vida-${id}`;
  const kenar = `lamba-kenar-${id}`;
  const yansima = `lamba-yansima-${id}`;
  const boyun = 'M29 52C29 33 35 15 51 11.5C60 9.6 66.5 12.6 68.6 19.4';
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

      {/* Contact shadow of the clamp on the cloth. */}
      <ellipse cx="30" cy="80.5" rx="11" ry="2.2" fill="#000" opacity=".35" />

      {/* Clamp gripping the cover edge, with its thumb screw. */}
      <path d="M22.4 66.5H35.6C36.6 66.5 37.4 67.3 37.4 68.3V96.4C37.4 98 36.1 99.3 34.5 99.3H23.5C21.9 99.3 20.6 98 20.6 96.4V68.3C20.6 67.3 21.4 66.5 22.4 66.5Z" fill={`url(#${kiskac})`} />
      <path d="M21.8 70.4H36.2" stroke="#2A1D09" strokeWidth=".8" opacity=".55" />
      <path d="M21.8 95.2H36.2" stroke="#2A1D09" strokeWidth=".8" opacity=".55" />
      <path d="M24 67.4V98.4" stroke="#FFF0C4" strokeWidth=".7" opacity=".45" />
      <circle cx="29" cy="87" r="4.4" fill="#2A1D09" opacity=".6" />
      <circle cx="29" cy="86.6" r="3.8" fill={`url(#${vida})`} />
      <path d="M26.9 86.6H31.1" stroke="#2A1D09" strokeWidth=".9" strokeLinecap="round" />

      {/* Stem collar and stem. */}
      <rect x="25.6" y="60.5" width="6.8" height="6.4" rx="1.4" fill={`url(#${kiskac})`} />
      <rect x="26.9" y="51" width="4.2" height="10" fill={`url(#${boru})`} />

      {/* Coiled gooseneck: an outline, the tube, its coils, a highlight along the top. */}
      <path d={boyun} stroke="#24180A" strokeWidth="5.6" fill="none" strokeLinecap="round" />
      <path d={boyun} stroke="#9C7838" strokeWidth="4.2" fill="none" strokeLinecap="round" />
      <path d={boyun} stroke="#3A2A0E" strokeWidth="4.2" fill="none" strokeDasharray=".9 1.5" opacity=".55" />
      <path d={boyun} stroke="#F6DFA0" strokeWidth="1.1" fill="none" strokeLinecap="round" opacity=".75" transform="translate(-.9 -.7)" />
      <path d="M58 11.4C63.5 11.4 67.4 14.2 68.8 18.8" stroke={`url(#${yansima})`} strokeWidth="2" fill="none" strokeLinecap="round" />

      {/* Knuckle joint and the shade's neck. */}
      <circle cx="69" cy="21" r="3.4" fill={`url(#${vida})`} />
      <rect x="66.6" y="22.2" width="5" height="3.6" rx="1" fill={`url(#${kiskac})`} />

      {/* Domed shade with a rolled rim. */}
      <path d="M53.2 41.2C53.2 31.4 60.4 24.6 69.2 24.6C78 24.6 85.2 31.4 85.2 41.2Z" fill={`url(#${kafa})`} />
      <path d="M57.4 37.6C57.8 31.6 61.9 27.4 67.2 26.6" stroke="#FFF6D6" strokeWidth="1.3" fill="none" strokeLinecap="round" opacity=".85" />
      <path d="M80.6 32C82.4 34.4 83.5 37 83.8 40" stroke="#2E200B" strokeWidth="1" fill="none" opacity=".45" />
      <ellipse cx="69.2" cy="41.4" rx="16.9" ry="2.7" fill={`url(#${kenar})`} />
      {/* The lit inside of the shade and the bulb, seen from slightly below. */}
      <ellipse cx="69.2" cy="42.1" rx="15.2" ry="2.5" fill={`url(#${ic})`} />
      <ellipse cx="69.2" cy="43" rx="5.6" ry="3.3" fill={`url(#${ampul})`} />
      <ellipse cx="68" cy="42.3" rx="1.8" ry="1" fill="#FFFFFF" opacity=".95" />
      <path d="M52.6 42.4C58 44.1 80.4 44.1 85.8 42.4" stroke="#FFE7A8" strokeWidth=".7" fill="none" opacity=".8" />
    </svg>
  );
}
