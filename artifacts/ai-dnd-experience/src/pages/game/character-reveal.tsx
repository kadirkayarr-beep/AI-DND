import { originFeatLabel } from '@/lib/catalog-display';
import { StartingEquipmentNotice } from '@/components/starting-equipment-notice';
import { PurseLine, StoredProgressionChoices } from '@/components/character-panel';
import {
  ArrowLeft,
  ArrowRight,
} from 'lucide-react';
import { skillLabel } from '@/lib/skill-label';
import type { GameState } from '@workspace/api-client-react';
import { SpellcastingPanel } from '@/components/spellcasting-panel';
import { CampaignDate } from '@/components/campaign-context-panel';
import { classLabel, speciesLabel } from '@/lib/campaign-presentation';
import { OuroborosMark } from '@/components/ouroboros-mark';
import { playGateSound, primeGateSound } from '@/lib/gate-sound';
import classPortraitSheet from '@assets/generated_images/ai-dnd-class-portraits.jpg';
import speciesPortraitSheet from '@assets/generated_images/ai-dnd-species-portraits.jpg';
import halfElfPortrait from '@assets/generated_images/ai-dnd-half-elf-portrait.png';
import { Brand, Kicker, Rule } from '@/pages/game/shell-parts';

function CharacterReveal({ state, catalog, onContinue, onBack }: { state: GameState; catalog?: unknown; onContinue: () => void; onBack: () => void }) {
  const character = state.character;
  const classPortraitCells: Record<string, number> = {
    fighter: 0, barbarian: 1, paladin: 2, ranger: 3, rogue: 4, monk: 5,
    bard: 6, cleric: 7, druid: 8, sorcerer: 9, wizard: 10, warlock: 11,
  };
  const speciesPortraitCells: Record<string, number> = {
    human: 0, elf: 1, dwarf: 2, halfling: 3, dragonborn: 4, gnome: 5,
    'half-orc': 6, tiefling: 7, goliath: 8, aasimar: 9, 'wood elf': 10, orc: 11,
  };
  const classCell = classPortraitCells[character.class.trim().toLowerCase()];
  const speciesCell = speciesPortraitCells[character.race.trim().toLowerCase()];
  const portraitCell = classCell ?? speciesCell;
  const portraitSheet = classCell !== undefined ? classPortraitSheet : speciesPortraitSheet;
  const portraitStyle = classCell === undefined && character.race.trim().toLowerCase() === 'half-elf'
    ? { backgroundImage: `url("${halfElfPortrait}")`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : portraitCell === undefined ? undefined : {
    backgroundImage: `url("${portraitSheet}")`,
    backgroundPosition: `${(portraitCell % 4) * 100 / 3}% ${Math.floor(portraitCell / 4) * 50}%`,
  };
  const abilities = [
    ['KUV', character.strength],
    ['ÇEV', character.dexterity],
    ['DAY', character.constitution],
    ['ZEK', character.intelligence],
    ['BİL', character.wisdom],
    ['KAR', character.charisma],
  ];
  return (
    <main className="reveal-screen gate-fade cinematic-reveal" data-testid="screen-character-reveal">
      <header className="dnd-shell reveal-header">
        <Brand />
        <button type="button" className="text-button reveal-back" onClick={() => { primeGateSound(); playGateSound('page'); onBack(); }} data-testid="button-back-opening">
          <ArrowLeft size={13} /> Geri dön
        </button>
      </header>
      <div className="reveal-wrap">
        <div className="reveal-heading">
          <Kicker>Yeni macera · Yolcu</Kicker>
          <h1 className="dnd-display">Adın artık<br /><em>bir hikâye.</em></h1>
          <p className="dnd-serif">Yolun belli. Dünya henüz seni tanımıyor.</p>
        </div>
        <div className="reveal-card">
          <div className={`reveal-portrait ${portraitStyle ? '' : 'reveal-portrait-neutral'}`} style={portraitStyle} role="img" aria-label={`${character.name} için ${speciesLabel(character.race)} ${classLabel(character.class)} temsili portre`}>
            <div className="portrait-vignette" />
            <div className="portrait-caption"><span>YOLCU PORTRESİ</span><strong>{character.name}</strong><small>Temsili görsel · karakter görünümünü belirlemez</small></div>
            <div className="portrait-insignia" aria-hidden="true"><OuroborosMark /></div>
          </div>
          <div className="reveal-data">
            <div className="reveal-top">
              <div>
                <Kicker>Karakter</Kicker>
                <h2 data-testid="reveal-character-name">{character.name}</h2>
                <div className="character-sub">{speciesLabel(character.race)} {classLabel(character.class)} · Seviye {character.level}</div>
              </div>
              <span className="character-badge">Sv. {character.level}</span>
            </div>
            <StartingEquipmentNotice characterClass={character.class} catalog={catalog} />
            <PurseLine totalCp={state.wallet?.total_cp ?? null} />
            <StoredProgressionChoices character={character} catalog={catalog} />
            {character.origin && (
              <div className="reveal-origin" data-testid="reveal-character-origin">
                <Kicker>Kişisel köken</Kicker>
                <span>{character.origin}</span>
              </div>
            )}
            {(character.origin_feat || character.species_bonus_feat) && (
              <div className="reveal-origin" data-testid="reveal-character-origin-feats">
                <Kicker>Başlangıç hünerleri</Kicker>
                <div className="mt-2 flex flex-wrap gap-2">
                  {character.origin_feat && (
                    <span className="status-pill" data-testid="reveal-background-origin-feat">
                      Geçmiş: {originFeatLabel((catalog as { origin_feats?: unknown } | undefined)?.origin_feats, character.origin_feat)}
                    </span>
                  )}
                  {character.species_bonus_feat && (
                    <span className="status-pill" data-testid="reveal-species-bonus-feat">
                      Tür: {originFeatLabel((catalog as { origin_feats?: unknown } | undefined)?.origin_feats, character.species_bonus_feat)}
                    </span>
                  )}
                </div>
              </div>
            )}
            <Rule />
            <div className="reveal-metrics">
              <div><Kicker>Can</Kicker><strong>{character.current_hp} / {character.max_hp}</strong></div>
              <div><Kicker>Zırh</Kicker><strong>{character.armor_class}</strong></div>
              <div><Kicker>Ustalık</Kicker><strong>+{character.proficiency_bonus}</strong></div>
            </div>
            <p className="subtle-text mt-3"><CampaignDate state={state} /></p>
            <div className="reveal-stats">
              <Kicker>Yetenekler</Kicker>
              <div className="stat-strip">
                {abilities.map(([label, value]) => (
                  <div className="stat-box" key={label}>
                    <Kicker>{label}</Kicker>
                    <div className="stat-value">{value}</div>
                  </div>
                ))}
              </div>
            </div>
            <SpellcastingPanel spellcasting={state.spellcasting} />
            <div className="reveal-skills">
              <Kicker>Usta olunan beceriler</Kicker>
              <div className="mt-3 flex flex-wrap gap-2">
                {character.proficient_skills.length
                  ? character.proficient_skills.map((skill) => <span className="status-pill" key={skill}>{skillLabel(skill)}</span>)
                  : <span className="subtle-text">Henüz bir beceride ustalaşmadın.</span>}
              </div>
            </div>
            {character.species_bonus_skills?.length ? (
              <div className="reveal-skills" data-testid="reveal-species-bonus-skills">
                <Kicker>Tür becerileri</Kicker>
                <div className="mt-3 flex flex-wrap gap-2">
                  {character.species_bonus_skills.map((skill) => (
                    <span className="status-pill" key={skill}>{skillLabel(skill)}</span>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="reveal-actions">
              <span>Bu yolculukta sana adın, geçmişin ve yeteneklerin eşlik edecek.</span>
              <button type="button" className="dnd-button" onClick={() => { primeGateSound(); playGateSound('success'); onContinue(); }} data-testid="button-continue-adventure">
                Macerayı aç <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

export { CharacterReveal };
