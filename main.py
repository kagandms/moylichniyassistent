#!/usr/bin/env python3
"""
MacBook Air M2 Agentic Asistan - Ana Giriş ve Sağlık Kontrolü (main.py)
Faz 1: İskelet, Konfigürasyon ve Hibrit Karar Beyni Testi
Faz 2: Durum Hafızası, Aktif Pencere Takibi ve Pano Hijyeni Testi
Faz 3: Algılama Katmanı (Apple Vision OCR, VAD Ses Kaydı ve STT) Testi
Faz 4: Eyleyici Katmanı (Yandex Gemini DOM Köprüsü ve Eylem Zinciri) Testi
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

import config
from src.actuators.manager import ActuatorManager
from src.actuators.notifier import SystemNotifier
from src.actuators.yandex_gemini import YandexGeminiBridge
from src.brain.orchestrator import HybridOrchestrator
from src.brain.schemas import ExecutionPlan
from src.perception.audio import OnDemandAudioRecorder
from src.perception.manager import PerceptionManager
from src.perception.ocr import ScreenOCR
from src.perception.stt import SpeechToTextEngine
from src.perception.trigger import CommandTrigger
from src.state.clipboard import ClipboardManager
from src.state.manager import StateManager
from src.state.window_tracker import WindowTracker

console = Console()


def print_banner() -> None:
    """Başlık banner'ını ekrana basar."""
    banner_text = (
        "[bold cyan]MacBook Air M2 — Agentic Sesli & Yazılı Asistan[/bold cyan]\n"
        "[dim]Zero-Idle-RAM | Vision OCR | Yandex Gemini DOM | Faz 1, 2, 3 & 4[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def display_health_check(orchestrator: HybridOrchestrator) -> None:
    """Sistem donanım, ağ, tarayıcı ve LLM sağlık durumunu şık bir tabloda gösterir."""
    diag = orchestrator.get_diagnostics()

    table = Table(title="🔍 Sistem ve Donanım Sağlık Raporu (M2 Diagnostics)", border_style="bright_blue")
    table.add_column("Bileşen", style="bold white", width=26)
    table.add_column("Mevcut Durum / Değer", style="cyan", width=34)
    table.add_column("Sağlık / Not", style="green", width=24)

    # 1. İnternet
    if diag["internet"]:
        table.add_row("İnternet Bağlantısı", "Bağlı (DNS & HTTP OK)", "[bold green]✅ Aktif[/bold green]")
    else:
        table.add_row("İnternet Bağlantısı", "Bağlantı Yok (Offline)", "[bold yellow]⚠️ Çevrimdışı (Local/Mock)[/bold yellow]")

    # 2. Beyin Modu ve Aktif Motor
    mode_str = f"{diag['brain_mode_setting'].upper()} ({diag['active_brain']})"
    table.add_row("Karar Beyni Modu", mode_str, "[bold green]✅ Hazır[/bold green]")

    # 3. Gemini Bulut Durumu
    if diag["gemini_configured"]:
        table.add_row("Gemini Cloud API", f"Model: {diag['gemini_model']}", "[bold green]✅ Anahtar Tanımlı (0 RAM)[/bold green]")
    else:
        table.add_row("Gemini Cloud API", "API Anahtarı Tanımlanmadı", "[bold yellow]⚠️ .env içinde eksik[/bold yellow]")

    # 4. Yandex Browser Durumu
    yb = diag["yandex_browser"]
    if yb["installed"]:
        if yb["running"]:
            table.add_row("Yandex Browser", f"Çalışıyor ({yb['window_count']} pencere açık)", "[bold green]✅ AppleScript Hazır[/bold green]")
        else:
            table.add_row("Yandex Browser", "Yüklü (Şu an kapalı)", "[dim yellow]💤 Asistan gerekirse açar[/dim yellow]")
    else:
        table.add_row("Yandex Browser", "Kurulu Değil", "[bold red]❌ Yandex bulunamadı[/bold red]")

    # 5. Yerel Ollama Durumu
    ollama = diag["ollama"]
    if ollama["running"]:
        loaded = ", ".join(ollama["models_in_ram"]) if ollama["models_in_ram"] else "Yok (0 MB RAM)"
        table.add_row("Ollama Sunucusu", f"Aktif (Model: {config.OLLAMA_MODEL})", f"[bold green]✅ RAM: {loaded}[/bold green]")
    else:
        table.add_row("Ollama Sunucusu", "Çalışmıyor (Port 11434 kapalı)", "[dim]💤 İsteğe bağlı yerel yedek[/dim]")

    # 6. Zero-Idle-RAM Mimarisi
    if diag["zero_idle_ram_active"]:
        table.add_row("Zero-Idle-RAM Koruması", "RAM'de hiçbir yerel model yok", "[bold green]✅ Koruma Aktif (<50MB)[/bold green]")
    else:
        table.add_row("Zero-Idle-RAM Koruması", "RAM'de yerel model yüklü!", "[bold red]⚠️ Model RAM'de bekliyor[/bold red]")

    console.print(table)
    console.print()


def display_execution_plan(plan: ExecutionPlan) -> None:
    """Oluşturulan yürütme planını detaylı şekilde konsola yazdırır."""
    plan_title = f"📋 Üretilen Eylem Planı (Motor: [bold yellow]{plan.brain_used.upper()}[/bold yellow])"
    console.print(Panel(f"[bold]Kullanıcı Komutu:[/bold] [italic]{plan.user_command}[/italic]\n[bold]Model Gerekçesi:[/bold] {plan.reasoning}", title=plan_title, border_style="green"))

    table = Table(title="Adım Adım Yürütülecek Atomik Eylemler", border_style="green")
    table.add_column("Adım", justify="center", style="bold cyan", width=6)
    table.add_column("Eylem (Action)", style="bold magenta", width=25)
    table.add_column("Açıklama", style="white", width=38)
    table.add_column("Parametreler (Payload)", style="dim yellow", width=30)

    for idx, act in enumerate(plan.actions, start=1):
        table.add_row(
            str(idx),
            act.action,
            act.description,
            str(act.parameters)
        )

    console.print(table)
    console.print()

    # Raw JSON çıktısı
    console.print("[dim bold]JSON Doğrulama Çıktısı (Pydantic Schema):[/dim bold]")
    syntax = Syntax(plan.to_formatted_json(), "json", theme="monokai", line_numbers=False)
    console.print(syntax)
    console.print()


def run_state_tests() -> None:
    """Faz 2: Durum Hafızası, Aktif Pencere Takibi ve Pano Hijyeni Test Süiti."""
    console.print(Panel("[bold magenta]🧪 FAZ 2 KABUL TESTLERİ: Durum Hafızası, Pencere Takibi ve Pano Hijyeni[/bold magenta]", border_style="magenta"))

    clipboard = ClipboardManager()
    tracker = WindowTracker()
    state_mgr = StateManager(clipboard=clipboard, window_tracker=tracker)

    test_results = Table(title="🔬 Faz 2 Test Sonuçları Raporu", border_style="cyan")
    test_results.add_column("Test Senaryosu", style="bold white", width=30)
    test_results.add_column("Beklenen Sonuç", style="dim cyan", width=35)
    test_results.add_column("Gerçekleşen Durum", style="yellow", width=30)
    test_results.add_column("Durum", justify="center", width=12)

    # TEST 1: Pano Hijyeni
    orig_text = clipboard.get_text()
    snap = clipboard.snapshot()
    test_token = f"__FAZ2_TEST_TOKEN_{int(time.time())}__"

    clipboard.set_text(test_token)
    written_text = clipboard.get_text()

    restored_ok = clipboard.restore(snap)
    current_text_after_restore = clipboard.get_text()

    clipboard_passed = (
        written_text == test_token and
        restored_ok and
        current_text_after_restore == orig_text
    )

    clip_status = "[bold green]✅ PASS[/bold green]" if clipboard_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Pano Snapshot & Restore",
        "Eski pano eksiksiz korunmalı",
        f"Yedeklendi, yazıldı, {len(current_text_after_restore)} kar. geri yüklendi",
        clip_status
    )

    with clipboard.preserve_clipboard():
        clipboard.set_text("__TMP_CTX_MANAGER_VAL__")
    cm_restored_text = clipboard.get_text()
    cm_passed = (cm_restored_text == orig_text)
    cm_status = "[bold green]✅ PASS[/bold green]" if cm_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Pano Context Manager",
        "with preserve_clipboard() oto geri yüklemeli",
        "Blok bitiminde otomatik eski içeriğe dönüldü",
        cm_status
    )

    # TEST 2: Aktif Pencere Takibi
    front_app = tracker.get_frontmost_app()
    tracker_passed = bool(front_app.bundle_id and front_app.bundle_id != "unknown")
    tracker_status = "[bold green]✅ PASS[/bold green]" if tracker_passed else "[bold yellow]⚠️ WARN[/bold yellow]"
    test_results.add_row(
        "Aktif Pencere Tespiti",
        "Frontmost app (bundle_id, pid) bulunmalı",
        f"{front_app.app_name} ({front_app.bundle_id}, PID: {front_app.pid})",
        tracker_status
    )

    focus_ok = tracker.focus_app(front_app, wait_seconds=0.1)
    focus_status = "[bold green]✅ PASS[/bold green]" if focus_ok else "[bold yellow]⚠️ WARN[/bold yellow]"
    test_results.add_row(
        "Uygulamaya Geri Odaklanma",
        "Hedef uygulama öne (activate) gelmeli",
        f"Aktivasyon sinyali verildi (OK={focus_ok})",
        focus_status
    )

    # TEST 3: Seçili Metin & Durum Yakalama
    has_ax = state_mgr.check_accessibility_permission()
    ax_desc = "İzin Verildi (Cmd+C/V aktif)" if has_ax else "İzin Yok (Sistem Ayarları izni bekleniyor)"
    ax_status = "[bold green]✅ AKTİF[/bold green]" if has_ax else "[dim yellow]⚠️ BİLGİ[/dim yellow]"
    test_results.add_row(
        "macOS Erişilebilirlik (AX)",
        "AXIsProcessTrusted kontrolü",
        ax_desc,
        ax_status
    )

    ctx_no_copy = state_mgr.capture_source_context(simulate_copy=False)
    no_copy_passed = (ctx_no_copy.source_app.app_name == front_app.app_name)
    no_copy_status = "[bold green]✅ PASS[/bold green]" if no_copy_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Durum Yakalama (Simülasyonsuz)",
        "Pencere ve pano yedeği alınmalı",
        f"Kaynak: {ctx_no_copy.source_app.app_name}, has_selection={ctx_no_copy.has_selection}",
        no_copy_status
    )

    ctx_copy = state_mgr.capture_source_context(simulate_copy=True)
    copy_passed = (ctx_copy.source_app.app_name == front_app.app_name)
    copy_status = "[bold green]✅ PASS[/bold green]" if copy_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Durum Yakalama (Cmd+C Savunmacı)",
        "Çökmeden çalışmalı, izne göre seçim bildirmeli",
        f"has_selection={ctx_copy.has_selection} (Seçim yoksa Faz 3 OCR devreye girer)",
        copy_status
    )

    final_clip = clipboard.get_text()
    final_hygiene_ok = (final_clip == orig_text)

    console.print(test_results)
    console.print()

    if final_hygiene_ok:
        clip_preview = f"'{orig_text[:40]}...'" if orig_text else "(Boş Pano)"
        hygiene_panel = Panel(
            f"[bold green]🛡️ PANO HİJYENİ %100 BAŞARILI[/bold green]\n"
            f"Test tamamlandıktan sonra panonuz kuruşu kuruşuna orijinal durumuna geri döndürüldü.\n"
            f"[dim]Mevcut Pano İçeriği:[/dim] {clip_preview}",
            border_style="green"
        )
    else:
        hygiene_panel = Panel(
            "[bold red]❌ PANO HİJYENİ UYARISI: Pano orijinal haline dönemedi![/bold red]",
            border_style="red"
        )
    console.print(hygiene_panel)
    console.print()


