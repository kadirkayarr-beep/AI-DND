# B05 devir kaydı — tarihsel çapraz eşleme (2026-10-27)

Kısa kabul kaydıdır; ürün kanıtı veya bütün oyunun başarısı değildir. Sır, jeton, kitap metni yoktur.

## Kaynak kimliği
- Dal `task/b01-source-identity-20261026`, HEAD `78b380384e70832156d2d9aa2785192bbbbdb74b`; izlenen dosyalarda değişiklik yok, B01-B05 işi izlenmeyen dosyalar.

## Kapsam (baştan yazılmadı, mevcut dosyalar incelendi)
- `tools/acceptance/historical_crosswalk.py` (74 satır), `docs/acceptance/historical-crosswalk.json`, `ai-dnd/api/tests/test_roadmap_b05.py` (10 test).
- Sahip modül: tarihsel kayıt hiçbir koşulda tam sürümü kapatmaz (`historical_pass_closes_full_release`); kaynağı olmayan kayıt UNKNOWN kalır, başlık uydurulmaz; var olmayan hedef görev UNKNOWN_TARGET olur.

## Test
- `python -m unittest api.tests.test_roadmap_b05 -v` (cwd `ai-dnd`): 10 test, OK, 0,047 sn. Test yalnız depodaki çapraz eşleme dosyasını, LR başlık satırlarını (SHA256 + satır) ve B02/B04 bağlantılarını okur; oyun, model veya sunucu çağrısı yoktur.
- Bu koşu yalnız B05 modülüdür; tam suite, B01-B04 yeniden koşusu, lint ve UI/Node testleri koşulmadı. B03'teki `run_isolated.py` sarmalayıcısı kullanılmadı (test dosya okuma dışında yan etki yapmıyor).

## Durum
- B05: ACCEPTED (dar kapsam: çapraz eşleme sözleşmesi). Bağımsız inceleme yapılmadı; düşük riskli veri/eşleme işi, onaylı hibrit düzende küçük grup incelemesine bırakıldı.
- Sınırlar: 6 G + 16 fırsat satırı `MAPPED_UNVERIFIED_SOURCE` (kaynak yalnız plan paketi kaydı; özgün belge B05'te açılmadı). 6 LR satırı depo başlığıyla doğrulandı. Tam sürüm kapanışı yoktur.

## Sonraki
- B06 (bağımlılıklar B01, B02): kendi dosyası/testi/kaydı yok; yalnız B02/B04 kayıtlarında ve B03 kanıt JSON'larında ad geçiyor. Plan zip'inden başlatılmalı.
