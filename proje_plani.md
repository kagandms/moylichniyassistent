# PROJE PLANI VE MİMARİ KARAR KAYDI (ADR)

**Proje:** MacBook Air M2 Agentic Sesli ve Yazılı PC Asistanı  
**Hedef Donanım:** Apple Silicon M2, 8/16 GB Unified Memory, macOS Sonoma/Sequoia  
**Temel Felsefe:** Sıfır bütçe, ultra düşük RAM/pil tüketimi, sıfır boşta bellek (Zero-Idle-RAM), AppleScript yerel entegrasyonu.

---

## 1. MİMARİ KARAR KAYITLARI (ADR - Architectural Decision Records)

### ADR-01: Zero-Idle-RAM & Hibrit Beyin (Cloud Gemini + Ollama On-Demand)
- **Bağlam:** MacBook Air M2 fansız bir kasaya ve sınırlı paylaşımlı belleğe (Unified Memory) sahiptir. Yerel 7B model bellekte tutulduğunda 4.5-5.5 GB RAM sürekli kilitlenir.
- **Karar:**
  1. Varsayılan mod (`cloud`): Google Gemini Flash API (ücretsiz katman). Yerel makinede 0 MB RAM tüketir.
  2. Çevrimdışı/Yedek mod (`local`): Yerel Ollama (`qwen2.5:7b` veya `llama3.2:3b`).
  3. `auto` modu: İnternet varsa Gemini Cloud çağrılır ve yerel model `keep_alive=0` ile RAM'den tahliye edilir. İnternet kesilirse Ollama `keep_alive="5m"` ile anlık devreye girer.

### ADR-02: Bluetooth HFP Sorunu ve Event-Driven Tetikleme (`Option + Space`)
- **Bağlam:** Sürekli açık kalan mikrofon iş parçacıkları AirPods ve Bluetooth kulaklıkları hands-free profile (HFP) moduna sokarak sistem ses çıkışını 16kHz mono teneke sesine düşürür ve bataryayı hızla bitirir.
- **Karar:** Mikrofon asla 7/24 dinlemede kalmaz. Yalnızca kullanıcı klavyeden `Option + Space` bastığında kayıt başlar, ses bittiğinde (VAD) mikrofon donanımı kapatılır.

### ADR-03: Selenium/Playwright Yerine AppleScript + DOM Enjeksiyonu
- **Bağlam:** Selenium veya Playwright başlatıldığında 500+ MB RAM harcayan yeni bir tarayıcı örneği açılır ve kullanıcının oturum açtığı Google/Gemini oturumu kullanılamaz.
- **Karar:** Kullanıcının zaten açık olan **Yandex Browser** (`application "Yandex"`) penceresi AppleScript üzerinden hedeflenir. Açık olan Gemini sekmesi tespit edilip JavaScript ile prompt gönderilir ve sonuç okunur.

### ADR-04: Pano (Clipboard) Koruması ve Geri Yükleme Protokolü
- **Bağlam:** Otomasyon esnasında `Cmd+C` / `Cmd+V` yapıldığında kullanıcının panosundaki önemli veri ezilebilir.
- **Karar:** Herhangi bir kopyalama/yapıştırma öncesinde panonun anlık görüntüsü alınır; işlem bittiğinde kullanıcının orijinal panosu birebir geri yüklenir.

---

## 2. 5 FAZLI GELİŞTİRME YOL HARİTASI

| Faz | Kapsam | Durum | Çıktılar |
| :--- | :--- | :---: | :--- |
| **Faz 1** | **Proje İskeleti, Anayasa & Hibrit Beyin** | **Tamamlandı** | `AGENTS.md`, `config.py`, `schemas.py`, `orchestrator.py`, `main.py` |
| **Faz 2** | **Sistem Durumu & Pano/Pencere İzleme** | **Tamamlandı** | `clipboard.py`, `window_tracker.py`, `manager.py`, `main.py --test-state` |
| **Faz 3** | **Algı Katmanı (MLX Whisper STT & Apple Vision OCR)** | **Tamamlandı** | `ocr.py`, `audio.py`, `stt.py`, `trigger.py`, `main.py --test-perception` |
| **Faz 4** | **Eyleyici Katmanı & Yandex DOM Köprüsü** | **Tamamlandı** | `yandex_gemini.py`, `notifier.py`, `manager.py`, `main.py --test-actuators` |
| **Faz 5** | **Uçtan Uca Entegrasyon & Sağlamlaştırma** | Sıradaki | Tam otonom döngü, arka plan servis modu, bildirimler ve canlı kullanım |

