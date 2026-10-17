# toolbox Projekt-Harness & Richtlinien

Diese Anweisungen gelten spezifisch für das Repository und die Entwicklung von **`toolbox`** (`linux-toolbox`).

## Architektur & Lizenz
- **Architektur:** Rein lokale CLI-Tools, Hintergrunddienste (systemd User/System Services, Daemons) und Setup-/Provisioning-Skripte. **Kein MCP-Server**, kein externes Backend, keine unnötige Cloud-Anbindung.
- **Lizenz:** Das gesamte Projekt steht unter der **MIT-Lizenz** (maximal permissiv).

## Bibliotheken & Abhängigkeiten (Zero-Dependency-Philosophie)
- **Standardbibliothek:** Alle mitgelieferten Python-Standardmodule (z. B. `json`, `os`, `sys`, `pathlib`, `subprocess`, `shutil`, `urllib`, `configparser`, `dataclasses`, `datetime`, `argparse`, `logging`, `math`, `signal`, `socket`, `typing` etc.) dürfen jederzeit frei und ohne Rückfrage eingesetzt werden.
- **Verbot externer Bibliotheken:** Drittanbieter-Pakete (`pip`) sind standardmäßig untersagt. Externe Abhängigkeiten sind nach Möglichkeit immer zu vermeiden (Standardbibliothek bevorzugen), um eine sofortige Ausführbarkeit auf frischen Linux-Systemen ohne virtuelle Umgebungen (`.venv`) zu gewährleisten.
- **Genehmigungspflicht:** Sollte ein zusätzliches externes Paket oder eine externe Bibliothek zwingend erforderlich sein, muss vor der Verwendung zwingend nachgefragt und eine nachvollziehbare Begründung sowie Alternativen geliefert werden.
- **System-Tools & CLI-Befehle:** Die Verwendung nativer Linux-Tools (`systemctl`, `journalctl`, `crontab`, `pacman`, `yay`/`paru`, `apt`, `dnf`, `flatpak`, `ssh`, `ssh-copy-id`, `chmod` etc.) ist im Rahmen der Programmlogik zulässig, muss jedoch fehlerresistent gekapselt sein (Prüfung auf Vorhandensein via `shutil.which` vor Ausführung).
- **Konfigurationsformat:** Für Konfigurationen werden ausschließlich `ini` (`configparser`), `json` (`json`) sowie das zeilenbasierte Format `*.applist` (Standardbibliothek) verwendet.

## Code-Kommentare
- Alle Code-Kommentare ausschließlich in deutscher Sprache verfassen.
- Code-Kommentare ausgewogen halten: Kurz und präzise, aber mit ausreichendem Kontext (nicht zu langatmig erklären und keine Programmier-Grundlagen dokumentieren, sondern den fachlichen Sinn erklären).

## Clean Code & OOP-Prinzipien
- Klare, aussagekräftige Bezeichner verwenden.
- Selbstdokumentierender Code durch sprechende Namen.
- Objektorientierte Prinzipien konsequent anwenden (SOLID-Prinzipien beachten, Kapselung sinnvoll einsetzen, Dataclasses für strukturierte Daten).
- Simplen und modularen Code schreiben (Single Responsibility: kurze, fokussierte Methoden und überschaubare Klassen).
- Idempotenz beachten: Alle Setup-, Installations- und Konfigurationsskripte müssen idempotent sein (beliebig oft ausführbar, ohne bestehende Konfigurationen zu zerstören oder Doppelungen anzulegen).

## Namensgebung & Variablen-Konventionen
- Bezeichner, Variablen-, Klassen- und Methodennamen grundsätzlich auf Englisch.
- **Buffer- und Zählvariablen (Typ-Präfix):**
  - Temporäre Puffer, Zwischenspeicher und Zähler müssen mit dem Datentyp-Präfix gekennzeichnet werden:
    - String-Puffer: `sBuffy` (oder `sBuffer...`)
    - Integer-Puffer / Zähler: `iBuffy` (oder `iBuffer...`)
  - Diese Konvention (`iBuffy` / `sBuffy`) ist verbindlich für Zwischenspeicherungen und Zählschleifen zu verwenden.
- Jede Klasse und jede Methode mit einer kurzen Dokumentation (Zweck und Verantwortlichkeit) versehen.

## Best Practices & Ermessensspielraum
- Innerhalb der gesetzten Grenzen und Vorgaben darf nach eigenem fachlichen Ermessen sinnvoll nach aktuellen Best Practices gearbeitet werden.
- Immer die Best Practices der jeweiligen Programmiersprache befolgen (idiomatischer Code, Typ-Annotationen via `typing`).
- Framework-, Sprach- und Linux-Konventionen einhalten:
  - XDG Base Directory Spezifikation (`~/.config`, `~/.local/share`).
  - systemd User-Unit Standards (Binding an `default.target` oder `graphical-session.target`).
  - Sichere Dateirechte (`0o600` für sensible Konfigurationen/SSH-Keys, `0o700` für Schlüssel-Verzeichnisse, `0o755` für Skripte).

