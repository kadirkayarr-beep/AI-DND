export function OuroborosMark({ awaken = false }: { awaken?: boolean }) {
  return (
    <svg className={`ouroboros ${awaken ? 'awaken' : ''}`} viewBox="0 0 200 200" aria-hidden="true">
      <circle className="ouroboros-ring" cx="100" cy="100" r="78" />
      <circle className="ouroboros-ring inner" cx="100" cy="100" r="46" />
      <path className="ouroboros-body" d="M148 78c18 18 14 52-12 68-28 18-66 8-78-22-12-30 6-62 36-70 22-6 40 2 54 24" />
      <path className="ouroboros-body" d="M58 126c-16-20-8-50 20-64 30-16 64-2 74 28 8 24-6 48-28 56" />
      <polygon className="ouroboros-head" points="146,70 168,78 150,96 138,84" />
      <circle className="ouroboros-eye" cx="156" cy="80" r="2.2" />
    </svg>
  );
}
