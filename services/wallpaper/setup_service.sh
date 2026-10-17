#!/usr/bin/env bash
# ==============================================================================
# Skript zur Verwaltung des systemd Wallpaper-Dienstes
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="kde-wallpaper-changer.service"
PLACEHOLDER_DIR="/pfad/zum/repository/services/wallpaper"

usage() {
    echo "Verwendung: $0 [install|uninstall|status|test]"
    echo ""
    echo "Befehle:"
    echo "  install    - Passt die Pfade dynamisch an, kopiert die Service-Datei nach ${SYSTEMD_USER_DIR}/ und aktiviert den Dienst"
    echo "  uninstall  - Stoppt, deaktiviert und entfernt ${SERVICE_NAME}"
    echo "  status     - Zeigt den aktuellen systemd-Status des Dienstes an"
    echo "  test       - Zeigt Status und Sonnenzeiten ohne Dienststart an"
    exit 1
}

cmd_install() {
    echo "==> Erstelle Zielverzeichnis: ${SYSTEMD_USER_DIR}"
    mkdir -p "${SYSTEMD_USER_DIR}"

    echo "==> Ersetze Platzhalter dynamisch durch das aktuelle Verzeichnis (${SCRIPT_DIR})..."
    sed "s|${PLACEHOLDER_DIR}|${SCRIPT_DIR}|g" \
        "${SCRIPT_DIR}/${SERVICE_NAME}" > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

    echo "==> Aktualisiere systemd-Benutzerkonfiguration..."
    systemctl --user daemon-reload

    echo "==> Aktiviere und starte ${SERVICE_NAME}..."
    systemctl --user enable --now "${SERVICE_NAME}"

    echo "==> Dienst erfolgreich eingerichtet und gestartet!"
    systemctl --user status "${SERVICE_NAME}" --no-pager || true
}

cmd_uninstall() {
    echo "==> Stoppe und deaktiviere ${SERVICE_NAME}..."
    systemctl --user disable --now "${SERVICE_NAME}" 2>/dev/null || true

    echo "==> Entferne Datei aus ${SYSTEMD_USER_DIR}..."
    rm -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

    echo "==> Aktualisiere systemd-Benutzerkonfiguration..."
    systemctl --user daemon-reload

    echo "==> Dienst wurde vollständig entfernt."
}

cmd_status() {
    echo "=== Service Status ==="
    systemctl --user status "${SERVICE_NAME}" --no-pager || true
}

cmd_test() {
    /usr/bin/env python3 "${SCRIPT_DIR}/wallpaper_changer.py" --status
}

# Auswahlmenü, wenn das Skript ohne Argumente gestartet wird
prompt_action() {
    if [ -t 0 ]; then
        # Interaktives Terminal
        echo "============================================================"
        echo "  KDE Wallpaper Changer - Verwaltung"
        echo "============================================================"
        echo "1) Dienst installieren & sofort starten (Standard)"
        echo "2) Status des Dienstes anzeigen"
        echo "3) Sonnenstand & Konfiguration testen"
        echo "4) Dienst stoppen & deinstallieren"
        echo "5) Beenden"
        echo "------------------------------------------------------------"
        read -r -p "Wähle eine Option [1-5] (Standard: 1): " choice
        choice="${choice:-1}"
        case "$choice" in
            1) cmd_install ;;
            2) cmd_status ;;
            3) cmd_test ;;
            4) cmd_uninstall ;;
            5) echo "Abgebrochen."; exit 0 ;;
            *) echo "Ungültige Auswahl."; exit 1 ;;
        esac
    elif [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        if command -v kdialog >/dev/null 2>&1; then
            choice=$(kdialog --title "KDE Wallpaper Changer" \
                --menu "Bitte wähle eine Aktion aus:" \
                "install" "1) Dienst installieren und starten" \
                "status" "2) Status des Dienstes anzeigen" \
                "test" "3) Sonnenstand & Konfiguration testen" \
                "uninstall" "4) Dienst deinstallieren" \
                2>/dev/null) || exit 0

            case "$choice" in
                install)
                    output=$(cmd_install 2>&1)
                    kdialog --title "KDE Wallpaper Changer" --msgbox "Installation erfolgreich abgeschlossen!

$output"
                    ;;
                status)
                    output=$(cmd_status 2>&1)
                    kdialog --title "KDE Wallpaper Changer Status" --msgbox "$output"
                    ;;
                test)
                    output=$(cmd_test 2>&1)
                    kdialog --title "KDE Wallpaper Changer Testlauf" --msgbox "$output"
                    ;;
                uninstall)
                    output=$(cmd_uninstall 2>&1)
                    kdialog --title "KDE Wallpaper Changer" --msgbox "Dienst deinstalliert!

$output"
                    ;;
            esac
        else
            usage
        fi
    else
        usage
    fi
}

case "${1:-}" in
    install)
        cmd_install
        ;;
    uninstall)
        cmd_uninstall
        ;;
    status)
        cmd_status
        ;;
    test)
        cmd_test
        ;;
    "")
        prompt_action
        ;;
    *)
        usage
        ;;
esac
