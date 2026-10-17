"""
Algılama Katmanı (src/perception)
MacBook Air M2 Zero-Idle-RAM Mimarisi (Faz 3)
"""

from src.perception.audio import AudioCaptureResult, OnDemandAudioRecorder
from src.perception.manager import CaptureMethodType, PerceivedContext, PerceptionManager
from src.perception.ocr import OCRResult, ScreenOCR
from src.perception.stt import SpeechToTextEngine, STTResult
from src.perception.trigger import CommandTrigger

__all__ = [
    "PerceptionManager",
    "PerceivedContext",
    "CaptureMethodType",
    "ScreenOCR",
    "OCRResult",
    "OnDemandAudioRecorder",
    "AudioCaptureResult",
    "SpeechToTextEngine",
    "STTResult",
    "CommandTrigger",
]
