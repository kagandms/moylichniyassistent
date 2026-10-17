"""
macOS Yerel Bildirim, Sesli Uyarıcı ve Yanıt Penceresi (src/actuators/notifier.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

1. Görsel macOS bildirimleri (Notification Center).
2. Çok Dilli (TR: Yelda, RU: Milena, EN: Samantha) sesli okuma (say -v).
3. Kaybolmayan zengin macOS yanıt diyalog kutusu (display dialog):
   - '📋 Kopyala': Cevabı panoya kopyalar.
   - '🎙️ Yeni Komut': Hemen yeni komut penceresini açar.
   - 'Tamam': Pencereyi kapatır.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional, Set

logger = logging.getLogger("mac_assistant.actuators.notifier")


class SystemNotifier:
    """
    macOS yerleşik bildirim merkezi, çok dilli sesli geri bildirim ve yanıt penceresi sınıfı.
    """

    def __init__(self, default_title: str = "Mac Agent Asistan") -> None:
        self.default_title = default_title
        self._voices_scanned = False
        self._available_voices: Set[str] = set()

    def _scan_available_voices(self) -> None:
        """Sistemde kurulu sesleri bir kez tarar."""
        if self._voices_scanned:
            return
        try:
            out = subprocess.check_output(["say", "-v", "?"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                parts = line.split()
                if parts:
                    self._available_voices.add(parts[0])
        except Exception as e:
            logger.debug(f"Ses tarama hatası: {e}")
        self._voices_scanned = True

    def detect_voice(self, text: str) -> Optional[str]:
        """
        Metnin dilini analiz ederek en uygun macOS sesini seçer:
        - Rusça karakterler varsa -> Milena
        - Türkçe karakter veya kelimeler varsa -> Yelda
        - İngilizce kelimeler veya genel -> Samantha
        """
        self._scan_available_voices()

        # 1. Rusça (Kiril karakter kontrolü)
        if any("\u0400" <= ch <= "\u04ff" for ch in text):
            if "Milena" in self._available_voices:
                return "Milena"

        # 2. Türkçe karakter veya kelime kontrolü
        tr_chars = set("çÇğĞıİöÖşŞüÜ")
        if any(ch in tr_chars for ch in text):
            if "Yelda" in self._available_voices:
                return "Yelda"

        words_lower = set(text.lower().replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split())
        tr_keywords = {
            "ve", "ile", "için", "tamam", "açıldı", "kapatıldı", "merhaba", "selam",
            "nedir", "nasıl", "bilgisayar", "evet", "hayır", "fıkra", "anlat",
            "saat", "bugün", "hava", "durumu", "kopyala", "bulundu", "bulunamadı"
        }
        if words_lower.intersection(tr_keywords):
            if "Yelda" in self._available_voices:
                return "Yelda"

        # 3. İngilizce kelimeler
        en_keywords = {"the", "and", "is", "opened", "closed", "hello", "hi", "how", "what", "computer", "tell", "joke"}
        if words_lower.intersection(en_keywords):
            if "Samantha" in self._available_voices:
                return "Samantha"

        # Varsayılan: Eğer Yelda varsa Yelda, yoksa Samantha, yoksa sistem varsayılanı
        if "Yelda" in self._available_voices:
            return "Yelda"
        if "Samantha" in self._available_voices:
            return "Samantha"
        return None

    def notify(
        self,
        message: str,
        title: Optional[str] = None,
        subtitle: str = "",
        sound: str = "default",
        speak: bool = False,
        show_dialog: bool = False,
        dialog_timeout: int = 25
    ) -> str:
        """
        macOS Bildirim Merkezi üzerinden görsel banner gösterir.
        speak=True ise eş zamanlı olarak seslendirir.
        show_dialog=True ise ekranda kaybolmayan yanıt diyalog kutusu açar.

        Döndürür: 'ok', 'copy', 'new_command' (diyalog açıldıysa) veya 'banner_shown'
        """
        notif_title = title or self.default_title
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

        # Sesli okuma
        if speak:
            self.speak_text(message)

        # Görünür yanıt kutusu (diyalog penceresi)
        if show_dialog:
            return self.show_response_popup(message, title=notif_title, timeout=dialog_timeout)

        return "banner_shown"

    def speak_text(self, text: str) -> None:
        """
        Metni macOS 'say' komutuyla arka planda (asenkron, non-blocking) seslendirir.
        Dile göre TR: Yelda, RU: Milena, EN: Samantha kullanılır.
        """
        voice = self.detect_voice(text)
        cmd = ["say"]
        if voice:
            cmd.extend(["-v", voice])
        cmd.append(text)

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"🔊 [Seslendirme ({voice or 'default'})] '{text}'")
        except Exception as e:
            logger.debug(f"Seslendirme hatası: {e}")

    def show_response_popup(
        self,
        message: str,
        title: str = "🤖 Mac Agent Asistan",
        timeout: int = 25
    ) -> str:
        """
        Ekranda kaybolmayan temiz bir macOS yanıt diyalog kutusu açar:
        - '📋 Kopyala': Yanıtı panoya kopyalar.
        - '🎙️ Yeni Komut': Yeni komut dinlemeye yönlendirir.
        - 'Tamam' veya timeout: Pencereyi kapatır.

        Döndürdüğü değer: 'ok' | 'copy' | 'new_command'
        """
        clean_msg = message.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")
        clean_title = title.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")

        script = f'''
        set dialogResult to display dialog "{clean_msg}" ¬
            with title "{clean_title}" ¬
            buttons {{"📋 Kopyala", "🎙️ Yeni Komut", "Tamam"}} ¬
            default button "Tamam" ¬
            giving up after {timeout}
        return "BUTTON:" & (button returned of dialogResult) & "|GAVEUP:" & (gave up of dialogResult)
        '''

        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout + 5
            )

            output = (res.stdout or "").strip()

            if "BUTTON:📋 Kopyala" in output:
                # Panoya kopyala
                try:
                    subprocess.run(["pbcopy"], input=message.encode("utf-8"), check=False, timeout=2)
                    self.notify("📋 Cevap panoya kopyalandı.", sound="Glass")
                except Exception as cp_err:
                    logger.debug(f"Panoya kopyalama hatası: {cp_err}")
                return "copy"

            if "BUTTON:🎙️ Yeni Komut" in output:
                logger.info("🎙️ Kullanıcı yanıt kutusundan 'Yeni Komut' talep etti.")
                return "new_command"

            return "ok"

        except Exception as e:
            logger.debug(f"Diyalog gösterme hatası: {e}")
            return "ok"
