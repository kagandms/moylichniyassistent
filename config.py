"""
Merkezi Konfigürasyon Modülü (config.py)
MacBook Air M2 Sesli ve Yazılı Asistan Projesi

Tüm ortam değişkenlerini, mimari ayarları ve donanım eşiklerini yönetir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Proje kök dizinini belirle ve .env dosyasını yükle
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()  # Fallback to default environment


BrainModeType = Literal["auto", "cloud", "local"]


@dataclass(frozen=True)
class Settings:
    """Uygulama genelinde kullanılan değişmez ayarlar sınıfı."""

    # Dizinler
    BASE_DIR: Path = BASE_DIR

    # 1. Hibrit Beyin Ayarları
    BRAIN_MODE: BrainModeType = field(
        default_factory=lambda: os.getenv("BRAIN_MODE", "auto").lower()  # type: ignore[return-value]
    )

    # Google Gemini Cloud (0 MB RAM)
    GEMINI_API_KEY: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip()
    )
    GEMINI_MODEL: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    )

    # Yerel Ollama (On-demand Lazy Load)
    OLLAMA_BASE_URL: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    )
    OLLAMA_MODEL: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()
    )
    OLLAMA_KEEP_ALIVE: str = field(
        default_factory=lambda: os.getenv("OLLAMA_KEEP_ALIVE", "5m").strip()
    )

    # 2. Tarayıcı ve Otomasyon
    TARGET_BROWSER: str = field(
        default_factory=lambda: os.getenv("TARGET_BROWSER", "Yandex").strip()
    )

    # 3. Kısayol ve Algı (Faz 2 & 3 Hazırlık)
    HOTKEY: str = field(
        default_factory=lambda: os.getenv("HOTKEY", "<alt>+<space>").strip()
    )
    VAD_SILENCE_SECONDS: float = field(
        default_factory=lambda: float(os.getenv("VAD_SILENCE_SECONDS", "1.5"))
    )

    # 4. Hata Ayıklama
    DEBUG: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    )

    def is_gemini_configured(self) -> bool:
        """Gemini API anahtarının geçerli formatta verilip verilmediğini doğrular."""
        key = self.GEMINI_API_KEY.strip()
        if not key or key == "your_gemini_api_key_here":
            return False
        return len(key) >= 15

    def __post_init__(self) -> None:
        if self.BRAIN_MODE not in ("auto", "cloud", "local"):
            object.__setattr__(self, "BRAIN_MODE", "auto")


# Global tekil konfigürasyon nesnesi
config = Settings()

# Kolay erişim için doğrudan değişken dışa aktarımı
BRAIN_MODE = config.BRAIN_MODE
GEMINI_API_KEY = config.GEMINI_API_KEY
GEMINI_MODEL = config.GEMINI_MODEL
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
OLLAMA_KEEP_ALIVE = config.OLLAMA_KEEP_ALIVE
TARGET_BROWSER = config.TARGET_BROWSER
HOTKEY = config.HOTKEY
VAD_SILENCE_SECONDS = config.VAD_SILENCE_SECONDS
DEBUG = config.DEBUG
