"""
Kısayol ve Komut Çubuğu Tetikleyici (src/perception/trigger.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

1. Option + Space (<alt>+<space>) genel klavye dinleyicisi (pynput).
2. macOS Spotlight tarzı yerel komut diyalogu (osascript display dialog).
"""

from __future__ import annotations

import logging
import subprocess
from typing import Callable, Optional, Tuple

import config

logger = logging.getLogger("mac_assistant.perception.trigger")

try:
    from pynput import keyboard
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False
    logger.warning("pynput bulunamadı, global klavye kısayolu dinlenemeyebilir.")


class CommandTrigger:
    """
    Kullanıcının asistanı klavyeden tetiklemesini veya Spotlight tarzı
    hızlı giriş kutusundan komut vermesini yöneten sınıf.
    """

    def __init__(self, hotkey: Optional[str] = None) -> None:
        self.hotkey = hotkey or config.HOTKEY
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def prompt_user_command(self) -> Tuple[str, str]:
        """
        macOS yerel Spotlight benzeri bir diyalog penceresi açar.
        Kullanıcı doğrudan metin yazabilir veya sesli konuşmayı seçebilir.

        Döndürdüğü değer: (mode, payload)
        - ('text', 'yazılan metin')
        - ('voice', '') -> Kullanıcı sesli konuşmak istiyor
        - ('cancel', '') -> İptal edildi
        """
        script = '''
        set dialogResult to display dialog "Masaüstü Asistanı için komutunuzu girin veya '🎙️ Sesli Konuş' butonuna basın:" ¬
            default answer "" ¬
            with title "MacBook Air M2 Asistan" ¬
            buttons {"Vazgeç", "🎙️ Sesli Konuş", "Çalıştır"} ¬
            default button "Çalıştır" ¬
            with icon note
        return "BUTTON:" & (button returned of dialogResult) & "|TEXT:" & (text returned of dialogResult)
        '''
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=60.0
            )

            if res.returncode != 0:
                logger.info("Kullanıcı komut penceresini iptal etti.")
                return "cancel", ""

            output = res.stdout.strip()

            if "BUTTON:🎙️ Sesli Konuş" in output:
                logger.info("🎙️ Kullanıcı sesli konuşma modunu seçti.")
                return "voice", ""

            if "BUTTON:Çalıştır" in output:
                text_part = output.split("|TEXT:")
                entered_text = text_part[1].strip() if len(text_part) > 1 else ""
                if not entered_text:
                    # Metin girilmediyse yine sesli moda yönlendir
                    return "voice", ""
                logger.info(f"✍️ Kullanıcı yazılı komut girdi: '{entered_text}'")
                return "text", entered_text

            return "cancel", ""

        except Exception as e:
            logger.debug(f"Spotlight diyalog penceresi hatası: {e}")
            return "cancel", ""

    def start_hotkey_listener(self, on_trigger: Callable[[], None]) -> bool:
        """
        Option + Space kısayolunu arka planda non-blocking dinlemeye başlar.
        """
        if not _HAS_PYNPUT:
            logger.error("pynput kütüphanesi olmadan kısayol dinlenemez.")
            return False

        try:
            hotkey_mapping = {self.hotkey: on_trigger}
            self._listener = keyboard.GlobalHotKeys(hotkey_mapping)
            self._listener.start()
            logger.info(f"⌨️ [Kısayol Dinleyici] {self.hotkey} dinleniyor...")
            return True
        except Exception as e:
            logger.error(f"Kısayol dinleyici başlatılamadı: {e}")
            return False

    def stop_hotkey_listener(self) -> None:
        """Kısayol dinleyicisini durdurur ve kaynakları serbest bırakır."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
            logger.info("Kısayol dinleyici durduruldu.")
