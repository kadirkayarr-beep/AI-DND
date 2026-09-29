import { useEffect, useState, type FormEvent } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  Compass,
  Feather,
  RefreshCw,
  ScrollText,
  Shield,
  Sparkles,
} from 'lucide-react';
import type {
  CampaignStartOptionsResponse,
  CampaignStartSelection,
  CharacterCreateInput,
  CharacterCreationOptions,
} from '@workspace/api-client-react';
import './character-creation-screen.css';

type Notice = { tone: 'error' | 'success' | 'warning'; title: string; detail: string };

type CharacterCreationScreenProps = {
  options?: CharacterCreationOptions;
  startOptions?: CampaignStartOptionsResponse;
  loadingOptions: boolean;
  loadingStartOptions: boolean;
  optionsError: unknown;
  startOptionsError: unknown;
  creating: boolean;
  notice: Notice | null;
  onBack: () => void;
  onCreate: (character: CharacterCreateInput, campaignStart: CampaignStartSelection) => void;
  onRetryOptions: () => void;
  onRetryStartOptions: () => void;
};

const abilityLabels = ['KUV', 'ÇEV', 'DAY', 'ZEK', 'BİL', 'KAR'];

export function CharacterCreationScreen({
  options,
  startOptions,
  loadingOptions,
  loadingStartOptions,
  optionsError,
  startOptionsError,
  creating,
  notice,
  onBack,
  onCreate,
  onRetryOptions,
  onRetryStartOptions,
}: CharacterCreationScreenProps) {
  const [mode, setMode] = useState<'custom' | 'random'>('custom');
  const [name, setName] = useState('Cedric');
  const [race, setRace] = useState('Elf');
  const [characterClass, setCharacterClass] = useState('Wizard');
  const [settingId, setSettingId] = useState('');
  const [regionPackId, setRegionPackId] = useState('');
  const [startingLocationId, setStartingLocationId] = useState('');
  const hasOptions = Boolean(options?.races.length && options.classes.length);
  const settings = startOptions?.settings ?? [];
  const selectedSetting = settings.find((item) => item.setting_id === settingId) ?? settings[0];
  const selectedRegion = selectedSetting?.regions.find(
    (item) => item.region_pack_id === regionPackId,
  ) ?? selectedSetting?.regions[0];
  const selectedLocation = selectedRegion?.starting_locations.find(
    (item) => item.entity_id === startingLocationId,
  ) ?? selectedRegion?.starting_locations[0];
  const hasCampaignStart = Boolean(selectedSetting && selectedRegion && selectedLocation);

  useEffect(() => {
    if (!options) return;
    if (!options.races.includes(race)) setRace(options.races[0] ?? '');
    if (!options.classes.includes(characterClass)) setCharacterClass(options.classes[0] ?? '');
  }, [characterClass, options, race]);

  useEffect(() => {
    if (selectedSetting && selectedSetting.setting_id !== settingId) {
      setSettingId(selectedSetting.setting_id);
    }
    if (selectedRegion && selectedRegion.region_pack_id !== regionPackId) {
      setRegionPackId(selectedRegion.region_pack_id);
    }
    if (selectedLocation && selectedLocation.entity_id !== startingLocationId) {
      setStartingLocationId(selectedLocation.entity_id);
    }
  }, [
    regionPackId,
    selectedLocation,
    selectedRegion,
    selectedSetting,
    settingId,
    startingLocationId,
  ]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasOptions || !hasCampaignStart || !selectedSetting || !selectedRegion || !selectedLocation || creating) return;
    const campaignStart: CampaignStartSelection = {
      setting_id: selectedSetting.setting_id,
      region_pack_id: selectedRegion.region_pack_id,
      region_id: selectedRegion.region_id,
      starting_location_id: selectedLocation.entity_id,
    };
    if (mode === 'random') {
      onCreate({ mode: 'random' }, campaignStart);
      return;
    }
    onCreate({ mode: 'custom', name: name.trim(), race, class: characterClass }, campaignStart);
  };

  const skillCount = characterClass === 'Rogue' ? 4 : 2;

  return (
    <main className="character-creation-screen dnd-frame dnd-creation" data-testid="screen-character-creation">
      <div className="cc-shell">
        <header className="cc-header">
          <div className="cc-brand" aria-label="AI Dungeon Master">
            <span className="cc-brand-mark"><Compass size={17} strokeWidth={1.3} /></span>
            <span><strong>AI DUNGEON MASTER</strong><small>Solo campaign · {selectedRegion?.name ?? 'Kanonik başlangıç yeri'}</small></span>
          </div>
          <div className="cc-header-caption"><span /> <span>Gün ışığında karakter kaydı</span></div>
          <button type="button" className="cc-back" onClick={onBack} data-testid="button-back-character-creation">
            <ArrowLeft size={13} /> Geri dön
          </button>
        </header>

        <section className="cc-content">
          <div className="cc-intro">
            <div>
              <div className="cc-label">Yeni macera · Karakter kaydı</div>
              <h1 className="cc-display">Sayfayı aç.</h1>
              <p className="cc-literary">Bir yolcu, bir isim ve ilk adım.</p>
            </div>
            <div className="cc-draft-mark"><ScrollText size={15} /><span>Motor kayıtlı seçimler</span></div>
          </div>

          <form className="cc-card" onSubmit={submit}>
            <aside className="cc-portrait" aria-label="Portre alanı boş">
              <div className="cc-portrait-border" />
              <span className="cc-roman">I</span>
              <div className="cc-portrait-caption">
                <div className="cc-label">Portre alanı · boş</div>
                <p className="cc-literary">Bu sayfada portre bulunmaz</p>
              </div>
            </aside>

            <section className="cc-form-panel">
              <section className="cc-start-section" aria-labelledby="campaign-start-heading">
                <div className="cc-start-title-row">
                  <div>
                    <span className="cc-label">Kampanya ayarı</span>
                    <h2 className="cc-start-heading" id="campaign-start-heading">Başlangıç yerini seç</h2>
                  </div>
                  {selectedRegion && (
                    <span className="cc-start-status">
                      {selectedRegion.coverage_status === 'VERIFIED_PARTIAL' ? 'Kısmi kaynak kapsamı' : 'Kaynaklar doğrulandı'}
                    </span>
                  )}
                </div>
                <div className="cc-start-fields">
                  <label className="cc-field">
                    <span className="cc-label">Dünya</span>
                    <span className="cc-select-wrap">
                      <select
                        className="cc-input cc-literary"
                        value={selectedSetting?.setting_id ?? ''}
                        onChange={(event) => {
                          setSettingId(event.target.value);
                          setRegionPackId('');
                          setStartingLocationId('');
                        }}
                        disabled={loadingStartOptions || !settings.length || creating}
                        data-testid="select-campaign-setting"
                      >
                        {settings.map((item) => <option value={item.setting_id} key={item.setting_id}>{item.name}</option>)}
                      </select>
                      <ChevronDown size={14} aria-hidden="true" />
                    </span>
                  </label>
                  <label className="cc-field">
                    <span className="cc-label">Bölge</span>
                    <span className="cc-select-wrap">
                      <select
                        className="cc-input cc-literary"
                        value={selectedRegion?.region_pack_id ?? ''}
                        onChange={(event) => {
                          setRegionPackId(event.target.value);
                          setStartingLocationId('');
                        }}
                        disabled={loadingStartOptions || !selectedSetting?.regions.length || creating}
                        data-testid="select-campaign-region"
                      >
                        {selectedSetting?.regions.map((item) => <option value={item.region_pack_id} key={item.region_pack_id}>{item.name}</option>)}
                      </select>
                      <ChevronDown size={14} aria-hidden="true" />
                    </span>
                  </label>
                  <label className="cc-field">
                    <span className="cc-label">Başlangıç</span>
                    <span className="cc-select-wrap">
                      <select
                        className="cc-input cc-literary"
                        value={selectedLocation?.entity_id ?? ''}
                        onChange={(event) => setStartingLocationId(event.target.value)}
                        disabled={loadingStartOptions || !selectedRegion?.starting_locations.length || creating}
                        data-testid="select-campaign-location"
                      >
                        {selectedRegion?.starting_locations.map((item) => <option value={item.entity_id} key={item.entity_id}>{item.name}</option>)}
                      </select>
                      <ChevronDown size={14} aria-hidden="true" />
                    </span>
                  </label>
                </div>
                {loadingStartOptions && <div className="cc-feedback" role="status">Onaylı başlangıç yerleri yükleniyor…</div>}
                {Boolean(startOptionsError) && (
                  <div className="cc-feedback cc-error" role="alert" data-testid="error-campaign-start-options">
                    Başlangıç yerleri yüklenemedi.
                    <button type="button" onClick={onRetryStartOptions} disabled={loadingStartOptions}>Tekrar dene</button>
                  </div>
                )}
                {!loadingStartOptions && !startOptionsError && !hasCampaignStart && (
                  <div className="cc-feedback cc-error" role="alert" data-testid="error-no-campaign-start">
                    Kullanılabilir, doğrulanmış bir başlangıç yeri bulunmuyor.
                  </div>
                )}
              </section>

              <div className="cc-mode-row">
                <div className="cc-mode-switch" role="group" aria-label="Karakter oluşturma yöntemi">
                  <button
                    type="button"
                    className={mode === 'custom' ? 'active' : ''}
                    aria-pressed={mode === 'custom'}
                    onClick={() => setMode('custom')}
                    data-testid="button-mode-custom"
                  >
                    <Feather size={13} /> Özel karakter
                  </button>
                  <button
                    type="button"
                    className={mode === 'random' ? 'active' : ''}
                    aria-pressed={mode === 'random'}
                    onClick={() => setMode('random')}
                    data-testid="button-mode-random"
                  >
                    <Sparkles size={13} /> Zarlarla örnekle
                  </button>
                </div>
                <span className="cc-mode-note">
                  {mode === 'custom' ? 'Adını ve kimliğini seç' : 'Tüm seçimleri Python motoru yapar'}
                </span>
              </div>

              <div className="cc-fields">
                <label className="cc-field">
                  <span className="cc-label">İsim</span>
                  <input
                    className="cc-input cc-literary"
                    type="text"
                    value={mode === 'custom' ? name : ''}
                    placeholder={mode === 'random' ? 'Motor seçecek' : 'Karakter adı'}
                    onChange={(event) => setName(event.target.value)}
                    maxLength={40}
                    minLength={1}
                    required={mode === 'custom'}
                    disabled={mode === 'random' || creating}
                    autoComplete="off"
                    data-testid="input-character-name"
                  />
                </label>
                <label className="cc-field">
                  <span className="cc-label">Irk</span>
                  <span className="cc-select-wrap">
                    <select
                      className="cc-input cc-literary"
                      value={mode === 'custom' ? race : ''}
                      onChange={(event) => setRace(event.target.value)}
                      required={mode === 'custom'}
                      disabled={mode === 'random' || loadingOptions || !hasOptions || creating}
                      data-testid="select-character-race"
                    >
                      {mode === 'random' && <option value="">Motor seçecek</option>}
                      {options?.races.map((item) => <option value={item} key={item}>{item}</option>)}
                    </select>
                    <ChevronDown size={14} aria-hidden="true" />
                  </span>
                </label>
                <label className="cc-field">
                  <span className="cc-label">Sınıf</span>
                  <span className="cc-select-wrap">
                    <select
                      className="cc-input cc-literary"
                      value={mode === 'custom' ? characterClass : ''}
                      onChange={(event) => setCharacterClass(event.target.value)}
                      required={mode === 'custom'}
                      disabled={mode === 'random' || loadingOptions || !hasOptions || creating}
                      data-testid="select-character-class"
                    >
                      {mode === 'random' && <option value="">Motor seçecek</option>}
                      {options?.classes.map((item) => <option value={item} key={item}>{item}</option>)}
                    </select>
                    <ChevronDown size={14} aria-hidden="true" />
                  </span>
                </label>
                <div className="cc-field cc-level">
                  <span className="cc-label">Yol seviyesi</span>
                  <span className="cc-level-value">Level 1 <Shield size={15} /></span>
                </div>
              </div>

              <div className="cc-rule" />

              <div className="cc-details">
                <section>
                  <div className="cc-detail-heading">
                    <span className="cc-label">Özellikler</span>
                    <span className="cc-small-note">Python zarlarıyla oluşturulacak</span>
                  </div>
                  <div className="cc-stats" aria-label="Altı özellik kampanya oluşturulurken atılacak">
                    {abilityLabels.map((label) => (
                      <div className="cc-stat" key={label}>
                        <span>{label}</span><strong>—</strong>
                      </div>
                    ))}
                  </div>
                  <p className="cc-explainer">Her değer motorun 4d6 atışıyla, en düşük zar çıkarılarak belirlenir.</p>
                </section>

                <section className="cc-skills">
                  <span className="cc-label">Beceriler</span>
                  <div className="cc-skill-placeholder">
                    {mode === 'custom'
                      ? `${characterClass} sınıfı için ${skillCount} beceriyi motor seçecek.`
                      : 'Seçilen sınıfa uygun becerileri motor belirleyecek.'}
                  </div>
                  <div className="cc-record-note">
                    <span className="cc-label">Kayıt notu</span>
                    <p className="cc-literary">Can, zırh, özellikler ve beceriler sunucu tarafından hesaplanır; tarayıcı bu değerleri göndermez.</p>
                  </div>
                </section>
              </div>

              {loadingOptions && <div className="cc-feedback" role="status">Motorun seçenekleri yükleniyor…</div>}
              {Boolean(optionsError) && (
                <div className="cc-feedback cc-error" role="alert" data-testid="error-character-options">
                  Seçenekler yüklenemedi.
                  <button type="button" onClick={onRetryOptions} disabled={loadingOptions}>Tekrar dene</button>
                </div>
              )}
              {!loadingOptions && options && !hasOptions && (
                <div className="cc-feedback cc-error" role="alert">Motor geçerli ırk ve sınıf seçeneği döndürmedi.</div>
              )}
              {notice && (
                <div className={`cc-feedback ${notice.tone === 'error' ? 'cc-error' : ''}`} role="status" data-testid={`status-character-${notice.tone}`}>
                  <strong>{notice.title}</strong> {notice.detail}
                </div>
              )}

              <div className="cc-footer">
                <span>Karakter, kampanya kaydı oluşturulurken sunucuya kaydedilir.</span>
                <button className="cc-entry" type="submit" disabled={!hasOptions || loadingOptions || loadingStartOptions || !hasCampaignStart || creating || (mode === 'custom' && !name.trim())} data-testid="button-create-character">
                  {creating ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                  {creating ? 'Kayıt oluşturuluyor' : 'Macerayı aç'}
                </button>
              </div>
            </section>
          </form>

          <div className="cc-page-note"><ScrollText size={12} /> Karakter sayfası · kanonik Python kaydı</div>
        </section>
      </div>
    </main>
  );
}