import { startingPurse } from '@/lib/starting-purse';

/** The starting purse at creation, read from the catalog: class package gold + background gold = total. Unknown: nothing. */
export function StartingEquipmentNotice({ characterClass, catalog, equipmentPackage, background, backgroundOption }: {
  characterClass: string; catalog?: unknown; equipmentPackage?: string;
  background?: string; backgroundOption?: string;
}) {
  const purse = startingPurse(catalog, characterClass, equipmentPackage, background, backgroundOption);
  if (!purse) return null;
  return <p className="subtle-text mt-3" data-testid="starting-equipment-notice">
    {`Başlangıç kesesi: sınıf paketi ${purse.classGp} altın + geçmiş ${purse.backgroundGp} altın = ${purse.totalGp} altın.`}
  </p>;
}
