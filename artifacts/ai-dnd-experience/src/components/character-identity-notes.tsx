import type { GameCharacter } from '@workspace/api-client-react';

const IDENTITY_FIELDS = [
  ['origin', 'Köken'],
  ['appearance', 'Görünüş'],
  ['personality', 'Kişilik'],
  ['backstory', 'Geçmiş'],
] as const;

type IdentityCharacter = Pick<GameCharacter, 'origin' | 'appearance' | 'personality' | 'backstory'>;

export function CharacterIdentityNotes({ character }: { character: IdentityCharacter }) {
  return (
    <div className="identity-notes" data-testid="character-identity-notes">
      <div className="dnd-kicker">Kimlik</div>
      {IDENTITY_FIELDS.map(([field, label]) => {
        const value = character[field];
        const missing = value == null;
        return (
          <div className="identity-note" key={field} data-testid={`character-identity-${field}`} data-state={missing ? 'missing' : value === '' ? 'empty' : 'present'}>
            <span className="identity-note-label">{label}</span>
            <p className="identity-note-text">{missing ? 'Kayıtta yok' : value}</p>
          </div>
        );
      })}
    </div>
  );
}
