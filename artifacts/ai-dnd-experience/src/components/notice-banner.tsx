import { AlertTriangle, CheckCircle2 } from 'lucide-react';

// `recover` is the server-proven way out of an unresolved action: ask the server what it recorded, or close the id for good.
// `recovery` is what the last server check left: `unknown` keeps every new change locked and offers a manual re-check.
// `scope` is the campaign (or session) the check was about; blockingMutation honours the lock only for that scope.
export type RecoveryState = { status: 'applied' | 'not_applied' | 'unresolved' | 'unknown'; loading: boolean; mutationAllowed: boolean; scope: string };
// `recheck` re-runs a lookup that timed out before any action id was known (nothing to abandon yet).
export type Notice = {
  tone: 'error' | 'success' | 'warning'; title: string; detail: string; retry?: () => void;
  recover?: { check: () => void; abandon: () => void }; checkLabel?: string; recovery?: RecoveryState; recheck?: () => void;
};

/** A success carries a check; only a warning or an error carries the warning triangle. */
export function NoticeBanner({ notice }: { notice: Notice }) {
  return (
    <div className={`notice ${notice.tone === 'error' ? 'error' : notice.tone === 'success' ? 'success' : ''}`} role="status" data-testid={`status-${notice.tone}`}>
      {notice.tone === 'success'
        ? <CheckCircle2 size={15} className="shrink-0" data-testid="notice-icon-success" />
        : <AlertTriangle size={15} className="shrink-0" data-testid="notice-icon-warning" />}
      <div><strong>{notice.title}</strong><div>{notice.detail}</div></div>
      {notice.retry && <button type="button" className="dnd-button" data-testid="button-retry-turn" onClick={notice.retry}>Aynı hamleyi yeniden dene</button>}
      {notice.recover && <button type="button" className="dnd-button" data-testid="button-check-action" onClick={notice.recover.check}>{notice.checkLabel ?? 'Durumu sunucudan kontrol et'}</button>}
      {notice.recover && <button type="button" className="dnd-button" data-testid="button-abandon-action" onClick={notice.recover.abandon}>Bu hamleden vazgeç (sunucu doğrular)</button>}
      {notice.recheck && <button type="button" className="dnd-button" data-testid="button-recheck-open-action" onClick={notice.recheck}>Tekrar kontrol et</button>}
    </div>
  );
}
