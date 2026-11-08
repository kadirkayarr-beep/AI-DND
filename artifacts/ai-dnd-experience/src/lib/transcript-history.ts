import type { CampaignHistoryEntry } from '@workspace/api-client-react';
import type { TranscriptEntry } from '@/components/campaign-transcript';

type UndoFlags = Pick<TranscriptEntry, 'undone' | 'undoNote' | 'undoTargetUnknown'>;

/** The server's read-time undo flags (receipt-backed, never guessed here); an absent flag stays absent. */
function undoFlags(entry: CampaignHistoryEntry): UndoFlags {
  return {
    ...(entry.undone === true ? { undone: true } : {}),
    ...(entry.undo_note === true ? { undoNote: true } : {}),
    ...(entry.undo_target_unknown === true ? { undoTargetUnknown: true } : {}),
  };
}

/**
 * The saved story as transcript entries: the opening (when there is one), then each history row as the player's
 * line and its narration. `lastPlayerMode` marks only the last player line (the move this screen just sent).
 */
export function historyToEntries(
  history: CampaignHistoryEntry[],
  options: { opening?: string | null; lastPlayerMode?: TranscriptEntry['mode'] } = {},
): TranscriptEntry[] {
  const { opening, lastPlayerMode } = options;
  return [
    ...(typeof opening === 'string' && opening.trim() ? [{ kind: 'narration' as const, text: opening }] : []),
    ...history.flatMap((entry, index): TranscriptEntry[] => [
      { kind: 'player', text: entry.player_message,
        ...(index === history.length - 1 && lastPlayerMode ? { mode: lastPlayerMode } : {}), ...undoFlags(entry) },
      { kind: 'narration', text: entry.narration,
        skillCheckResult: entry.skill_check_result ?? undefined, ...undoFlags(entry) },
    ]),
  ];
}
