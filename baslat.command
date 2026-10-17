#!/bin/bash
# ==============================================================================
# MacBook Air M2 - Masaüstü AI Asistanı Başlatıcı (baslat.command)
# Zero-Idle-RAM | Apple Vision OCR | Yandex Gemini DOM | Option+Space Kısayolu
# ==============================================================================

# Betiğin bulunduğu dizine geç
cd "$(dirname "$0")"

# Terminal başlığını ayarla
echo -ne "\033]0;MacBook Air M2 — Agentic Asistan\007"

# Renkler
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

clear
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}    🚀 MACBOOK AIR M2 — AGENTIC SESLİ VE YAZILI PC ASİSTANI${NC}"
echo -e "${CYAN}    Zero-Idle-RAM | Apple Vision OCR | Yandex Browser Gemini DOM${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""

# Sanal ortam kontrolü
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  Python sanal ortamı (.venv) bulunamadı! Kurulum yapılıyor...${NC}"
    if command -v uv &> /dev/null; then
        uv venv .venv
        uv pip install -r requirements.txt
    else
        python3 -m venv .venv
        .venv/bin/pip install -r requirements.txt
    fi
fi

PYTHON=".venv/bin/python"

# Menü Döngüsü
while true; do
    echo -e "${GREEN}Lütfen yapmak istediğiniz işlemi seçin:${NC}"
    echo "  [1] 🎧 Kısayol Servisini Başlat (Option + Space Dinleyicisi)"
    echo "  [2] ⚡ Hemen Komut Ver (Spotlight Komut Penceresini Aç)"
    echo "  [3] 🔍 Sistem Sağlık ve Donanım Kontrolü (Diagnostics)"
    echo "  [4] 🧪 Uçtan Uca (E2E) Sistem Kabul Testini Çalıştır"
    echo "  [5] 🧹 Yerel LLM Bellek Tahliyesi (RAM Temizliği)"
    echo "  [0] ❌ Çıkış"
    echo ""
    read -p "Seçiminiz [0-5]: " secim

    case $secim in
        1)
            echo ""
            echo -e "${CYAN}🎧 Kısayol servisi başlatılıyor... (Durdurmak için Ctrl+C tuşlayın)${NC}"
            $PYTHON main.py --listen
            echo ""
            ;;
        2)
            echo ""
            echo -e "${CYAN}⚡ Komut penceresi açılıyor...${NC}"
            $PYTHON main.py --once
            echo ""
            ;;
        3)
            echo ""
            $PYTHON main.py --health-check
            echo ""
            ;;
        4)
            echo ""
            $PYTHON main.py --test-e2e
            echo ""
            ;;
        5)
            echo ""
            $PYTHON main.py --unload-ollama
            echo ""
            ;;
        0)
            echo -e "${GREEN}Görüşmek üzere!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Geçersiz seçim! Lütfen 0-5 arasında bir numara girin.${NC}"
            echo ""
            ;;
    esac
done
