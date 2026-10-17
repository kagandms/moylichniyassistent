"""
macOS Yerel Bildirim ve Sesli Uyarıcı (src/actuators/notifier.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Kullanıcıya görsel macOS bildirimleri (Notification Center)
ve arka planda non-blocking Türkçe sesli bildirim (say -v Yelda) gönderir.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

logger = logging.getLogger("mac_assistant.actuators.notifier")


class SystemNotifier:
    """
    macOS yerleşik bildirim merkezi ve sesli geri bildirim sınıfı.
    """

    def __init__(self, default_title: str = "Mac Agent Asistan") -> None:
        self.default_title = default_title
        self._voice_checked = False
        self._turkish_voice: Optional[str] = None

    def _get_turkish_voice(self) -> Optional[str]:
        """Sistemde kurulu Türkçe ses olup olmadığını denetler (Yelda vb.)."""
        if self._voice_checked:
            return self._turkish_voice

        try:
            out = subprocess.check_output(["say", "-v", "?"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if "tr_TR" in line or "Turkish" in line:
                    voice_name = line.split()[0]
                    self._turkish_voice = voice_name
                    break
        except Exception:
            self._turkish_voice = None

        self._voice_checked = True
        return self._turkish_voice

    def notify(
        self,
        message: str,
        title: Optional[str] = None,
        subtitle: str = "",
        sound: str = "default",
        speak: bool = False
    ) -> bool:
        """
        macOS Bildirim Merkezi üzerinden görsel banner gösterir.
        speak=True ise eş zamanlı olarak seslendirir.
        """
        notif_title = title or self.default_title
        # Tırnak işaretlerini güvenli escape et
        clean_msg = message.replace('"', '\\"').replace("'", "’")
        clean_title = notif_title.replace('"', '\\"').replace("'", "’")
        clean_sub = subtitle.replace('"', '\\"').replace("'", "’")

        sub_part = f'subtitle "{clean_sub}"' if clean_sub else ""
        sound_part = f'sound name "{sound}"' if sound else ""

        script = f'display notification "{clean_msg}" with title "{clean_title}" {sub_part} {sound_part}'

        try:
            subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=1.5
            )
            logger.info(f"🔔 [Bildirim] {notif_title}: '{message}'")
        except Exception as e:
            logger.debug(f"Bildirim gönderme hatası: {e}")
            return False

        if speak:
            self.speak_text(message)

        return True

    def speak_text(self, text: str) -> None:
        """
        Metni macOS 'say' komutuyla arka planda (asenkron, non-blocking) seslendirir.
        """
        voice = self._get_turkish_voice()
        cmd = ["say"]
        if voice:
            cmd.extend(["-v", voice])
        cmd.append(text)

        try:
            # Non-blocking arka plan işlemi
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.debug(f"🔊 [Seslendirme] '{text}'")
        except Exception as e:
            logger.debug(f"Seslendirme hatası: {e}")
