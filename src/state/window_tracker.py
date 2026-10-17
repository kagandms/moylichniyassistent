"""
Aktif Pencere ve Uygulama Takipçisi (src/state/window_tracker.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Kullanıcının asistanı tetiklediği andaki kaynak pencereyi (app_name, bundle_id, pid)
milisaniyeler içinde kaydeder ve otomasyon sonunda kaynak uygulamayı tekrar öne getirir.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("mac_assistant.state.window_tracker")

try:
    from AppKit import (
        NSApplicationActivateIgnoringOtherApps,
        NSRunningApplication,
        NSWorkspace,
    )
    _HAS_PYOBJC = True
except ImportError:
    _HAS_PYOBJC = False
    logger.warning("AppKit (PyObjC) bulunamadı; osascript pencere takip yedek yöntemine geçiliyor.")


@dataclass(frozen=True)
class SourceAppInfo:
    """Kullanıcının çalıştığı kaynak uygulamanın kimlik ve pencere bilgisi."""

    app_name: str
    bundle_id: str
    window_title: str = ""
    pid: Optional[int] = None
    captured_at: float = field(default_factory=time.time)

    def summary(self) -> str:
        title_part = f" - '{self.window_title}'" if self.window_title else ""
        return f"{self.app_name} ({self.bundle_id}, PID: {self.pid}){title_part}"


class WindowTracker:
    """
    macOS üzerinde o an en önde (frontmost) bulunan uygulamayı takip eden
    ve istenildiğinde o uygulamaya odaklanan sınıf.
    """

    def __init__(self) -> None:
        self._has_pyobjc = _HAS_PYOBJC
        if self._has_pyobjc:
            self._workspace = NSWorkspace.sharedWorkspace()
        else:
            self._workspace = None

    def get_frontmost_app(self) -> SourceAppInfo:
        """
        Şu anda kullanıcının aktif olarak çalıştığı en öndeki uygulamayı yakalar (<10ms).
        Erişilebilirlik izni yoksa pencere başlığı boş gelebilir ancak işlem asla çökmez.
        """
        app_name = "Unknown"
        bundle_id = "unknown"
        pid = None
        window_title = ""

        if self._has_pyobjc and self._workspace is not None:
            try:
                front_app = self._workspace.frontmostApplication()
                if front_app is not None:
                    app_name = str(front_app.localizedName() or "Unknown")
                    bundle_id = str(front_app.bundleIdentifier() or "unknown")
                    pid = int(front_app.processIdentifier())
            except Exception as e:
                logger.debug(f"NSWorkspace frontmostApplication hatası: {e}")

        # PyObjC yoksa veya eksik geldiyse AppleScript ile tamamla
        if app_name == "Unknown" or bundle_id == "unknown":
            app_name, bundle_id, pid = self._get_frontmost_via_osascript()

        # Pencere başlığını hafifçe sorgula (hata verirse boş string döner)
        window_title = self._get_window_title_safely()

        info = SourceAppInfo(
            app_name=app_name,
            bundle_id=bundle_id,
            window_title=window_title,
            pid=pid,
            captured_at=time.time()
        )
        logger.debug(f"Aktif pencere yakalandı: {info.summary()}")
        return info

    def focus_app(self, target: SourceAppInfo, wait_seconds: float = 0.2) -> bool:
        """
        Önceden kaydedilen kaynak uygulamayı tekrar en öne (activate/frontmost) getirir.
        Önce PID üzerinden NSRunningApplication dener, gerekirse bundle_id AppleScript çağrısı yapar.
        """
        success = False
        logger.info(f"🎯 [Pencere Odaklama] Kaynak uygulamaya geri dönülüyor: {target.app_name} ({target.bundle_id})")

        # 1. Native NSRunningApplication aktivasyonu (En hızlı & sessiz)
        if self._has_pyobjc and target.pid is not None:
            try:
                running_app = NSRunningApplication.runningApplicationWithProcessIdentifier_(target.pid)
                if running_app is not None:
                    success = running_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            except Exception as e:
                logger.debug(f"NSRunningApplication activate hatası: {e}")

        # 2. Bundle ID veya App Name üzerinden AppleScript yedek aktivasyonu
        if not success and target.bundle_id and target.bundle_id != "unknown":
            script = f'tell application id "{target.bundle_id}" to activate'
            try:
                subprocess.run(
                    ["osascript", "-e", script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=1.0
                )
                success = True
            except Exception as e:
                logger.debug(f"AppleScript focus_app hatası: {e}")

        # macOS pencere yöneticisinin animasyonu tamamlaması için bekle
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # Doğrulama: Gerçekten öne geldi mi?
        current = self.get_frontmost_app()
        is_front = (current.bundle_id == target.bundle_id) or (current.pid == target.pid)
        if is_front:
            logger.debug(f"Pencere başarıyla öne getirildi: {target.app_name}")
            return True
        else:
            logger.warning(f"Pencere öne getirme doğrulanamadı (Şu anki: {current.app_name})")
            return success

    def _get_frontmost_via_osascript(self) -> tuple[str, str, Optional[int]]:
        """AppleScript ile en öndeki uygulamanın adını ve bundle id'sini alır."""
        script = '''
        tell application "System Events"
            set frontApp to first process whose frontmost is true
            set appName to name of frontApp
            set appBundle to bundle identifier of frontApp
            set appPid to unix id of frontApp
            return appName & "|" & appBundle & "|" & appPid
        end tell
        '''
        try:
            out = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0
            ).strip()
            parts = out.split("|")
            name = parts[0] if len(parts) > 0 else "Unknown"
            bundle = parts[1] if len(parts) > 1 else "unknown"
            pid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            return name, bundle, pid
        except Exception:
            return "Unknown", "unknown", None

    def _get_window_title_safely(self) -> str:
        """Pencere başlığını hafifçe ve çökmeye karşı korumalı şekilde okur."""
        script = '''
        tell application "System Events"
            try
                set frontApp to first process whose frontmost is true
                return name of front window of frontApp
            on error
                return ""
            end try
        end tell
        '''
        try:
            out = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=0.3
            ).strip()
            return out
        except Exception:
            return ""
