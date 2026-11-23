# Implementer önsözü (her implementer istemine eklenir)

Ana ilke: kalite ve güvenlik kaybına müsamaha göstermeden hız. Çelişkide kalite ve güvenlik kazanır.

## Koda giriş
- Koda `graphify query "<soru>"` ile gir; ham dosyayı yalnız grafiğin ya da önceki okumanın gösterdiği satırlar için oku. Grafik JSON içeriğini (şablon, katalog, menü tablosu) ve dinamik yolları görmez; oralarda dosyayı oku.
- Görev sonunda ve rapordan önce bir kez `graphify update .` çalıştır (commit etme).
- Testleri yalnız korumalı WSL başlatıcısıyla koş; önce hızlı set (yeni testler + `api.tests.test_journey_runner`, `test_journey_report`, `test_journey_schema`, `test_journeys`), uzun set görev sonunda bir kez.

## Kontrol listesi (her maddeyi cevapla; uygulanmıyorsa "uygulanmaz" + neden)
- (a) Tüm çağıran yollar yeni davranışı alıyor mu (ikinci yol, savaş içi yol, karakteri geçmeyen çağıran)?
- (b) Eski kayıt (alan yok) uyumu?
- (c) Geri Al ve yeniden yükleme sonrası aynı durum?
- (d) Rastgele kasabaya bağlı test yok mu (sabit tohum: `fixed_town`, `campaign_seed`)?
- (e) Oyuncuya gösterilen metin o durumda doğru mu (yalan gerekçe yok)?
- (f) Önce kırmızı test; gevşetilen test yok.
- (g) Para ve envanter yalnız doğrulanmış bir kartla değişir. İki ayrı yol var: modelin ya da doğal dilin önerdiği ekonomik değişiklik kart (teklif/onay) ister; oyuncunun açık `/item buy` ve `/item sell` komutları ise doğrudan katalog ticaretidir ve motor fiyatı, stok ve ödeme yazıcısı doğrulamasıyla kartsız çalışır (`equipment_economy.py`, `test_coin_writers.py`). Yeni bir ticaret yolu bu iki sınıftan birine açıkça girmeli. Görev ve iz yalnız motor kaydıyla değişir (model tek başına değiştirmez).
- (h) Yeniden kullanım merdiveni: yeni kod yazmadan önce sırayla bak: (1) repoda bunu zaten yapan bir işlev ya da modül var mı (`graphify query`), (2) standart kütüphane, (3) ancak sonra en az yeni kod. Raporda tek satırla yaz: neyi yeniden kullandın ya da yeni kod neden gerekti. Bu madde para, kayıt ve Geri Al kodunda doğrulamayı, hata işlemeyi, makbuzu/tekrar güvenliğini (idempotency), kayıt ve Geri Al denetimlerini ve testleri ASLA azaltmaz; başka hiçbir kontrol listesi maddesini de geçersiz kılmaz. Kod azaltma kalite ve güvenliğin altında kalır.
- (i) Motor dosyası (CLAUDE.md, karar 8): game.py'ye yeni işlev eklenmez; yeni kod ilgili `game_parts` modülüne ya da kendi modülüne girer. `game_parts` içinde motor adları `game.X` diye çağrılır. Boyut bütçesi yalnız Kadir'in onayıyla yükseltilir. Yeni bir parça ya da `game.py`'de iki boş satırdan uzun boşluk `test_engine_layout` ve `test_engine_size_budget` tarafından reddedilir. `game.py` ya da `game_parts/` değişen her görevin hedefli koşusuna komşu setin yanında şunlar da girer: `api.tests.test_engine_size_budget`, `test_engine_surface`, `test_engine_patch_census`, `test_engine_routing`, `test_engine_sensitivity`, `test_engine_layout`, `test_engine_sources`.

## Karar
Belirsizlikte dur ve sorma: karar ver, raporda `Ruling: <karar> — <neden> — <yanlışsa maliyeti>` yaz. Yalnız geri alınamaz işlem, güvenlik açısından hassas işlem, worktree dışı yan etki ya da bozuk plan durdurur.

## Kesim dilimleri için ek kurallar
- Her koşunun RESULT satırı deftere şu biçimde yazılır: `tests N skipped N failing_ids N PAR_EXIT=N`. "N tests exit 0" yetmez.
- Bir işlev ya da çağrı başka dosyaya taşınıyorsa, testlerde taşınan işlevin dosya yolunu ve çağrı adını ara (grep); dosya yolunu sabitleyen her test o görevin hedefli setine girer.
