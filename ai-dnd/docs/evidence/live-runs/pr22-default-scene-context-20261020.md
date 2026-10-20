# PR22 — varsayılan NPC hedefleme canlı kanıtı

## Son durum düzeltmesi — 2026-10-20

- İlk üç deneme aşağıdaki gibi sonuçlanmıştı; daha sonraki `pr22-normal-npc-dialogue-final/report.json` normal modda başarılı bir zincir kaydediyor. Qwen kanıtı `tested_commit=55a76886878610bc7738b249a1684034adaef191` içindir; bu turda canlı model yeniden çağrılmadı.
- Son rapor: `status=PASS`, `qwen3:8b`, `turn_count=5`, `model_calls=5`, `max_turns=8`, `max_model_calls=16`, kampanya izole ve opt-in/deneysel bayrak kapalı. NPC `npc_live_normal_marek`; seyahat `completed`, hedef inceleme `resolved`; yeni uygulama/manager ile resume sonrasında NPC kimliği ve atıf korunmuş.
- Kaydedilmiş canlı JSON özetinde tam `TurnResponse`, seyahat/inceleme hedef kimlikleri ve yer referansı nesnesi yok. Bu yüzden tam canlı `action/target/outcome` payload'ı veya `said_by` kaydı varmış gibi yazılmamalı. Eski deneysel rapor bu boşluğu kapatmaz.
- Güncel sahte-model API regresyonu `test_default_npc_targeting` içinde **4 test geçti**. Yeni yer önerisi payload'ı `dialogue/resolved`; `target_name=null` (API makbuzu NPC hedef kimliğini dışarı vermiyor). Hedef, istek `target_id`'si ve kaydedilmiş `said_by` ile doğrulanıyor. Bilinmeyen yer alıntı/atıfla kaydediliyor, `location_id` boş kalıyor; aynı eylem aynı yanıta replay ediliyor; save + yeni manager/app ile resume sonrasında kayıt korunuyor ve ikinci kampanyaya sızmıyor. Bu “cold load” aynı Python sürecinde yeni manager/app açılmasıdır, süreç yeniden başlatması değildir.
- Sahte-model travel yoklamasında `turn_outcome={action: grounded_action, status: completed, target_name: Mavi Fener Camhanesi}` dönmesine karşın gerçek `world_state.location` şehirde kaldı. Bu sonuç seyahat başarısı değildir; bu turdaki regresyon hareket/varış iddiasında bulunmaz.
- `328` toplam test sayısı için güncel bir koşum kanıtı bulunmadı; bu güncellemede yalnızca yukarıdaki 4 test çalıştırıldı. Önceki 14 test bilgisi eski koşum kaydıdır, yeni sayıyla toplanmamalı. PR21/22 merge veya ready durumu değiştirilmedi.

## Kapsam

- Ayrı aday dalı, başlangıç: `14a6fe91`.
- Varsayılan NPC konuşma modu; `AI_DND_NPC_SPEECH` etkinleştirilmedi.
- Yalnızca geçici kampanyalar kullanıldı; kişisel kampanya verisi kullanılmadı.
- Gerçek `qwen3:8b` denemeleri: toplam 12 oyuncu turu, 9 model çağrısı.
- Ham istek/yanıt dosyaları silindi; bu rapor yalnızca sonuç özetini tutar.

## Canlı sonuçlar

| Deneme | Tur/çağrı | Sonuç |
| --- | ---: | --- |
| Sahne tarifinden muhafıza hitap | 5/4 | Muhafız hedefi seçildi. NPC yer bilmediğini belirtti; atfedilmiş bir yer önerisi ve öneriden seyahat oluşmadı. Sonraki hedef incelemesinde doğrulanmamış referans için `feature_001` üretildi; bu, istenen zincirin başarısı sayılmaz. |
| Belirsiz “kişi” tarifi | 5/4 | İki aday bulunduğu için sistem doğru biçimde açıklama istedi. Yer önerisi/seyahat zinciri oluşmadı. |
| Selam ve yer önerisini tek mesajda sorma | 2/1 | Muhafız hedefi seçildi, ancak yanıt yalnızca selam verdi ve asıl soruyu yanıtlamadı. |

**Sonuç:** Gerçek Qwen ile NPC sözü → seyahat → hedef inceleme zinciri henüz tamamlanmadı. Bu çalışma uçtan uca başarı kanıtı değildir.

## Deterministik API testleri

Varsayılan modda eklenen testler; önceki oyuncuya görünür sahne metninin yalnızca hedef eşleştirme bağlamı olarak kullanılmasını, NPC kimliğinin etkin Python adaylarından seçilmesini, alıntının güncel oyuncu mesajından doğrulanmasını ve NPC'ye atfedilen yer sözünün kaydetme/devam ettirme sonrası korunmasını sınar. Testte seyahat varış noktasının kapısı kilitli olduğundan seyahat `blocked` kalır; ardından gerçek kapı kimliğiyle hedefli inceleme `grounded_action/completed/kind=door` verir. Bu, başarılı seyahat iddiası değildir.

Son doğrulama: yeni varsayılan hedefleme, deneysel NPC konuşması ve seçilmiş NPC profil API testleri birlikte **14 test geçti**. UI regresyon testi önceki çalıştırmada `CHROMIUM_PATH=/repl/tools/bin/chromium` ile geçti.

Önceden kalibre edilmiş `test_location_npc_and_defeat_authority_remain_strict` / `CANONICAL_LOCATION_CONTRADICTION` taban hatası burada yeniden sınıflandırılmadı veya gevşetilmedi.
