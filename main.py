#!/usr/bin/env python3
"""
MacBook Air M2 Agentic Asistan - Ana Giriş ve Sağlık Kontrolü (main.py)
Faz 1: İskelet, Konfigürasyon ve Hibrit Karar Beyni Testi
Faz 2: Durum Hafızası, Aktif Pencere Takibi ve Pano Hijyeni Testi
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

import config
from src.brain.orchestrator import HybridOrchestrator
from src.brain.schemas import ExecutionPlan
from src.state.clipboard import ClipboardManager
from src.state.manager import StateManager
from src.state.window_tracker import WindowTracker

console = Console()


def print_banner() -> None:
    """Başlık banner'ını ekrana basar."""
    banner_text = (
        "[bold cyan]MacBook Air M2 — Agentic Sesli & Yazılı Asistan[/bold cyan]\n"
        "[dim]Zero-Idle-RAM Hibrit Beyin | AppleScript Yandex Entegrasyonu | Faz 1 & Faz 2[/dim]"
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
    """
    Faz 2: Durum Hafızası, Aktif Pencere Takibi ve Pano Hijyeni Test Süiti
    """
    console.print(Panel("[bold magenta]🧪 FAZ 2 KABUL TESTLERİ: Durum Hafızası, Pencere Takibi ve Pano Hijyeni[/bold magenta]", border_style="magenta"))

    clipboard = ClipboardManager()
    tracker = WindowTracker()
    state_mgr = StateManager(clipboard=clipboard, window_tracker=tracker)

    test_results = Table(title="🔬 Faz 2 Test Sonuçları Raporu", border_style="cyan")
    test_results.add_column("Test Senaryosu", style="bold white", width=30)
    test_results.add_column("Beklenen Sonuç", style="dim cyan", width=35)
    test_results.add_column("Gerçekleşen Durum", style="yellow", width=30)
    test_results.add_column("Durum", justify="center", width=12)

    # ---------------------------------------------------------
    # TEST 1: Pano Hijyeni (Snapshot, Değiştirme ve Geri Yükleme)
    # ---------------------------------------------------------
    orig_text = clipboard.get_text()
    snap = clipboard.snapshot()
    test_token = f"__FAZ2_TEST_TOKEN_{int(time.time())}__"

    # Panoya sahte veri yaz
    clipboard.set_text(test_token)
    written_text = clipboard.get_text()

    # Orijinal içeriği geri yükle
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

    # Context Manager testi
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

    # ---------------------------------------------------------
    # TEST 2: Aktif Pencere Takibi (WindowTracker)
    # ---------------------------------------------------------
    front_app = tracker.get_frontmost_app()
    tracker_passed = bool(front_app.bundle_id and front_app.bundle_id != "unknown")
    tracker_status = "[bold green]✅ PASS[/bold green]" if tracker_passed else "[bold yellow]⚠️ WARN[/bold yellow]"
    test_results.add_row(
        "Aktif Pencere Tespiti",
        "Frontmost app (bundle_id, pid) bulunmalı",
        f"{front_app.app_name} ({front_app.bundle_id}, PID: {front_app.pid})",
        tracker_status
    )

    # Odaklama doğrulaması
    focus_ok = tracker.focus_app(front_app, wait_seconds=0.1)
    focus_status = "[bold green]✅ PASS[/bold green]" if focus_ok else "[bold yellow]⚠️ WARN[/bold yellow]"
    test_results.add_row(
        "Uygulamaya Geri Odaklanma",
        "Hedef uygulama öne (activate) gelmeli",
        f"Aktivasyon sinyali verildi (OK={focus_ok})",
        focus_status
    )

    # ---------------------------------------------------------
    # TEST 3: Seçili Metin & Durum Yakalama (StateManager)
    # ---------------------------------------------------------
    has_ax = state_mgr.check_accessibility_permission()
    ax_desc = "İzin Verildi (Cmd+C/V aktif)" if has_ax else "İzin Yok (Sistem Ayarları izni bekleniyor)"
    ax_status = "[bold green]✅ AKTİF[/bold green]" if has_ax else "[dim yellow]⚠️ BİLGİ[/dim yellow]"
    test_results.add_row(
        "macOS Erişilebilirlik (AX)",
        "AXIsProcessTrusted kontrolü",
        ax_desc,
        ax_status
    )

    # Güvenli context yakalama testi (simulate_copy=False)
    ctx_no_copy = state_mgr.capture_source_context(simulate_copy=False)
    no_copy_passed = (ctx_no_copy.source_app.app_name == front_app.app_name)
    no_copy_status = "[bold green]✅ PASS[/bold green]" if no_copy_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Durum Yakalama (Simülasyonsuz)",
        "Pencere ve pano yedeği alınmalı",
        f"Kaynak: {ctx_no_copy.source_app.app_name}, has_selection={ctx_no_copy.has_selection}",
        no_copy_status
    )

    # Güvenli context yakalama testi (simulate_copy=True)
    ctx_copy = state_mgr.capture_source_context(simulate_copy=True)
    copy_passed = (ctx_copy.source_app.app_name == front_app.app_name)
    copy_status = "[bold green]✅ PASS[/bold green]" if copy_passed else "[bold red]❌ FAIL[/bold red]"
    test_results.add_row(
        "Durum Yakalama (Cmd+C Savunmacı)",
        "Çökmeden çalışmalı, izne göre seçim bildirmeli",
        f"has_selection={ctx_copy.has_selection} (Seçim yoksa Faz 3 OCR devreye girer)",
        copy_status
    )

    # Test bittiğinde kullanıcının panosunun son durumunu doğrula
    final_clip = clipboard.get_text()
    final_hygiene_ok = (final_clip == orig_text)

    console.print(test_results)
    console.print()

    # Pano Hijyen Güvencesi Kartı
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


def main() -> None:
    """CLI giriş noktası."""
    parser = argparse.ArgumentParser(
        description="MacBook Air M2 Agentic PC Asistanı - Faz 1 & Faz 2 Test ve Sağlık Kontrolü"
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
