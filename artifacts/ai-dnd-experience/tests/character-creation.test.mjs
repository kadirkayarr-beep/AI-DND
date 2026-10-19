import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';

let vite;
let renderCreationScreen;
let renderSpellSelectionHeading;
let React;
let catalogNormalizer;
let characterPreview;
let defaultCatalog;

const mockCatalog = {
  races: {
    Human: { name_tr: 'İnsan (Human)', speed: '9 metre (30 ft)', darkvision: 'Yok', traits: ['Yetenekli', 'Çok Yönlü'] },
    Elf: { name_tr: 'Elf', speed: '9 metre (30 ft)', darkvision: '18 metre (60 ft)', traits: ['Elf Soyu', 'Keskin Duyular'] },
  },
  classes: {
    Fighter: {
      name_tr: 'Savaşçı (Fighter)',
      hit_die: 10,
      primary_ability: 'strength',
      skill_count: 2,
      skill_options: ['Athletics', 'Intimidation', 'Perception', 'Survival'],
      features: ['İkinci Soluk', 'Dövüş Tarzı'],
      is_spellcaster: false,
      equipment_packages: [
        { id: 'A', label: 'Zincir Zırh Paketi', items: ['Zincir Zırh', 'Kalkan', 'Uzun Kılıç'] },
      ],
    },
    Wizard: {
      name_tr: 'Büyücü (Wizard)',
      hit_die: 6,
      primary_ability: 'intelligence',
      skill_count: 2,
      skill_options: ['Arcana', 'History', 'Investigation'],
      features: ['Büyü Kitabı', 'Ritüel Büyücülük'],
      is_spellcaster: true,
      cantrips_count: 3,
      spells_count: 6,
    },
  },
  backgrounds: {
    Soldier: {
      name_tr: 'Asker (Soldier)',
      desc: 'Savaş deneyimi olan bir nefer.',
      abilities: ['strength', 'dexterity', 'constitution'],
      skills: ['Athletics', 'Intimidation'],
      tool: 'Oyun Seti',
      feat: 'Savage Attacker',
    },
    Sage: {
      name_tr: 'Bilge (Sage)',
      desc: 'Yıllarını kütüphanelerde geçirmiş bir araştırmacı.',
      abilities: ['constitution', 'intelligence', 'wisdom'],
      skills: ['Arcana', 'History'],
      tool: 'Hattat Seti',
      feat: 'Magic Initiate (Wizard)',
    },
  },
  ability_score_methods: [
    { id: 'standard_array', name_tr: 'Standart Dizi' },
    { id: 'point_buy', name_tr: 'Puan Satın Alma' },
    { id: 'rolled', name_tr: 'Zar Atma' },
  ],
  alignments: [
    { id: 'Lawful Good', name_tr: 'Hukuka Bağlı İyi' },
    { id: 'Neutral Good', name_tr: 'Tarafsız İyi' },
  ],
  origin_feats: {},
  spells_catalog: {
    Wizard: {
      cantrips: [
        { id: 'Fire Bolt', name_tr: 'Ateş Oku', desc: '1d10 ateş hasarı' },
        { id: 'Ray of Frost', name_tr: 'Buz Işını', desc: '1d8 soğuk hasarı' },
        { id: 'Mage Hand', name_tr: 'Büyücü Eli', desc: 'Uzakta nesne taşıyan el' },
      ],
      spells_level_1: [
        { id: 'Magic Missile', name_tr: 'Büyülü Füze', desc: 'Üç büyü oku fırlatır' },
        { id: 'Shield', name_tr: 'Kalkan', desc: 'Tepki olarak zırh sınıfını artırır' },
        { id: 'Mage Armor', name_tr: 'Büyücü Zırhı', desc: 'Zırhsız hedefin zırh sınıfını artırır' },
        { id: 'Detect Magic', name_tr: 'Büyü Algılama', desc: 'Yakındaki büyüleri hissettirir' },
        { id: 'Sleep', name_tr: 'Uyku', desc: 'Hedefleri büyülü uykuya daldırır' },
        { id: 'Burning Hands', name_tr: 'Alevli Eller', desc: 'Bir koniye ateş hasarı saçar' },
      ],
    },
  },
  skills: {
    Athletics: { ability: 'strength', name_tr: 'Atletizm' },
  },
};

