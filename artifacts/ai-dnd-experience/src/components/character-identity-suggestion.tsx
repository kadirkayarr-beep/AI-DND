import { useEffect, useRef, useState } from 'react';
import {
  canAccept,
  type IdentityField,
  type IdentitySuggestionJob,
  type IdentityValues,
} from '@/lib/character-identity-suggestion';

const FIELD_LABELS: Record<IdentityField, string> = {
  origin: 'Köken',
  appearance: 'Görünüş',
  personality: 'Kişilik',
  backstory: 'Geçmiş',
};

export function CharacterIdentitySuggestion({
  values,
  revisions,
  locked,
  allowLockedContext,
  activeField,
  job,
  open,
  notice,
  busy,
  onActivate,
  onToggleLock,
  onAllowLockedContext,
  onAsk,
  onAccept,
  onDiscard,
  onDismiss,
  onPoll,
}: {
  values: IdentityValues;
  revisions: Record<IdentityField, number>;
  locked: Record<IdentityField, boolean>;
  allowLockedContext: boolean;
  activeField: IdentityField;
  job: IdentitySuggestionJob | null;
  open: boolean;
  notice: string;
  busy: boolean;
  onActivate: (field: IdentityField) => void;
  onToggleLock: () => void;
  onAllowLockedContext: (value: boolean) => void;
  onAsk: () => void;
  onAccept: () => void;
  onDiscard: () => void;
  onDismiss: () => void;
  onPoll: () => void;
}) {
  const [askedOnce, setAskedOnce] = useState(false);
  const compareRef = useRef<HTMLDivElement>(null);
  const suggestionVisible = open && job?.status === 'ready' && Boolean(job.suggestion);
  useEffect(() => {
    if (suggestionVisible) compareRef.current?.focus();
  }, [suggestionVisible, job?.suggestion]);
  const acceptable = suggestionVisible && canAccept(job, values, revisions, locked);
  const label = FIELD_LABELS[activeField];

  return (
    <div
      className="identity-suggestion"
      data-testid="character-identity-suggestion"
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !open) return;
        event.preventDefault();
        event.stopPropagation();
        onDismiss();
      }}
    >
      <div className="identity-suggestion-targets" role="group" aria-label="Öneri alanı">
        {(Object.keys(FIELD_LABELS) as IdentityField[]).map((field) => (
          <button
            key={field}
            type="button"
            className="identity-suggestion-action"
            aria-pressed={activeField === field}
            onClick={() => onActivate(field)}
          >
            {FIELD_LABELS[field]}
          </button>
        ))}
      </div>
      <div className="identity-suggestion-actions">
        <button
          type="button"
          className="identity-suggestion-action"
          data-testid="identity-suggestion-ask"
          disabled={busy || locked[activeField]}
          onClick={() => {
            setAskedOnce(true);
            onAsk();
          }}
        >
          {askedOnce ? 'Yeni öneri' : `${label} için öneri al`}
        </button>
        <button
          type="button"
          className="identity-suggestion-action"
          aria-pressed={locked[activeField]}
          onClick={onToggleLock}
        >
          {locked[activeField] ? `${label} kilidini aç` : `${label} kilitle`}
        </button>
        <label className="identity-suggestion-context">
          <input
            type="checkbox"
            checked={allowLockedContext}
            onChange={(event) => onAllowLockedContext(event.target.checked)}
          />
          Kilitli metni yalnız bağlam olarak kullan
        </label>
      </div>
      <p className="identity-suggestion-persistence">
        Kabul, macerayı oluşturana kadar bu formdadır. Sayfa yenilenirse form metni de gider.
      </p>
      <p className="identity-suggestion-status" role="status" aria-live="polite">{notice}</p>
      {open && job && (job.status === 'pending' || job.status === 'queued' || job.status === 'running') && (
        <button type="button" className="identity-suggestion-action" onClick={onPoll}>
          Durumu sor
        </button>
      )}
      {suggestionVisible && (
        <div className="identity-suggestion-compare" ref={compareRef} tabIndex={-1} data-testid="identity-suggestion-compare">
          <div>
            <span>Şimdiki metin</span>
            <p>{job?.baseText}</p>
          </div>
          <div>
            <span>Öneri</span>
            <p>{job?.suggestion}</p>
          </div>
        </div>
      )}
      {suggestionVisible && (
        <div className="identity-suggestion-actions">
          {acceptable && (
            <button type="button" className="identity-suggestion-action" data-testid="identity-suggestion-accept" onClick={onAccept}>
              Kabul
            </button>
          )}
          <button type="button" className="identity-suggestion-action" data-testid="identity-suggestion-discard" onClick={onDiscard}>
            Vazgeç
          </button>
        </div>
      )}
    </div>
  );
}
