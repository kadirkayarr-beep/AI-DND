import type { CSSProperties } from 'react';
import { inkStepMs, splitInkPieces } from '@/lib/ink-reveal';
import type { InkRevealSpeed } from '@/lib/appearance-settings';

type InkVars = CSSProperties & Record<`--${string}`, string | number>;

/**
 * The story text of one narration entry. Every word is always in the DOM in its original order and
 * spacing (copy, search and screen readers get the full text at once); a fresh entry only fades the
 * words in one after another with CSS. Atmosphere never touches this text. `quill` adds the waiting
 * pen tip after the last word: an empty decorative span, so the text content stays exactly the story.
 */
export function InkText({ text, speed, animate, quill, still }: {
  text: string;
  speed: InkRevealSpeed;
  animate: boolean;
  quill: boolean;
  /** No motion at all (effects off or reduced motion): the tip is drawn but does not pulse. */
  still: boolean;
}) {
  const pieces = splitInkPieces(text);
  const wordCount = pieces.filter((piece) => piece.word).length;
  const step = animate ? inkStepMs(speed, wordCount) : 0;
  const reveal = step > 0;
  let index = 0;
  const tipStyle: InkVars | undefined = reveal ? { '--ink-delay': `${Math.round(step * wordCount + 300)}ms` } : undefined;
  return (
    <p className={reveal ? 'story-text ink-fresh' : 'story-text'} style={reveal ? ({ '--ink-step': `${step}ms` } as InkVars) : undefined}>
      {reveal
        ? pieces.map((piece, key) => (piece.word
          ? <span key={key} className="ink-word" style={{ '--ink-i': index++ } as InkVars}>{piece.text}</span>
          : piece.text))
        : text}
      {quill && <span className={still ? 'ink-tip ink-tip-still' : 'ink-tip'} style={tipStyle} data-testid="ink-tip" aria-hidden="true" />}
    </p>
  );
}
