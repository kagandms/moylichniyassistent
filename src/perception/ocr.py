"""
Apple Vision Framework Yerel Ekran ve Görsel Okuyucu (src/perception/ocr.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

macOS'un yerel Vision Framework (VNRecognizeTextRequest) motorunu kullanarak
sıfır harici ağırlık ve sıfır boşta RAM ile ekran görüntülerinden Türkçe/İngilizce metin okur.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Union

from PIL import Image, ImageDraw

logger = logging.getLogger("mac_assistant.perception.ocr")

try:
    from ocrmac import ocrmac
    _HAS_OCRMAC = True
except ImportError:
    _HAS_OCRMAC = False
    logger.warning("ocrmac paketi bulunamadı, Apple Vision OCR kullanılamayabilir.")


@dataclass(frozen=True)
class OCRResult:
    """OCR tarama çıktısını temsil eden veri modeli."""

    text: str = ""
    line_count: int = 0
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    error: Optional[str] = None
    has_text: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "has_text", len(self.text.strip()) > 0)

    def summary(self) -> str:
        if self.error:
            return f"OCR Hatası: {self.error}"
        preview = self.text.replace("\n", " ")[:40]
        return f"{self.line_count} satır ({len(self.text)} kar., güven=%{self.confidence*100:.1f}, {self.elapsed_ms:.1f}ms) - '{preview}...'"


class ScreenOCR:
    """
    Apple Vision Framework tabanlı ekran ve görsel metin ayrıştırıcısı.
    """

    def __init__(self, languages: Optional[List[str]] = None) -> None:
        self.languages = languages or ["tr-TR", "en-US"]

    def extract_text_from_image(
        self,
        image_or_path: Union[str, Path, Image.Image],
        confidence_threshold: float = 0.3
    ) -> OCRResult:
        """
        Verilen PIL görseli veya görsel dosya yolundan Apple Vision ile metin çıkarır.
        """
        if not _HAS_OCRMAC:
            return OCRResult(
                error="ocrmac / Apple Vision kütüphanesi kurulu değil.",
                elapsed_ms=0.0
            )

        t0 = time.time()
        try:
            # ocrmac ile Apple Neural Engine üzerinde VNRecognizeTextRequest çalıştır
            raw_results = ocrmac.OCR(
                image_or_path,
                recognition_level="accurate",
                language_preference=self.languages,
                confidence_threshold=confidence_threshold
            ).recognize()

            elapsed = (time.time() - t0) * 1000

            if not raw_results:
                return OCRResult(
                    text="",
                    line_count=0,
                    confidence=0.0,
                    elapsed_ms=elapsed
                )

            extracted_lines: List[str] = []
            confidences: List[float] = []

            for item in raw_results:
                # Format: (line_text, confidence, bbox)
                line_text = str(item[0]).strip()
                conf = float(item[1]) if len(item) > 1 else 1.0
                if line_text:
                    extracted_lines.append(line_text)
                    confidences.append(conf)

            full_text = "\n".join(extracted_lines)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            logger.info(f"🔍 [Apple Vision OCR] {len(extracted_lines)} satır metin okundu ({elapsed:.1f}ms)")
            return OCRResult(
                text=full_text,
                line_count=len(extracted_lines),
                confidence=avg_conf,
                elapsed_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            logger.error(f"Vision OCR işlemi sırasında hata: {e}")
            return OCRResult(
                error=str(e),
                elapsed_ms=elapsed
            )

    def extract_text_from_screen(self, silent: bool = True) -> OCRResult:
        """
        macOS screencapture ile ekran görüntüsünü sessizce alıp metinleri okur.
        İşlem bitiminde geçici görsel diski kirletmemek için derhal silinir.
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # -x: sessiz deklanşör
            cmd = ["/usr/sbin/screencapture", "-x", tmp_path]
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=3.0
            )

            if res.returncode != 0 or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                err_msg = res.stderr.strip() or "Ekran görüntüsü alınamadı (Ekran Kaydı izni gerekebilir)"
                logger.warning(f"⚠️ screencapture uyarısı: {err_msg}")
                return OCRResult(
                    error=f"Ekran Kaydı Hatası: {err_msg}",
                    elapsed_ms=0.0
                )

            return self.extract_text_from_image(tmp_path)
        except Exception as e:
            logger.error(f"Ekran yakalama hatası: {e}")
            return OCRResult(error=str(e), elapsed_ms=0.0)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def create_synthetic_test_image(text: str = "MacBook Air M2 Apple Vision OCR Testi") -> Image.Image:
        """Test ortamında ekran kaydı izni olmadan doğrulamayı sağlayan sentetik görsel üretici."""
        img = Image.new("RGB", (500, 120), color="white")
        draw = ImageDraw.Draw(img)
        # Metni çiz
        draw.text((20, 45), text, fill="black")
        return img
