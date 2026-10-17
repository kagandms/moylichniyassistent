# 🚀 MacBook Air M2 — Agentic Sesli ve Yazılı PC Asistanı

> **MacBook Air M2 (Apple Silicon - Fansız Tasarım)** için özel olarak geliştirilmiş; sıfır bütçeli, ultra düşük kaynak tüketimli, sesli ve yazılı komutlarla macOS masaüstünü ve **Yandex Browser** içindeki açık **Google Gemini** sekmesini kontrol eden otonom masaüstü AI ajanı.

---

## 🌟 Temel Mimari Prensipler (Neden Farklı?)

1. **Sıfır Boşta RAM Mimarisi (Zero-Idle-RAM Architecture):**
   - Asistan boşta beklerken sistem RAM tüketimi **<50 MB** seviyesindedir.
   - Yerel LLM modelleri (Ollama vb.) bellekte kalıcı tutulmaz; sadece çevrimdışıyken veya yerel mod istendiğinde istekle yüklenir, iş bitince `keep_alive=0` ile **RAM'den derhal tahliye edilir**.
   - Varsayılan olarak Google Gemini Flash API kullanılarak **0 MB yerel model RAM yükü** ile çalışır.
2. **Bluetooth HFP Ses Kalitesi ve Mikrofon Koruması:**
   - 7/24 arka planda dinleyen mikrofon iş parçacıkları **kesinlikle yasaktır**. (AirPods vb. kulaklıklarda mikrofon açık kaldığında macOS otomatik olarak Hands-Free Profile (HFP) moduna geçerek ses çıkışını 48kHz stereo'dan 16kHz teneke sesine düşürür ve bataryayı tüketir).
   - Mikrofon yalnızca `Option + Space` kısayoluna basılıp sesli konuşma seçildiğinde açılır; konuşma bittiğinde **1.5 sn sessizlik tespitiyle (VAD)** mikrofon donanımı tamamen kapatılır.
3. **Mevcut Yandex Browser Oturumuna Doğrudan Bağlantı:**
   - Selenium veya Playwright gibi 500+ MB RAM tüketen ve oturumu olmayan harici tarayıcılar açılmaz.
   - Kullanıcının halihazırda açık olan **Yandex Browser** uygulamasındaki açık Gemini sekmesi AppleScript ve DOM JavaScript enjeksiyonu ile doğrudan yönetilir.
4. **Pano (Clipboard) %100 Hijyen Güvencesi:**
   - Asistan metin yakalamak veya yapıştırmak için panoyu kullandığında, kullanıcının orijinal panosu (şifre, link vb.) işlem öncesinde anlık yedeklenir (`snapshot`) ve işlem sonunda **kuruşu kuruşuna geri yüklenir**.

---

## 🏗️ 5 Fazlı Proje Mimarisi

| Faz | Kapsam | Durum | Ana Bileşenler |
| :--- | :--- | :---: | :--- |
| **Faz 1** | **Proje İskeleti, Anayasa & Hibrit Beyin** | ✅ Tamamlandı | `AGENTS.md`, `config.py`, `schemas.py`, `orchestrator.py` |
| **Faz 2** | **Durum Hafızası, Pencere Takibi & Pano Hijyeni** | ✅ Tamamlandı | `clipboard.py`, `window_tracker.py`, `manager.py` |
| **Faz 3** | **Algılama Katmanı (Vision OCR + VAD + STT)** | ✅ Tamamlandı | `ocr.py`, `audio.py`, `stt.py`, `trigger.py` |
| **Faz 4** | **Eyleyici Katmanı & Yandex DOM Köprüsü** | ✅ Tamamlandı | `yandex_gemini.py`, `notifier.py`, `manager.py` |
| **Faz 5** | **Uçtan Uca Entegrasyon, Kısayol & Başlatıcı** | ✅ Tamamlandı | `runtime.py`, `baslat.command`, `main.py` |

---

## ⚡ Hızlı Başlangıç

### 1. Çift Tıklama ile Başlatma (En Kolay Yol)
Finder üzerinden proje klasöründeki **`baslat.command`** dosyasına çift tıklayın. Karşınıza interaktif terminal menüsü gelecektir:
- `[1]` Kısayol Dinleyicisini Başlat (`Option + Space`)
- `[2]` Hemen Komut Ver (Spotlight Giriş Penceresi)
- `[3]` Sistem Sağlık Kontrolü (Diagnostics)
- `[4]` Uçtan Uca (E2E) Sistem Kabul Testi
- `[5]` Yerel LLM Bellek Temizliği

### 2. Terminal ile Başlatma
```bash
# Sanal ortamı aktifleştir
source .venv/bin/activate

# Option + Space arka plan servisini başlat
python main.py --listen

# Veya tek seferlik hızlı komut penceresini aç
python main.py --once

# Veya doğrudan komut çalıştır
python main.py --cmd "Ekranda yer alan çıktıyı kopyala, Yandex'teki Gemini'ye sor ve cevabı buraya yapıştır"
```

---

## ⚙️ Yandex Browser Yapılandırması (Önemli)

Yandex Browser içindeki açık Gemini sekmesine AppleScript üzerinden komut gönderebilmek için:

1. Yandex Browser'ı açın.
2. Üst menü çubuğundan: **Вид (Görünüm) > Разработчикам (Geliştirici)** menüsüne gidin.
3. **Разрешить JavaScript из событий Apple (Apple Olaylarından JavaScript'e İzin Ver)** seçeneğini işaretleyin.

> **Not:** Bu ayar kapalı olsa bile asistan çökmeyecek, savunmacı hata yönetimi sayesinde kesintisiz olarak Gemini API fallback mekanizması üzerinden çalışmaya devam edecektir.

---

## 🔐 macOS İzinleri Rehberi

Asistanın ilk çalışmasında macOS tarafından şu izinler talep edilebilir:
- **Erişilebilirlik (Accessibility):** `Cmd+C` / `Cmd+V` tuş simülasyonu ve pencereler arası odak değişimi için gereklidir (*Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik*).
- **Ekran Kaydı (Screen Recording):** Seçili metin olmadığında ekrandaki hatayı okumak (Apple Vision OCR) için gereklidir (*Sistem Ayarları > Gizlilik ve Güvenlik > Ekran Kaydı*).
- **Mikrofon (Microphone):** Yalnızca sesli komut modunu seçtiğinizde konuşabilmeniz için gereklidir.

---

## 🧪 Sistem Test Komutları

```bash
# Uçtan Uca (E2E) Full Pipeline Testi:
.venv/bin/python main.py --test-e2e

# Sistem Sağlık ve Donanım Teşhisi:
.venv/bin/python main.py --health-check

# Durum Hafızası & Pano Hijyen Testi:
.venv/bin/python main.py --test-state

# Apple Vision OCR & VAD Ses Testi:
.venv/bin/python main.py --test-perception

# Yandex Browser Gemini DOM Köprü Testi:
.venv/bin/python main.py --test-actuators
```
