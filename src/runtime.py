"""
Uçtan Uca Asistan Çalışma Zamanı (src/runtime.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Tüm katmanları (Brain, State, Perception, Actuators, Trigger) tek bir
orkestra şefi altında birleştiren ana asistan çalışma zamanı sınıfı.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any, Dict, Optional

from src.actuators.manager import ActuatorManager
from src.brain.orchestrator import HybridOrchestrator
from src.perception.manager import PerceptionManager
from src.perception.trigger import CommandTrigger
from src.state.manager import StateManager
from src.state.window_tracker import SourceAppInfo

logger = logging.getLogger("mac_assistant.runtime")


class MacAgentRuntime:
    """
    MacBook Air M2 Agentic PC Asistanı Ana Çalışma Zamanı.
    """

    def __init__(
        self,
        orchestrator: Optional[HybridOrchestrator] = None,
        state_mgr: Optional[StateManager] = None,
        perception_mgr: Optional[PerceptionManager] = None,
        actuator_mgr: Optional[ActuatorManager] = None,
        trigger: Optional[CommandTrigger] = None
    ) -> None:
        self.orchestrator = orchestrator or HybridOrchestrator()
        self.state_mgr = state_mgr or StateManager()
        self.perception_mgr = perception_mgr or PerceptionManager()
        self.actuator_mgr = actuator_mgr or ActuatorManager(
            state_mgr=self.state_mgr,
            perception_mgr=self.perception_mgr
        )
        self.trigger = trigger or CommandTrigger()
        self._is_running = False

    def trigger_interactive_session(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Kullanıcı Option + Space bastığında çalışan interaktif akış:
        1. Diyalog kutusu açılmadan ÖNCE o anki aktif pencereyi ve seçili metni kaydeder!
        2. Spotlight tarzı komut kutusunu açar (yazılı komut veya '🎙️ Sesli Konuş').
        3. Komutu Hibrit Beyin (Orchestrator) ile atomik plana dönüştürür.
        4. Eylemleri sırasıyla yürütür (Yandex Gemini -> İlk Pencereye Yapıştır -> Pano Geri Yükle).
        5. Zero-Idle-RAM kuralı gereği RAM'deki yerel modeli boşaltır.
        """
        logger.info("⚡ [Asistan Tetiklendi] İnteraktif oturum başlatılıyor...")

        # 1. KRİTİK: Diyalog açılmadan kaynak pencereyi ve seçili metni kaydet!
        source_app = self.state_mgr.window_tracker.get_frontmost_app()
        logger.info(f"🎯 [Kaynak Uygulama Kilitlendi] {source_app.summary()}")

        # 2. Komut diyalogunu aç
        mode, entered_text = self.trigger.prompt_user_command()

        if mode == "cancel":
            logger.info("Kullanıcı işlemi iptal etti.")
            return {"status": "cancelled", "message": "İşlem iptal edildi."}

        user_command = ""

        # 2A. Sesli Konuşma Modu
        if mode == "voice":
            self.actuator_mgr.notifier.notify(
                message="Dinleniyor... Konuşun.",
                title="Mac Agent Sesli Mod",
                speak=False
            )
            logger.info("🎙️ Ses kaydı başlatılıyor (VAD sessizlik takibi aktif)...")
            perceived_voice = self.perception_mgr.record_and_transcribe(
                source_app=source_app,
                language="tr"
            )
            user_command = perceived_voice.raw_text.strip()
            if not user_command:
                self.actuator_mgr.notifier.notify(
                    message="Sesli komut algılanamadı.",
                    title="Mac Agent Asistan",
                    speak=False
                )
                return {"status": "no_speech", "message": "Ses algılanamadı."}
            logger.info(f"🎤 [Ses Transkripsiyonu]: '{user_command}'")

        # 2B. Yazılı Komut Modu
        elif mode == "text":
            user_command = entered_text.strip()

        if not user_command:
            return {"status": "empty_command", "message": "Komut boş."}

        # 3. Hibrit Beyin ile Plan Üretimi
        logger.info(f"🧠 [Karar Beyni] Plan üretiliyor: '{user_command}'...")
        plan = self.orchestrator.plan(user_command)

        # 4. Eyleyici Zinciri ile Yürütme
        logger.info("🚀 [Yürütme] Plan adımları koşturuluyor...")
        exec_result = self.actuator_mgr.execute_plan(plan, dry_run=dry_run)

        # 5. Zero-Idle-RAM Koruması: Arka planda kalmış yerel model varsa tahliye et
        self.orchestrator.unload_local_model()

        return {
            "status": "success" if exec_result["success"] else "failed",
            "user_command": user_command,
            "plan": plan,
            "execution": exec_result
        }

    def run_command_directly(self, command_text: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Diyalog açmadan, verilen komutu doğrudan kaynak pencereye uygulayan metot (CLI / Test için).
        """
        logger.info(f"⚡ [Doğrudan Komut]: '{command_text}' (dry_run={dry_run})")
        plan = self.orchestrator.plan(command_text)
        result = self.actuator_mgr.execute_plan(plan, dry_run=dry_run)
        self.orchestrator.unload_local_model()
        return {
            "status": "success" if result["success"] else "failed",
            "command": command_text,
            "plan": plan,
            "execution": result
        }

    def run_hotkey_daemon(self) -> None:
        """
        Option + Space kısayolunu arka planda sürekli dinler.
        Sıfır işlemci ve 0 MB LLM RAM yüküyle çalışır.
        """
        logger.info(f"🎧 [Kısayol Servisi] {self.trigger.hotkey} dinleniyor. Çıkış için Ctrl+C...")
        self._is_running = True

        def on_hotkey_triggered() -> None:
            logger.info(f"🔥 [{self.trigger.hotkey} Algılandı] Asistan devreye giriyor!")
            try:
                self.trigger_interactive_session(dry_run=False)
            except Exception as e:
                logger.error(f"İnteraktif oturum hatası: {e}")

        started = self.trigger.start_hotkey_listener(on_hotkey_triggered)
        if not started:
            logger.error("Kısayol dinleyicisi başlatılamadı.")
            return

        # Sinyal yönetimi (Ctrl+C ile temiz çıkış)
        def handle_signal(sig, frame):
            logger.info("Durdurma sinyali alındı. Kısayol servisi kapatılıyor...")
            self.trigger.stop_hotkey_listener()
            self._is_running = False
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Ana iş parçacığını düşük CPU ile uykuda tut
        try:
            while self._is_running:
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            self.trigger.stop_hotkey_listener()
            logger.info("Servis sonlandırıldı.")
