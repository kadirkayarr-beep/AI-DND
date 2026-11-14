import { useId } from 'react';

// Drawing taken as drawn from kaynak/Main.dc.html (aria-label "Kurdele ayraç: ..." and the uw-kurdele gradient);
// see KAYNAK.md. The colours inside are part of the drawing and stay as drawn. It stretches to the book height.
export function Kurdele({ etiket = 'Kurdele ayraç' }: { etiket?: string }) {
  const id = useId().replace(/:/g, '');
  const yol = 'M7.4 0C6.2 120 9 260 7.5 400C6.4 540 8.6 680 7.3 782L6 817L10.6 812L15.2 817L14.6 782C15.6 680 13.8 540 14.8 400C16.1 260 13.4 120 14.6 0Z';
  return (
    <svg className="kitap-kurdele" width="20" height="818" viewBox="0 0 20 818" preserveAspectRatio="none" role="img" aria-label={etiket}>
      <defs>
        <linearGradient id={`uw-kurdele-${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5A1714" />
          <stop offset=".45" stopColor="#96302B" />
          <stop offset="1" stopColor="#671C19" />
        </linearGradient>
      </defs>
      <path d={yol} fill="#000" opacity=".35" transform="translate(1.8 1)" />
      <path d={yol} fill={`url(#uw-kurdele-${id})`} />
    </svg>
  );
}
