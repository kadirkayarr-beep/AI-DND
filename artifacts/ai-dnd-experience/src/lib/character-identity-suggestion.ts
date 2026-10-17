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

function asJob(remote: RemoteJob, baseText: string): IdentitySuggestionJob {
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
      return asJob(await get(body.request_id), baseText);
    } catch {
      return asJob({
        request_id: body.request_id,
        draft_id: body.draft_id,
        field: body.field,
        input_revision: body.input_revision,
        status: 'failed',
        code: 'status_unavailable',
      }, baseText);
    }
  }
  while (remote.status === 'queued' || remote.status === 'running') {
    if (Date.now() >= deadline) {
      try {
        return asJob(await get(body.request_id), baseText);
      } catch {
        return asJob({ ...remote, status: 'failed', code: 'status_unavailable' }, baseText);
      }
    }
    await wait(pollMs);
    remote = await get(body.request_id);
  }
  return asJob(remote, baseText);
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
