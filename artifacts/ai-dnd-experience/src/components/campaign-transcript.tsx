import type { CSSProperties, RefObject } from 'react';
import { CircleHelp, MessageCircle, Swords } from 'lucide-react';
import type { SkillCheckResult } from '@workspace/api-client-react';
import { SkillCheckResultCard } from '@/components/skill-check-result';
import { DEFAULT_READING_PREFERENCES, type ReadingPreferences } from '@/lib/reading-preferences';

export type TranscriptEntry = {
  kind: 'player' | 'narration';
  text: string;
  skillCheckResult?: SkillCheckResult;
  mode?: 'do' | 'say' | 'ask_dm';
};

/** Display only: the stored text stays the command; the player sees a sentence, not the raw slash line. */
function playerDisplayText(text: string): string {
  return /^\/item\s+shop_buy\s/.test(text) ? 'Tezgâhtan satın alıyorum.' : text;
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
  return <div className="transcript-region"><div className="transcript-scroll" ref={scrollRef} onScroll={onScroll} data-testid="transcript-scroll" tabIndex={0} aria-label="Hikâye akışı" aria-description="Anlatı ve oyuncunun özgün sözleri tek akışta">{cue}<div className="mt-2" data-testid="transcript-local" style={readingStyle}>{entries.map((entry, index) => entry.kind === 'player' ? <div className="player-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-player-${index}`}><div className="player-label">{entry.mode === 'say' ? <MessageCircle size={12} aria-hidden="true" /> : entry.mode === 'ask_dm' ? <CircleHelp size={12} aria-hidden="true" /> : <Swords size={12} aria-hidden="true" />}{entry.mode === 'say' ? 'Söyledin' : entry.mode === 'ask_dm' ? 'Anlatıcıya sordun' : entry.mode === 'do' ? 'Hamlen' : 'Önceki sözün'}</div><p className="player-text">{playerDisplayText(entry.text)}</p></div> : <div className="story-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-narration-${index}`}><p className="story-text">{entry.text}</p>{entry.skillCheckResult && <SkillCheckResultCard result={entry.skillCheckResult} />}</div>)}</div></div>{newResponseEntryIndex !== null && <button type="button" className="new-response-button" data-testid="button-new-response" aria-label="Yeni yanıta git" onMouseDown={(event) => event.preventDefault()} onClick={(event) => onJumpToNewResponse(event.detail === 0)}>↓ Yeni yanıt</button>}</div>;
}
