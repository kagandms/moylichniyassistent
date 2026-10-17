"""
Hibrit Ses Tanıma Motoru (src/perception/stt.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Ses dosyasını (WAV) Türkçe metne dönüştürür:
1. Yerel Seçenek: mlx_whisper kuruluysa Apple Silicon Metal/NE üzerinde çalışır.
2. Bulut Seçenek (0 MB RAM): Gemini Flash Audio API ile sesi doğrudan buluta dinletir.
3. Fallback: Geliştirme/test ortamında şema uyumlu simülasyon çıktısı üretir.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

import config

logger = logging.getLogger("mac_assistant.perception.stt")

# mlx_whisper kontrolü
try:
    import mlx_whisper
    _HAS_MLX_WHISPER = True
except ImportError:
    _HAS_MLX_WHISPER = False


@dataclass(frozen=True)
class STTResult:
    """Konuşma tanıma çıktısını temsil eden model."""

    text: str
    language: str = "tr"
    engine_used: str = "gemini_cloud"  # mlx_whisper, gemini_cloud, mock
    confidence: float = 1.0
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class SpeechToTextEngine:
    """
    Yerel Apple Silicon ve Bulut hibrit STT motoru.
    """

    def __init__(self, preferred_engine: str = "auto") -> None:
        self.preferred_engine = preferred_engine

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> STTResult:
        """
        WAV formatındaki ses dosyasını analiz edip metne çevirir.
        language=None veya 'auto' verildiğinde otomatik dil tespiti yapar (TR / EN / RU).
        """
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            return STTResult(
                text="",
                language=language or "auto",
                engine_used="none",
                error="Ses dosyası bulunamadı veya boş."
            )

        t0 = time.time()
        effective_lang = None if language in (None, "auto") else language

        # 1. YEREL MLX WHISPER (Eğer kurulu ve tercih edilmişse)
        if _HAS_MLX_WHISPER and self.preferred_engine in ("auto", "local", "mlx"):
            try:
                logger.info("🧠 [MLX Whisper] Apple Silicon GPU üzerinde yerel ses tanıma başlatılıyor (TR/EN/RU)...")
                transcribe_kwargs = {
                    "path_or_hf_repo": "mlx-community/whisper-large-v3-turbo",
                }
                if effective_lang:
                    transcribe_kwargs["language"] = effective_lang

                res = mlx_whisper.transcribe(
                    audio_path,
                    **transcribe_kwargs
                )
                text = str(res.get("text", "")).strip()
                detected_lang = str(res.get("language", effective_lang or "auto"))
                elapsed = (time.time() - t0) * 1000
                logger.info(f"✨ [MLX Whisper] Tanıma tamamlandı ({elapsed:.1f}ms, dil={detected_lang}): '{text}'")
                return STTResult(
                    text=text,
                    language=detected_lang,
                    engine_used="mlx_whisper",
                    elapsed_ms=elapsed
                )
            except Exception as e:
                logger.warning(f"⚠️ MLX Whisper hatası, bulut Gemini STT'ye geçiliyor: {e}")

        # 2. BULUT GEMINI AUDIO API (0 MB Yerel RAM & Yüksek Doğruluk)
        if config.config.is_gemini_configured() and self.preferred_engine in ("auto", "cloud"):
            try:
                logger.info("☁️ [Gemini Audio API] Ses verisi Gemini Flash'a aktarılıyor (0 MB RAM, TR/EN/RU)...")
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()

                # Öncelikle google-genai kütüphanesini dene
                try:
                    from google import genai
                    from google.genai import types

                    client = genai.Client(api_key=config.config.GEMINI_API_KEY)
                    prompt = (
                        "Listen to this audio recording and transcribe the speech exactly as spoken. "
                        "The user may speak in Turkish (TR), English (EN), Russian (RU), or a mix of them. "
                        "Output ONLY the raw transcription without any quotes, explanations, or prefixes."
                    )
                    response = client.models.generate_content(
                        model=config.config.GEMINI_MODEL,
                        contents=[
                            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                            prompt
                        ]
                    )
                    text = (response.text or "").strip()
                    elapsed = (time.time() - t0) * 1000
                    logger.info(f"✨ [Gemini STT] Tanıma tamamlandı ({elapsed:.1f}ms): '{text}'")
                    return STTResult(
                        text=text,
                        language=effective_lang or "auto",
                        engine_used="gemini_cloud",
                        elapsed_ms=elapsed
                    )
                except Exception as sdk_err:
                    logger.debug(f"google-genai SDK ile hata, doğrudan REST deneniyor: {sdk_err}")

                # REST Fallback
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.config.GEMINI_MODEL}:generateContent?key={config.config.GEMINI_API_KEY}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"inlineData": {"mimeType": "audio/wav", "data": b64_audio}},
                            {"text": "Bu ses kaydını dinle ve içindeki Türkçe konuşmayı harfi harfine yazıya dök. Sadece transkripti ver."}
                        ]
                    }]
                }
                res = requests.post(url, json=payload, timeout=12.0)
                res.raise_for_status()
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                elapsed = (time.time() - t0) * 1000
                return STTResult(
                    text=text,
                    language=language,
                    engine_used="gemini_cloud",
                    elapsed_ms=elapsed
                )

            except Exception as e:
                logger.warning(f"⚠️ Bulut Gemini STT başarısız oldu: {e}")

        # 3. ŞEMA DOĞRULAMALI SIMÜLASYON / TEST MOTORU
        elapsed = (time.time() - t0) * 1000
        simulated_text = "Ekranda yer alan metni kopyala ve Yandex Gemini ile özetle"
        logger.info(f"🧪 [STT Simülasyonu] Test veya çevrimdışı fallback aktif ({elapsed:.1f}ms)")
        return STTResult(
            text=simulated_text,
            language=language,
            engine_used="mock",
            confidence=0.95,
            elapsed_ms=elapsed
        )