const mockStartOptions = {
  settings: [
    {
      setting_id: 'forgotten_realms',
      name: 'Unutulmuş Diyarlar (Forgotten Realms)',
      regions: [
        {
          region_pack_id: 'sword_coast',
          region_id: 'sword_coast',
          name: 'Kılıç Sahili (Sword Coast)',
          epoch_id: '1492_dr',
          coverage_status: 'VERIFIED_CANONICAL',
          starting_locations: [
            { entity_id: 'neverwinter', name: 'Neverwinter' },
          ],
        },
      ],
    },
  ],
};

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  const component = await vite.ssrLoadModule('/src/components/character-creation-screen.tsx');
  const catalogDefaults = await vite.ssrLoadModule('/src/lib/character-catalog-defaults.ts');
  catalogNormalizer = await vite.ssrLoadModule('/src/lib/character-catalog-normalizer.ts');
  characterPreview = await vite.ssrLoadModule('/src/lib/character-preview-stats.ts');
  defaultCatalog = catalogDefaults.DEFAULT_CATALOG;
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');

  renderSpellSelectionHeading = (props) => renderToStaticMarkup(React.createElement(component.SpellSelectionHeading, props));

  renderCreationScreen = (props = {}) => renderToStaticMarkup(
    React.createElement(component.CharacterCreationScreen, {
      catalog: mockCatalog,
      startOptions: mockStartOptions,
      loadingOptions: false,
      loadingStartOptions: false,
      optionsError: null,
      startOptionsError: null,
      creating: false,
      notice: null,
      onBack: () => {},
      onCreate: () => {},
      onRetryOptions: () => {},
      onRetryStartOptions: () => {},
      ...props,
    }),
  );
});

after(async () => {
  if (vite) await vite.close();
});

test('character creation screen renders all 8 progression steps and navigation controls', () => {
  const html = renderCreationScreen();
  assert.ok(html.includes('data-testid="screen-character-creation"'));
  assert.ok(html.includes('1. Sınıf'));
  assert.ok(html.includes('2. Geçmiş'));
  assert.ok(html.includes('3. Tür'));
  assert.ok(html.includes('4. Yetenekler'));
  assert.ok(html.includes('5. Beceriler &amp; Büyü') || html.includes('5. Beceriler & Büyü'));
  assert.ok(html.includes('6. Ekipman'));
  assert.ok(html.includes('7. Kimlik'));
  assert.ok(html.includes('8. Karakter Sayfası'));
  assert.ok(html.includes('Karakterini Yarat.'));
});

test('presents genuine player choices for class, species, background, and alignment', () => {
  const html = renderCreationScreen();
  assert.ok(html.includes('>Savaşçı<'));
  assert.ok(html.includes('>Sihirbaz<'));
  assert.ok(!html.includes('Savaşçı (Fighter)'));
  assert.ok(!html.includes('Büyücü (Wizard)'));
  assert.ok(html.includes('value="Fighter"'));
  assert.ok(html.includes('value="Wizard"'));
  assert.ok(html.includes('d10 Can Zarı'));
  assert.ok(html.includes('data-testid="button-mode-random"'));
  assert.ok(html.includes('Rastgele Karakterle Macera Oluştur'));
});

test('species cards render API-shaped trait objects without passing objects to React', () => {
  const description = 'Uzun dinlenme sonrası Kahramanca İlham kazanırsın.';
  const html = renderCreationScreen({
    initialStep: 'species',
    catalog: {
      ...mockCatalog,
      races: {
        Human: {
          ...mockCatalog.races.Human,
          traits: [
            { name: 'Azimli', desc: description },
            'Eski biçimli özellik',
          ],
        },
      },
    },
  });

  assert.ok(html.includes('Azimli'));
  assert.ok(html.includes(description));
  assert.ok(html.includes('Eski biçimli özellik'));
  assert.ok(!html.includes('[object Object]'));
});

