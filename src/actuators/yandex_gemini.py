"""
Yandex Browser Açık Gemini Sekmesi DOM Köprüsü (src/actuators/yandex_gemini.py)
MacBook Air M2 Zero-Idle-RAM Mimarisi

Kullanıcının halihazırda açık olan Yandex Browser oturumunu kullanarak:
1. Açık sekmeleri tarar ve 'gemini.google.com' sekmesini bulur (yoksa açar).
2. AppleScript ve DOM JavaScript enjeksiyonu ile promptu gönderir.
3. Yanıt akışını (streaming) takip eder ve tamamlanınca cevabı alır.
4. JS izni kapalıysa savunmacı hata yönetimi ve API fallback desteği sunar.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger("mac_assistant.actuators.yandex_gemini")


@dataclass(frozen=True)
class GeminiTabInfo:
    """Yandex Browser içindeki Gemini sekmesinin konum ve başlık bilgisi."""

    found: bool
    window_index: int = 1
    tab_index: int = 1
    url: str = ""
    title: str = ""

    def summary(self) -> str:
        if not self.found:
            return "Gemini sekmesi bulunamadı"
        return f"Pencere {self.window_index}, Sekme {self.tab_index}: '{self.title}' ({self.url[:35]}...)"


@dataclass(frozen=True)
class GeminiBridgeResult:
    """Gemini köprüsünden dönen sonuç modeli."""

    success: bool
    response_text: str = ""
    method_used: str = "yandex_dom"  # yandex_dom, api_fallback, mock_dry_run, keyboard_fallback
    tab_info: Optional[GeminiTabInfo] = None
    js_apple_events_enabled: bool = False
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class YandexGeminiBridge:
    """
    Yandex Browser ve Google Gemini web oturumu köprüsü.
    """

    def __init__(self, browser_name: Optional[str] = None) -> None:
        self.browser_name = browser_name or config.TARGET_BROWSER

    def is_yandex_running(self) -> bool:
        """Yandex Browser'ın çalışıp çalışmadığını milisaniyeler içinde kontrol eder."""
        try:
            out = subprocess.check_output(
                ["osascript", "-e", f'application "{self.browser_name}" is running'],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=1.5
            ).strip()
            return out == "true"
        except Exception:
            return False

    def list_open_tabs(self) -> List[GeminiTabInfo]:
        """Açık olan tüm Yandex pencerelerini ve sekmelerini tarar."""
        if not self.is_yandex_running():
            return []

        script = f'''
        tell application "{self.browser_name}"
            set outText to ""
            repeat with w from 1 to count of windows
                repeat with t from 1 to count of tabs of window w
                    set tabUrl to URL of tab t of window w
                    set tabTitle to title of tab t of window w
                    set outText to outText & w & "|" & t & "|" & tabUrl & "|" & tabTitle & linefeed
                end repeat
            end repeat
            return outText
        end tell
        '''
        tabs: List[GeminiTabInfo] = []
        try:
            raw = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3.0
            )
            for line in raw.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 4:
                    w_idx = int(parts[0]) if parts[0].isdigit() else 1
                    t_idx = int(parts[1]) if parts[1].isdigit() else 1
                    url = parts[2]
                    title = parts[3]
                    tabs.append(GeminiTabInfo(
                        found=("gemini.google.com" in url.lower()),
                        window_index=w_idx,
                        tab_index=t_idx,
                        url=url,
                        title=title
                    ))
        except Exception as e:
            logger.debug(f"Sekme listeleme hatası: {e}")

        return tabs

    def find_gemini_tab(self, auto_open: bool = False) -> GeminiTabInfo:
        """
        Açık sekmeler arasında 'gemini.google.com' sekmesini bulur.
        Bulunamazsa ve auto_open=True ise yeni sekmede açar.
        """
        if not self.is_yandex_running():
            logger.warning(f"⚠️ {self.browser_name} çalışmıyor.")
            return GeminiTabInfo(found=False)

        all_tabs = self.list_open_tabs()
        for tab in all_tabs:
            if "gemini.google.com" in tab.url.lower():
                logger.info(f"🎯 [Gemini Sekmesi Bulundu] {tab.summary()}")
                return tab

        # Açık değilse ve açılması istendiyse
        if auto_open:
            logger.info("🌐 [Sekme Açılıyor] Yandex'te yeni Gemini sekmesi açılıyor...")
            open_script = f'''
            tell application "{self.browser_name}"
                tell window 1
                    make new tab with properties {{URL:"https://gemini.google.com/app"}}
                end tell
            end tell
            '''
            try:
                subprocess.run(
                    ["osascript", "-e", open_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=3.0
                )
                time.sleep(1.5)  # Sayfanın yüklenmesi için kısa bekleme
                # Tekrar tara
                for tab in self.list_open_tabs():
                    if "gemini.google.com" in tab.url.lower():
                        return tab
            except Exception as e:
                logger.error(f"Gemini sekmesi açılamadı: {e}")

        return GeminiTabInfo(found=False)

    def check_js_permission(self, tab: Optional[GeminiTabInfo] = None) -> Tuple[bool, str]:
        """
        Yandex'te Apple Events ile JavaScript çalıştırma iznini test eder (1+1 çalıştırarak).
        """
        if not self.is_yandex_running():
            return False, f"{self.browser_name} çalışmıyor."

        target_tab = tab or self.find_gemini_tab()
        if not target_tab.found:
            # Herhangi bir ilk sekmeyi test et
            w_idx, t_idx = 1, 1
        else:
            w_idx, t_idx = target_tab.window_index, target_tab.tab_index

        script = f'''
        tell application "{self.browser_name}"
            tell tab {t_idx} of window {w_idx}
                execute javascript "1 + 1"
            end tell
        end tell
        '''
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=2.0
            )

            if res.returncode == 0 and res.stdout.strip() in ("2", "2.0"):
                return True, "Apple Events JavaScript izni AKTİF (DOM kontrolü hazır)."

            err_msg = res.stderr.strip()
            # Yandex/Chromium tipik hata kalıpları
            if any(term in err_msg.lower() for term in ["отключено", "turned off", "javascript", "applescript", "12"]):
                guidance = (
                    "Yandex Browser'da Apple Events JavaScript izni kapalı. "
                    "Açmak için: Yandex üst menüsünden 'Вид (Görünüm) > Разработчикам (Geliştirici) > "
                    "Разрешить JavaScript из событий Apple (Apple Olaylarından JavaScript'e İzin Ver)' seçeneğini işaretleyin."
                )
                return False, guidance

            return False, f"Bilinmeyen JS hatası: {err_msg}"

        except Exception as e:
            return False, str(e)

    def ui_paste_fallback(self, tab: GeminiTabInfo, text: str) -> bool:
        """
        Apple Events JS izni kapalı olduğunda Yandex sekmesini öne getirip
        klavye/pano simülasyonu ile promptu yapıştırıp gönderir.
        """
        try:
            activate_script = f'''
            tell application "{self.browser_name}"
                activate
                set active tab index of window {tab.window_index} to {tab.tab_index}
                set index of window {tab.window_index} to 1
            end tell
            '''
            subprocess.run(["osascript", "-e", activate_script], check=False, timeout=2.0)
            time.sleep(0.3)

            # Panoya koyup Cmd+V ve Return simüle et
            from src.state.clipboard import ClipboardManager
            cb = ClipboardManager()
            cb.set_text(text)

            keystroke_script = '''
            tell application "System Events"
                keystroke "v" using command down
                delay 0.15
                key code 36
            end tell
            '''
            subprocess.run(["osascript", "-e", keystroke_script], check=False, timeout=2.0)
            logger.info("⌨️ [UI Paste Fallback] Metin Yandex sekmesine yapıştırıldı ve Enter gönderildi.")
            return True
        except Exception as e:
            logger.error(f"UI Paste Fallback hatası: {e}")
            return False

    def send_prompt_and_wait_response(
        self,
        prompt: str,
        context_text: str = "",
        timeout: float = 45.0,
        dry_run: bool = False,
        fallback_to_api: bool = True
    ) -> GeminiBridgeResult:
        """
        Prompt ve bağlam metnini Yandex'teki açık Gemini sekmesine gönderir ve cevabı bekler.
        dry_run=True ise gerçek sekme durumunu doğrular ancak sohbete mesaj yazmaz.
        """
        t0 = time.time()

        if not self.is_yandex_running():
            return GeminiBridgeResult(
                success=False,
                error=f"{self.browser_name} açık değil. Lütfen tarayıcıyı başlatın.",
                elapsed_ms=(time.time() - t0) * 1000
            )

        tab_info = self.find_gemini_tab(auto_open=False)
        js_ok, js_msg = self.check_js_permission(tab_info)

        # 1. DRY-RUN TEST MODU (Test ortamı & doğrulamalar için)
        if dry_run:
            elapsed = (time.time() - t0) * 1000
            if tab_info.found:
                resp = f"[Dry-Run] Yandex Gemini sekmesi doğrulandı ({tab_info.title}). JS İzni: {'Açık' if js_ok else 'Kapalı'}."
                return GeminiBridgeResult(
                    success=True,
                    response_text=resp,
                    method_used="mock_dry_run",
                    tab_info=tab_info,
                    js_apple_events_enabled=js_ok,
                    elapsed_ms=elapsed
                )
            else:
                return GeminiBridgeResult(
                    success=True,
                    response_text="[Dry-Run] Yandex çalışıyor fakat açık Gemini sekmesi bulunamadı (auto_open ile açılabilir).",
                    method_used="mock_dry_run",
                    tab_info=tab_info,
                    js_apple_events_enabled=js_ok,
                    elapsed_ms=elapsed
                )

        # 2. CANLI MOD: JS İZNİ KAPALIYSA VEYA SEKME YOKSA FALLBACK
        combined_prompt = f"{prompt}\n\n[İLGİLİ EKRAN METNİ]:\n{context_text}" if context_text else prompt

        if not tab_info.found or not js_ok:
            if fallback_to_api and config.config.is_gemini_configured():
                logger.info(f"🔄 [Fallback] Yandex DOM doğrudan kullanılamadı ({js_msg}). Gemini API'ye yönlendiriliyor...")
                try:
                    from google import genai
                    client = genai.Client(api_key=config.config.GEMINI_API_KEY)
                    api_resp = client.models.generate_content(
                        model=config.config.GEMINI_MODEL,
                        contents=combined_prompt
                    )
                    text_out = (api_resp.text or "").strip()
                    elapsed = (time.time() - t0) * 1000
                    return GeminiBridgeResult(
                        success=True,
                        response_text=text_out,
                        method_used="api_fallback",
                        tab_info=tab_info,
                        js_apple_events_enabled=js_ok,
                        elapsed_ms=elapsed
                    )
                except Exception as api_err:
                    logger.error(f"Fallback API çağrısı da başarısız: {api_err}")

            return GeminiBridgeResult(
                success=False,
                error=f"Yandex Gemini kullanılamadı: {js_msg}",
                tab_info=tab_info,
                js_apple_events_enabled=js_ok,
                elapsed_ms=(time.time() - t0) * 1000
            )

        # 3. DOĞRUDAN DOM JAVASCRIPT ENJEKSİYONU (Canlı Yandex Oturumu)
        logger.info(f"🚀 [DOM Enjeksiyonu] Prompt Yandex Gemini sekmesine ({tab_info.title}) gönderiliyor...")

        # Prompt metnini JS için güvenli escape et
        escaped_prompt = json.dumps(combined_prompt)

        injection_script = f'''
        tell application "{self.browser_name}"
            tell tab {tab_info.tab_index} of window {tab_info.window_index}
                execute javascript "(function() {{
                    const text = {escaped_prompt};
                    // 1. Giriş kutusunu bul
                    const input = document.querySelector('div.ql-editor[contenteditable=\\"true\\"]') ||
                                  document.querySelector('rich-textarea div[contenteditable=\\"true\\"]') ||
                                  document.querySelector('div[role=\\"textbox\\"]') ||
                                  document.querySelector('textarea');
                    if (!input) return JSON.stringify({{error: 'input_not_found'}});
                    
                    input.focus();
                    input.innerText = text;
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    // 2. Gönder butonunu bul ve tıkla
                    const sendBtn = document.querySelector('button.send-button') ||
                                    document.querySelector('button[aria-label*=\\"Gönder\\"]') ||
                                    document.querySelector('button[aria-label*=\\"Send\\"]');
                    if (sendBtn && !sendBtn.disabled) {{
                        sendBtn.click();
                        return JSON.stringify({{status: 'sent_via_button'}});
                    }}
                    
                    return JSON.stringify({{status: 'input_filled'}});
                }})()"
            end tell
        end tell
        '''

        try:
            inject_res = subprocess.check_output(
                ["osascript", "-e", injection_script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5.0
            ).strip()
            logger.debug(f"DOM inject sonucu: {inject_res}")

            # Yanıt akışını (Streaming) takip et
            start_wait = time.time()
            last_text = ""
            stable_count = 0

            read_script = f'''
            tell application "{self.browser_name}"
                tell tab {tab_info.tab_index} of window {tab_info.window_index}
                    execute javascript "(function() {{
                        const responses = document.querySelectorAll('model-response, .markdown, .response-container');
                        if (responses.length === 0) return '';
                        const last = responses[responses.length - 1];
                        return last.innerText || '';
                    }})()"
                end tell
            end tell
            '''

            while time.time() - start_wait < timeout:
                time.sleep(0.6)
                current_text = subprocess.check_output(
                    ["osascript", "-e", read_script],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=3.0
                ).strip()

                if len(current_text) > 10:
                    if current_text == last_text:
                        stable_count += 1
                        # 2 ardışık kontrolde metin değişmediyse tamamlanmıştır
                        if stable_count >= 2:
                            logger.info(f"✨ [Yanıt Alındı] Gemini üretimi tamamlandı ({len(current_text)} karakter).")
                            return GeminiBridgeResult(
                                success=True,
                                response_text=current_text,
                                method_used="yandex_dom",
                                tab_info=tab_info,
                                js_apple_events_enabled=True,
                                elapsed_ms=(time.time() - t0) * 1000
                            )
                    else:
                        stable_count = 0
                        last_text = current_text

            elapsed = (time.time() - t0) * 1000
            return GeminiBridgeResult(
                success=bool(last_text),
                response_text=last_text or "Yanıt bekleme süresi doldu.",
                method_used="yandex_dom",
                tab_info=tab_info,
                js_apple_events_enabled=True,
                elapsed_ms=elapsed
            )

        except Exception as e:
            logger.error(f"DOM köprüsü yürütme hatası: {e}")
            return GeminiBridgeResult(
                success=False,
                error=str(e),
                tab_info=tab_info,
                js_apple_events_enabled=js_ok,
                elapsed_ms=(time.time() - t0) * 1000
            )
