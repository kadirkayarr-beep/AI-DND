import { Dice5 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { pickRandomKey } from '@/lib/pick-random';

const ROLL_MS = 450;

export function StepDice({ label, keys, current, onPick, testId }: {
  label: string;
  keys: string[];
  current: string;
  onPick: (key: string) => void;
  testId: string;
}) {
  const [rolling, setRolling] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const roll = () => {
    const key = pickRandomKey(keys, current);
    if (key === null) return;
    onPick(key);
    setRolling(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setRolling(false), ROLL_MS);
  };
  return (
    <button
      type="button"
      className={`cc-step-dice${rolling ? ' rolling' : ''}`}
      onClick={roll}
      disabled={keys.length === 0}
      aria-label={label}
      title={label}
      data-testid={testId}
    >
      <Dice5 size={20} aria-hidden="true" />
    </button>
  );
}
