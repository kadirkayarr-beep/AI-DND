export function keyboardInset(innerHeight: number, viewportHeight: number, offsetTop: number) {
  if (!Number.isFinite(innerHeight) || !Number.isFinite(viewportHeight) || !Number.isFinite(offsetTop)) return 0;
  return Math.max(0, Math.round(innerHeight - viewportHeight - offsetTop));
}

export function focusReturnTarget(openerConnected: boolean): 'opener' | 'draft' {
  return openerConnected ? 'opener' : 'draft';
}

export function transcriptFollowsBottom(wasAtBottom: boolean) {
  return wasAtBottom;
}
