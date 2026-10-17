"""
Birleşik Algılama Yöneticisi (src/perception/manager.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Faz 2'deki StateManager (seçili metin) ile Faz 3'teki Apple Vision OCR
ve Ses Kayıt/STT motorlarını tek bir akıllı arayüzde birleştirir.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from src.perception.audio import AudioCaptureResult, OnDemandAudioRecorder
from src.perception.ocr import OCRResult, ScreenOCR
from src.perception.stt import SpeechToTextEngine, STTResult
from src.perception.trigger import CommandTrigger
from src.state.manager import StateManager
from src.state.window_tracker import SourceAppInfo

logger = logging.getLogger("mac_assistant.perception.manager")

CaptureMethodType = Literal["selection", "vision_ocr", "voice", "dialog"]


@dataclass(frozen=True)
class PerceivedContext:
    """Algılama katmanından gelen zenginleştirilmiş bağlam modeli."""

    source_app: SourceAppInfo
    raw_text: str
    capture_method: CaptureMethodType
    has_content: bool = field(init=False)
    ocr_result: Optional[OCRResult] = None
    stt_result: Optional[STTResult] = None
    captured_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "has_content", len(self.raw_text.strip()) > 0)

    def summary(self) -> str:
        preview = self.raw_text.replace("\n", " ")[:40]
        return f"[{self.capture_method.upper()}] Kaynak: {self.source_app.app_name} | {len(self.raw_text)} kar. - '{preview}...'"


class PerceptionManager:
    """
    Ekran görüntüsü okuma (OCR), seçili metin yakalama, ses kaydı ve transkripsiyonu
    koordine eden ana algılama yöneticisi.
    """

    def __init__(
        self,
        ocr: Optional[ScreenOCR] = None,
        audio: Optional[OnDemandAudioRecorder] = None,
        stt: Optional[SpeechToTextEngine] = None,
        trigger: Optional[CommandTrigger] = None
    ) -> None:
        self.ocr = ocr or ScreenOCR()
        self.audio = audio or OnDemandAudioRecorder()
        self.stt = stt or SpeechToTextEngine()
        self.trigger = trigger or CommandTrigger()

    def capture_screen_or_selection(
        self,
        state_manager: StateManager,
        simulate_copy: bool = True
    ) -> PerceivedContext:
        """
        Kullanıcı durumunu akıllıca yakalar:
        1. Önce StateManager ile seçili metin arar.
        2. Seçili metin varsa OCR'a hiç gerek kalmadan metni döndürür (capture_method='selection').
        3. Seçili metin yoksa (has_selection=False), Apple Vision OCR ile ekranı okur (capture_method='vision_ocr').
        """
        ctx = state_manager.capture_source_context(simulate_copy=simulate_copy)

        # 1. Seçili metin varsa doğrudan onu kullan
        if ctx.has_selection and ctx.selected_text.strip():
            logger.info(f"✅ [Algılama: Seçim] Kullanıcının seçtiği {len(ctx.selected_text)} karakter metin alındı.")
            return PerceivedContext(
                source_app=ctx.source_app,
                raw_text=ctx.selected_text.strip(),
                capture_method="selection"
            )

        # 2. Seçili metin yoksa Apple Vision OCR'ı devreye sok
        logger.info("👁️ [Algılama: Vision OCR] Seçili metin yok, ekrandaki yazılar Apple Vision ile taranıyor...")
        ocr_result = self.ocr.extract_text_from_screen()

        if ocr_result.has_text:
            logger.info(f"✅ [Algılama: OCR Başarılı] Ekrandan {ocr_result.line_count} satır metin okundu.")
            return PerceivedContext(
                source_app=ctx.source_app,
                raw_text=ocr_result.text,
                capture_method="vision_ocr",
                ocr_result=ocr_result
            )

        # 3. OCR da başarısız olduysa veya izin yoksa
        logger.warning(f"⚠️ [Algılama] Ekrandan metin okunamadı: {ocr_result.error or 'Boş ekran'}")
        return PerceivedContext(
            source_app=ctx.source_app,
            raw_text="",
            capture_method="vision_ocr",
            ocr_result=ocr_result
        )

    def record_and_transcribe(
        self,
        source_app: SourceAppInfo,
        language: Optional[str] = None,
        max_duration: float = 15.0
    ) -> PerceivedContext:
        """
        Mikrofonu VAD ile açar, kullanıcı susunca kaydı bitirip çok dilli (TR/EN/RU) STT yapar.
        """
        capture_res = self.audio.record_until_silence(max_duration=max_duration)
        if not capture_res.had_speech:
            logger.info("Konuşma tespit edilemedi.")
            return PerceivedContext(
                source_app=source_app,
                raw_text="",
                capture_method="voice"
            )

        stt_res = self.stt.transcribe(capture_res.audio_path, language=language)
        return PerceivedContext(
            source_app=source_app,
            raw_text=stt_res.text,
            capture_method="voice",
            stt_result=stt_res
        )
