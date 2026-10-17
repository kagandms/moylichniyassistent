"""
Eylem Koordinatörü ve Plan Yürütücüsü (src/actuators/manager.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Faz 1'deki ExecutionPlan eylem adımlarını (AgentAction)
State, Perception, Yandex Gemini Köprüsü ve Notifier modülleri üzerinden
baştan sona güvenli ve pano hijyeni korumalı şekilde yürütür.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from src.actuators.notifier import SystemNotifier
from src.actuators.yandex_gemini import GeminiBridgeResult, YandexGeminiBridge
from src.brain.schemas import AgentAction, ExecutionPlan
from src.perception.manager import PerceivedContext, PerceptionManager
from src.state.manager import CapturedContext, StateManager

logger = logging.getLogger("mac_assistant.actuators.manager")


class ActuatorManager:
    """
    Eyleyici katmanını koordine eden ve asistan planlarını uçtan uca yürüten motor.
    """

    def __init__(
        self,
        state_mgr: Optional[StateManager] = None,
        perception_mgr: Optional[PerceptionManager] = None,
        yandex_bridge: Optional[YandexGeminiBridge] = None,
        notifier: Optional[SystemNotifier] = None
    ) -> None:
        self.state_mgr = state_mgr or StateManager()
        self.perception_mgr = perception_mgr or PerceptionManager()
        self.yandex_bridge = yandex_bridge or YandexGeminiBridge()
        self.notifier = notifier or SystemNotifier()

    def execute_plan(
        self,
        plan: ExecutionPlan,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Verilen ExecutionPlan içindeki eylemleri adım adım çalıştırır:
        1. capture_source_context: Pencereyi ve seçili metni (veya OCR ile ekranı) kaydeder.
        2. send_to_yandex_gemini: Prompt ve metni Yandex Gemini sekmesine gönderip yanıt alır.
        3. paste_to_source_app: Yanıtı kaynak pencereye yapıştırır ve panoyu geri yükler.
        4. speak_or_notify: İşlem sonucunu bildirir.
        """
        t0 = time.time()
        logger.info(f"▶️ [Plan Yürütme Başladı] {len(plan.actions)} adım koşturuluyor (dry_run={dry_run})...")

        step_results: List[Dict[str, Any]] = []
        captured_ctx: Optional[PerceivedContext] = None
        gemini_response = ""
        success_overall = True

        for idx, act in enumerate(plan.actions, start=1):
            step_t0 = time.time()
            action_name = act.action
            logger.info(f"📍 Adım {idx}/{len(plan.actions)}: '{action_name}' - {act.description}")

            try:
                # -----------------------------------------------------------------
                # EYLEM 1: capture_source_context
                # -----------------------------------------------------------------
                if action_name == "capture_source_context":
                    # simulate_copy: dry_run modunda panoyu tetiklememek için False yapılabilir
                    do_copy = not dry_run
                    captured_ctx = self.perception_mgr.capture_screen_or_selection(
                        self.state_mgr,
                        simulate_copy=do_copy
                    )
                    step_results.append({
                        "step": idx,
                        "action": action_name,
                        "status": "success",
                        "method": captured_ctx.capture_method,
                        "source_app": captured_ctx.source_app.app_name,
                        "text_length": len(captured_ctx.raw_text),
                        "elapsed_ms": (time.time() - step_t0) * 1000
                    })

                # -----------------------------------------------------------------
                # EYLEM 2: send_to_yandex_gemini
                # -----------------------------------------------------------------
                elif action_name == "send_to_yandex_gemini":
                    prompt = act.parameters.get("prompt", plan.user_command)
                    context_data = captured_ctx.raw_text if captured_ctx else ""

                    bridge_res: GeminiBridgeResult = self.yandex_bridge.send_prompt_and_wait_response(
                        prompt=prompt,
                        context_text=context_data,
                        dry_run=dry_run,
                        fallback_to_api=True
                    )
                    gemini_response = bridge_res.response_text
                    step_results.append({
                        "step": idx,
                        "action": action_name,
                        "status": "success" if bridge_res.success else "failed",
                        "method_used": bridge_res.method_used,
                        "response_preview": gemini_response[:60],
                        "error": bridge_res.error,
                        "elapsed_ms": (time.time() - step_t0) * 1000
                    })
                    if not bridge_res.success and not dry_run:
                        success_overall = False

                # -----------------------------------------------------------------
                # EYLEM 3: paste_to_source_app
                # -----------------------------------------------------------------
                elif action_name == "paste_to_source_app":
                    if dry_run:
                        logger.info("🧪 [Dry-Run] Yapıştırma adımı test ortamında ekranı değiştirmemek için simüle edildi.")
                        step_results.append({
                            "step": idx,
                            "action": action_name,
                            "status": "simulated",
                            "message": "Dry-run modunda yapıştırma simüle edildi, pano korundu.",
                            "elapsed_ms": (time.time() - step_t0) * 1000
                        })
                    else:
                        if captured_ctx is not None and gemini_response:
                            # StateManager ile orijinal pencereye odaklanıp yapıştır
                            # Dönüştür: PerceivedContext -> CapturedContext
                            compat_ctx = CapturedContext(
                                source_app=captured_ctx.source_app,
                                selected_text=captured_ctx.raw_text,
                                has_selection=(captured_ctx.capture_method == "selection"),
                                clipboard_snapshot=self.state_mgr.clipboard.snapshot()
                            )
                            pasted = self.state_mgr.paste_to_source_app(
                                text=gemini_response,
                                context=compat_ctx,
                                restore_clipboard_after=True
                            )
                            step_results.append({
                                "step": idx,
                                "action": action_name,
                                "status": "success" if pasted else "failed",
                                "target_app": captured_ctx.source_app.app_name,
                                "elapsed_ms": (time.time() - step_t0) * 1000
                            })
                        else:
                            step_results.append({
                                "step": idx,
                                "action": action_name,
                                "status": "skipped",
                                "message": "Kaynak bağlam veya yanıt metni bulunamadı.",
                                "elapsed_ms": (time.time() - step_t0) * 1000
                            })

                # -----------------------------------------------------------------
                # EYLEM 4: speak_or_notify
                # -----------------------------------------------------------------
                elif action_name == "speak_or_notify":
                    msg = act.parameters.get("message", "İşlem başarıyla tamamlandı.")
                    notify_type = act.parameters.get("notify_type", "banner")
                    speak = (notify_type == "voice")

                    # Dry-run modunda seslendirmeyi sessiz yap
                    self.notifier.notify(
                        message=msg,
                        title="Mac Agent Asistan",
                        speak=(speak and not dry_run)
                    )
                    step_results.append({
                        "step": idx,
                        "action": action_name,
                        "status": "success",
                        "notification": msg,
                        "spoken": speak and not dry_run,
                        "elapsed_ms": (time.time() - step_t0) * 1000
                    })

                else:
                    logger.warning(f"Bilinmeyen eylem tipi: {action_name}")
                    step_results.append({
                        "step": idx,
                        "action": action_name,
                        "status": "unknown",
                        "elapsed_ms": (time.time() - step_t0) * 1000
                    })

            except Exception as e:
                logger.error(f"Adım {idx} ({action_name}) sırasında hata: {e}")
                step_results.append({
                    "step": idx,
                    "action": action_name,
                    "status": "error",
                    "error": str(e),
                    "elapsed_ms": (time.time() - step_t0) * 1000
                })
                success_overall = False

        total_elapsed = (time.time() - t0) * 1000
        logger.info(f"🏁 [Plan Tamamlandı] {len(step_results)} adım yürütüldü ({total_elapsed:.1f}ms).")

        return {
            "success": success_overall,
            "dry_run": dry_run,
            "steps_count": len(step_results),
            "steps": step_results,
            "final_response": gemini_response,
            "elapsed_ms": total_elapsed
        }
