/** Creation-only disclosure, not a wallet calculator or historical-save capability. */
export function StartingEquipmentNotice({ characterClass, classes, equipmentPackage, backgroundOption, backgroundData }: {
  characterClass: string; classes?: unknown; equipmentPackage?: string;
  backgroundOption?: string; backgroundData?: unknown;
}) {
  if (characterClass !== 'Barbarian') return null;
  const packages = (classes as { Barbarian?: { equipment_packages?: unknown } } | undefined)?.Barbarian?.equipment_packages;
  const source = Array.isArray(packages) ? packages : [];
  const a = source.find(item => item?.id === 'A')?.items;
  const b = source.find(item => item?.id === 'B')?.items;
  // The corrected source signature admits this bounded policy. Never parse cash labels.
  const verified = Array.isArray(a) && a.length === 4 &&
    ['Büyük Balta (Greataxe)', '4 Handaxes', "Explorer's Pack", '15 GP'].every((item, index) => a[index] === item) &&
    Array.isArray(b) && b.length === 1 && b[0] === '75 GP';
  const gp = (backgroundData as { starting_gp?: unknown } | undefined)?.starting_gp;
  const certified = typeof gp === 'number' && Number.isInteger(gp) && gp >= 0;
  return <aside className="subtle-text mt-3" data-testid="starting-equipment-notice">
    <strong>Başlangıç ekipmanı ve kayıtlı bakiye</strong>
    {verified ? <p>{equipmentPackage === 'A' ? `Seçilen sınıf paketi nakdi: ${a[3]}.` : equipmentPackage === 'B' ? `Seçilen sınıf paketi nakdi: ${b[0]}.` : `Katalogdaki sınıf paketi nakdi — A: ${a[3]}; B: ${b[0]}. Sonuç için seçilmiş paket tutarı burada çıkarılmaz.`} Sınıf nakdi cüzdana kaydedilir.</p>
      : <p>Bu katalogdan sınıf nakdi doğrulanamıyor; burada bir tutar veya sıfır varsayılmaz.</p>}
    {verified && backgroundOption === 'A' && certified && <p>Arka plan A için doğrulanmış nakit: {gp} GP; sunucu cüzdana kaydeder.</p>}
    {verified && backgroundOption === 'B' && <p>Arka plan B seçeneğinin 50 Altını sunucu tarafından ayrıca cüzdana kaydedilir.</p>}
    <p>Yalnız doğrulanmış arka plan nakdi cüzdana eklenir. Arka plan A nakdi doğrulanmamışsa para etiketi envanterde dönüştürülmeden kalır; bilinmeyen tutar sıfır değildir. Gösterilen bakiye toplam başlangıç serveti değildir. Paket içeriğinin tüm mekanikleri uygulanmış sayılmaz.</p>
  </aside>;
}
