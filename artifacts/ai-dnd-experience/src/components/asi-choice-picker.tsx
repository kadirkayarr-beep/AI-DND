import { readAsiChoices, asiChoiceKey, asiChoiceLabel, type AsiChoice } from '@/lib/asi-choices';
export function AsiChoicePicker({ choices, selected, onChange, disabled = false, testId }: {
  choices: unknown; selected?: AsiChoice; onChange: (choice: AsiChoice | undefined) => void; disabled?: boolean; testId: string;
}) {
  const options = readAsiChoices(choices) ?? [];
  return <div>
    <label>Ability Score Improvement <select data-testid={testId} disabled={disabled} value={selected ? asiChoiceKey(selected) : ''} onChange={event => {
      if (!disabled) onChange(options.find(choice => asiChoiceKey(choice) === event.target.value));
    }}><option value="">Bir artış seç</option>{options.map(choice => <option key={asiChoiceKey(choice)} value={asiChoiceKey(choice)}>{asiChoiceLabel(choice)}</option>)}</select></label>
    <p>Desteklenen kapsam: Strength, Dexterity, Constitution, Intelligence, Wisdom veya Charisma için tek +2 ya da iki farklı +1. Üst sınır 20 ve son değerler sunucuda doğrulanır. Dexterity artışı Zırh Sınıfını giyilen zırha göre günceller; zırhın kaynağı doğrulanamayan karakterde Dexterity değiştirici yükselten seçenek sunulmaz. Diğer feat seçenekleri desteklenmiyor.</p>
  </div>;
}