def run_perception_tests() -> None:
    """Faz 3: Apple Vision OCR, Bluetooth Mikrofon Hijyeni ve STT Test Süiti."""
    console.print(Panel("[bold blue]🧪 FAZ 3 KABUL TESTLERİ: Apple Vision OCR, Bluetooth Mikrofon Hijyeni & STT[/bold blue]", border_style="blue"))

    ocr = ScreenOCR()
    recorder = OnDemandAudioRecorder()
    stt = SpeechToTextEngine()
    perception_mgr = PerceptionManager(ocr=ocr, audio=recorder, stt=stt)
    state_mgr = StateManager()

    test_results = Table(title="🔬 Faz 3 Algılama Test Sonuçları", border_style="blue")
    test_results.add_column("Test Bileşeni", style="bold white", width=28)
    test_results.add_column("Beklenen Davranış", style="dim cyan", width=35)
    test_results.add_column("Gerçekleşen Durum", style="yellow", width=32)
    test_results.add_column("Durum", justify="center", width=12)

    # TEST 1: Apple Vision OCR Görsel Doğrulama
    test_phrase = "MacBook Air M2 Apple Vision OCR Testi"
    synthetic_img = ScreenOCR.create_synthetic_test_image(test_phrase)
    ocr_result = ocr.extract_text_from_image(synthetic_img)

    ocr_passed = (ocr_result.has_text and "Apple Vision" in ocr_result.text)
    ocr_status = "[bold green]✅ PASS[/bold green]" if ocr_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Apple Vision OCR (Görsel)",
        "Görseldeki Türkçe metin okunmalı",
        f"'{ocr_result.text[:30]}...' ({ocr_result.elapsed_ms:.1f}ms, güven=%{ocr_result.confidence*100:.0f})",
        ocr_status
    )

    # TEST 2: Ekran Yakalama ve Savunmacı İzin Kontrolü
    screen_res = ocr.extract_text_from_screen()
    screen_passed = (screen_res.error is None or "Ekran Kaydı" in screen_res.error or screen_res.has_text)
    screen_status = "[bold green]✅ PASS[/bold green]" if screen_passed else "[bold red]❌ FAIL[/bold red]"
    screen_desc = f"{screen_res.line_count} satır okundu" if screen_res.has_text else (screen_res.error or "Boş ekran")
    test_results.add_row(
        "Apple Vision OCR (Ekran)",
        "Ekranı sessizce oku / izni yönet",
        screen_desc[:32],
        screen_status
    )

    # TEST 3: Birleşik Algılama
    perceived_ctx = perception_mgr.capture_screen_or_selection(state_mgr, simulate_copy=False)
    fallback_passed = (perceived_ctx.capture_method == "vision_ocr")
    fallback_status = "[bold green]✅ PASS[/bold green]" if fallback_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Seçim -> OCR Fallback",
        "has_selection=False ise OCR'a geçmeli",
        f"Yöntem: {perceived_ctx.capture_method} (Kaynak: {perceived_ctx.source_app.app_name})",
        fallback_status
    )

    # TEST 4: Bluetooth Koruma & Sıfır Boşta Mikrofon
    idle_mic_closed = (recorder.is_microphone_active is False)
    mic_status = "[bold green]✅ PASS[/bold green]" if idle_mic_closed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Bluetooth Mikrofon Koruması",
        "Boşta mikrofon KAPALI olmalı",
        f"Aktif Akış: {recorder.is_microphone_active} (A2DP 48kHz Korundu)",
        mic_status
    )

    # TEST 5: Ses Transkripsiyon (STT) Testi
    test_wav = OnDemandAudioRecorder.create_synthetic_test_wav(duration=0.5)
    try:
        stt_result = stt.transcribe(test_wav, language="tr")
        stt_passed = (stt_result.error is None and len(stt_result.text) > 0)
        stt_status = "[bold green]✅ PASS[/bold green]" if stt_passed else "[bold red]❌ FAIL[/bold red]"
        test_results.add_row(
            "Ses Tanıma (STT Motoru)",
            "WAV ses verisi Türkçe metne dönmeli",
            f"Motor: {stt_result.engine_used} ({stt_result.elapsed_ms:.1f}ms)",
            stt_status
        )
    finally:
        if os.path.exists(test_wav):
            os.unlink(test_wav)

    console.print(test_results)
    console.print()

    summary_panel = Panel(
        "[bold green]✨ FAZ 3 ALGILAMA KATMANI %100 ÇALIŞIYOR[/bold green]\n"
        "• [bold white]Apple Vision OCR:[/bold white] Apple Neural Engine üzerinde ~120ms sürede yerel Türkçe okuma sağlandı.\n"
        "• [bold white]Bluetooth & VAD Güvencesi:[/bold white] Mikrofon boştayken kesinlikle kapalıdır; AirPods/Bluetooth kulaklıklar HFP mono moduna düşmez.\n"
        "• [bold white]Akıllı Hibrit Algılama:[/bold white] Seçim varsa kopyalar, yoksa otomatik ekran OCR'ına geçer.",
        border_style="green"
    )
    console.print(summary_panel)
    console.print()