---

## 3. FAZ DETAYLI GÖREV LİSTESİ

### Faz 1 (Tamamlandı)
- [x] Temel dosya mimarisi ve Python sanal ortamı kurulumu (`uv venv`, `requirements.txt`).
- [x] Proje Anayasası (`AGENTS.md`) ve Mimari Plan (`proje_plani.md`) oluşturulması.
- [x] `.env.example` ve `.gitignore` yapılandırması.
- [x] Merkezi konfigürasyon modülü (`config.py`).
- [x] Pydantic v2 tabanlı yapısal plan şemaları (`src/brain/schemas.py`).
- [x] Hibrit Karar Beyni (`src/brain/orchestrator.py` - Gemini Flash + Ollama Fallback + Lazy Unload).
- [x] Gelecek fazlar için iskelet dizinleri (`src/state`, `src/perception`, `src/actuators`).
- [x] Komut satırı sağlık kontrolü ve test aracı (`main.py --health-check`, `--test-brain`).

### Faz 2 (Tamamlandı)
- [x] AppKit `NSPasteboard` tabanlı yüksek hızlı pano okuma, yazma ve `changeCount` takibi (`src/state/clipboard.py`).
- [x] Pano içeriği anlık yedekleme (`snapshot`) ve %100 doğrulukla geri yükleme (`restore`).
- [x] Pano hijyeni için hata korumalı bağlam yöneticisi (`with clipboard.preserve_clipboard():`).
- [x] `NSWorkspace` ile <10ms içinde aktif uygulama tespiti (`bundle_id`, `pid`, `app_name`) (`src/state/window_tracker.py`).
- [x] `NSRunningApplication` ve AppleScript yedekli kaynak pencereye geri odaklanma (`focus_app`).
- [x] Nöbetçi token (sentinel) ve savunmacı tuş simülasyonu ile seçili metin yakalama (`src/state/manager.py`).
- [x] Erişilebilirlik izni kontrolü (`AXIsProcessTrusted`) ve seçim yoksa Faz 3 OCR sinyallemesi.
- [x] CLI kabul testleri ve görsel pano hijyen raporu (`python main.py --test-state`).

### Faz 3 (Tamamlandı)
- [x] Apple Vision Framework (`VNRecognizeTextRequest`) ile yerel, sıfır boşta RAM ekran ve görsel OCR (`src/perception/ocr.py`).
- [x] Bluetooth HFP korumalı, sadece çağrıldığında açılan on-demand mikrofon ve RMS/VAD sessizlik tespiti (`src/perception/audio.py`).
- [x] MLX Whisper + Gemini Cloud Audio hibrit STT motoru (`src/perception/stt.py`).
- [x] Spotlight tarzı hızlı komut diyalogu ve Option+Space kısayol dinleyicisi (`src/perception/trigger.py`).
- [x] Seçili metin yoksa otomatik Apple Vision OCR'a düşen birleşik algılama yöneticisi (`src/perception/manager.py`).
- [x] CLI kabul testleri ve görsel algılama raporu (`python main.py --test-perception`).

### Faz 4 (Tamamlandı)
- [x] Yandex Browser açık sekmelerini tarama ve `gemini.google.com` sekmesini otomatik bulma/açma (`src/actuators/yandex_gemini.py`).
- [x] AppleScript üzerinden DOM JavaScript enjeksiyonu ve streaming yanıt takibi.
- [x] Savunmacı Apple Events JS izin kontrolü (`Görünüm > Geliştirici`) ve API fallback desteği.
- [x] macOS yerel Bildirim Merkezi ve Türkçe `say` TTS seslendirici (`src/actuators/notifier.py`).
- [x] State, Perception ve Actuator katmanlarını birleştiren uçtan uca plan yürütücüsü (`src/actuators/manager.py`).
- [x] CLI kabul testleri ve pano koruma doğrulaması (`python main.py --test-actuators`).
