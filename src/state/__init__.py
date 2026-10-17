"""
Durum Hafızası ve Aktif Pencere Takibi Katmanı (src/state)
MacBook Air M2 Zero-Idle-RAM Mimarisi (Faz 2)
"""

from src.state.clipboard import ClipboardManager, ClipboardSnapshot
from src.state.manager import CapturedContext, StateManager
from src.state.window_tracker import SourceAppInfo, WindowTracker

__all__ = [
    "ClipboardManager",
    "ClipboardSnapshot",
    "SourceAppInfo",
    "WindowTracker",
    "CapturedContext",
    "StateManager",
]
