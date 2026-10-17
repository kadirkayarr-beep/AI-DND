export const IDENTITY_FIELDS = ['origin', 'appearance', 'personality', 'backstory'] as const;

export type IdentityField = (typeof IDENTITY_FIELDS)[number];

export type IdentityValues = Record<IdentityField, string>;

export type IdentitySuggestionJob = {
  requestId: string;
  draftId: string;
  field: IdentityField;
  revision: number;
  baseText: string;
  status: 'pending' | 'queued' | 'running' | 'ready' | 'failed' | 'timed_out' | 'rejected';
  suggestion: string | null;
  code: string | null;
};

export const DISMISS_NOTICE = 'Öneri görünümü kapatıldı.';

const LIMITS: Record<IdentityField, number> = {
  origin: 240,
  appearance: 500,
  personality: 500,
  backstory: 1000,
};

export function dismissNotice() {
  return DISMISS_NOTICE;
}

export type SuggestionGate = {
  requestId: string;
  draftId: string;
  field: IdentityField;
  revision: number;
  epoch: number;
  currentEpoch: number;
  currentRevision: number;
  locked: boolean;
  discarded: boolean;
};

export function applyObservedJob(
  current: IdentitySuggestionJob | null,
  observed: IdentitySuggestionJob,
  gate: SuggestionGate,
) {
  if (!current || current.requestId !== gate.requestId) return current;
  if (current.draftId !== gate.draftId || current.field !== gate.field || current.revision !== gate.revision) return current;
  if (
    observed.requestId !== gate.requestId
    || observed.draftId !== gate.draftId
    || observed.field !== gate.field
    || observed.revision !== gate.revision
  ) return current;
  if (gate.currentEpoch !== gate.epoch || gate.locked || gate.discarded) return current;
  if (gate.currentRevision !== gate.revision) return current;
  if (current.status === 'ready' && current.suggestion && (observed.status !== 'ready' || !observed.suggestion)) {
    return current;
  }
  return observed;
}

export function noticeForJob(status: string, code?: string | null) {
  if (code === 'status_unavailable') return 'Durum alınamadı. Kabul edilen metin duruyor.';
  if (status === 'ready') return 'Öneri hazır.';
  if (status === 'failed') return 'Öneri üretilemedi.';
  if (status === 'rejected') return 'Öneri uygulanmadı.';
  if (status === 'timed_out') return 'Süre doldu. Yeni üretim başlatılmadı.';
  if (status === 'queued' || status === 'running' || status === 'pending') return 'Öneri bekleniyor.';
  return 'Durum alınamadı. Kabul edilen metin duruyor.';
}

export function canAccept(
  job: IdentitySuggestionJob | null,
  values: IdentityValues,
  revisions: Record<IdentityField, number>,
  locked: Record<IdentityField, boolean>,
) {
  if (!job || job.status !== 'ready' || !job.suggestion) return false;
  if (locked[job.field]) return false;
  if (revisions[job.field] !== job.revision) return false;
  return values[job.field] === job.baseText;
}

export function applySuggestion(
  values: IdentityValues,
  job: IdentitySuggestionJob | null,
  revisions: Record<IdentityField, number>,
  locked: Record<IdentityField, boolean>,
) {
  if (!canAccept(job, values, revisions, locked) || !job?.suggestion) {
    return { applied: false as const, values };
  }
  return {
    applied: true as const,
    values: { ...values, [job.field]: job.suggestion },
  };
}

export function buildSuggestionRequest(input: {
  draftId: string;
  requestId: string;
  field: IdentityField;
  revision: number;
  values: IdentityValues;
  locked: Record<IdentityField, boolean>;
  allowLockedContext: boolean;
  name?: string;
  species?: string;
  characterClass?: string;
}) {
  const context_fields = IDENTITY_FIELDS.filter((field) => field !== input.field && input.locked[field] && input.allowLockedContext)
    .map((field) => ({
      field,
      text: input.values[field].slice(0, LIMITS[field]),
      locked: true,
      allow_as_context: true,
    }));
  return {
    draft_id: input.draftId,
    request_id: input.requestId,
    field: input.field,
    input_revision: input.revision,
    current_text: input.values[input.field].slice(0, LIMITS[input.field]),
    locked: input.locked[input.field],
    name: input.name || null,
    species: input.species || null,
    character_class: input.characterClass || null,
    context_fields,
  };
}

type RemoteJob = {
  request_id: string;
  draft_id: string;
  field: IdentityField;
  input_revision: number;
  status: IdentitySuggestionJob['status'];
  suggestion?: string | null;
  code?: string | null;
};

export function jobFromRemote(remote: RemoteJob, baseText: string): IdentitySuggestionJob {
  return {
    requestId: remote.request_id,
    draftId: remote.draft_id,
    field: remote.field,
    revision: remote.input_revision,
    baseText,
    status: remote.status,
    suggestion: remote.suggestion ?? null,
    code: remote.code ?? null,
  };
}

export async function submitIdentitySuggestion(
  post: (body: ReturnType<typeof buildSuggestionRequest>) => Promise<RemoteJob>,
  get: (requestId: string) => Promise<RemoteJob>,
  body: ReturnType<typeof buildSuggestionRequest>,
  baseText: string,
  options: { timeoutMs?: number; pollMs?: number } = {},
) {
  const timeoutMs = options.timeoutMs ?? 15000;
  const pollMs = options.pollMs ?? 250;
  const deadline = Date.now() + timeoutMs;
  let known: 'pending' | 'queued' | 'running' = 'pending';
  const unavailable = (): IdentitySuggestionJob => jobFromRemote({
    request_id: body.request_id,
    draft_id: body.draft_id,
    field: body.field,
    input_revision: body.input_revision,
    status: known,
    code: 'status_unavailable',
  }, baseText);
  let remote: RemoteJob;
  try {
    remote = await Promise.race([
      post(body),
      wait(timeoutMs).then(() => {
        throw new Error('timeout');
      }),
    ]);
  } catch {
    try {
      return jobFromRemote(await bounded(get(body.request_id), timeoutMs), baseText);
    } catch {
      return unavailable();
    }
  }
  if (remote.status === 'queued' || remote.status === 'running') known = remote.status;
  while (remote.status === 'queued' || remote.status === 'running') {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      try {
        return jobFromRemote(await bounded(get(body.request_id), timeoutMs), baseText);
      } catch {
        return unavailable();
      }
    }
    await wait(Math.min(pollMs, remaining));
    try {
      remote = await bounded(get(body.request_id), Math.max(1, deadline - Date.now()));
    } catch {
      return unavailable();
    }
  }
  return jobFromRemote(remote, baseText);
}

function bounded<T>(work: Promise<T>, timeoutMs: number): Promise<T> {
  return Promise.race([
    work,
    wait(timeoutMs).then(() => {
      throw new Error('timeout');
    }),
  ]);
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
