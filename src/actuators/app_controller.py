"""
macOS Uygulama ve Web Kontrolcüsü (src/actuators/app_controller.py)
Uygulama açma, kapatma, web sitelerini Yandex Browser'da açma ve akıllı web fallback işlevlerini yönetir.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("mac_assistant.actuators.app_controller")

# Yaygın takma adları standart macOS uygulama adlarına eşleme
APP_ALIASES = {
    "antigravity": "Antigravity",
    "antigravityi": "Antigravity",
    "antigravity'yi": "Antigravity",
    "yandex": "Yandex",
    "yandex browser": "Yandex",
    "yandexi": "Yandex",
    "yandex'i": "Yandex",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "notlar": "Notes",
    "notes": "Notes",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "finder": "Finder",
    "hesap makinesi": "Calculator",
    "calculator": "Calculator",
    "ayarlar": "System Settings",
    "system settings": "System Settings",
    "sistem ayarları": "System Settings",
    "mesajlar": "Messages",
    "messages": "Messages",
    "haritalar": "Maps",
    "maps": "Maps",
    "muzik": "Music",
    "müzik": "Music",
    "music": "Music",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "spotify": "Spotify",
}

# Bilinen popüler web servisleri ve doğrudan URL eşlemeleri
KNOWN_WEB_SERVICES = {
    "youtube": "https://www.youtube.com",
    "youtubu": "https://www.youtube.com",
    "youtubeu": "https://www.youtube.com",
    "youtube'u": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://github.com",
    "githubı": "https://github.com",
    "github'ı": "https://github.com",
    "gmail": "https://mail.google.com",
    "gmail'i": "https://mail.google.com",
    "gmaili": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "chatgpt'yi": "https://chatgpt.com",
    "chatgptyi": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "geminiyi": "https://gemini.google.com",
    "gemini'yi": "https://gemini.google.com",
    "google gemini": "https://gemini.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "netflix": "https://www.netflix.com",
    "netflixi": "https://www.netflix.com",
    "netflix'i": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "instagramı": "https://www.instagram.com",
    "instagram'ı": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "linkedini": "https://www.linkedin.com",
    "google": "https://www.google.com",
    "googleı": "https://www.google.com",
    "yandex web": "https://ya.ru",
    "reddit": "https://www.reddit.com",
    "spotify web": "https://open.spotify.com",
}


def normalize_app_name(raw_name: str) -> str:
    """Kullanıcının söylediği veya modelin ürettiği uygulama adını standartlaştırır."""
    cleaned = raw_name.strip().strip("'\"").strip()
    lower = cleaned.lower()

    # Türkçe ekleri temizleme: "antigravityi" -> "antigravity", "youtubu" -> "youtube"
    for suffix in ("'yi", "'yı", "'i", "'ı", "'yu", "'yü", "'u", "'ü", "yi", "yı", "i", "ı", "yu", "yü", "bu", "bı", "bi", "u", "ü"):
        if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
            base = lower[:-len(suffix)]
            if base in APP_ALIASES:
                return APP_ALIASES[base]
            if base in KNOWN_WEB_SERVICES:
                return base.capitalize()

    if lower in APP_ALIASES:
        return APP_ALIASES[lower]

    return cleaned


def normalize_url_or_search(raw_target: str) -> str:
    """
    Parametreyi analiz edip garantili bir web URL'sine veya arama motoru URL'sine çevirir:
    - 'https://...' veya 'http://...' -> Aynen korunur.
    - 'youtube', 'github', 'chatgpt' vb. -> https://www.youtube.com
    - 'youtube.com', 'google.com' -> https://youtube.com
    - 'istanbul hava durumu', 'dolar kuru' -> https://www.google.com/search?q=...
    """
    import urllib.parse

    cleaned = raw_target.strip().strip("'\"").strip()
    lower = cleaned.lower()

    # Kullanıcı "yandex'ten youtube.com sitesini aç" gibi komut metnini parametreye geçirmişse temizle
    for prefix in ("yandex'ten ", "yandex'te ", "yandex ", "tarayıcıdan ", "tarayıcıda "):
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            lower = cleaned.lower()
            break

    for suffix in (" sitesini aç", " sitesi aç", " sitesine git", " sitesini", " sitesi", " aç", " git", " ara"):
        if lower.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
            lower = cleaned.lower()
            break

    # 1. Zaten tam URL mi?
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    # 2. Bilinen servisler veya Türkçe ekler
    clean_key = lower
    for suffix in ("'yi", "'yı", "'i", "'ı", "'yu", "'yü", "'u", "'ü", "yi", "yı", "i", "ı", "yu", "yü", "bu", "u", "ü"):
        if clean_key.endswith(suffix) and len(clean_key) > len(suffix) + 2:
            base = clean_key[:-len(suffix)]
            if base in KNOWN_WEB_SERVICES:
                clean_key = base
                break

    if clean_key in KNOWN_WEB_SERVICES:
        return KNOWN_WEB_SERVICES[clean_key]

    # 3. Domain içeriyor mu? (Boşluksuz ve nokta içeren: örn: youtube.com, github.com)
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"

    # 4. Arama sorgusu (örn: 'istanbul hava durumu')
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(cleaned)}"


class AppController:
    """macOS uygulamalarını ve web sitelerini açma, kapatma ve kontrol yöneticisi."""

    @staticmethod
    def is_running(app_name: str) -> bool:
        """Uygulamanın çalışıp çalışmadığını System Events ile kontrol eder."""
        target = normalize_app_name(app_name)
        apple_script = f'''
        tell application "System Events"
            set isRunning to (count (every process whose name contains "{target}")) > 0
        end tell
        return isRunning
        '''
        try:
            res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=5)
            return res.stdout.strip().lower() == "true"
        except Exception:
            return False

    @classmethod
    def open_url_in_browser(cls, url: str, browser_name: str = "Yandex") -> bool:
        """
        Belirtilen URL veya arama sorgusunu normalize eder ve Yandex Browser'da
        AppleScript ile garantili olarak YENİ SEKME açıp en öne getirir.
        """
        target_url = normalize_url_or_search(url)
        logger.info(f"🌐 [Web Açıcı] '{url}' -> '{target_url}' (Tarayıcı: {browser_name}) yeni sekmede açılıyor...")

        # 1. Öncelik: AppleScript ile Yandex'te garantili YENİ SEKME açma ve öne getirme
        apple_script = f'''
        tell application "{browser_name}"
            activate
            if (count of windows) = 0 then
                make new window
            end if
            tell front window
                set newTab to make new tab at end of tabs with properties {{URL:"{target_url}"}}
                set active tab index to (count of tabs)
            end tell
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=6)
            if res.returncode == 0:
                logger.info(f"✅ [Web Açıcı] '{target_url}' {browser_name} içinde yeni sekmede başarıyla açıldı.")
                return True
            else:
                logger.debug(f"AppleScript yeni sekme uyarısı: {res.stderr.strip()}")
        except Exception as as_err:
            logger.debug(f"AppleScript sekme açma hatası: {as_err}")

        # 2. Fallback: 'open -a Yandex <url>'
        try:
            res = subprocess.run(["open", "-a", browser_name, target_url], capture_output=True, text=True, timeout=5)
            subprocess.run(["osascript", "-e", f'tell application "{browser_name}" to activate'], capture_output=True, timeout=3)
            if res.returncode == 0:
                return True
        except Exception as e:
            logger.debug(f"{browser_name} open -a denemesi başarısız: {e}")

        # 3. Fallback: Genel sistem varsayılan tarayıcısı
        try:
            res = subprocess.run(["open", target_url], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception as e:
            logger.error(f"Genel URL açma hatası: {e}")
            return False

    @classmethod
    def open_app(cls, app_name: str) -> Tuple[bool, str]:
        """
        Belirtilen uygulamayı başlatır veya ön plana getirir.
        Eğer hedef bir web servisi ise veya masaüstü uygulaması bulunamazsa
        akıllı web fallback mekanizması devreye girerek Yandex Browser'da açar.
        
        Döndürür: (başarılı_mı, açılan_hedef_türü_ve_adı)
        """
        raw_clean = app_name.strip().strip("'\"").strip()
        lower_raw = raw_clean.lower()

        # 0. Adım: Bilinen bir web servisi veya URL mi?
        cleaned_web = lower_raw
        for suffix in ("'yi", "'yı", "'i", "'ı", "'yu", "'yü", "'u", "'ü", "yi", "yı", "i", "ı", "yu", "yü", "bu", "u", "ü"):
            if cleaned_web.endswith(suffix) and len(cleaned_web) > len(suffix) + 2:
                base = cleaned_web[:-len(suffix)]
                if base in KNOWN_WEB_SERVICES:
                    cleaned_web = base
                    break

        if (
            cleaned_web in KNOWN_WEB_SERVICES
            or lower_raw in KNOWN_WEB_SERVICES
            or any(ext in lower_raw for ext in [".com", ".org", ".net", ".io", ".dev", "http://", "https://"])
        ):
            url = KNOWN_WEB_SERVICES.get(cleaned_web) or KNOWN_WEB_SERVICES.get(lower_raw) or (lower_raw if lower_raw.startswith("http") else f"https://{lower_raw}")
            ok = cls.open_url_in_browser(url)
            return ok, f"web:{url}"

        target = normalize_app_name(app_name)
        logger.info(f"🚀 Uygulama açılıyor: {target}")

        # 1. Deneme: AppleScript ile activate
        apple_script = f'tell application "{target}" to activate'
        try:
            res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True, f"app:{target}"
        except Exception as e:
            logger.debug(f"AppleScript activate denemesi başarısız: {e}")

        # 2. Deneme: open -a
        try:
            res = subprocess.run(["open", "-a", target], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True, f"app:{target}"
        except Exception as e:
            logger.debug(f"open -a komutu başarısız: {e}")

        # 3. Deneme: Bilinen bir web servisi ile eşleşiyorsa Yandex Browser'da aç
        matching_web_url = None
        words = set(lower_raw.replace("_", " ").replace("-", " ").split())
        for service_key, service_url in KNOWN_WEB_SERVICES.items():
            if len(service_key) <= 2:
                if service_key in words or service_key == lower_raw or service_key == cleaned_web:
                    matching_web_url = service_url
                    break
            else:
                if service_key == lower_raw or service_key == cleaned_web or service_key in lower_raw or service_key in cleaned_web:
                    matching_web_url = service_url
                    break

        if matching_web_url:
            logger.info(f"🌐 [Akıllı Web Fallback] '{target}' yerel uygulaması bulunamadı, web servisi açılıyor: {matching_web_url}")
            ok = cls.open_url_in_browser(matching_web_url)
            if ok:
                return True, f"web:{matching_web_url}"

        return False, f"failed:{target}"

    @staticmethod
    def close_app(app_name: str) -> bool:
        """Belirtilen uygulamayı nazikçe kapatır (quit)."""
        target = normalize_app_name(app_name)
        logger.info(f"🛑 Uygulama kapatılıyor: {target}")

        # 1. Deneme: AppleScript ile zarifçe kapat (quit)
        apple_script = f'tell application "{target}" to quit'
        try:
            res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
        except Exception as e:
            logger.debug(f"AppleScript quit denemesi başarısız: {e}")

        # 2. Deneme: System Events üzerinden kill/quit
        as_force = f'''
        tell application "System Events"
            set procs to (every process whose name contains "{target}")
            repeat with proc in procs
                do shell script "kill -15 " & (unix id of proc)
            end repeat
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", as_force], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception as e:
            logger.debug(f"System Events quit denemesi başarısız: {e}")

        # 3. Deneme: pkill -f
        try:
            res = subprocess.run(["pkill", "-f", target], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception as e:
            logger.error(f"pkill hatası: {e}")
            return False
