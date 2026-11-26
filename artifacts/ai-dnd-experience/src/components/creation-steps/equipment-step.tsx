import { StartingEquipmentNotice } from '@/components/starting-equipment-notice';
import { packageGoods } from '@/lib/starting-purse';
import type { CharacterCreationCatalogResponse } from '@workspace/api-client-react';

type EquipmentStepProps = {
  characterClass: string;
  propCatalog: CharacterCreationCatalogResponse | undefined;
  equipmentPackage: string;
  background: string;
  backgroundEquipmentOption: 'A' | 'B' | '';
  classData: any;
  setEquipmentPackage: (value: string) => void;
  setBackgroundEquipmentOption: (value: 'A' | 'B' | '') => void;
  artisanTool: string;
  setArtisanTool: (value: string) => void;
  backgroundData: any;
};

export function EquipmentStep({ characterClass, propCatalog, equipmentPackage, background, backgroundEquipmentOption, classData, setEquipmentPackage, setBackgroundEquipmentOption, artisanTool, setArtisanTool, backgroundData }: EquipmentStepProps) {
  return (
    <section className="cc-step-panel">
          <div className="cc-step-header">
            <div className="cc-label">Adım 6</div>
            <h2 className="cc-step-title-text">Başlangıç Ekipman Paketi</h2><StartingEquipmentNotice characterClass={characterClass} catalog={propCatalog} equipmentPackage={equipmentPackage} background={background} backgroundOption={backgroundEquipmentOption} />
            <p className="cc-literary">Karakterinin macera yolculuğuna başlarken kuşanacağı silah, zırh ve teçhizatı seç.</p>
          </div>

          <div className="cc-cards-grid cc-portrait-grid">
            {(classData?.equipment_packages ?? [
              { id: 'A', label: 'Standart Macera Paketi', items: ['Zırh', 'Silah', 'Macera Çantası', '10 Altın'] },
            ]).map((pkg: any) => {
              const isSelected = equipmentPackage === pkg.id;
              return (
                <div
                  key={pkg.id}
                  className={`cc-choice-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => setEquipmentPackage(pkg.id)}
                >
                  <div className="cc-card-top">
                    <span className="cc-card-title">Paket {pkg.id}: {pkg.label}</span>
                  </div>
                  <ul className="cc-item-list">
                    {packageGoods(pkg).map((it: string) => (
                      <li key={it}>{it}</li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>

          <div className="cc-sub-section mt-4">
            <div className="cc-sub-header">
              <span className="cc-label">Arka Plan Başlangıç Teçhizatı (Seçenek A veya B)</span>
              <small>2024 kurallarına göre geçmişinden gelen ekipman paketini veya alternatif 50 Altın alabilirsin.</small>
            </div>
            <div className="cc-cards-grid">
              <div
                className={`cc-choice-card ${backgroundEquipmentOption === 'A' ? 'selected' : ''}`}
                onClick={() => setBackgroundEquipmentOption('A')}
              >
                <div className="cc-card-top">
                  <span className="cc-card-title">Seçenek A: Geçmiş Teçhizat Paketi</span>
                </div>
                <p className="cc-card-desc">Geçmişine özgü mesleki aletler, kıyafetler ve başlangıç kesesi.</p>
              </div>
              <div
                className={`cc-choice-card ${backgroundEquipmentOption === 'B' ? 'selected' : ''}`}
                onClick={() => setBackgroundEquipmentOption('B')}
              >
                <div className="cc-card-top">
                  <span className="cc-card-title">Seçenek B: 50 Altın</span>
                </div>
                <p className="cc-card-desc">Paket yerine serbest harcama için 50 Altın nakit para ile başla.</p>
              </div>
            </div>
            {background === 'Artisan' && (
              <label className="cc-label">
                Araç seçimi
                <select value={artisanTool} onChange={(event) => setArtisanTool(event.target.value)}>
                  {(backgroundData?.tool_options ?? ["Smith's Tools"]).map((tool: string) => (
                    <option key={tool} value={tool}>{tool}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
        </section>
  );
}
