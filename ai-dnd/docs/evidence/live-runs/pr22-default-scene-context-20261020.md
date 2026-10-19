# PR22 — varsayılan NPC hedefleme canlı kanıtı

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