## Workspace- & Ausführungs-Richtlinie
- Artefakte, Pläne und Notizen dürfen ausschließlich im aktuellen Arbeitsverzeichnis (Workspace-Root) abgelegt werden, nicht in globalen Anwendungsdaten-Verzeichnissen (wie `~/.gemini/`).
- **Freie Befehlsausführung im Projekt:** Innerhalb des Projektverzeichnisses (`toolbox`) dürfen Dateien, Verzeichnisse und Befehle (`ls`, `cat`, `grep`, `pytest`, `python3` etc.) vollkommen frei, eigenständig und ohne Rückfrage aufgerufen und gelesen werden.
- **Rückfragepflicht außerhalb:** Eine vorherige Rückfrage ist zwingend erforderlich, wenn Aktionen außerhalb des Projektverzeichnisses stattfinden sollen (z. B. Live-Ausführung von Setup-/Installationsskripten auf dem Host-System, systemweite Paketinstallationen, Änderungen an globalen OS-/Benutzer-Dateien wie `~/.bashrc`, `~/.config/fish/`, `~/.ssh` oder Starten/Aktivieren von systemd-Diensten).

## Berichts- & Dokumentations-Datenschutz (Public-Repo-Konformität)
- **Strikter Ausschluss von Dateipfaden in Berichten:**
  - In allen generierten Test- und Audit-Berichten (`docs/*_report.md`), Dokumentationen und Plänen dürfen **keine absoluten Dateipfade** (wie `/home/...` oder `C:\Users\...`), privaten Benutzernamen, Servernamen, IP-Adressen, Discord-Webhook-URLs oder interne Quellcode-Dateipfade aufgeführt werden.
  - Verwende in Berichten und Tabellen ausschließlich sprechende Modul- und Komponentennamen (z. B. `AppInstaller`, `WallpaperChanger`, `BackupServer`, `ShellConfigurator`) oder relative/anonymisierte Verweise ohne sensible Pfadinformationen.

## Arbeitsweise, Test-Zwang & Projekt-Journal (`docs/JOURNAL.md`)
- **Autonome Arbeitsweise & durchgängige Ausführung:**
  - Logisch aufeinanderfolgende Schritte (Planen -> Implementieren -> Tests ausführen -> Fehler beheben -> Dokumentieren -> Commit/Push vorbereiten) sind **selbstständig, proaktiv und am Stück** durchzuführen.
  - Es muss nicht nach jedem einzelnen Zwischenschritt auf Bestätigung gewartet werden.
  - Bei klaren Anforderungen durcharbeiten und das Gesamtergebnis präsentieren. Nur bei echten Zielkonflikten oder unklaren Anforderungen rückfragen.
- **Test-Ausführung nach jedem Schritt (Pflicht):**
  - Nach jedem implementierten Schritt oder jeder Code-Änderung ist zwingend eine passende Prüfung (z. B. `python3 -m py_compile`, `unittest`/`pytest`, Dry-Run) eigenständig auszuführen.
  - Kein Schritt gilt als abgeschlossen, bevor nicht alle Tests grün durchgelaufen sind.
- **Lückenlose Dokumentation in `docs/JOURNAL.md` (Pflicht):**
  - Jeder durchgeführte Schritt, jede Architekturentscheidung und jede Änderung ist verbindlich und chronologisch oben in `docs/JOURNAL.md` zu vermerken.
- **Session-Start & Referenzierung (Pflicht):**
  - Lies zu Beginn jeder neuen Sitzung oder vor der Bearbeitung neuer Aufgaben zuerst `docs/JOURNAL.md` ein.
  - Nutze die dort dokumentierten Entscheidungen und offenen Punkte als primäre Referenz für den aktuellen Projektstand.

---

## Architektur & Modul-Übersicht

```text
╭────────────────────────────────────────────────────────────────────────╮
│                                toolbox                                 │
├───────────────────┬──────────────────────┬─────────────────────────────┤
│      setup/       │         cli/         │          services/          │
│ (Systemeinrichtung)│ (Interaktive Tools)  │ (Hintergrund & Cron)        │
├───────────────────┼──────────────────────┼─────────────────────────────┤
│ • app_installer   │ • appimage_mover     │ • backup/ (Backup & Restore)│
│ • setup           │                      │ • wallpaper/ (KDE Daemon)   │
│ • shell_config    │                      │   - Sonnenstand (NOAA)      │
│ • applists/       │                      │   - systemd User Service    │
╰───────────────────┴──────────────────────┴─────────────────────────────╯
        │                      │                         │
        ▼                      ▼                         ▼
  ┌─────────────────────────────────────────────────────────────┐
  │         Zero-Dependencies (Python Standardbibliothek)        │
  │     Konfiguration via INI / JSON / deklarative .applist     │
  └─────────────────────────────────────────────────────────────┘
```
