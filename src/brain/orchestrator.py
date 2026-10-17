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


from src.brain.prompts import AGENTIC_SYSTEM_PROMPT

SYSTEM_PROMPT = AGENTIC_SYSTEM_PROMPT


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
        models_to_try = [self.config.GEMINI_MODEL, "gemini-3.8-flash", "gemini-flash-latest"]
        # Tekrarları temizle
        models_to_try = list(dict.fromkeys([m for m in models_to_try if m]))

        last_error = None
        for model_name in models_to_try:
            # 1. google-genai SDK
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.config.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                raw_text = response.text or "{}"
                return self._parse_json_to_plan(raw_text, user_command, brain="cloud")
            except Exception as e:
                logger.debug(f"google-genai SDK ile hata ({model_name}): {e}")

            # 2. Doğrudan Google Gemini REST API
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.config.GEMINI_API_KEY}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.1
                    }
                }
                res = requests.post(url, headers=headers, json=payload, timeout=8.0)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return self._parse_json_to_plan(raw_text, user_command, brain="cloud")
                else:
                    last_error = f"Status {res.status_code}: {res.text[:120]}"
            except Exception as req_err:
                last_error = str(req_err)

        raise RuntimeError(f"Gemini Cloud çağrısı başarısız oldu: {last_error}")

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
            if action_name in (
                "capture_source_context",
                "send_to_yandex_gemini",
                "paste_to_source_app",
                "speak_or_notify",
                "open_application",
                "close_application",
                "open_website"
            ):
                actions.append(AgentAction(
                    action=action_name,
                    description=act.get("description", action_name),
                    parameters=act.get("parameters", {})
                ))

        # Kritik Güvenlik Kuralı: Uygulama açma/kapatma veya web açma varsa OCR veya Gemini adımlarını temizle
        has_app_control = any(a.action in ("close_application", "open_application", "open_website") for a in actions)
        if has_app_control:
            actions = [a for a in actions if a.action in ("close_application", "open_application", "open_website", "speak_or_notify")]
            if not any(a.action == "speak_or_notify" for a in actions):
                actions.append(AgentAction(
                    action="speak_or_notify",
                    description="Eylem bildirimini ver",
                    parameters={"message": "İşlem tamamlandı.", "notify_type": "banner"}
                ))

        if not actions:
            logger.warning("LLM geçerli eylem listesi döndürmedi, kural tabanlı motor devreye giriyor.")
            return self._generate_mock_plan(user_command, reason="Model geçerli eylemler üretemedi.")

        return ExecutionPlan(
            user_command=user_command,
            reasoning=reasoning,
            brain_used="cloud" if brain == "cloud" else "local",
            actions=actions
        )

    # -------------------------------------------------------------------------
    # Kural Tabanlı Simülasyon (Mock Mode / Smart Fallback)
    # -------------------------------------------------------------------------

    def _generate_mock_plan(self, user_command: str, reason: Optional[str] = None) -> ExecutionPlan:
        """API anahtarı veya Ollama olmadan test ve doğrulama yapabilen çok dilli (TR/EN/RU) kural tabanlı planlayıcı."""
        cmd_lower = user_command.lower().strip()
        actions: List[AgentAction] = []

        # 1. Kapatma / Quit / Close / Закрыть Komutları (TR / EN / RU)
        close_patterns = [
            "kapat", "çık", "sonlandır", "bitir",
            "close", "quit", "exit", "terminate", "kill",
            "закрой", "выйди", "выключи", "закрыть", "останови"
        ]
        is_close_cmd = any(w in cmd_lower for w in close_patterns)

        # 2. Açma / Open / Launch / Открыть Komutları (TR / EN / RU)
        open_patterns = [
            "aç", "başlat", "çalıştır", "git",
            "open", "launch", "start", "go to",
            "открой", "запусти", "открыть", "запустить", "перейди"
        ]
        is_open_cmd = any(w in cmd_lower for w in open_patterns)

        # Bilinen popüler web servisleri (TR / EN / RU)
        known_web_services = [
            ("youtube", "https://www.youtube.com", "YouTube"),
            ("youtub", "https://www.youtube.com", "YouTube"),
            ("yutub", "https://www.youtube.com", "YouTube"),
            ("ютуб", "https://www.youtube.com", "YouTube"),
            ("github", "https://github.com", "GitHub"),
            ("гитхаб", "https://github.com", "GitHub"),
            ("google", "https://www.google.com", "Google"),
            ("гугл", "https://www.google.com", "Google"),
            ("chatgpt", "https://chatgpt.com", "ChatGPT"),
            ("gemini", "https://gemini.google.com", "Gemini"),
            ("netflix", "https://www.netflix.com", "Netflix"),
            ("нетфликс", "https://www.netflix.com", "Netflix"),
            ("twitter", "https://twitter.com", "Twitter"),
            ("x.com", "https://x.com", "X"),
            ("твиттер", "https://twitter.com", "Twitter"),
            ("gmail", "https://mail.google.com", "Gmail"),
        ]

        detected_web = None
        for alias, url, service_name in known_web_services:
            if alias in cmd_lower:
                detected_web = (service_name, url)
                break

        # Bilinen macOS uygulamaları eşlemesi (TR / EN / RU)
        known_apps = [
            ("antigravity", "Antigravity"),
            ("антигравити", "Antigravity"),
            ("yandex", "Yandex"),
            ("яндекс", "Yandex"),
            ("safari", "Safari"),
            ("сафари", "Safari"),
            ("notes", "Notes"),
            ("notlar", "Notes"),
            ("заметки", "Notes"),
            ("terminal", "Terminal"),
            ("терминал", "Terminal"),
            ("vscode", "Visual Studio Code"),
            ("vs code", "Visual Studio Code"),
            ("visual studio code", "Visual Studio Code"),
            ("calculator", "Calculator"),
            ("hesap makinesi", "Calculator"),
            ("калькулятор", "Calculator"),
        ]

        detected_app = None
        for alias, app_name in known_apps:
            if alias in cmd_lower:
                detected_app = app_name
                break

        # A) SİSTEM KOMUTU: UYGULAMA KAPATMA (ASLA OCR / YANDEX ÇAĞRILMAZ!)
        if is_close_cmd:
            target = detected_app or "Antigravity"
            actions.append(AgentAction(
                action="close_application",
                description=f"{target} uygulamasını kapat",
                parameters={"target_app": target}
            ))
            if any(w in cmd_lower for w in ["закрой", "закрыть", "выйди", "выключи"]):
                msg = f"Приложение {target} закрыто."
            elif any(w in cmd_lower for w in ["close", "quit", "exit"]):
                msg = f"{target} has been closed."
            else:
                msg = f"{target} kapatıldı."

            actions.append(AgentAction(
                action="speak_or_notify",
                description="Uygulama kapatma bildirimini ver",
                parameters={"message": msg, "notify_type": "banner"}
            ))
            return ExecutionPlan(
                user_command=user_command,
                reasoning=reason or f"Sistem komutu algılandı: {target} uygulaması kapatılıyor.",
                brain_used="mock",
                actions=actions
            )

        # B) SİSTEM KOMUTU: WEB SİTESİ AÇMA (YANDEX BROWSER İLE)
        if (is_open_cmd or "http" in cmd_lower or ".com" in cmd_lower) and detected_web:
            service_name, target_url = detected_web
            actions.append(AgentAction(
                action="open_website",
                description=f"{service_name} web sitesini Yandex Browser'da aç",
                parameters={"url": target_url}
            ))
            if any(w in cmd_lower for w in ["открой", "открыть", "запусти", "запустить"]):
                msg = f"Сайт {service_name} открыт."
            elif any(w in cmd_lower for w in ["open", "launch", "start"]):
                msg = f"{service_name} has been opened."
            else:
                msg = f"{service_name} açıldı."

            actions.append(AgentAction(
                action="speak_or_notify",
                description="Web sitesi açma bildirimini ver",
                parameters={"message": msg, "notify_type": "banner"}
            ))
            return ExecutionPlan(
                user_command=user_command,
                reasoning=reason or f"Web servisi algılandı: {service_name} Yandex Browser'da açılıyor.",
                brain_used="mock",
                actions=actions
            )

        # C) SİSTEM KOMUTU: UYGULAMA AÇMA (ASLA OCR / YANDEX ÇAĞRILMAZ!)
        if is_open_cmd and detected_app:
            target = detected_app
            actions.append(AgentAction(
                action="open_application",
                description=f"{target} uygulamasını aç",
                parameters={"target_app": target}
            ))
            if any(w in cmd_lower for w in ["открой", "открыть", "запусти", "запустить"]):
                msg = f"Приложение {target} запущено."
            elif any(w in cmd_lower for w in ["open", "launch", "start"]):
                msg = f"{target} has been opened."
            else:
                msg = f"{target} açıldı."

            actions.append(AgentAction(
                action="speak_or_notify",
                description="Uygulama açma bildirimini ver",
                parameters={"message": msg, "notify_type": "banner"}
            ))
            return ExecutionPlan(
                user_command=user_command,
                reasoning=reason or f"Sistem komutu algılandı: {target} uygulaması açılıyor.",
                brain_used="mock",
                actions=actions
            )

        # D) GEMINI & METİN İŞLEME KOMUTLARI (TR / EN / RU)
        needs_paste = any(w in cmd_lower for w in [
            "yapıştır", "geri", "aktar", "yerine",
            "paste", "insert", "back",
            "вставь", "обратно", "вставить"
        ])
        needs_notify_only = any(w in cmd_lower for w in [
            "söyle", "sesli", "haber ver",
            "tell me", "say", "speak",
            "скажи", "озвучь", "прочитай"
        ])

        # 1. Adım: Kaynak yakalama (OCR / Selection)
        is_screen = any(w in cmd_lower for w in ["ekran", "экране", "экран", "screen"])
        actions.append(AgentAction(
            action="capture_source_context",
            description="Aktif penceredeki metni veya ekranı kaydet",
            parameters={"capture_type": "screen" if is_screen else "selection", "save_source_app": True}
        ))

        # 2. Adım: Yandex Gemini'ye gönderme
        actions.append(AgentAction(
            action="send_to_yandex_gemini",
            description="Yandex Browser'daki açık Gemini sekmesine prompt ve metni gönder",
            parameters={"prompt": user_command, "include_captured_text": True}
        ))

        # 3. Adım: Geri Yapıştırma
        if needs_paste or not needs_notify_only:
            actions.append(AgentAction(
                action="paste_to_source_app",
                description="Gemini yanıtını kaynak uygulamaya geri yapıştır",
                parameters={"target": "original_app"}
            ))

        # 4. Adım: Bildirim
        if any(w in cmd_lower for w in ["вставь", "отправь", "скопируй", "текст"]):
            done_msg = "Ответ Gemini успешно получен и обработан."
        elif any(w in cmd_lower for w in ["copy", "paste", "ask", "summarize"]):
            done_msg = "Gemini processing completed."
        else:
            done_msg = "İşlem tamamlandı, sonuç aktarıldı."

        actions.append(AgentAction(
            action="speak_or_notify",
            description="İşlem sonucunu kullanıcıya bildir",
            parameters={"message": done_msg, "notify_type": "banner"}
        ))

        return ExecutionPlan(
            user_command=user_command,
            reasoning=reason or "Çok dilli kural tabanlı motor ile yürütme planı oluşturuldu.",
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
