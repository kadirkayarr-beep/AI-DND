const METAMAGIC_LABELS: Record<string, string> = {"Careful Spell": "Özenli Büyü", "Distant Spell": "Uzak Büyü", "Empowered Spell": "Güçlendirilmiş Büyü", "Extended Spell": "Uzatılmış Büyü", "Heightened Spell": "Yoğunlaştırılmış Büyü", "Quickened Spell": "Hızlandırılmış Büyü", "Seeking Spell": "Arayıcı Büyü", "Subtle Spell": "Gizli Büyü", "Transmuted Spell": "Dönüştürülmüş Büyü", "Twinned Spell": "İkiz Büyü"};

import type { ReactNode } from 'react';
import { Backpack, Heart } from 'lucide-react';
import type { GameCharacter } from '@workspace/api-client-react';
import { RageStatus } from '@/components/rage-controls';
import { FighterStatus } from '@/components/fighter-controls';
import { PaladinStatus } from '@/components/paladin-controls';
import { RogueStatus } from '@/components/rogue-controls';
import { MonkStatus } from '@/components/monk-controls';
import { skillLabel } from '@/lib/skill-label';
import { inventoryDisplay } from '@/lib/inventory-display';
import { CharacterIdentityNotes } from '@/components/character-identity-notes';
import { classLabel, speciesLabel } from '@/lib/campaign-presentation';
import { coinText } from '@/lib/coins';
import { subclassCatalogName } from '@/lib/catalog-display';

function Kicker({ children }: { children: ReactNode }) {
  return <div className="dnd-kicker">{children}</div>;
}

/** The purse as the wallet says it; not a number: nothing. */
export function PurseLine({ totalCp }: { totalCp?: number | null }) {
  if (typeof totalCp !== 'number') return null;
  return <div className="data-row mt-3" data-testid="text-character-purse">{`Kese: ${coinText(totalCp)}`}</div>;
}

export function StoredProgressionChoices({ character, catalog }: { character: GameCharacter; catalog?: unknown }) {
  const subclassName = subclassCatalogName(catalog, character.class, character.subclass_id);
  // A raw subclass identifier is not a player-facing catalog name.
  return <>{character.metamagic?.length ? <p>Üstbüyü seçimleri: {character.metamagic.map(id => METAMAGIC_LABELS[id] ?? id).join(', ')}</p> : null}{character.subclass_id && subclassName?.trim() ? <p>Alt sınıf: {subclassName}</p> : null}</>;
}

export function CharacterPanel({ character, compact = false, walletTotalCp, catalog }: { character: GameCharacter; compact?: boolean; walletTotalCp?: number | null; catalog?: unknown }) {
  const abilities = [['KUV', character.strength], ['ÇEV', character.dexterity], ['DAY', character.constitution], ['ZEK', character.intelligence], ['BİL', character.wisdom], ['KAR', character.charisma]];
  const hp = character.max_hp > 0 ? Math.max(0, Math.min(100, character.current_hp / character.max_hp * 100)) : 0;
  return (
    <section className={`state-panel ${compact ? 'compact-character' : ''}`} data-testid="panel-character">
      <div className="character-top"><div><Kicker>Yolcu kaydı</Kicker><h2 data-testid="text-character-name">{character.name}</h2><div className="character-sub">{speciesLabel(character.race)} {classLabel(character.class)} · Seviye {character.level}</div></div><span className="character-badge">Sv. {character.level}</span></div>
      <div className="health-row"><span className="flex items-center gap-2"><Heart size={13} /> Can durumu</span><span data-testid="text-character-hp">{character.current_hp} / {character.max_hp}</span></div>
      <div className="health-track"><div className="health-fill" style={{ width: `${hp}%` }} data-testid="meter-health" /></div>
      <div className="key-values"><div className="key-value"><Kicker>ZIRH</Kicker><span>{character.armor_class}</span></div><div className="key-value"><Kicker>USTALIK</Kicker><span>+{character.proficiency_bonus}</span></div></div>
      <div className="data-row mt-3" data-testid="text-character-xp">Deneyim: {character.xp}</div>
      <PurseLine totalCp={walletTotalCp} />
      {!compact && <div className="mt-5"><Kicker>Yetenekler</Kicker><div className="stat-strip">{abilities.map(([label, value]) => <div className="stat-box" key={label}><Kicker>{label}</Kicker><div className="stat-value">{value}</div></div>)}</div></div>}
      {!compact && <div className="mt-5 border-t border-(color:--unw-border) pt-4"><Kicker>Usta olunan beceriler</Kicker><div className="mt-3 flex flex-wrap gap-2">{character.proficient_skills.length ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skillLabel(skill)}</span>) : <span className="subtle-text">Henüz bir beceride ustalaşmadın.</span>}</div></div>}
      <RageStatus rage={character.rage} />
      <FighterStatus fighter={character.fighter} />
      <PaladinStatus paladin={character.paladin} />
      <RogueStatus rogue={character.rogue} />
      <MonkStatus monk={character.monk} />
      <StoredProgressionChoices character={character} catalog={catalog} />
      <CharacterIdentityNotes character={character} />
    </section>
  );
}

export function InventoryPanel({ items }: { items: string[] }) {
  return <section className="state-panel" data-testid="panel-inventory"><div className="flex items-end justify-between"><div><Kicker>Üzerinde</Kicker><h2>Envanter</h2></div><span className="character-badge">{String(items.length).padStart(2, '0')}</span></div>{items.length ? <div className="list-stack">{items.map((item, index) => { const display = inventoryDisplay(item); return <div className="list-row" key={`${item}-${index}`} data-testid={`item-inventory-${index}`}><span className="list-icon"><Backpack size={14} /></span><span>{display.name}</span>{display.equipped && <small className="status-pill">kuşanılmış</small>}</div>; })}</div> : <div className="empty-line mt-4">Çantada kaydedilmiş eşya yok.</div>}</section>;
}
