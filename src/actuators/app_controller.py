"""
macOS Uygulama Kontrolcüsü (src/actuators/app_controller.py)
Uygulama açma, kapatma ve kontrol işlevlerini yönetir.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

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


def normalize_app_name(raw_name: str) -> str:
    """Kullanıcının söylediği veya modelin ürettiği uygulama adını standartlaştırır."""
    cleaned = raw_name.strip().strip("'\"").strip()
    lower = cleaned.lower()

    # Türkçe ekleri temizleme: "antigravityi" -> "antigravity"
    for suffix in ("'yi", "'yı", "'i", "'ı", "'yu", "'yü", "yi", "yı", "i", "ı"):
        if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
            base = lower[:-len(suffix)]
            if base in APP_ALIASES:
                return APP_ALIASES[base]

    if lower in APP_ALIASES:
        return APP_ALIASES[lower]

    return cleaned


class AppController:
    """macOS uygulamalarını açma, kapatma ve durumlarını denetleme yöneticisi."""

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

    @staticmethod
    def open_app(app_name: str) -> bool:
        """Belirtilen uygulamayı başlatır veya ön plana getirir."""
        target = normalize_app_name(app_name)
        logger.info(f"🚀 Uygulama açılıyor: {target}")

        # 1. Deneme: AppleScript ile activate
        apple_script = f'tell application "{target}" to activate'
        try:
            res = subprocess.run(["osascript", "-e", apple_script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
        except Exception as e:
            logger.debug(f"AppleScript activate denemesi başarısız: {e}")

        # 2. Deneme: open -a
        try:
            res = subprocess.run(["open", "-a", target], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception as e:
            logger.error(f"open -a komutu başarısız: {e}")
            return False

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
