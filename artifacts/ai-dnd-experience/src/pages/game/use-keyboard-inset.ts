import { useEffect } from 'react';
import { clippedControlOverflow, keyboardInset } from '@/lib/play-viewport';

/** Keeps the send button above the on-screen keyboard: the shell shrinks by the keyboard's height and scrolls the clipped control into view. */
export function useKeyboardInset(phase: string, sessionId: string) {
  useEffect(() => {
    if (phase !== 'adventure' || !sessionId) return;
    const shell = document.querySelector<HTMLElement>('.play-shell');
    const viewport = window.visualViewport;
    if (!shell || !viewport) return;
    const apply = () => {
      const inset = keyboardInset(window.innerHeight, viewport.height, viewport.offsetTop);
      shell.style.setProperty('--keyboard-inset', `${inset}px`);
      if (inset <= 0) {
        shell.scrollTop = 0;
        return;
      }
      window.requestAnimationFrame(() => {
        const send = shell.querySelector<HTMLElement>('[data-testid="button-send-turn"]');
        if (!send) return;
        const container = send.closest<HTMLElement>('.app-main') ?? shell;
        const overflow = clippedControlOverflow(
          send.getBoundingClientRect().bottom,
          container.getBoundingClientRect().bottom,
          window.innerHeight - inset,
        );
        if (overflow > 1) container.scrollTop += overflow;
      });
    };
    apply();
    viewport.addEventListener('resize', apply);
    viewport.addEventListener('scroll', apply);
    return () => {
      viewport.removeEventListener('resize', apply);
      viewport.removeEventListener('scroll', apply);
    };
  }, [phase, sessionId]);
}