test('species picker shows 2024 additions and retains the 2014 Half species with source labels', () => {
  const html = renderCreationScreen({
    initialStep: 'species',
    catalog: defaultCatalog,
  });

  assert.ok(html.includes('Göksoylu (Aasimar)'));
  assert.ok(html.includes('Devsoylu (Goliath)'));
  assert.ok(html.includes('Ork (Orc)'));
  assert.ok(html.includes('Yarı-Elf (Half-Elf)'));
  assert.ok(html.includes('Yarı-Ork (Half-Orc)'));
  assert.ok(html.includes('D&amp;D 2024 PHB'));
  assert.equal((html.match(/D&amp;D 2014 · Eski seçenek/g) ?? []).length, 2);
  assert.ok(html.includes('Göksel Tecelli (Celestial Revelation)'));
  assert.ok(html.includes('Adrenalin Patlaması (Adrenaline Rush)'));
});

test('normalizes server catalog fields and keeps spell selection keyed by unique IDs', () => {
  const normalized = catalogNormalizer.normalizeCharacterCreationCatalog({
    backgrounds: {
      Noble: {
        abilities: ['strength', 'intelligence', 'charisma'],
        feat: 'Skilled',
      },
    },
    spells_catalog: {
      Sorcerer: {
        cantrips: [
          { id: 'Fire Bolt', name_tr: 'Ateş Oku' },
          { id: 'Ray of Frost', name_tr: 'Buz Işını' },
          { id: 'Mage Hand', name_tr: 'Büyücü Eli' },
        ],
        spells_level_1: [{ id: 'Magic Missile', name_tr: 'Sihirli Füze' }],
      },
    },
  });

  assert.deepEqual(
    normalized.backgrounds.Noble.ability_bonuses_options,
    ['strength', 'intelligence', 'charisma'],
  );
  assert.equal(normalized.backgrounds.Noble.origin_feat, 'Skilled');
  assert.deepEqual(
    normalized.spells_catalog.Sorcerer.level_1.map((spell) => spell.id),
    ['Magic Missile'],
  );

  const cantrips = normalized.spells_catalog.Sorcerer.cantrips;
  const chosenId = catalogNormalizer.getSpellOptionId(cantrips[0]);
  assert.equal(chosenId, 'Fire Bolt');
  const selected = catalogNormalizer.updateLimitedSelection([], chosenId, true, 4);
  assert.deepEqual(selected, ['Fire Bolt']);
  assert.equal(
    cantrips.filter((spell) =>
      selected.includes(catalogNormalizer.getSpellOptionId(spell)),
    ).length,
    1,
  );
});

test('species bonus skill selections stay separate from class skills', () => {
  const {
    getClassSkillOptions,
    getRequiredSkillCount,
    getSpeciesBonusSkillCount,
    getSpeciesBonusSkillOptions,
  } = catalogNormalizer;
  const skillCatalog = {
    Arcana: { ability: 'intelligence' },
    Nature: { ability: 'intelligence' },
    Perception: { ability: 'wisdom' },
  };

  assert.equal(getRequiredSkillCount(2), 2);
  assert.equal(getSpeciesBonusSkillCount({ skill_bonus_count: 1 }), 1);
  assert.equal(getSpeciesBonusSkillCount({ skill_bonus_count: 2 }), 2);
  assert.deepEqual(getClassSkillOptions(['Arcana', 'Arcana']), ['Arcana']);
  assert.deepEqual(
    getSpeciesBonusSkillOptions(skillCatalog, 2),
    ['Arcana', 'Nature', 'Perception'],
  );
  assert.deepEqual(getSpeciesBonusSkillOptions(skillCatalog, 0), []);
});

test('Expertise choices follow each class and level progression', () => {
  const { getExpertiseChoiceCount } = catalogNormalizer;
  assert.equal(
    getExpertiseChoiceCount(defaultCatalog.classes.Rogue.expertise_progression, 1),
    2,
  );
  assert.equal(
    getExpertiseChoiceCount(defaultCatalog.classes.Rogue.expertise_progression, 5),
    2,
  );
  assert.equal(
    getExpertiseChoiceCount(defaultCatalog.classes.Rogue.expertise_progression, 6),
    4,
  );
  assert.equal(
    getExpertiseChoiceCount(defaultCatalog.classes.Bard.expertise_progression, 1),
    0,
  );
  assert.equal(
    getExpertiseChoiceCount(defaultCatalog.classes.Bard.expertise_progression, 2),
    2,
  );
  assert.equal(getExpertiseChoiceCount(undefined, 1), 0);
});

