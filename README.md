# toolbox

Strukturierte Sammlung modularer Automatisierungs-, Setup- und Hilfswerkzeuge für Linux (Server & Clients).

---

## Inhaltsverzeichnis

- [Projektübersicht](#projektübersicht)
- [Verzeichnisstruktur](#verzeichnisstruktur)
- [System-Setup (`setup/`)](#system-setup-setup)
  - [App Installer (`setup/app_installer.py`)](#app-installer-setupapp_installerpy)
  - [Workstation-Setup (`setup/setup.py`)](#workstation-setup-setupsetuppy)
  - [App-Listen (`setup/applists/`)](#app-listen-setupapplists)
- [CLI-Tools (`cli/`)](#cli-tools-cli)
  - [AppImage Mover (`cli/appimage_mover.py`)](#appimage-mover-cliappimage_moverpy)
- [Dienste & Cronjobs (`services/`)](#dienste--cronjobs-services)
  - [Backup & Restore (`services/backup/`)](#backup--restore-servicesbackup)
  - [KDE Wallpaper Changer (`services/wallpaper/`)](#kde-wallpaper-changer-serviceswallpaper)
- [Dokumentation (`docs/`)](#dokumentation-docs)

---

<a id="projektübersicht"></a>
## Projektübersicht

Dieses Repository bündelt Werkzeuge für die Systemadministration, Desktop-Einrichtung und Server-Wartung in einer sauberen, modularen Architektur:
* **[`setup/`](setup/)**: Provisioning, App-Installer und Paketlisten für die Ersteinrichtung von Rechnern.
* **[`cli/`](cli/)**: Interaktive Werkzeuge für den alltäglichen Aufruf im Terminal.
* **[`services/`](services/)**: Hintergrunddienste, Daemons und unbeaufsichtigte Cronjobs.
* **[`docs/`](docs/)**: Detaillierte Anleitungen und Dokumentationen.

---

<a id="verzeichnisstruktur"></a>
## Verzeichnisstruktur

```text
.
├── README.md                      # Gesamtübersicht des Repositories
├── AGENTS.md                      # Projekt-Harness & Entwicklungsrichtlinien
├── setup/                         # Systemeinrichtung & Provisioning
│   ├── app_installer.py           # Paket-Installer und Statusprüfer
│   ├── setup.py                   # Vollautomatisches Workstation Setup
│   ├── shell_configurator.py      # Idempotenter Shell-Alias-Manager
│   ├── shell_config.json          # Alias- und Shell-Konfigurationsdaten
│   └── applists/                  # Paketlisten (*.applist)
│       └── workstation.applist    # Basis- und Beispiel-Paketliste für Workstations
├── cli/                           # Interaktive Werkzeuge für das Terminal
│   └── appimage_mover.py          # AppImage-Aufräum- und Bereinigungsskript
├── services/                      # Hintergrunddienste & Cronjobs
│   ├── backup/                    # Datensicherungs-Dienst
│   │   ├── backup-server.py       # Vollautomatisches Backup-Skript (Cronjob)
│   │   ├── restore-server.py      # Wiederherstellungs-Skript
│   │   ├── discord_notifier.py    # Discord-Webhook Notifier
│   │   ├── backup_config.ini      # Konfiguration für Backups
│   │   ├── notifier.ini           # Webhook-Konfiguration
│   │   └── backup-hook.png        # Avatar-Icon
│   └── wallpaper/                 # Dynamischer Wallpaper-Wechsler (Daemon & Service)
│       ├── wallpaper_changer.py   # Python-Daemon & CLI-Tool (Sonnenstand)
│       ├── wallpaper_config.ini   # Konfigurationsdatei für Bildpfade
│       ├── kde-wallpaper-changer.service # systemd-Benutzerdienst-Vorlage
│       ├── setup_service.sh       # Installations- & Steuerungsskript
│       └── README.md              # Detaillierte Dokumentation
└── docs/                          # Vertiefende Anleitungen & Projekt-Journal
    ├── ANLEITUNG_APP_INSTALLER.md # Ausführliches Handbuch für app_installer.py
    └── JOURNAL.md                 # Chronologisches Projekt-Journal
```

---

<a id="system-setup-setup"></a>
## System-Setup (`setup/`)

<a id="app-installer-setupapp_installerpy"></a>
### App Installer ([`setup/app_installer.py`](setup/app_installer.py))

Modulares Python-Werkzeug zur Batch-Überprüfung und Installation von Softwarepaketen anhand frei definierbarer `*.applist`-Dateien.

* **Statusprüfung (`check`)**: Prüft, welche Pakete auf dem System bereits installiert sind.
* **Intelligente Installation (`install`)**: Installiert ausschließlich fehlende Programme; vorhandene Pakete werden automatisch übersprungen.
* **Paketmanager-Unterstützung**:
  * **Arch / Manjaro**: Native Unterstützung für `pacman` sowie AUR-Helper (`yay` oder `paru`).
  * **Debian / Ubuntu**: `apt` und `dpkg-query`.
  * **Fedora / RedHat**: `dnf` und `rpm`.
  * **Flatpak**: Isolierte Anwendungen von Flathub.

```bash
# Kurzhilfe und gefundene Listen anzeigen
python3 setup/app_installer.py

# Pakete einer Liste prüfen
python3 setup/app_installer.py check workstation.applist

# Fehlende Pakete installieren
python3 setup/app_installer.py install workstation.applist

# Alle vorhandenen Listen abarbeiten
python3 setup/app_installer.py check all
python3 setup/app_installer.py install all
```

*Ausführliche Anleitung:* [docs/ANLEITUNG_APP_INSTALLER.md](docs/ANLEITUNG_APP_INSTALLER.md)

<a id="workstation-setup-setupsetuppy"></a>
### Workstation-Setup ([`setup/setup.py`](setup/setup.py))
Interaktive Ersteinrichtung eines Arbeitsplatzsystems (z. B. CachyOS / Arch / Manjaro Linux):
1. **Systempakete**: Automatische Installation der Basis-Tools via [`app_installer.py`](setup/app_installer.py) und [`workstation.applist`](setup/applists/workstation.applist).
2. **Git & GitHub SSH**: Konfiguration von Git-Name/-E-Mail, Generierung eines dedizierten Ed25519-Schlüssels (`~/.ssh/github`), automatisches Kopieren in die Zwischenablage und bequeme Verknüpfung via GitHub-Web-Interface oder Token.
3. **Remote-Server SSH & Aliase**: Interaktives Hinzufügen von Remote-Servern mit servereigenem SSH-Schlüssel (`~/.ssh/<servername>`), automatischer Public-Key-Übertragung (`ssh-copy-id`), `~/.ssh/config`-Eintrag und direktem Shell-Alias.
4. **Antigravity CLI**: Automatische Installation / Aktualisierung der Google Antigravity CLI (`agy`).
5. **Shell-Aliase**: Zentrale Pflege von Shell-Aliasen für Fish, Bash und Zsh über [`shell_configurator.py`](setup/shell_configurator.py) und [`shell_config.json`](setup/shell_config.json).

<a id="app-listen-setupapplists"></a>
### App-Listen ([`setup/applists/`](setup/applists/))
Enthält deklarative Paketlisten für Software-Installationen:
* [`workstation.applist`](setup/applists/workstation.applist): Basis- und Beispiel-Paketliste für Desktop & Workstation (kombinierte Installation über `pacman` und `flatpak`).

---

<a id="cli-tools-cli"></a>
## CLI-Tools (`cli/`)

<a id="appimage-mover-cliappimage_moverpy"></a>
### AppImage Mover ([`cli/appimage_mover.py`](cli/appimage_mover.py))

Durchsucht `~/Downloads` nach `.AppImage`-Dateien, entfernt Versionsnummern und unschöne Sonderzeichen aus dem Dateinamen, verschiebt die Dateien nach `~/software` und setzt die Ausführungsrechte (`chmod 0o755`).

---

<a id="dienste--cronjobs-services"></a>
## Dienste & Cronjobs (`services/`)

<a id="backup--restore-servicesbackup"></a>
### Backup & Restore ([`services/backup/`](services/backup/))

Ein vollständiges Sicherungssystem für Debian- und Linux-Server:
* **Konsistente Datensicherung**: Sichert Anwendungsdaten, Portainer-Volumes und MariaDB-Datenbankdumps über [`backup-server.py`](services/backup/backup-server.py) und [`backup_config.ini`](services/backup/backup_config.ini).
* **Cronjob-tauglich**: Für die automatisierte, unbeaufsichtigte Ausführung im Hintergrund konzipiert.
* **Discord-Benachrichtigungen**: Sendet Statusberichte bei Erfolg oder detaillierte Fehlermeldungen bei Problemen via Webhook ([`discord_notifier.py`](services/backup/discord_notifier.py)).
* **Wiederherstellung**: Einfache Rekonstruktion gesicherter Zustände über [`restore-server.py`](services/backup/restore-server.py).

Beispiel für die Crontab (`crontab -e`):
```text
0 3 * * * /usr/bin/python3 /pfad/zu/toolbox/services/backup/backup-server.py >> ~/Bkup/cron_output.log 2>&1
```

<a id="kde-wallpaper-changer-serviceswallpaper"></a>
### KDE Wallpaper Changer ([`services/wallpaper/`](services/wallpaper/))

Tageszeitabhängiger Wallpaper-Wechsler für KDE Plasma 6 basierend auf dem realen Sonnenstand:
* **Auf Prozessebene ein Daemon**: [`wallpaper_changer.py`](services/wallpaper/wallpaper_changer.py) läuft im Dauerbetrieb als Hintergrund-Daemon mit 5-Minuten-Prüfschleife, berechnet Sonnenauf- und -untergang (NOAA-Algorithmus, Zero-Dependencies) und reagiert sauber auf Prozess-Signale.
* **Auf Systemebene ein systemd-Benutzerdienst**: Über [`kde-wallpaper-changer.service`](services/wallpaper/kde-wallpaper-changer.service) an `graphical-session.target` gebunden. Startet automatisch bei KDE-Anmeldung, bietet automatischen Neustart bei Abstürzen und Journal-Logging.
* **CLI- & Testwerkzeug**: Kann über Parameter wie `--status`, `--once` oder `--test-period` auch direkt im Terminal verwendet werden.

*Ausführliche Anleitung:* [services/wallpaper/README.md](services/wallpaper/README.md)

---

<a id="dokumentation-docs"></a>
## Dokumentation (`docs/`)

- [docs/ANLEITUNG_APP_INSTALLER.md](docs/ANLEITUNG_APP_INSTALLER.md): Ausführliches Handbuch mit allen Parametern, Syntaxregeln für `.applist`-Dateien und Konfigurationsoptionen (`~/.applists/apps.config`).
- [docs/JOURNAL.md](docs/JOURNAL.md): Kontinuierliches Projekt-Journal mit Architekturentscheidungen und Änderungsverlauf.

