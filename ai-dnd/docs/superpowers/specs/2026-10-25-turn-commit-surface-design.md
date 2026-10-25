# Faz 6: Yüzey mutasyonu mevcut tur makbuzuna girer

25 Ekim 2026. Karar: yeni kayıt defteri yok. `api/main.py` tur kilidi, `session_manager.autosave_turn` ve `campaign_store` makbuzu sahibi kalır.

İz, yüzey eşyası ve masa yokluğu `world_state` içindedir. Tur başındaki `_capture_runtime_snapshot` bu dünyanın tamamını alır. Kayıt başarısız olursa `_restore_runtime_snapshot` aynı nesneleri yerinde geri yükler. Başarılı kayıt `action_id` makbuzunu saklar. Aynı kimlik ve aynı gövde oyunu yeniden çalıştırmaz; aynı kimlik ve farklı gövde `action_id_conflict` olur.

Belirsiz kayıt (`CampaignStaleError`) adayı geri yükledikten sonra makbuzu okur. Makbuz yoksa veya gövde aynıysa bayatlık hatası döner; gövde farklıysa çakışma döner. İkinci kez uygulanmaz.

Başka kampanyanın oturumu bu makbuzun yazılacağı yer değildir. Eşzamanlı aynı istek tek iz bırakır; kayıp yanıtın tekrarı aynı anlatımı ve aynı izi verir.

Çözülmüş bir eylemin anlatıcı çağrısı düşerse deterministik yedek metin kalır ve etki durur. Yerel eylem sahibi hata verirse dünya geri alınır ve sonraki sahip aynı işi bir kez yapar. Üretim denemesi (`no_proposal` / `consumed`) geri alınmış tur diye yazılmaz; dünya değişmez.

Kapsam dışı: yeni event-store, tur kilidinin yeniden yazılması, `free_v1`, istem metni, Faz 7 canlı model kabulü.
