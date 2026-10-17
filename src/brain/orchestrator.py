"""
Hibrit Karar Beyni (src/brain/orchestrator.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

İnternet bağlantısını ve ortam durumunu kontrol ederek:
1. Varsayılan (Bulut): Google Gemini Flash API (0 MB RAM harcar)
2. Çevrimdışı/Yedek: Yerel Ollama (İstek anında yüklenir, keep_alive="5m" veya buluta geçilince keep_alive=0 ile bellekten atılır)
3. Simülasyon (Mock): API anahtarı veya Ollama yoksa geliştirici/test ortamında çalışır.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import requests

import config
from src.brain.schemas import ActionType, AgentAction, ExecutionPlan

# Loglama yapılandırması
logger = logging.getLogger("mac_assistant.brain")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [Brain] %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)


SYSTEM_PROMPT = """Sen MacBook Air M2 üzerinde çalışan bir masaüstü AI asistanının karar beynisin.
Kullanıcının doğal dilde verdiği komutu analiz etmeli ve bunu SADECE aşağıdaki 4 atomik eylemden oluşan sıralı bir plana dönüştürmelisin:

DESTEKLENEN ARAÇLAR (ACTIONS):
1. 'capture_source_context':
   - Kullanıcının o anda çalıştığı aktif pencereyi ve seçili metni (veya ekran görüntüsünü) kopyalayıp hafızaya alır.
   - Parametreler: {"capture_type": "selection" | "screen", "save_source_app": true}

2. 'send_to_yandex_gemini':
   - Yandex Browser'da açık olan Google Gemini sekmesine odaklanır (yoksa açar), metni/promptu yapıştırıp cevabı bekler.
   - Parametreler: {"prompt": "...", "include_captured_text": true}

3. 'paste_to_source_app':
   - Gemini'den alınan cevabı kullanıcının ilk başta çalıştığı kaynak pencereye geri yapıştırır.
   - Parametreler: {"target": "original_app"}

4. 'speak_or_notify':
   - Kullanıcıya işlem tamamlandığında veya hata durumunda sesli ya da görsel bildirim verir.
   - Parametreler: {"message": "...", "notify_type": "voice" | "banner"}

