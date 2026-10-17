"""
Karar Şemaları (src/brain/schemas.py)
Pydantic v2 tabanlı yapısal plan ve eylem tanımları.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field

# Asistanın desteklediği 6 temel atomik eylem tipi
ActionType = Literal[
    "capture_source_context",  # Aktif pencereyi kaydet ve seçili metni/ekranı kopyala
    "send_to_yandex_gemini",   # Yandex'teki açık Gemini sekmesine metni/promptu gönder ve cevabı al
    "paste_to_source_app",     # Alınan cevabı ilk pencereye geri yapıştır
    "speak_or_notify",         # Kullanıcıya sesli/yazılı bildirim ver
    "open_application",        # Belirtilen macOS uygulamasını açar veya öne getirir
    "close_application",       # Belirtilen macOS uygulamasını güvenli şekilde kapatır
]


class AgentAction(BaseModel):
    """Asistan tarafından yürütülecek tek bir atomik eylem."""

    action: ActionType = Field(
        ...,
        description="Yürütülecek atomik aracın adı (capture_source_context, send_to_yandex_gemini, paste_to_source_app, speak_or_notify)"
    )
    description: str = Field(
        ...,
        description="Bu adımın ne amaçla yapıldığını açıklayan insan tarafından okunabilir kısa açıklama"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Eyleme özel parametreler (örn: prompt, message, capture_mode, target_app)"
    )


class ExecutionPlan(BaseModel):
    """Kullanıcının doğal dil komutuna karşılık gelen adım adım yürütme planı."""

    user_command: str = Field(
        ...,
        description="Kullanıcıdan gelen orijinal doğal dil komutu veya transkript"
    )
    reasoning: str = Field(
        ...,
        description="Modelin bu adımları hangi gerekçeyle seçtiğini anlatan düşünce süreci"
    )
    brain_used: Literal["cloud", "local", "mock"] = Field(
        default="cloud",
        description="Planı oluşturan beyin motoru ('cloud', 'local' veya simülasyon için 'mock')"
    )
    actions: List[AgentAction] = Field(
        default_factory=list,
        description="Sırasıyla çalıştırılacak atomik eylemler listesi"
    )

    def to_formatted_json(self) -> str:
        """Kolay loglama için okunabilir JSON döndürür."""
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2)

    def summary(self) -> str:
        """Kısa özet metni döndürür."""
        return f"Plan [{self.brain_used}]: {len(self.actions)} adım - '{self.user_command}'"
