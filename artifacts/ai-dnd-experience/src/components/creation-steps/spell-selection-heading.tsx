export function SpellSelectionHeading({ characterClass, selectedCount, requiredCount }: {
  characterClass: string;
  selectedCount: number;
  requiredCount: number;
}) {
  const isSpellbook = characterClass === 'Wizard';
  const preparationClosed = isSpellbook || characterClass === 'Cleric' || characterClass === 'Druid';
  const title = isSpellbook ? 'Büyü Kitabına Eklenen 1. Seviye Büyüler'
    : preparationClosed ? '1. Seviye Büyü Seçimleri' : '1. Seviye Hazırlanan Büyüler';
  const description = isSpellbook
    ? 'Bu seçimler büyü kitabına eklenir. Bu sürümde Sihirbaz için büyü hazırlama ve 1. seviye büyü yapma henüz açık değil.'
    : preparationClosed
      ? 'Bu seçimler karakter kaydında saklanır; hazırlanmış büyü sayılmaz. Bu sürümde bu sınıfın 1. seviye büyüleri yuva harcayarak kullanılamaz.'
      : 'Büyü yuvası harcayarak yapılan güçlü büyüler.';
  return <div className="cc-sub-header" data-testid="spell-selection-heading">
    <span className="cc-label">{title} ({selectedCount} / {requiredCount} Seçildi)</span>
    <small>{description}</small>
  </div>;
}