test('species bonus feat options exclude the background feat base name', () => {
  const options = catalogNormalizer.getOriginFeatOptions(
    {
      'Magic Initiate': { name_tr: 'Büyüye Giriş', desc: 'Choose spells.' },
      Tough: { name_tr: 'Sağlam', desc: 'Gain hit points.' },
    },
    'Magic Initiate (Wizard)',
  );

  assert.deepEqual(options, [
    { id: 'Tough', label: 'Sağlam', description: 'Gain hit points.' },
  ]);
});

test('Fighter style options come from the complete class rules catalog', () => {
  const styles = catalogNormalizer.getFightingStyleOptions({
    fighting_styles: [
      { id: 'Archery', name_tr: 'Okçuluk' },
      { id: 'Defense', name_tr: 'Savunma' },
      { id: 'Dueling', name_tr: 'Düello' },
      { id: 'Great Weapon Fighting', name_tr: 'Büyük Silah Dövüşü' },
      { id: 'Protection', name_tr: 'Koruma' },
      { id: 'Two-Weapon Fighting', name_tr: 'Çift Silah Dövüşü' },
    ],
  });

  assert.equal(styles.length, 6);
  assert.ok(styles.some((style) => style.id === 'Protection' && style.label === 'Koruma'));
});

test('HP and AC previews follow package, armor, shield, Defense, Dwarf, and Tough rules', () => {
  const classData = {
    hit_die: 10,
    equipment_packages: [
      { id: 'A', items: ['Zincir Zırh', 'Kalkan'] },
      { id: 'B', items: ['Deri Zırh'] },
      { id: 'C', items: ['Büyük Kılıç'] },
    ],
  };
  const scores = {
    strength: 12,
    dexterity: 16,
    constitution: 14,
    intelligence: 10,
    wisdom: 10,
    charisma: 10,
  };
  const preview = (equipmentPackage, backgroundData = { equipment: [] }, options = {}) =>
    characterPreview.calculateCharacterPreviewStats({
      characterClass: 'Fighter',
      classData,
      speciesData: { hp_bonus: 0 },
      backgroundData,
      abilityScores: scores,
      equipmentPackage,
      backgroundEquipmentOption: 'B',
      fightingStyle: 'Defense',
      originFeats: { Tough: { hp_bonus: 2 } },
      equipmentRules: characterPreview.DEFAULT_EQUIPMENT_RULES,
      ...options,
    });

  assert.deepEqual(
    ['A', 'B', 'C'].map((packageId) => preview(packageId).ac),
    [19, 15, 13],
  );
  assert.equal(preview('A').hasShield, true);

  const backgroundArmor = preview(
    'C',
    { equipment: ['Pul Zırh', 'Ahşap Kalkan'] },
    { backgroundEquipmentOption: 'A' },
  );
  assert.equal(backgroundArmor.ac, 19);
  assert.equal(backgroundArmor.equippedArmor, 'Scale Mail');

  const dwarfWithTough = preview(
    'A',
    { equipment: [], origin_feat: 'Tough' },
    {
      speciesData: { hp_bonus: 1 },
      speciesBonusFeat: 'Tough',
    },
  );
  assert.equal(dwarfWithTough.hp, 15);
});

test('review does not invent Tough when a background feat is missing', () => {
  const html = renderCreationScreen({ initialStep: 'review' });
  assert.ok(html.includes('Geçmiş Hüneri: Seçilmedi'));
  assert.ok(!html.includes('Köken Hüneri: Tough'));
});

test('background cards render the server ability and feat fields', () => {
  const html = renderCreationScreen({ initialStep: 'background' });
  assert.ok(html.includes('Hüner: Savage Attacker'));
  assert.ok(html.includes('Bonus Alanları: KUV / ÇEV / DAY'));
  assert.ok(!html.includes('Hüner: undefined'));
});

