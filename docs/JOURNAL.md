# Projekt-Journal: toolbox

Dieses Dokument dient als kontinuierliches Gedächtnis des Projekts. 
Hier werden fundamentale Architekturentscheidungen, erreichte Meilensteine und offene Punkte chronologisch (neueste Einträge oben) dokumentiert.

### 2026-10-17 - Anpassung von AGENTS.md nach Vorbild von whisper_pill (ohne Projektziel)
- **Entscheidung / Änderung:**
  - `AGENTS.md`: Struktur und Formulierungen eng an die Vorlage aus `whisper_pill` angeglichen und auf das Repository `toolbox` angepasst.
  - Sektion `Projektziel` sowie doppelte Projektstruktur-Auflistungen entfernt (auf reine `Architektur & Lizenz` sowie die komprimierte `Architektur & Modul-Übersicht` am Ende reduziert).

### 2026-10-17 - Bereinigung privater Pfade, Benutzernamen & Server-Referenzen (Public-Repo-Konformität)
- **Entscheidung / Änderung:**
  1. **Konfigurations- und INI-Dateien:**
     - `setup/shell_config.json`: Hartcodierte absolute Benutzerpfade und alten Repository-Namen bei den Aliasen `putzputz` und `apps` durch `~/Dev/linux-toolbox/...` ersetzt.
     - `services/backup/backup_config.ini`: Privaten Benutzerpfad im auskommentierten Nextcloud-Beispiel durch neutralen Platzhalter `/pfad/zu/nextcloud/data` ersetzt.
     - `services/backup/notifier.ini`: Webhook-Platzhalter auf `DEIN_WEBHOOK_TOKEN` vereinheitlicht (passend zur Prüfung in `discord_notifier.py`).
  2. **Skript-Header, Assets, Lizenz & Dokumentation:**
     - `LICENSE`: Offizielle MIT-Lizenzdatei im Hauptverzeichnis erstellt (ohne persönliche Klardaten, für automatische GitHub-Lizenzerkennung).
     - `services/backup/backup-server.py` & `services/backup/restore-server.py`: Private Benutzernamen aus den Dateiköpfen entfernt und den Cronjob-Beispielpfad neutralisiert (`/pfad/zu/linux-toolbox/...` bzw. `~/Bkup/...`).
     - `services/backup/backup-hook.png`: Webhook-Avatar-Grafik von Server-spezifischem Dateinamen auf neutralen Namen `backup-hook.png` umbenannt.
     - `README.md` & `docs/ANLEITUNG_APP_INSTALLER.md`: Verbliebene Referenzen auf private Home-Pfade, alten Repository-Namen und Servernamen vollständig durch `~/Dev/linux-toolbox/...` bzw. neutrale Platzhalter ersetzt.
  3. **Validierung:**
     - Syntaxprüfung aller Python-Module (`py_compile`), Parser-Validierung aller `.json`- und `.ini`-Dateien sowie Repository-weiter Grep-Check erfolgreich durchgeführt.

### 2026-10-13 - Etablierung des Projekt-Harness (AGENTS.md) & Modul-Konsolidierung
- **Entscheidung / Änderung:**
  1. **Projekt-Harness (`AGENTS.md` / `.agents/AGENTS.md`):**
     - Vollständige Richtlinie nach Vorbild von `whisper-pill` etabliert.
     - Definition der **Zero-Dependency-Philosophie** (ausschließlich Python-Standardbibliothek für maximale Portabilität).
     - Verbindliche Naming-Conventions (`sBuffy`, `iBuffy` für Puffer/Zähler), deutsche Code-Kommentare und englische Bezeichner.
     - Strikte Schutzregeln für System-Eingriffe (Rückfragepflicht bei Ausführung auf dem Host-System oder Ändern von OS-Configs).
     - Dokumentations- und Datenschutzvorgaben (keine privaten Pfade, Discord-Webhooks oder Passwörter in Logs/Dokumenten).
  2. **Projekt-Gedächtnis (`docs/JOURNAL.md`):**
     - Initialisierung des chronologischen Projekt-Journals zur kontinuierlichen Nachverfolgung.
- **Aktueller Modulstatus:**
  - `setup/`: Voll funktionsfähig (`app_installer.py`, `setup.py`, `shell_configurator.py`, `workstation.applist`).
  - `cli/`: `appimage_mover.py` einsatzbereit.
  - `services/backup/`: Backup- & Restore-Skripte mit Discord-Benachrichtigung vorhanden.
  - `services/wallpaper/`: Daemon für KDE Plasma 6 mit Sonnenstandsberechnung (NOAA) und systemd-User-Service betriebsbereit.
- **Offene Punkte / Nächste Schritte:**
  - Test-Suite (`tests/`) aufbauen zur automatisierten Validierung der Kernmodule via Standard-`unittest`.
