import type { RefObject } from 'react';
import { MessageCircle } from 'lucide-react';
import type { SkillCheckResult } from '@workspace/api-client-react';
import { SkillCheckResultCard } from '@/components/skill-check-result';

export type TranscriptEntry = {
  kind: 'player' | 'narration';
  text: string;
  skillCheckResult?: SkillCheckResult;
};

export function Transcript({
  entries,
  scrollRef,
  onScroll,
  resultCue = '',
}: {
  entries: TranscriptEntry[];
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  resultCue?: string;
}) {
  const cue = <div className="sr-only" role="status" aria-live="polite" data-testid="status-new-result">{resultCue}</div>;
  if (!entries.length) return <div className="transcript-scroll empty-line mt-4" data-testid="empty-transcript">İlk hamleni yaz. Dünya seçiminin ardından karşılık verecek.{cue}</div>;
  return <div className="transcript-scroll" ref={scrollRef} onScroll={onScroll} data-testid="transcript-scroll" tabIndex={0} aria-label="Hikâye akışı">{cue}<div className="mt-2" data-testid="transcript-local">{entries.map((entry, index) => entry.kind === 'player' ? <div className="player-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-player-${index}`}><div className="player-label"><MessageCircle size={12} /> Sen</div>{entry.text}</div> : <div className="story-entry" key={`${entry.kind}-${index}`} data-testid={`transcript-narration-${index}`}><p className="story-text">{entry.text}</p>{entry.skillCheckResult && <SkillCheckResultCard result={entry.skillCheckResult} />}</div>)}</div><div className="reader-note">Sahne, kişiler ve öykü notları karakter ve dünya panellerinde</div></div>;
}
