"""
İsteğe Bağlı (On-Demand) Ses Kaydedici ve VAD Algılayıcı (src/perception/audio.py)
MacBook Air M2 Zero-Idle-RAM ve Bluetooth HFP Koruma Mimarisi

KRİTİK KURAL: Mikrofon asla 7/24 dinlemede kalamaz!
Yalnızca kullanıcı kısayola bastığında açılır, konuşma bittiğinde VAD (1.5s sessizlik)
ile mikrofon donanımı tamamen kapatılır (stream.close) ve Bluetooth kulaklık 48kHz stereo moduna döner.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy.io import wavfile

import config

logger = logging.getLogger("mac_assistant.perception.audio")

try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except ImportError:
    _HAS_SOUNDDEVICE = False
    logger.warning("sounddevice kütüphanesi bulunamadı; mikrofon kaydı yapılamayabilir.")


@dataclass(frozen=True)
class AudioCaptureResult:
    """Ses kayıt oturumunun çıktısını temsil eder."""

    audio_path: str
    duration_seconds: float
    sample_rate: int
    samples_count: int
    had_speech: bool
    rms_peak: float
    error: Optional[str] = None


class OnDemandAudioRecorder:
    """
    Sadece çağrıldığında açılan ve sessizlik algılandığında donanımı kapatan ses kayıtçısı.
    """

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._stream: Optional[sd.InputStream] = None

    @property
    def is_microphone_active(self) -> bool:
        """Mikrofonun o anda donanım seviyesinde açık olup olmadığını döndürür (Boştayken False olmalıdır)."""
        if self._stream is not None:
            try:
                return bool(self._stream.active)
            except Exception:
                return False
        return False

    def record_until_silence(
        self,
        max_duration: float = 15.0,
        silence_duration: Optional[float] = None,
        energy_threshold: float = 350.0
    ) -> AudioCaptureResult:
        """
        Mikrofonu anlık açar, kullanıcı konuşmasını bitirip silence_duration (varsayılan 1.5s)
        kadar sessizlik oluştuğunda mikrofonu derhal kapatır.
        """
        if not _HAS_SOUNDDEVICE:
            return AudioCaptureResult(
                audio_path="",
                duration_seconds=0.0,
                sample_rate=self.sample_rate,
                samples_count=0,
                had_speech=False,
                rms_peak=0.0,
                error="sounddevice kütüphanesi kurulu değil."
            )

        silence_limit = silence_duration or config.VAD_SILENCE_SECONDS
        chunk_size = 1024  # ~64 ms per chunk
        recorded_frames: List[np.ndarray] = []

        speech_started = False
        silence_start_time: Optional[float] = None
        rms_peak = 0.0
        start_time = time.time()

        logger.info(f"🎙️ [Mikrofon Açıldı] Dinleniyor... (Maks: {max_duration}s, Sessizlik Eşiği: {silence_limit}s)")

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_size
            )
            self._stream.start()

            while True:
                elapsed = time.time() - start_time
                if elapsed >= max_duration:
                    logger.debug("Maksimum kayıt süresine ulaşıldı.")
                    break

                # Chunk oku
                data, overflowed = self._stream.read(chunk_size)
                if data is None or len(data) == 0:
                    continue

                recorded_frames.append(data.copy())

                # RMS enerji hesapla
                rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
                if rms > rms_peak:
                    rms_peak = rms

                # Konuşma başladı mı?
                if rms > energy_threshold:
                    if not speech_started:
                        logger.debug(f"Konuşma algılandı (RMS={rms:.1f} > {energy_threshold})")
                        speech_started = True
                    silence_start_time = None
                else:
                    # Konuşma daha önce başladıysa sessizlik sayacını çalıştır
                    if speech_started:
                        now = time.time()
                        if silence_start_time is None:
                            silence_start_time = now
                        elif now - silence_start_time >= silence_limit:
                            logger.info(f"🤫 [VAD] {silence_limit} sn sessizlik tespit edildi, kayıt tamamlandı.")
                            break

        except Exception as e:
            logger.error(f"Mikrofon kaydı sırasında hata: {e}")
            return AudioCaptureResult(
                audio_path="",
                duration_seconds=0.0,
                sample_rate=self.sample_rate,
                samples_count=0,
                had_speech=False,
                rms_peak=rms_peak,
                error=str(e)
            )
        finally:
            # KRİTİK: Mikrofonu derhal serbest bırak!
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug(f"Stream kapatma hatası: {e}")
                self._stream = None
            logger.info("🔇 [Mikrofon Kapatıldı] Donanım serbest bırakıldı, Bluetooth HFP korundu.")

        # Yakalanan ses verilerini birleştir ve WAV olarak kaydet
        if recorded_frames:
            full_audio = np.concatenate(recorded_frames, axis=0)
        else:
            full_audio = np.zeros((0, 1), dtype=np.int16)

        total_samples = len(full_audio)
        total_duration = total_samples / self.sample_rate

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            wav_path = tmp_file.name

        wavfile.write(wav_path, self.sample_rate, full_audio)
        logger.debug(f"WAV dosyası kaydedildi: {wav_path} ({total_duration:.2f}s)")

        return AudioCaptureResult(
            audio_path=wav_path,
            duration_seconds=total_duration,
            sample_rate=self.sample_rate,
            samples_count=total_samples,
            had_speech=speech_started,
            rms_peak=rms_peak
        )

    @staticmethod
    def create_synthetic_test_wav(
        duration: float = 1.0,
        frequency: float = 440.0,
        sample_rate: int = 16000
    ) -> str:
        """Test amaçlı sentetik bir bip/ton WAV dosyası üretir."""
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        # Sinüs dalgası
        tone = np.sin(frequency * t * 2 * np.pi)
        audio = (tone * 32767 * 0.5).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        wavfile.write(tmp_path, sample_rate, audio)
        return tmp_path
