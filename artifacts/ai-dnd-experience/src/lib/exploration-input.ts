/** Display intents only. This never resolves actions or creates canonical state. */
export function explorationInputLabel(input: string): string {
  const [namespace, verb, , operation] = input.trim().split(/\s+/);
  if (namespace === '/travel') {
    return ({
      pace: 'Yolculuk tempomu seçiyorum.',
      go: 'Seçtiğim yola çıkıyorum.',
      continue: 'Yolculuğa devam ediyorum.',
      return: 'Geldiğim yoldan geri dönüyorum.',
      stop: 'Yolculuğu durduruyorum.',
    } as Record<string, string>)[verb] ?? 'Yolculuk için kararımı veriyorum.';
  }
  if (namespace !== '/explore') return input;
  if (verb === 'door') {
    return ({
      open: 'Seçtiğim kapıyı açıyorum.',
      close: 'Seçtiğim kapıyı kapatıyorum.',
      unlock: 'Seçtiğim kapının kilidini açmayı deniyorum.',
      break: 'Seçtiğim kapıyı kırmayı deniyorum.',
    } as Record<string, string>)[operation] ?? 'Seçtiğim kapıyla ilgileniyorum.';
  }
  return ({
    begin: 'Taş patikanın macerasını seçiyorum.',
    search: 'Bulunduğum yeri dikkatle araştırıyorum.',
    exit: 'Seçtiğim geçitten geçiyorum.',
    trap: 'Fark ettiğim tuzağı güvenli hâle getirmeyi deniyorum.',
    hazard: 'Önümdeki engeli aşmayı deniyorum.',
    interact: 'Seçtiğim nesneyle etkileşime giriyorum.',
    encounter: 'Avluyu inceliyorum.',
    decision: 'Karşılaşmada nasıl ilerleyeceğime karar veriyorum.',
    look: 'Çevreme bakıyorum.',
  } as Record<string, string>)[verb] ?? 'Keşfe ilişkin kararımı veriyorum.';
}
