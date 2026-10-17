# PROJE ANAYASASI VE GELİŞTİRİCİ AJAN KURALLARI (AGENTS.md)

Bu belge, **MacBook Air M2 (Apple Silicon)** üzerinde çalışan sesli ve yazılı masaüstü AI asistanı projesinin temel anayasasıdır. Bu depoda kod yazan, refactor eden veya özellik ekleyen her AI asistanı ve geliştirici bu kurallara istisnasız uymak zorundadır.

---

## 1. DONANIM VE MİMARİ KISITLARI (APPLE SILICON M2)

1. **Fansız Kasa & Termal Disiplin:**
   - Proje MacBook Air M2 (fansız donanım) için geliştirilmektedir. Sürekli CPU/GPU veya RAM tüketen arka plan iş parçacıkları (threads/loops) **kesinlikle yasaktır**.
2. **Sıfır Boşta RAM Mimarisi (Zero-Idle-RAM Architecture):**
   - Asistan boşta beklerken sistem RAM tüketimi minimum düzeyde (<50 MB) olmalıdır.
   - Yerel LLM modelleri (Ollama / Llama / Qwen) sistem belleğinde **sürekli tutulamaz**.
   - Yerel model yalnızca internet bağlantısı olmadığında veya kullanıcı `local` modunu seçtiğinde yüklenmeli (`keep_alive="5m"`), işlem tamamlandığında veya bulut moduna geçildiğinde `keep_alive=0` API çağrısı ile bellekten anında tahliye (unload) edilmelidir.
3. **Bluetooth HFP Ses Kalitesi & Mikrofon Kuralı:**
   - Mikrofonun 7/24 arka planda sürekli dinlemede kalması **KESİNLİKLE YASAKTIR**.
   - Bluetooth kulaklıklarda (AirPods vb.) sürekli mikrofon açık kaldığında macOS otomatik olarak **HFP (Hands-Free Profile)** moduna geçerek ses kalitesini 48kHz stereo'dan 16kHz mono'ya düşürür ve aşırı batarya tüketir.
   - Mikrofon sadece kullanıcı `Option + Space` (`<alt>+<space>`) kısayoluna bastığında açılır, ses bitiminde (VAD - Voice Activity Detection) otomatik olarak kapanır.

---

## 2. TARAYICI VE OTOMASYON KURALLARI

1. **Selenium / Playwright / Puppeteer YASAKTIR:**
   - Yeni bir tarayıcı penceresi veya headless instance açmak kesinlikle yasaktır. Bu hem RAM israfına yol açar hem de kullanıcının aktif oturumunu (Gemini hesabı, çerezler vb.) kullanamaz.
2. **Yandex Browser Entegrasyonu:**
   - Hedef tarayıcı **Yandex Browser** (`application "Yandex"`)'dir.
   - Chromium tabanlı olduğu için kontrol `tell application "Yandex"` AppleScript ve DOM JavaScript enjeksiyonu üzerinden sağlanır.
   - Kullanıcının zaten açık olan oturumu, aktif sekmeleri ve Gemini sohbet penceresi doğrudan kullanılır.

---

## 3. PANO (CLIPBOARD) VE SİSTEM HİJYENİ

1. **Pano Kirletme Yasağı:**
   - Asistan metin yakalamak veya yapıştırmak için panoyu (`pbcopy` / `NSPasteboard`) kullandığında, işlem öncesinde mevcut pano içeriğini (metin, zengin metin, dosya referansı) yedeklemelidir.
   - İşlem bittikten sonra kullanıcının orijinal pano içeriği eksiksiz geri yüklenmelidir (`restore_clipboard`).
2. **Pencere Odak Yönetimi:**
   - Bir eylem tamamlandığında, kullanıcının çalıştığı kaynak uygulama penceresine odaklanılmalı ve odak kaybı yaşatılmamalıdır.

---

## 4. KODLAMA STANDARTLARI VE MİMARİ MODÜLERLİK

1. **Tip Güvenliği (Strict Type Hints):**
   - Tüm fonksiyonlar, metotlar ve veri modelleri Python 3.10+ tip ipuçları (`typing`, `Pydantic v2`) ile tanımlanmalıdır.
2. **Modüler Klasör Yapısı:**
   - `src/brain`: Hibrit Karar Beyni, şemalar ve LLM orkestrasyonu.
   - `src/state`: Aktif pencere takibi, pano hafızası ve durum yönetimi.
   - `src/perception`: MLX Whisper (STT) ve macOS native Vision OCR.
   - `src/actuators`: Yandex Browser AppleScript/DOM köprüsü ve klavye/fare eylemleri.
3. **Loglama ve Dil Desteği:**
   - Kullanıcıya yönelik bildirimler ve arayüz çıktıları temiz Türkçe olmalıdır.
   - Dahili hata ve debug logları uluslararası standartta, net ve izlenebilir İngilizce/Türkçe formatta yazılmalıdır.
4. **Hata Yönetimi ve Savunmacı Kodlama (Defensive Programming):**
   - Ağ kesintileri, API anahtarı eksikliği veya uygulamanın kapalı olması gibi durumlarda asistan çökmeyecek, kullanıcıya net teşhis mesajı ve alternatif eylem sunacaktır.

---

## 5. PROJE FAZLARI VE GELİŞTİRME YOL HARİTASI

- **Faz 1:** Proje Anayasası, İskelet ve Hibrit Karar Beyni *(Bu Aşama)*
- **Faz 2:** Sistem Durumu & Pano/Pencere İzleme (`Option+Space` Hotkey, Clipboard Snapshot & Restore)
- **Faz 3:** Algı Katmanı (MLX Whisper STT + Apple Vision OCR)
- **Faz 4:** Eyleyici Katmanı & Yandex Browser Gemini DOM Köprüsü (AppleScript + JS Enjeksiyonu)
- **Faz 5:** Uçtan Uca Entegrasyon, Testler ve Performans Optimizasyonu
