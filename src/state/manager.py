"""
Durum Yöneticisi ve Oturum Bağlamı (src/state/manager.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Kaynak pencere tespiti, seçili metin yakalama, pano hijyeni ve
sonucu ilk pencereye geri yapıştırma işlemlerini koordine eden ana sınıf.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from src.state.clipboard import ClipboardManager, ClipboardSnapshot
from src.state.window_tracker import SourceAppInfo, WindowTracker

logger = logging.getLogger("mac_assistant.state.manager")

# Erişilebilirlik izni kontrolü (AXIsProcessTrusted)
try:
    from ApplicationServices import AXIsProcessTrusted
    _HAS_ACCESSIBILITY_API = True
except ImportError:
    _HAS_ACCESSIBILITY_API = False

# Quartz klavye simülasyonu
try:
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventSetFlags,
        kCGEventFlagMaskCommand,
        kCGHIDEventTap,
    )
    _HAS_QUARTZ_EVENTS = True
except ImportError:
    _HAS_QUARTZ_EVENTS = False


@dataclass(frozen=True)
class CapturedContext:
    """Kullanıcının asistanı çağırdığı andaki tüm durum görüntüsü."""

    source_app: SourceAppInfo
    selected_text: str = ""
    has_selection: bool = False
    clipboard_snapshot: ClipboardSnapshot = field(default_factory=ClipboardSnapshot)
    captured_at: float = field(default_factory=time.time)

    def summary(self) -> str:
        sel_info = f"'{self.selected_text[:30]}...' ({len(self.selected_text)} karakter)" if self.has_selection else "Seçim yok (OCR adayı)"
        return f"Kaynak: {self.source_app.app_name} | Seçili Metin: {sel_info}"


class StateManager:
    """
    Asistanın durum hafızasını, aktif pencere koordinasyonunu
    ve pano hijyenini yöneten ana orkestrasyon sınıfı.
    """

    def __init__(
        self,
        clipboard: Optional[ClipboardManager] = None,
        window_tracker: Optional[WindowTracker] = None
    ) -> None:
        self.clipboard = clipboard or ClipboardManager()
        self.window_tracker = window_tracker or WindowTracker()

    def check_accessibility_permission(self) -> bool:
        """
        macOS Erişilebilirlik (Accessibility) izninin verilip verilmediğini kontrol eder.
        Tuş simülasyonu (Cmd+C / Cmd+V) için gereklidir.
        """
        if _HAS_ACCESSIBILITY_API:
            try:
                return bool(AXIsProcessTrusted())
            except Exception:
                pass
        return False

    def simulate_keystroke(self, char: str, modifiers: tuple[str, ...] = ("cmd",)) -> bool:
        """
        Klavye kısayolunu simüle eder (Cmd+C veya Cmd+V).
        Sırasıyla Quartz CGEvent, pynput veya AppleScript yöntemlerini dener.
        """
        char_lower = char.lower()

        # 1. Quartz CGEvent (En hızlı ve native yöntem)
        if _HAS_QUARTZ_EVENTS:
            # macOS Virtual Keycodes: 'c' = 8, 'v' = 9
            keycode_map = {"c": 8, "v": 9}
            keycode = keycode_map.get(char_lower)
            if keycode is not None and "cmd" in modifiers:
                try:
                    event_down = CGEventCreateKeyboardEvent(None, keycode, True)
                    CGEventSetFlags(event_down, kCGEventFlagMaskCommand)
                    event_up = CGEventCreateKeyboardEvent(None, keycode, False)
                    CGEventSetFlags(event_up, kCGEventFlagMaskCommand)

                    CGEventPost(kCGHIDEventTap, event_down)
                    time.sleep(0.02)
                    CGEventPost(kCGHIDEventTap, event_up)
                    return True
                except Exception as e:
                    logger.debug(f"Quartz CGEventPost hatası: {e}")

        # 2. AppleScript Yedek Yöntemi
        try:
            mod_str = "using command down" if "cmd" in modifiers else ""
            script = f'tell application "System Events" to keystroke "{char_lower}" {mod_str}'
            subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=1.0
            )
            return True
        except Exception as e:
            logger.debug(f"AppleScript keystroke hatası: {e}")

        return False

    def capture_source_context(self, simulate_copy: bool = True) -> CapturedContext:
        """
        Kullanıcının o anki durumunu eksiksiz yakalar:
        1. Kullanıcının mevcut panosunu belleğe yedekler (snapshot).
        2. Aktif pencereyi (app_name, bundle_id, pid) kaydeder.
        3. simulate_copy=True ise Cmd+C ile seçili metin olup olmadığını kontrol eder.
           - Seçili metin varsa: has_selection=True döner.
           - Seçili metin yoksa: has_selection=False döner ve pano anında geri yüklenir.
        """
        # 1. Pano anlık görüntüsü
        snap = self.clipboard.snapshot()

        # 2. Aktif pencereyi kaydet
        source_app = self.window_tracker.get_frontmost_app()

        selected_text = ""
        has_selection = False

        # 3. Seçili metni güvenli yakala
        if simulate_copy:
            has_perm = self.check_accessibility_permission()
            if not has_perm:
                logger.warning(
                    "⚠️ [Erişilebilirlik İzni Gerekli] Sistem Ayarları -> Gizlilik ve Güvenlik -> Erişilebilirlik "
                    "üzerinden terminale izin verilmediği için Cmd+C simülasyonu yapılamadı. (has_selection=False)"
                )
            else:
                # Nöbetçi token ile panoyu işaretle
                sentinel = f"__AGY_EMPTY_SENTINEL_{time.time_ns()}__"
                self.clipboard.set_text(sentinel)

                # Cmd + C simüle et
                self.simulate_keystroke("c", modifiers=("cmd",))
                time.sleep(0.15)  # Hedef uygulamanın panoya yazması için kısa bekleme

                new_text = self.clipboard.get_text()

                # Pano nöbetçi değerden farklı bir metinle güncellendiyse seçim vardır
                if new_text != sentinel and len(new_text.strip()) > 0:
                    selected_text = new_text
                    has_selection = True
                    logger.info(f"📋 [Seçim Yakalandı] {len(selected_text)} karakter seçili metin alındı.")
                else:
                    logger.info("ℹ️ [Seçim Yok] Kaynak uygulamada seçili metin tespit edilmedi (Faz 3 OCR adayı).")
                    # Seçim yoksa nöbetçi token panoda kalmasın, orijinal panoyu anında geri yükle!
                    self.clipboard.restore(snap)

        return CapturedContext(
            source_app=source_app,
            selected_text=selected_text,
            has_selection=has_selection,
            clipboard_snapshot=snap,
            captured_at=time.time()
        )

    def paste_to_source_app(
        self,
        text: str,
        context: CapturedContext,
        restore_clipboard_after: bool = True
    ) -> bool:
        """
        Gemini veya yerel modelden gelen yanıtı ilk çalışılan kaynak pencereye geri yapıştırır:
        1. window_tracker ile kaynak pencereyi tekrar öne getirir.
        2. Yanıt metnini panoya koyar.
        3. Cmd + V simüle eder.
        4. Uygulamanın metni alması için 0.25s bekler.
        5. restore_clipboard_after=True ise kullanıcının ilk baştaki orijinal panosunu geri yükler.
        """
        logger.info(f"🚀 [Geri Yapıştırma] {context.source_app.app_name} uygulamasına yanıt yapıştırılıyor...")

        # 1. Kaynak uygulamaya odaklan
        self.window_tracker.focus_app(context.source_app, wait_seconds=0.2)

        # 2. Yanıt metnini panoya koy
        self.clipboard.set_text(text)

        # 3. Cmd + V gönder
        self.simulate_keystroke("v", modifiers=("cmd",))
        time.sleep(0.25)  # Uygulamanın yapıştırma olayını tamamlaması için bekle

        # 4. Pano hijyeni: kullanıcının ilk baştaki orijinal içeriğini geri yükle
        if restore_clipboard_after:
            self.clipboard.restore(context.clipboard_snapshot)

        return True
