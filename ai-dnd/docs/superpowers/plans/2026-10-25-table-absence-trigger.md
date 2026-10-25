# Masa Yokluğu Tetikleyicisi: Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Oyuncu masalı bir mekândan ayrılınca tek gizli `table_absence` olayı kurmak ve dönüşte en eski izi ya da ilk eşyayı bir kez değiştirmek.

**Architecture:** `scheduled_events.arm_table_absence` olayı kurar. `commit_location_change` onu ayrılışta çağırır. Varış gözlemi pencere açıkken olayı çözer. Mutasyon `equipment_economy.resolve_table_absence` üzerinden mevcut yüzey sahibine gider. Süre dolunca veya NPC yoksa olay `EXPIRED` olur, dünya değişmez.

**Tech Stack:** Python 3.12, unittest, `game.create_session`.

## Global Constraints

- Python dünya gerçeğinin sahibidir. Neden oyuncu bilgisine yazılmaz.
- Yeni kural `scheduled_events.py` ve `equipment_economy.py` içindedir. `game.py` yalnız tek çağrı alır.
- Pencere 86400 saniyedir. Aynı mekân için ikinci `PENDING` olay kurulmaz.
- Canlı model çağrısı yok. Birleştirme yok.
- Yeni test dosyası LF. Ürün dosyaları CRLF. `PYTHONUTF8=1`.
- Komutlar `C:\Users\Kadir\Desktop\AI-DND-v01-scene-truth\ai-dnd` içinden çalışır.

### Task 1: Kırmızı testler

**Files:**
- Create: `ai-dnd/api/tests/test_table_absence_trigger.py`

- [x] Write the six spec tests plus window expiry.
- [x] Run `python -m unittest api.tests.test_table_absence_trigger -v` and confirm they fail because `arm_table_absence` does not exist.

### Task 2: Uygulama

**Files:**
- Modify: `ai-dnd/scheduled_events.py`
- Modify: `ai-dnd/equipment_economy.py`
- Modify: `ai-dnd/game.py` (`commit_location_change`, one call before the arrival `process_events`)

- [x] Accept effect `{"kind": "table_absence"}` only when the event stays hidden and non-interruptive.
- [x] `arm_table_absence(world, location_id)` registers one pending event when the location has a mark or a surface item.
- [x] `resolve_table_absence(world, location_id, event_id)` picks the first living NPC, then the oldest mark, else the first item on the lowest feature id.
- [x] Arrival while the window is open resolves the event once. A false result or a closed window expires it with no mutation.
- [x] Run the new tests and expect OK.

### Task 3: Komşu testler

- [x] Run `api.tests.test_scene_small_events_contract` and `api.tests.test_campaign_time`.
- [x] Commit the tests and the three product files.

## Spec coverage

Arm, tek olay, en eski iz, ilk eşya, NPC yok, süre dolumu, oyuncu bilgisinin değişmemesi ve `commit_location_change` çağrısı bu görevlerdedir.
