"""
Pano (Clipboard) Yöneticisi ve Hijyen Katmanı (src/state/clipboard.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Kullanıcının panosunu asistan eylemleri öncesinde anlık olarak yedekler (snapshot)
ve işlem tamamlandığında orijinal içeriği kuruşu kuruşuna geri yükler (restore).
"""

from __future__ import annotations

import logging
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

logger = logging.getLogger("mac_assistant.state.clipboard")

# PyObjC AppKit kullanılabilirliğini kontrol et (hızlı native erişim)
try:
    from AppKit import NSPasteboard, NSPasteboardTypeString
    _HAS_PYOBJC = True
except ImportError:
    _HAS_PYOBJC = False
    logger.warning("AppKit (PyObjC) bulunamadı; pbcopy / pbpaste yedek yöntemine geçiliyor.")


@dataclass(frozen=True)
class ClipboardSnapshot:
    """Kullanıcının panosundaki anlık içeriği ve meta verisini temsil eder."""

    text: str = ""
    timestamp: float = field(default_factory=time.time)
    change_count: int = 0
    is_empty: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_empty", len(self.text) == 0)


class ClipboardManager:
    """
    macOS panosunu okuyan, yazan ve pano hijyeni sağlayan yönetici sınıf.
    Öncelikli olarak AppKit.NSPasteboard kullanır, yoksa pbcopy/pbpaste CLI araçlarına düşer.
    """

    def __init__(self) -> None:
        self._has_pyobjc = _HAS_PYOBJC
        self._fallback_change_count = 0
        if self._has_pyobjc:
            self._pb = NSPasteboard.generalPasteboard()
        else:
            self._pb = None

    def get_text(self) -> str:
        """Panodaki mevcut metni döndürür. Pano boşsa veya metin yoksa boş string döner."""
        if self._has_pyobjc and self._pb is not None:
            try:
                content = self._pb.stringForType_(NSPasteboardTypeString)
                return str(content) if content else ""
            except Exception as e:
                logger.debug(f"NSPasteboard get_text hatası: {e}")

        # Yedek CLI yöntemi (pbpaste)
        try:
            res = subprocess.run(
                ["pbpaste"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=1.0
            )
            return res.stdout or ""
        except Exception as e:
            logger.error(f"pbpaste çağrısı başarısız: {e}")
            return ""

    def set_text(self, text: str) -> None:
        """Panoya belirtilen metni yazar."""
        if self._has_pyobjc and self._pb is not None:
            try:
                self._pb.clearContents()
                if text:
                    self._pb.setString_forType_(text, NSPasteboardTypeString)
                return
            except Exception as e:
                logger.debug(f"NSPasteboard set_text hatası: {e}")

        # Yedek CLI yöntemi (pbcopy)
        try:
            subprocess.run(
                ["pbcopy"],
                input=text,
                text=True,
                check=True,
                timeout=1.0
            )
            self._fallback_change_count += 1
        except Exception as e:
            logger.error(f"pbcopy çağrısı başarısız: {e}")

    def get_change_count(self) -> int:
        """
        macOS NSPasteboard changeCount değerini döndürür.
        Panonun değişip değişmediğini sıfır işlemci yüküyle anlamayı sağlar.
        """
        if self._has_pyobjc and self._pb is not None:
            try:
                return int(self._pb.changeCount())
            except Exception:
                pass
        return self._fallback_change_count

    def snapshot(self) -> ClipboardSnapshot:
        """Kullanıcının o anki pano durumunu tam olarak yedekler."""
        current_text = self.get_text()
        count = self.get_change_count()
        logger.debug(f"Pano anlık görüntüsü alındı (uzunluk={len(current_text)}, changeCount={count})")
        return ClipboardSnapshot(
            text=current_text,
            timestamp=time.time(),
            change_count=count
        )

    def restore(self, snapshot: ClipboardSnapshot) -> bool:
        """
        Önceden alınan anlık görüntüyü panoya geri yükler.
        Orijinal pano boş idi ise panoyu temizler; dolu ise orijinal metni yazar.
        """
        try:
            if snapshot.is_empty:
                if self._has_pyobjc and self._pb is not None:
                    self._pb.clearContents()
                else:
                    self.set_text("")
            else:
                self.set_text(snapshot.text)

            logger.info("🛡️ [Pano Hijyeni] Kullanıcının orijinal panosu başarıyla geri yüklendi.")
            return True
        except Exception as e:
            logger.error(f"Pano geri yüklenirken hata oluştu: {e}")
            return False

    @contextmanager
    def preserve_clipboard(self) -> Generator[ClipboardSnapshot, None, None]:
        """
        Pano koruma context manager'ı.
        with clipboard.preserve_clipboard(): bloğu sonunda (hata çıksa bile)
        kullanıcının orijinal panosu otomatik olarak geri yüklenir.
        """
        snap = self.snapshot()
        try:
            yield snap
        finally:
            self.restore(snap)
