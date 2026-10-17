"""
Kısayol ve Komut Çubuğu Tetikleyici (src/perception/trigger.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

1. Option + A (<alt>+a) genel klavye dinleyicisi (pynput).
   - TR/EN/RU klavyelerde macOS 'Option+A' basıldığında 'å' / 'Å' / vk=0 karakterleri de yakalanır.
2. macOS Spotlight tarzı yerel komut diyalogu (osascript display dialog).
"""

from __future__ import annotations

import logging
import subprocess
import time
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
        self._listener: Optional[keyboard.Listener] = None
        self._hotkey_listener: Optional[keyboard.GlobalHotKeys] = None
        self._alt_pressed: bool = False
        self._last_trigger_time: float = 0.0

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
            with title "MacBook Air M2 Asistan (Option + A)" ¬
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
        Option + A (veya yapılandırılan kısayol) tuşunu arka planda non-blocking dinlemeye başlar.
        macOS klavye düzeni farklılıklarına (TR/EN/RU 'å', 'Å', vk=0) karşı çift katmanlı dinleme yapar.
        """
        if not _HAS_PYNPUT:
            logger.error("pynput kütüphanesi olmadan kısayol dinlenemez.")
            return False

        def debounced_trigger():
            now = time.time()
            if now - self._last_trigger_time > 1.2:
                self._last_trigger_time = now
                logger.info("🎯 [Kısayol Tetiklendi] Option + A yakalandı!")
                on_trigger()

        try:
            # 1. Standart GlobalHotKeys Dinleyicisi
            try:
                hotkey_mapping = {self.hotkey: debounced_trigger}
                self._hotkey_listener = keyboard.GlobalHotKeys(hotkey_mapping)
                self._hotkey_listener.start()
            except Exception as gh_err:
                logger.debug(f"GlobalHotKeys başlatma uyarısı: {gh_err}")

            # 2. macOS Klavye Düzeni Güvenlik Ağı (Listener)
            # macOS'ta Option+A basıldığında 'å' karakteri veya vk=0 üretilebilir
            def on_press(key):
                if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, getattr(keyboard.Key, 'alt_gr', None)):
                    self._alt_pressed = True
                    return

                if self._alt_pressed:
                    char = getattr(key, 'char', None)
                    vk = getattr(key, 'vk', None)
                    if (char in ('a', 'A', 'å', 'Å')) or (vk == 0):
                        debounced_trigger()

            def on_release(key):
                if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, getattr(keyboard.Key, 'alt_gr', None)):
                    self._alt_pressed = False

            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.start()

            logger.info(f"⌨️ [Kısayol Dinleyici] {self.hotkey} (Option + A) arka planda dinleniyor...")
            return True
        except Exception as e:
            logger.error(f"Kısayol dinleyici başlatılamadı: {e}")
            return False

    def stop_hotkey_listener(self) -> None:
        """Kısayol dinleyicisini durdurur ve kaynakları serbest bırakır."""
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

        logger.info("Kısayol dinleyici durduruldu.")