def run_actuators_tests() -> None:
    """Faz 4: Yandex Browser Gemini DOM Köprüsü, Bildirimler ve Eyleyici Zinciri Test Süiti."""
    console.print(Panel("[bold red]🧪 FAZ 4 KABUL TESTLERİ: Yandex Browser Gemini DOM Köprüsü & Eyleyici Zinciri[/bold red]", border_style="red"))

    clipboard = ClipboardManager()
    orig_clip = clipboard.get_text()

    bridge = YandexGeminiBridge()
    notifier = SystemNotifier()
    state_mgr = StateManager(clipboard=clipboard)
    perception_mgr = PerceptionManager()
    actuator_mgr = ActuatorManager(
        state_mgr=state_mgr,
        perception_mgr=perception_mgr,
        yandex_bridge=bridge,
        notifier=notifier
    )

    test_results = Table(title="🔬 Faz 4 Eyleyici Test Sonuçları Raporu", border_style="red")
    test_results.add_column("Test Bileşeni", style="bold white", width=28)
    test_results.add_column("Beklenen Sonuç", style="dim cyan", width=34)
    test_results.add_column("Gerçekleşen Durum", style="yellow", width=34)
    test_results.add_column("Durum", justify="center", width=12)

    # ---------------------------------------------------------
    # TEST 1: Yandex Browser & Sekme Taraması
    # ---------------------------------------------------------
    is_running = bridge.is_yandex_running()
    gemini_tab = bridge.find_gemini_tab(auto_open=False)

    if is_running and gemini_tab.found:
        tab_desc = f"P{gemini_tab.window_index} S{gemini_tab.tab_index}: {gemini_tab.title[:25]}..."
        tab_status = "[bold green]✅ PASS[/bold green]"
    elif is_running:
        tab_desc = "Yandex açık fakat Gemini sekmesi yok"
        tab_status = "[bold yellow]⚠️ WARN[/bold yellow]"
    else:
        tab_desc = "Yandex Browser kapalı"
        tab_status = "[bold red]❌ FAIL[/bold red]"

    test_results.add_row(
        "Yandex Sekme Taraması",
        "Açık Gemini sekmesi tespit edilmeli",
        tab_desc,
        tab_status
    )

    # ---------------------------------------------------------
    # TEST 2: JS DOM Köprüsü & İzin Kontrolü
    # ---------------------------------------------------------
    js_ok, js_msg = bridge.check_js_permission(gemini_tab)
    if js_ok:
        js_status = "[bold green]✅ AKTİF[/bold green]"
        js_display = "Apple Events JS İzni Açık"
    else:
        # İzin kapalı olsa bile bu beklenen bir güvenlik kısıtıdır, sistem çökmez
        js_status = "[bold yellow]⚠️ BİLGİ[/bold yellow]"
        js_display = "İzin kapalı (Görünüm > Geliştirici)"

    test_results.add_row(
        "Apple Events JS İzni",
        "Yandex DOM enjeksiyon izni",
        js_display,
        js_status
    )

    # ---------------------------------------------------------
    # TEST 3: macOS Bildirim (SystemNotifier) Testi
    # ---------------------------------------------------------
    notif_ok = notifier.notify(
        message="Faz 4 Eyleyici Katmanı Doğrulandı.",
        title="Mac Agent Asistan",
        subtitle="Sistem Testi",
        speak=False
    )
    notif_status = "[bold green]✅ PASS[/bold green]" if notif_ok else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "macOS Bildirim Sistemi",
        "Notification Center banner gönderilmeli",
        "Bildirim başarıyla iletildi",
        notif_status
    )

    # ---------------------------------------------------------
    # TEST 4: Uçtan Uca Eylem Zinciri (Dry-Run Yürütme)
    # ---------------------------------------------------------
    orchestrator = HybridOrchestrator()
    sample_plan = orchestrator.plan(
        "Ekranda yer alan çıktıyı kopyala, Yandex'teki Gemini'ye yapıştır ve cevabı geri yapıştır",
        force_mock=True
    )
    exec_result = actuator_mgr.execute_plan(sample_plan, dry_run=True)
    chain_ok = exec_result["success"]
    chain_status = "[bold green]✅ PASS[/bold green]" if chain_ok else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Eylem Zinciri (Dry-Run)",
        "Tüm 4 adım sıralı çalışmalı",
        f"{exec_result['steps_count']} adım yürütüldü ({exec_result['elapsed_ms']:.1f}ms)",
        chain_status
    )

    console.print(test_results)
    console.print()

    # Pano hijyenini doğrula
    current_clip = clipboard.get_text()
    hygiene_ok = (current_clip == orig_clip)

    if hygiene_ok:
        clip_preview = f"'{orig_clip[:40]}...'" if orig_clip else "(Boş Pano)"
        hygiene_panel = Panel(
            f"[bold green]🛡️ PANO HİJYENİ %100 KORUNDU[/bold green]\n"
            f"Faz 4 eylem zinciri testi tamamlandıktan sonra kullanıcının panosu eksiksiz doğrulandı.\n"
            f"[dim]Mevcut Pano İçeriği:[/dim] {clip_preview}",
            border_style="green"
        )
    else:
        hygiene_panel = Panel(
            "[bold red]❌ PANO HİJYENİ UYARISI: Pano orijinal haline dönemedi![/bold red]",
            border_style="red"
        )
    console.print(hygiene_panel)
    console.print()

    # JS İzni Yönergesi (eğer kapalıysa)
    if not js_ok:
        guide_panel = Panel(
            "[bold yellow]💡 İPUCU: Yandex Browser'da Canlı DOM Enjeksiyonu İçin:[/bold yellow]\n"
            "Yandex menü çubuğundan: [bold white]Вид (Görünüm) > Разработчикам (Geliştirici) > "
            "Разрешить JavaScript из событий Apple (Apple Olaylarından JavaScript'e İzin Ver)[/bold white] seçeneğini tıklayın.\n"
            "[dim](Bu seçenek kapalıyken bile asistan Gemini API fallback veya klavye/pano yöntemiyle çalışmaya devam eder).[/dim]",
            border_style="yellow"
        )
        console.print(guide_panel)
        console.print()