test('never exposes developer terminology or internal server jargon in normal player UI', () => {
  const html = renderCreationScreen();
  assert.ok(!html.includes('Python motoru'));
  assert.ok(!html.includes('motor seçecek'));
  assert.ok(!html.includes('motor seçti'));
  assert.ok(!html.includes('backend'));
  assert.ok(!html.includes('Qwen'));
  assert.ok(!html.includes('kanonik kayıt'));
});

test('starting location options are bound to canonical verified regions', () => {
  const html = renderCreationScreen({ initialStep: 'identity' });
  assert.ok(html.includes('Neverwinter'));
  assert.ok(html.includes('Kılıç Sahili (Sword Coast)'));
});

test('initial state contains zero silent preselected choices and blocks progression', () => {
  const html = renderCreationScreen();
  // No preselected character name or defaults
  assert.ok(!html.includes('value="Cedric"'));
  assert.ok(!html.includes('cc-choice-card selected'));
  // Forward progression button is disabled and displays player-facing guidance
  assert.ok(html.includes('disabled=""') || html.includes('disabled'));
  assert.ok(html.includes('İlerlemek için bir sınıf seçin.'));
});

test('identity step exposes player-owned appearance, personality, and backstory fields', () => {
  const html = renderCreationScreen({ initialStep: 'identity' });
  assert.ok(html.includes('data-testid="input-character-name"'));
  assert.ok(html.includes('data-testid="input-character-appearance"'));
  assert.ok(html.includes('data-testid="input-character-personality"'));
  assert.ok(html.includes('data-testid="input-character-backstory"'));
  assert.ok(html.includes('-- Ahlaki Yönelim Seçiniz --'));
  assert.ok(html.includes('-- 1. Ek Dil Seçin --'));
  assert.ok(html.includes('>Hukuka Bağlı İyi<'));
  assert.ok(html.includes('value="Lawful Good"'));
  assert.ok(!html.includes('(Lawful Good)'));
  assert.ok(!html.includes('(Alignment)'));
  assert.ok(!html.includes('(Appearance)'));
  assert.ok(html.includes('>Dwarvish<'));
});

test('review step renders comprehensive summary including roleplay identity box', () => {
  const html = renderCreationScreen({ initialStep: 'review' });
  assert.ok(html.includes('Karakter Sayfasını İncele ve Başla'));
  assert.ok(html.includes('Karakter Kimliği ve Rol Yapma Notları'));
  assert.ok(html.includes('Görünüş:'));
  assert.ok(html.includes('Kişilik:'));
  assert.ok(html.includes('Hikaye:'));
  assert.ok(html.includes('>Ortak Dil<'));
  assert.ok(!html.includes('>Common<'));
});



test('Wizard keeps six spellbook choices without claiming prepared or usable access', () => {
  const requiredCount = mockCatalog.classes.Wizard.spells_count;
  assert.equal(requiredCount, 6);
  const html = renderSpellSelectionHeading({ characterClass: 'Wizard', selectedCount: 6, requiredCount });
  assert.ok(html.includes('Büyü Kitabına Eklenen 1. Seviye Büyüler (6 / 6 Seçildi)'));
  assert.ok(html.includes('büyü hazırlama ve 1. seviye büyü yapma henüz açık değil'));
  assert.ok(html.includes('Sihirbaz için'));
  assert.ok(!html.includes('Wizard için'));
  assert.ok(!html.includes('1. Seviye Hazırlanan Büyüler'));
  assert.ok(!html.includes('Büyü yuvası harcayarak yapılan güçlü büyüler.'));
});

test('Cleric and Druid selections explicitly confer no prepared or slot-casting access', () => {
  for (const characterClass of ['Cleric', 'Druid']) {
    const html = renderSpellSelectionHeading({ characterClass, selectedCount: 2, requiredCount: 2 });
    assert.ok(html.includes('1. Seviye Büyü Seçimleri (2 / 2 Seçildi)'));
    assert.ok(html.includes('hazırlanmış büyü sayılmaz'));
    assert.ok(html.includes('yuva harcayarak kullanılamaz'));
    assert.ok(!html.includes('1. Seviye Hazırlanan Büyüler'));
    assert.ok(!html.includes('Büyü yuvası harcayarak yapılan güçlü büyüler.'));
  }
});

