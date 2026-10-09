# V2.2 errata doğrulama eki

Yapısal doğrulama: TAMAMLANDI

Kaynak anahtar kelime taraması: TAMAMLANDI

Semantik doğrulama: EKSİK

Üretim entegrasyonu: YETKİSİZ

Canlı yayın: NO-GO

Dal `phase8/emergent-storytelling-expansion`. HEAD `f63d952506064cd59e960f1e3efa6627d4e52053`. V1, V2, V2.1, V2.2 ve mevcut errata paketi değiştirilmedi. 47 yama ve 38 kayıt duruyor. Kayıtlar DRAFT, UNREVIEWED ve `player_knowledge=not_granted`.

## Kapatılan iki yanlış negatif

Eski `view_errors` her iki denemede de boş liste döndürdü.

1. `FR22-F-001` alıntısının başlığı `Invented Chronicle` yapıldı, SHA-256 durdu. Ek kontrol reddetti: `source title mismatch FR22-F-001`.
2. `FR22-F-001` atasının `FR21-F-001` yerine var olan `WD21-F-001` yapılması. Ek kontrol reddetti: `lineage parent mismatch FR22-F-001: v21_id is WD21-F-001; required parent is FR21-F-001`.

Düzeltilmiş 202 kaydın bellek içi görünümünde başlık ve soy zinciri hatası 0. Ayrıntı `validation_addendum_results.txt` içindedir.

## Dört ayrı durum

Yapısal doğrulama, alanların, kimliklerin, sayfa sınırlarının ve bu ekteki başlık-hash ile kayıt bazlı soy kontrollerinin geçmesidir. Geçti.

Anahtar kelime taraması `build_ledger.py` içindedir. Yamalı 38 kayıt, kelime karşılaşmasından önce `corrected_by_erratum` alır. Kalan 164 kayıt, sayfadaki sınırlı kelime örtüşmesiyle 137 destekli, 20 tarihsel veya macera, 7 açık sahip kararı olarak etiketlenir. Bu tarama semantik doğrulama değildir.

Kaynak cümlesiyle elle bakılan kısım, 38 yamanın değişen cümlesidir. Bu bakış kaydın diğer alanlarını doğrulamaz. 202 kaydın hiçbiri bütünüyle VERIFIED değildir.

Semantik doğrulaması eksik olanlar 202 kaydın tamamıdır. Defterdeki `supported_at_stated_scope` ve `corrected_by_erratum` etiketleri bu eksiği kapatmaz.

Üretim paketi, profil, çalışma zamanı ve şehir etkinleştirmesine dokunulmadı. Commit, push, merge ve Phase 9 yok.