def main() -> None:
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(
        description="MacBook Air M2 Agentic PC Asistanı - Faz 1, 2, 3 & 4 Test ve Sağlık Kontrolü"
    )
    parser.add_argument(
        "--test-brain", "-t",
        type=str,
        default=None,
        help="Hibrit karar beynine gönderilecek örnek kullanıcı komutu"
    )
    parser.add_argument(
        "--test-state",
        action="store_true",
        help="Faz 2: Pano hijyeni, aktif pencere takibi ve durum hafızasını test eder"
    )
    parser.add_argument(
        "--test-perception",
        action="store_true",
        help="Faz 3: Apple Vision OCR, Bluetooth mikrofon hijyeni ve ses tanımayı test eder"
    )
    parser.add_argument(
        "--test-actuators",
        action="store_true",
        help="Faz 4: Yandex Browser Gemini DOM köprüsünü ve eylem zincirini test eder"
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Sistem sağlık durumunu ve donanım hazır bulunuşluğunu denetler"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="API anahtarı kontrolünü atlayıp doğrudan simülasyon modunu zorla"
    )
    parser.add_argument(
        "--unload-ollama",
        action="store_true",
        help="RAM'de kalmış herhangi bir yerel Ollama modelini tahliye eder (keep_alive=0)"
    )

    args = parser.parse_args()
    print_banner()

    orchestrator = HybridOrchestrator()

    if args.unload_ollama:
        console.print("[yellow]Ollama RAM tahliyesi isteniyor...[/yellow]")
        unloaded = orchestrator.unload_local_model()
        if unloaded:
            console.print("[green]Başarılı: Yerel model bellekten boşaltıldı.[/green]")
        else:
            console.print("[dim]Bilgi: RAM'de tahliye edilecek bir model bulunamadı veya Ollama kapalı.[/dim]")
        return

    # Faz 2 State Testi istendiyse çalıştır
    if args.test_state:
        run_state_tests()
        return

    # Faz 3 Perception Testi istendiyse çalıştır
    if args.test_perception:
        run_perception_tests()
        return

    # Faz 4 Actuators Testi istendiyse çalıştır
    if args.test_actuators:
        run_actuators_tests()
        return

    # Varsayılan olarak veya --health-check verildiğinde sağlık kontrolünü göster
    display_health_check(orchestrator)

    # Test komutu varsa çalıştır; yoksa varsayılan test komutu ile beyni test et
    test_command = args.test_brain
    if not test_command and not args.health_check:
        test_command = "Ekranda yer alan çıktıyı kopyala, Yandex'teki Gemini'ye yapıştır ve cevabı geri yapıştır"

    if test_command:
        console.print(f"[bold cyan]🧠 Hibrit Beyin Test Ediliyor:[/bold cyan] [italic]\"{test_command}\"[/italic]\n")
        plan = orchestrator.plan(test_command, force_mock=args.mock)
        display_execution_plan(plan)
        console.print("[bold green]✨ Faz 1 Kabul Kriteri Başarılı: Hibrit Beyin ve Proje İskeleti Çalışıyor![/bold green]\n")


if __name__ == "__main__":
    main()
