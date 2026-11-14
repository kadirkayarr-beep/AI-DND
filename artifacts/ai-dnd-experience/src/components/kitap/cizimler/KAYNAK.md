# Çizim klasörü: kaynak notu

Bu klasör yalnız taslaktan aynen alınan çizimleri ve kâğıt dokularını tutar (Kadir, 13 Kasım 2026). Çizimlerin iç renkleri (gölge, ışık, renk geçişi durakları) çizimin parçasıdır ve olduğu gibi kalır. Temaya göre değişen renkler değişkenden gelir: `--mum` (kalem ucu), `--mum-cizgi` (mumun kenar çizgisi), `--soluk` (sönük mumun dumanı). "Elle yazılmış renk kodu yok" araması bu klasörü kapsamaz.

Kaynak klasörü: `AI-DND-b01-isolated/kitap-taslagi-20261113/kaynak/` (oyunun kodu değildir; yalnız çizim ve değer kaynağı). Düzen işaretlemesi ve stil kodu alınmadı; React biçimine çevrildi (öznitelik adları, tekil `id`).

| Oyundaki dosya | Geldiği dosya | Nasıl bulundu | Not |
|---|---|---|---|
| `kalem-ucu.tsx` | `Main.dc.html` | Yazma satırının (`class="yaz-sira"`) ilk `<svg>`'si, 38 piksel | Renk: `var(--mum)`, yarık `var(--sayfa)` |
| `kurdele.tsx` | `Main.dc.html` | `aria-label="Kurdele ayraç: ..."` taşıyan `<svg>` ve `uw-kurdele` geçişi | Kitap boyuna esner (`preserveAspectRatio="none"`) |
| `secim-damgasi.tsx` | `KurulumGece.dc.html` | `aria-label="Seçildi"` taşıyan `<svg>`; `uw-balmumu` süzgeci, `uw-mum-kirmizi` ve `uw-cukur` geçişleri aynı dosyanın gizli `<defs>`'inden | Süzgeç yalnız 30 piksellik damgaya uygulanır |
| `kagit-tanesi-koyu.png` | `kagit-tanesi-koyu.png` | Aynı ad | 61593 bayt, 256×256; Gündüz ve Gece |
| `kagit-tanesi-acik.png` | `kagit-tanesi-acik.png` | Aynı ad | 54679 bayt, 256×256; Karanlık |

Oturum 2'de eklenecek: mum (yanan, sönük), can mührü (büyük, küçük, basılmamış), okuma lambası, kenar simgeleri. Alınmayacak: `uw-demir`, `uw-fener-cam` (eski asılı fener).