test('other caster selection headings and counts retain their existing presentation', () => {
  for (const characterClass of ['Sorcerer', 'Warlock', 'Bard', 'Paladin', 'Ranger']) {
    const html = renderSpellSelectionHeading({ characterClass, selectedCount: 1, requiredCount: 2 });
    assert.ok(html.includes('1. Seviye Hazırlanan Büyüler (1 / 2 Seçildi)'));
    assert.ok(html.includes('Büyü yuvası harcayarak yapılan güçlü büyüler.'));
    assert.ok(!html.includes('henüz açık değil'));
    assert.ok(!html.includes('kullanılamaz'));
  }
});


test('Half-Elf uses its own portrait while other species keep atlas and unknown fallback', () => {
  const html = renderCreationScreen({ initialStep: 'species', catalog: {
    ...defaultCatalog,
    races: { ...defaultCatalog.races, Unknown: { name_tr: 'Unknown portrait fixture' } },
  } });
  function portraitPrefix(label) {
    const index = html.indexOf(label);
    assert.ok(index >= 0, label);
    const start = html.lastIndexOf('class="cc-choice-card', index);
    assert.ok(start >= 0);
    return html.slice(start, index);
  }
  const halfElf = portraitPrefix('Yarı-Elf (Half-Elf)');
  assert.ok(halfElf.includes('ai-dnd-half-elf-portrait.png'));
  assert.ok(halfElf.includes('background-size:cover'));
  assert.ok(halfElf.includes('background-position:center'));
  assert.ok(!halfElf.includes('cc-portrait-neutral'));
  assert.ok(!halfElf.includes('ai-dnd-species-portraits.jpg'));
  const elf = portraitPrefix(defaultCatalog.races.Elf.name_tr);
  assert.ok(elf.includes('ai-dnd-species-portraits.jpg'));
  assert.ok(!elf.includes('ai-dnd-half-elf-portrait.png'));
  assert.ok(portraitPrefix('Unknown portrait fixture').includes('cc-portrait-neutral'));
});

 test('random creation visibly explains immediate campaign saving, not preview', () => {
  const html = renderCreationScreen();
  assert.match(html, /Rastgele bir karakter seçilir ve yeni macera kaydedilir/);
  assert.match(html, /aria-describedby="random-creation-help"/);
  assert.doesNotMatch(html, /önizlemeye aç/);
});

test('class cards use shared presentation labels and keep class ids', () => {
  const html = renderCreationScreen({
    catalog: {
      ...mockCatalog,
      classes: {
        ...mockCatalog.classes,
        Rogue: { name_tr: 'Hırsız (Rogue)', hit_die: 8, primary_ability: 'dexterity', features: [], is_spellcaster: false },
        Sorcerer: { name_tr: 'Büyücü (Sorcerer)', hit_die: 6, primary_ability: 'charisma', features: [], is_spellcaster: true },
      },
    },
  });
  assert.ok(html.includes('>Sihirbaz<'));
  assert.ok(html.includes('>Düzenbaz<'));
  assert.ok(html.includes('>Büyücü<'));
  assert.ok(!html.includes('Büyücü (Wizard)'));
  assert.ok(!html.includes('Hırsız (Rogue)'));
  assert.ok(!html.includes('Büyücü (Sorcerer)'));
  assert.ok(html.includes('value="Wizard"'));
  assert.ok(html.includes('value="Rogue"'));
  assert.ok(html.includes('value="Sorcerer"'));
});

test('background cards show existing Turkish skill names without translating unknown tools', () => {
  const html = renderCreationScreen({ initialStep: 'background', catalog: defaultCatalog });
  assert.ok(html.includes('Beceriler: Sezgi, Din'));
  assert.ok(html.includes("Araç: Calligrapher&#x27;s Supplies") || html.includes("Araç: Calligrapher's Supplies"));
  assert.ok(html.includes('Hüner: Magic Initiate (Cleric)'));
  assert.ok(!html.includes('Origin Background'));
  assert.ok(!html.includes('Beceriler: Insight, Religion'));
});
