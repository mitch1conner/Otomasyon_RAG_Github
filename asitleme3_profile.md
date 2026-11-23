
---
Özel Tarama Profili: 3.Asitleme (2016–2020 ELOT Görev Raporu PDF)
Kaynak: asitleme3_2016-2020.pdf (26 sayfa, ELOT GÖREV RAPORU)

Amaç: Bu formata özgü alan eşlemesi, kümelendirme anahtarları ve aksiyon/kanıt çıkarım ipuçları eklenmiştir. Bu kurallar veri bulunduğu sürece uygulanır; belirsizlikte “Varsayım” etiketi kullanılır.

1) Alan Eşlemesi Kuralları (Heuristik)
- hat_adi: “Hat Adı” sütunu ve/veya satırdaki “3.ASITLEME” ibaresi → "3.ASITLEME".
- tarih: Kayıt başlığı yakınındaki tarih alanı (ör. 2016-01- …). Net tarih parçası bulunamazsa Varsayım.
- vardiya: “Vardiya” sütunu (1,2,3 vb.).
- ariza_aciklamasi: “Açıklama” sütunundaki problem tanımı cümleleri (örn. “EPC otomatikten düşüyor”, “X-ray open beam changed too much”).
- yapilan_islemler: Açıklamadaki müdahale fiilleriyle başlayan kısımlar (örn. “kontrol edildi”, “ayarlandı”, “değiştirildi”, “resetlendi”, “enerji verildi”, “test edildi”, “yedekle değiştirildi”, “temizlendi”).
- ekipman/istasyon: Açıklamadaki ekipman terimleri çıkarılır (bkz. Terimler Sözlüğü). Birden fazlaysa en baskın 1–2 terim yazılır.
- duruş_suresi_dk: “3.ASITLEME” ibaresini takip eden sayısal süre alanında virgüllü saat biçimi (örn. 2,5) görülürse saat→dakika çevrilir (2,5 saat ≈ 150 dk). Netlik yoksa Varsayım notu düşülür.
- tekrar_durumu: “tekrar”, “yeniden”, “aynı arıza” gibi ifadeler yakalanırsa tekrar=Evet.
- hata_kodu: Kodu andıran desenler (örn. “M11”, “I 1.7”, “I205.6”) yakalanırsa hata_kodu listesine eklenir.
- Kayıt sınırı: Yeni kayıt; genellikle “Arıza No” numarası (ör. 41123), “ARIZA” ve/veya “3.ASITLEME” içeren satırlarla başlar. Yeni numara/başlık görüldüğünde önceki kayıt kapanır.
- Satır birleştirme: PDF satır kesmeleri nedeniyle bölünmüş cümleler birleştirilir; noktalama ve küçük-büyük harf normalize edilir; “,” ondalık ayırıcı olarak kabul edilir.

2) Kümelendirme Anahtarları
- Birincil: [hat_adi + ekipman_terimi + arıza_fiil_ifadesi]
- İkincil ipuçları: hata_kodu (M11, I205.6 vb.), iletişim hattı (Profibus/Can bus), besleme gerilimi (24V, 78–150kV aralığı), mekanik konum (deflectör, merdane, kriko), sensör tipi (fotoswitch, absocoder, linear sensör), X-ray alt sistemi (shutter, magazine, JB-3 paneli).
- Örnek kümeler:
  - EPC otomatikten çıkıyor/center’a geçmiyor [EPC, kontrol/ayar]
  - Fotoswitch kurmuyor [Fotoswitch, ayar/kirlenme]
  - Absocoder led yanıp sönüyor/saymıyor [Encoder/Absocoder, konnektör/kablo]
  - X-ray “open beam changed too much” [X-ray, power supply/kalibrasyon]
  - Shutter sürtme/solenoid arızası [Shutter, solenoid/mekanik hizalama]
  - Kablo/konnektör yerinden çıkmış [Operatör masası anahtarı, kablo/konnektör]
  - Mekanik bağlantı cıvataları gevşek/yerinden çıkmış [Merdane/yatak]

3) Fishbone (İshikawa) İpuçları Eşlemesi
- Makine: arızalı switch/solenoid/encoder, gevşek cıvata, güç kaynağı dengesizliği, donanım arızası.
- Metot: yanlış sayfa/seçim (HMI/GOT “rols in mill”), hatalı ayar/prosedür, yanlış reset/sekans.
- Ölçüm: sensör hizasızlığı/kalibrasyon, kirli lamba, yanlış referans/measuring sinyali.
- İnsan: konnektör/kablo çıkması, hatalı konfigürasyon/yanlış seçim.
- Malzeme: arızada yedek parça kalite şüphesi (Varsayım, kanıt istenir).
- Ortam: kirlenme, titreşim, sıcaklık.

4) Aksiyon Değerlendirme Kalıpları
- “Konnektör sök-tak” veya “reset” sonrası “normal çalışıyor” → geçici düzeltme olasılığı yüksek; tekrarlama riski: Orta/Yüksek.
- “Ayar yapıldı/temizlik yapıldı” → kalıcılık için izleme gerekir; kirlenme kaynağı/ayar standardı sorgulanır.
- “Yedekle değiştirildi” → kalıcı olabilir; arızalı parça kök nedeni (yaşlanma/ortam) araştırılmalı.
- “Program/sekans incelendi-düzeltildi” → Metot kaynaklı kök neden olası; değişiklik kaydı/versiyonlama kanıtı istenir.

5) Terimler Sözlüğü (çıkarılan anahtar terimler)
EPC (tension reel), fotoswitch (I 1.7 vb.), absocoder/encoder, deflectör merdanesi, outboard bearing/destek, bobin arabası, doğrultucu, kriko, kalınlık ölçme cihazı, X-ray, shutter, solenoid, magazine, JB-3 paneli, 24V power supply, HMI/GOT, Unico PN 923-227, Profibus, Can bus, UPS, temper.

Notlar
- Her çıkarımda metinden kısa alıntı veya sayfa/satır referansı ver; emin değilsen “Varsayım” de ve kanıt iste.
- Süre/dakika hesabında ondalık virgülü noktaya çevirerek dakika hesapla; emin değilsen kullanıcıdan süre alanı doğrulaması iste.
---

