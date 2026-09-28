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
import type { CharacterCreateInput, CharacterCreationOptions } from '@workspace/api-client-react';
import './character-creation-screen.css';

type Notice = { tone: 'error' | 'success' | 'warning'; title: string; detail: string };

type CharacterCreationScreenProps = {
  options?: CharacterCreationOptions;
  loadingOptions: boolean;
  optionsError: unknown;
  creating: boolean;
  notice: Notice | null;
  onBack: () => void;
  onCreate: (character: CharacterCreateInput) => void;
  onRetryOptions: () => void;
};

const abilityLabels = ['KUV', 'ÇEV', 'DAY', 'ZEK', 'BİL', 'KAR'];

export function CharacterCreationScreen({
  options,
  loadingOptions,
  optionsError,
  creating,
  notice,
  onBack,
  onCreate,
  onRetryOptions,
}: CharacterCreationScreenProps) {
  const [mode, setMode] = useState<'custom' | 'random'>('custom');
  const [name, setName] = useState('Cedric');
  const [race, setRace] = useState('Elf');
  const [characterClass, setCharacterClass] = useState('Wizard');
  const hasOptions = Boolean(options?.races.length && options.classes.length);

  useEffect(() => {
    if (!options) return;
    if (!options.races.includes(race)) setRace(options.races[0] ?? '');
    if (!options.classes.includes(characterClass)) setCharacterClass(options.classes[0] ?? '');
  }, [characterClass, options, race]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasOptions || creating) return;
    if (mode === 'random') {
      onCreate({ mode: 'random' });
      return;
    }
    onCreate({ mode: 'custom', name: name.trim(), race, class: characterClass });
  };

  const skillCount = characterClass === 'Rogue' ? 4 : 2;

  return (
    <main className="character-creation-screen dnd-frame dnd-creation" data-testid="screen-character-creation">
      <div className="cc-shell">
        <header className="cc-header">
          <div className="cc-brand" aria-label="AI Dungeon Master">
            <span className="cc-brand-mark"><Compass size={17} strokeWidth={1.3} /></span>
            <span><strong>AI DUNGEON MASTER</strong><small>Solo campaign · Sword Coast</small></span>
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
                <button className="cc-entry" type="submit" disabled={!hasOptions || loadingOptions || creating || (mode === 'custom' && !name.trim())} data-testid="button-create-character">
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