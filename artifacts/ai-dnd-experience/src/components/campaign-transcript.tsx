import type { CSSProperties, RefObject } from 'react';
import { CircleHelp, MessageCircle, RotateCcw, Swords } from 'lucide-react';
import type { SkillCheckResult } from '@workspace/api-client-react';
import { SkillCheckResultCard } from '@/components/skill-check-result';
import { DEFAULT_READING_PREFERENCES, type ReadingPreferences } from '@/lib/reading-preferences';

export type TranscriptEntry = {
  kind: 'player' | 'narration';
  text: string;
  skillCheckResult?: SkillCheckResult;
  mode?: 'do' | 'say' | 'ask_dm';
  /** The server's read-time undo flags (receipt-backed): a faded undone turn, a proven undo row, an unprovable target. */
  undone?: boolean;
  undoNote?: boolean;
  undoTargetUnknown?: boolean;
};

/** Display only: the stored text stays the command; the player sees a sentence, not the raw slash line. */
function playerDisplayText(text: string): string {
  return /^\/item\s+shop_buy\s/.test(text) ? 'Tezgâhtan satın alıyorum.' : text;
}

function undoneLabel(entry: TranscriptEntry, index: number) {
  return entry.undone ? <span className="transcript-undone-label" data-testid={`transcript-undone-${index}`}>Geri alındı</span> : null;
}

function PlayerEntry({ entry, index }: { entry: TranscriptEntry; index: number }) {
  const className = entry.undone ? 'player-entry transcript-undone' : 'player-entry';
  // A receipt-proven undo row reads as a sentence; the marker text alone (a player may type it) stays their words.
  if (entry.undoNote) {
    return <div className={className} data-testid={`transcript-player-${index}`}><div className="player-label"><RotateCcw size={12} aria-hidden="true" />Geri aldın</div><p className="player-text">Son turu geri aldın.{entry.undoTargetUnknown && <> <span data-testid={`transcript-undo-unknown-${index}`}>Hangi turun geri alındığı bu kayıtta artık doğrulanamıyor.</span></>}</p></div>;
  }
  return <div className={className} data-testid={`transcript-player-${index}`}><div className="player-label">{entry.mode === 'say' ? <MessageCircle size={12} aria-hidden="true" /> : entry.mode === 'ask_dm' ? <CircleHelp size={12} aria-hidden="true" /> : <Swords size={12} aria-hidden="true" />}{entry.mode === 'say' ? 'Söyledin' : entry.mode === 'ask_dm' ? 'Anlatıcıya sordun' : entry.mode === 'do' ? 'Hamlen' : 'Önceki sözün'}{undoneLabel(entry, index)}</div><p className="player-text">{playerDisplayText(entry.text)}</p></div>;
}

function NarrationEntry({ entry, index }: { entry: TranscriptEntry; index: number }) {
  return <div className={entry.undone ? 'story-entry transcript-undone' : 'story-entry'} data-testid={`transcript-narration-${index}`}>{undoneLabel(entry, index)}<p className="story-text">{entry.text}</p>{entry.skillCheckResult && <SkillCheckResultCard result={entry.skillCheckResult} />}</div>;
}

export function Transcript({
  entries,
  scrollRef,
  onScroll,
  readingPreferences = DEFAULT_READING_PREFERENCES,
  resultCue = '',
  newResponseEntryIndex,
  onJumpToNewResponse,
}: {
  entries: TranscriptEntry[];
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  readingPreferences?: ReadingPreferences;
  resultCue?: string;
  newResponseEntryIndex: number | null;
  onJumpToNewResponse: (focusTarget: boolean) => void;
}) {
  const cue = <div className="sr-only" role="status" aria-live="polite" data-testid="status-new-result">{resultCue}</div>;
  const readingStyle = {
    ...(readingPreferences.fontSizePx === null ? {} : { '--story-font-size': `${readingPreferences.fontSizePx}px` }),
    ...(readingPreferences.lineHeight === null ? {} : { '--story-line-height': String(readingPreferences.lineHeight) }),
  } as CSSProperties;
  if (!entries.length) return <div className="transcript-region"><div className="transcript-scroll empty-line mt-4" data-testid="empty-transcript">İlk hamleni yaz. Dünya seçiminin ardından karşılık verecek.{cue}</div></div>;
  return <div className="transcript-region"><div className="transcript-scroll" ref={scrollRef} onScroll={onScroll} data-testid="transcript-scroll" tabIndex={0} aria-label="Hikâye akışı" aria-description="Anlatı ve oyuncunun özgün sözleri tek akışta">{cue}<div className="mt-2" data-testid="transcript-local" style={readingStyle}>{entries.map((entry, index) => entry.kind === 'player' ? <PlayerEntry key={`${entry.kind}-${index}`} entry={entry} index={index} /> : <NarrationEntry key={`${entry.kind}-${index}`} entry={entry} index={index} />)}</div></div>{newResponseEntryIndex !== null && <button type="button" className="new-response-button" data-testid="button-new-response" aria-label="Yeni yanıta git" onMouseDown={(event) => event.preventDefault()} onClick={(event) => onJumpToNewResponse(event.detail === 0)}>↓ Yeni yanıt</button>}</div>;
}
