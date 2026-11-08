export const TR_TERMS = {
  action: { tr: 'Eylem', en: 'Action' }, bonus_action: { tr: 'Bonus eylem', en: 'Bonus Action' },
  reaction: { tr: 'Tepki', en: 'Reaction' }, attack: { tr: 'Saldırı', en: 'Attack' },
  dash: { tr: 'Koş', en: 'Dash' }, ready: { tr: 'Hazırlan', en: 'Ready' },
  speed: { tr: 'Hız', en: 'Speed' }, feet: { tr: 'fit', en: 'feet' }, opportunity: { tr: 'fırsat', en: 'Opportunity' },
  second_wind: { tr: 'İkinci Nefes', en: 'Second Wind' }, action_surge: { tr: 'Eylem Atılımı', en: 'Action Surge' },
  tactical_mind: { tr: 'Taktik Zihin', en: 'Tactical Mind' }, tactical_shift: { tr: 'Taktik Kayma', en: 'Tactical Shift' },
  sneak_attack: { tr: 'Gizli Saldırı', en: 'Sneak Attack' }, cunning_action: { tr: 'Kurnaz Eylem', en: 'Cunning Action' },
  rage: { tr: 'Öfke', en: 'Rage' }, reckless_attack: { tr: 'Pervasız Saldırı', en: 'Reckless Attack' },
  flurry_of_blows: { tr: 'Darbe Yağmuru', en: 'Flurry of Blows' }, patient_defense: { tr: 'Sabırlı Savunma', en: 'Patient Defense' },
  step_of_the_wind: { tr: 'Rüzgâr Adımı', en: 'Step of the Wind' }, divine_smite: { tr: 'İlahi Darbe', en: 'Divine Smite' },
  lay_on_hands: { tr: 'Şifa Eli', en: 'Lay on Hands' }, quickened_spell: { tr: 'Hızlandırılmış Büyü', en: 'Quickened Spell' },
  sorcery_points: { tr: 'Büyücülük Puanı', en: 'Sorcery Points' },
} as const;
export type TermKey = keyof typeof TR_TERMS;
export const term = (key: TermKey): string => TR_TERMS[key].tr;
export const termTitle = (key: TermKey): string => TR_TERMS[key].en;
export const feetText = (n: number): string => `${n} fit`;
export const SENT = {
  attack: 'Saldırıyorum.', continue_attack: 'Aynı saldırı eyleminde bir saldırı daha yapıyorum.',
  dash: 'Koşuyorum.', ready: 'Hazırlanıp bekliyorum.', react: 'Hazırladığım tepkiyi kullanıyorum.',
  decline_reaction: 'Tepki fırsatını geçiyorum.',
} as const;
export const moveSentence = (n: number): string => `${feetText(n)} hareket ediyorum.`;
export const abilitySentence = (label: string): string => `${label} kullanıyorum.`;