YANIT FORMATI:
Sadece ve sadece aşağıdaki JSON şemasını döndür. Markdown etiketleri veya ekstra açıklama yazma:
{
  "user_command": "<kullanıcının orijinal komutu>",
  "reasoning": "<bu adımların neden seçildiğine dair kısa açıklama>",
  "actions": [
    {
      "action": "capture_source_context",
      "description": "Kaynak uygulamadan seçili metni kopyala",
      "parameters": {"capture_type": "selection", "save_source_app": true}
    },
    ...
  ]
}
"""


class HybridOrchestrator:
    """MacBook Air M2 için bellek korumalı hibrit orkestratör."""

    def __init__(self, settings: config.Settings = config.config) -> None:
        self.config = settings
        self._local_model_loaded: bool = False

    # -------------------------------------------------------------------------
    # Sistem ve Ağ Durum Kontrolleri
    # -------------------------------------------------------------------------

    def check_internet(self, timeout: float = 1.5) -> bool:
        """Hızlı DNS/Socket bağlantı testi ile internet varlığını denetler (1.5 sn max)."""
        # 1. Hızlı UDP DNS soket denemesi (Cloudflare / Google DNS)
        for host, port in [("1.1.1.1", 53), ("8.8.8.8", 53)]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                s.close()
                return True
            except (socket.timeout, OSError):
                continue

        # 2. HTTP HEAD yedek testi
        try:
            res = requests.head("https://www.google.com", timeout=timeout)
            return res.status_code < 400
        except requests.RequestException:
            return False

    def check_yandex_status(self) -> Dict[str, Any]:
        """AppleScript ile Yandex Browser'ın çalışıp çalışmadığını ve durumunu denetler."""
        browser_name = self.config.TARGET_BROWSER
        try:
            bundle_id = subprocess.check_output(
                ["osascript", "-e", f'id of application "{browser_name}"'],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.5
            ).strip()
            is_installed = bool(bundle_id)
        except Exception:
            is_installed = False
            bundle_id = "unknown"

        if not is_installed:
            return {
                "installed": False,
                "running": False,
                "window_count": 0,
                "bundle_id": bundle_id
            }

        script = f'''
        if application "{browser_name}" is running then
            tell application "{browser_name}" to count of windows
        else
            return -1
        end if
        '''
        try:
            output = subprocess.check_output(
                ["osascript", "-e", script],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2.0
            ).strip()
            count = int(output) if output.lstrip("-").isdigit() else -1
            is_running = (count >= 0)
            window_count = max(0, count)
            return {
                "installed": True,
                "running": is_running,
                "window_count": window_count,
                "bundle_id": bundle_id
            }
        except Exception as e:
            logger.debug(f"Yandex Browser kontrol hatası: {e}")
            return {
                "installed": is_installed,
                "running": False,
                "window_count": 0,
                "bundle_id": bundle_id
            }

    def check_ollama_status(self) -> Dict[str, Any]:
        """Ollama sunucusunu ve RAM'de yüklü model olup olmadığını kontrol eder."""
        try:
            res = requests.get(f"{self.config.OLLAMA_BASE_URL}/api/ps", timeout=1.2)
            if res.status_code == 200:
                data = res.json()
                models = data.get("models", [])
                loaded_model_names = [m.get("name") for m in models if m.get("name")]
                return {
                    "running": True,
                    "models_in_ram": loaded_model_names,
                    "ram_occupied": len(loaded_model_names) > 0
                }
        except requests.RequestException:
            pass

        return {
            "running": False,
            "models_in_ram": [],
            "ram_occupied": False
        }

    # -------------------------------------------------------------------------
    # RAM Koruması & Lazy Unload Mekanizması
    # -------------------------------------------------------------------------

    def unload_local_model(self, model: Optional[str] = None) -> bool:
        """
        KRİTİK M2 KURALI: Yerel LLM'i RAM'den derhal tahliye eder (keep_alive=0).
        Bulut modu çalıştığında veya yerel işlem bittiğinde MacBook belleğini serbest bırakır.
        """
        target_model = model or self.config.OLLAMA_MODEL
        try:
            res = requests.post(
                f"{self.config.OLLAMA_BASE_URL}/api/generate",
                json={"model": target_model, "keep_alive": 0},
                timeout=2.0
            )
            if res.status_code == 200:
                logger.info(f"🧹 [RAM Temizliği] Yerel model '{target_model}' RAM'den başarıyla tahliye edildi.")
                self._local_model_loaded = False
                return True
        except requests.RequestException:
            # Ollama çalışmıyorsa zaten RAM'de model yoktur
            pass
        return False

    # -------------------------------------------------------------------------
    # Karar Motoru (Orchestration Engine)
    # -------------------------------------------------------------------------

    def plan(self, user_command: str, force_mock: bool = False) -> ExecutionPlan:
        """
        Kullanıcı komutunu analiz ederek Pydantic ExecutionPlan nesnesi üretir.
        Hibrit Akış:
        1. force_mock ise doğrudan mock plan üretir.
        2. auto modunda internet varsa: Cloud Gemini API çağrılır + Yerel RAM boşaltılır.
        3. auto modunda internet yoksa veya local modu seçildiyse: Yerel Ollama çağrılır.
        4. Gerekli anahtarlar/servisler yoksa şema uyumlu akıllı simülasyon döndürülür.
        """
        if force_mock:
            logger.info("🧪 [Mock Modu] Kullanıcı isteği simüle ediliyor.")
            return self._generate_mock_plan(user_command)

        # İnternet kontrolü
        has_internet = self.check_internet()
        mode = self.config.BRAIN_MODE

        logger.debug(f"Planlama başlatıldı: mod={mode}, internet={'var' if has_internet else 'yok'}")

        # 1. BULUT GEMINI ROTASI (Varsayılan & 0 MB RAM)
        if (mode == "cloud" or (mode == "auto" and has_internet)):
            if self.config.is_gemini_configured():
                try:
                    plan = self._call_gemini_cloud(user_command)
                    # Bulut başarıyla çalıştı, eğer arka planda kalmış yerel model varsa RAM'i temizle
                    self.unload_local_model()
                    return plan
                except Exception as e:
                    logger.warning(f"⚠️ Bulut Gemini API çağrısı başarısız oldu: {e}")
                    if mode == "cloud":
                        logger.error("Bulut modu zorunlu kılındığı için yerel modele geçilmiyor.")
                        return self._generate_mock_plan(user_command, reason=f"Gemini API Hatası: {e}")
                    logger.info("🔄 Otomatik olarak yerel Ollama modeline geçiş yapılıyor...")
            else:
                logger.warning("⚠️ GEMINI_API_KEY .env dosyasında tanımlı değil.")
                if mode == "cloud":
                    return self._generate_mock_plan(
                        user_command,
                        reason="GEMINI_API_KEY bulunamadı. Lütfen .env dosyasına ekleyin."
                    )

        # 2. YEREL OLLAMA ROTASI (Offline / Fallback)
        ollama_status = self.check_ollama_status()
        if ollama_status["running"]:
            try:
                plan = self._call_ollama_local(user_command)
                self._local_model_loaded = True
                return plan
            except Exception as e:
                logger.warning(f"⚠️ Yerel Ollama çağrısı başarısız oldu: {e}")
        else:
            logger.info("ℹ️ Yerel Ollama sunucusu aktif değil.")

        # 3. ŞEMA DOĞRULAMALI MOCK FALLBACK (Sıfır Hata Garantisi)
        logger.info("💡 Ne canlı bulut API anahtarı ne de Ollama hazır; akıllı şema simülasyonu devrede.")
        return self._generate_mock_plan(
            user_command,
            reason="Gemini API anahtarı veya Ollama hazır olmadığı için güvenli simülasyon planı oluşturuldu."
        )

    # -------------------------------------------------------------------------
    # Model Çağrı Uygulamaları
    # -------------------------------------------------------------------------

    def _call_gemini_cloud(self, user_command: str) -> ExecutionPlan:
        """Google Gemini API çağrısı yapar (0 MB yerel bellek tüketir)."""
        prompt = f"{SYSTEM_PROMPT}\n\nKULLANICI KOMUTU:\n\"{user_command}\"\n"

        # Öncelikle yeni google-genai kütüphanesini dene
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.config.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=self.config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            raw_text = response.text or "{}"
            return self._parse_json_to_plan(raw_text, user_command, brain="cloud")
        except Exception as e:
            logger.debug(f"google-genai SDK ile hata, doğrudan REST API deneniyor: {e}")

        # Yedek: Doğrudan Google Gemini REST API (Bağımlılık hatasız)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.GEMINI_MODEL}:generateContent?key={self.config.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        res = requests.post(url, headers=headers, json=payload, timeout=8.0)
        res.raise_for_status()
        data = res.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_json_to_plan(raw_text, user_command, brain="cloud")

    def _call_ollama_local(self, user_command: str) -> ExecutionPlan:
        """
        Yerel Ollama modeline istek atar.
        keep_alive=self.config.OLLAMA_KEEP_ALIVE parametresiyle modelin RAM'de sonsuza kadar kalmasını önler.
        """
        prompt = f"{SYSTEM_PROMPT}\n\nKULLANICI KOMUTU:\n\"{user_command}\"\n"
        url = f"{self.config.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": self.config.OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "keep_alive": self.config.OLLAMA_KEEP_ALIVE,
            "options": {"temperature": 0.1}
        }
        res = requests.post(url, json=payload, timeout=25.0)
        res.raise_for_status()
        raw_text = res.json().get("response", "{}")
        return self._parse_json_to_plan(raw_text, user_command, brain="local")

    def _parse_json_to_plan(self, raw_json_text: str, user_command: str, brain: str) -> ExecutionPlan:
        """LLM çıktısından JSON ayıklar ve Pydantic ExecutionPlan modeline dönüştürür."""
        clean_text = raw_json_text.strip()
        # Markdown kod bloklarını temizle (```json ... ```)
        if "```" in clean_text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
            if match:
                clean_text = match.group(1).strip()

        data = json.loads(clean_text)

        # Gerekli alanları doğrula
        reasoning = data.get("reasoning", "LLM tarafından otomatik üretilen eylem planı.")
        raw_actions = data.get("actions", [])

        actions: List[AgentAction] = []
        for act in raw_actions:
            action_name = act.get("action")
            if action_name in ("capture_source_context", "send_to_yandex_gemini", "paste_to_source_app", "speak_or_notify"):
                actions.append(AgentAction(
                    action=action_name,
                    description=act.get("description", action_name),
                    parameters=act.get("parameters", {})
                ))

        if not actions:
            # Fallback güvenli eylem
            actions = [
                AgentAction(
                    action="capture_source_context",
                    description="Kaynak içeriği kopyala",
                    parameters={"capture_type": "selection", "save_source_app": True}
                ),
                AgentAction(
                    action="send_to_yandex_gemini",
                    description="Yandex Gemini'ye ilet",
                    parameters={"prompt": user_command, "include_captured_text": True}
                ),
                AgentAction(
                    action="paste_to_source_app",
                    description="Sonucu kaynak pencereye yapıştır",
                    parameters={"target": "original_app"}
                )
            ]

        return ExecutionPlan(
            user_command=user_command,
            reasoning=reasoning,
            brain_used="cloud" if brain == "cloud" else "local",
            actions=actions
        )

    # -------------------------------------------------------------------------
    # Kural Tabanlı Simülasyon (Mock Mode)
    # -------------------------------------------------------------------------

    def _generate_mock_plan(self, user_command: str, reason: Optional[str] = None) -> ExecutionPlan:
        """API anahtarı veya Ollama olmadan test ve doğrulama yapabilen şema uyumlu simülasyon."""
        cmd_lower = user_command.lower()
        actions: List[AgentAction] = []

        # Komut analizi
        needs_capture = any(w in cmd_lower for w in ["kopyala", "seçili", "ekrandaki", "ekran", "metni", "çıktı", "bu"])
        needs_gemini = any(w in cmd_lower for w in ["gemini", "yandex", "çevir", "özetle", "düzelt", "açıkla", "sor"])
        needs_paste = any(w in cmd_lower for w in ["yapıştır", "geri", "yaz", "aktar"])
        needs_notify = any(w in cmd_lower for w in ["haber ver", "söyle", "bildir", "sesli"])

        # 1. Adım: Kaynak yakalama
        if needs_capture or not actions:
            actions.append(AgentAction(
                action="capture_source_context",
                description="Kullanıcının aktif penceresini kaydet ve seçili metni/ekranı kopyala",
                parameters={"capture_type": "selection", "save_source_app": True}
            ))

        # 2. Adım: Yandex Gemini'ye gönderme
        if needs_gemini or True:
            actions.append(AgentAction(
                action="send_to_yandex_gemini",
                description="Yandex Browser'daki açık Gemini sekmesine prompt ve yakalanan metni gönder",
                parameters={
                    "prompt": user_command,
                    "include_captured_text": True
                }
            ))

        # 3. Adım: Sonucu geri yapıştırma
        if needs_paste or not needs_notify:
            actions.append(AgentAction(
                action="paste_to_source_app",
                description="Gemini'den alınan yanıtı kullanıcının ilk çalıştığı kaynak pencereye geri yapıştır",
                parameters={"target": "original_app"}
            ))

        # 4. Adım: Kullanıcıya bildirim
        actions.append(AgentAction(
            action="speak_or_notify",
            description="İşlemin başarıyla tamamlandığını kullanıcıya sesli/yazılı bildir",
            parameters={"message": "İşlem tamamlandı, sonuç aktarıldı.", "notify_type": "banner"}
        ))

        explanation = reason or "Kural tabanlı simülatör kullanılarak komut 4 atomik adıma ayrıştırıldı."

        return ExecutionPlan(
            user_command=user_command,
            reasoning=explanation,
            brain_used="mock",
            actions=actions
        )

    # -------------------------------------------------------------------------
    # Sistem Teşhis Raporu
    # -------------------------------------------------------------------------

    def get_diagnostics(self) -> Dict[str, Any]:
        """Tüm sistemin sağlık durumunu özetleyen sözlük döndürür."""
        internet_ok = self.check_internet()
        yandex_info = self.check_yandex_status()
        ollama_info = self.check_ollama_status()
        gemini_ok = self.config.is_gemini_configured()

        active_brain = "None"
        if self.config.BRAIN_MODE == "cloud":
            active_brain = "Google Gemini Flash (Cloud)" if gemini_ok else "Cloud (API Anahtarı Eksik)"
        elif self.config.BRAIN_MODE == "local":
            active_brain = f"Ollama Local ({self.config.OLLAMA_MODEL})" if ollama_info["running"] else "Local (Ollama Kapalı)"
        else:  # auto
            if internet_ok and gemini_ok:
                active_brain = "Google Gemini Flash (Cloud - 0 RAM)"
            elif ollama_info["running"]:
                active_brain = f"Ollama Local ({self.config.OLLAMA_MODEL} - On-Demand)"
            else:
                active_brain = "Mock Simulation Engine"

        return {
            "internet": internet_ok,
            "brain_mode_setting": self.config.BRAIN_MODE,
            "active_brain": active_brain,
            "gemini_configured": gemini_ok,
            "gemini_model": self.config.GEMINI_MODEL,
            "yandex_browser": yandex_info,
            "ollama": ollama_info,
            "zero_idle_ram_active": not ollama_info["ram_occupied"]
        }
