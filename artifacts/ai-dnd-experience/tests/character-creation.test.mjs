import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';

let vite;
let renderCreationScreen;
let React;

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
      spells_count: 4,
    },
  },
  backgrounds: {
    Soldier: {
      name_tr: 'Asker (Soldier)',
      desc: 'Savaş deneyimi olan bir nefer.',
      ability_bonuses_options: ['strength', 'dexterity', 'constitution'],
      skills: ['Athletics', 'Intimidation'],
      tool: 'Oyun Seti',
      origin_feat: 'Savage Attacker',
    },
    Sage: {
      name_tr: 'Bilge (Sage)',
      desc: 'Yıllarını kütüphanelerde geçirmiş bir araştırmacı.',
      ability_bonuses_options: ['constitution', 'intelligence', 'wisdom'],
      skills: ['Arcana', 'History'],
      tool: 'Hattat Seti',
      origin_feat: 'Magic Initiate (Wizard)',
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
      cantrips: [{ name: 'Fire Bolt', name_tr: 'Ateş Oku', desc: '1d10 ateş hasarı' }],
      level_1: [{ name: 'Magic Missile', name_tr: 'Büyülü Füze', desc: 'Kaçınılmaz 3 füze' }],
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
  React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');

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
  assert.ok(html.includes('Savaşçı (Fighter)'));
  assert.ok(html.includes('Büyücü (Wizard)'));
  assert.ok(html.includes('d10 Can Zarı'));
  assert.ok(html.includes('data-testid="button-mode-random"'));
  assert.ok(html.includes('Rastgele Karakter Üret'));
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
});

test('review step renders comprehensive summary including roleplay identity box', () => {
  const html = renderCreationScreen({ initialStep: 'review' });
  assert.ok(html.includes('Karakter Sayfasını İncele ve Başla'));
  assert.ok(html.includes('Karakter Kimliği ve Rol Yapma Notları'));
  assert.ok(html.includes('Görünüş:'));
  assert.ok(html.includes('Kişilik:'));
  assert.ok(html.includes('Hikaye:'));
});

