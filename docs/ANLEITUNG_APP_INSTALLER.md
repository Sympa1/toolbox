# Anleitung für app_installer.py

[`app_installer.py`](../setup/app_installer.py) ist ein modulares Python-Werkzeug zur Überprüfung und Batch-Installation von Softwarepaketen auf Linux-Systemen. Es verarbeitet benutzerdefinierte Listen (`*.applist`) und unterstützt native Systempaketmanager sowie Flatpaks.

---

## Inhaltsverzeichnis
1. [Funktionsweise](#1-funktionsweise)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Schnellstart & Befehle](#3-schnellstart--befehle)
4. [Eigene App-Listen erstellen (*.applist)](#4-eigene-app-listen-erstellen-applist)
5. [Konfiguration (`~/.applists/apps.config`)](#5-konfiguration-applistsappsconfig)
6. [Terminal-Alias einrichten (Optional)](#6-terminal-alias-einrichten-optional)

---

<a id="1-funktionsweise"></a>
## 1. Funktionsweise

* **Intelligente Prüfung**: Vor jeder Installation wird geprüft, ob ein Paket bereits vorhanden ist. Bereits installierte Programme werden übersprungen.
* **Multi-Paketmanager-Unterstützung**:
  * **System (Arch Linux / Manjaro)**: `pacman` und AUR-Helper (`yay` oder `paru`)
  * **System (Debian / Ubuntu)**: `apt` und `dpkg-query`
  * **System (Fedora / RedHat)**: `dnf` und `rpm`
  * **Flatpak**: Isolierte Anwendungen über `flatpak` (Flathub)
* **Gemischte Listen**: In einer einzigen `*.applist`-Datei können sowohl Systempakete als auch Flatpaks definiert werden.

---

<a id="2-voraussetzungen"></a>
## 2. Voraussetzungen

* **Python 3** (Standardbibliothek, keine zusätzlichen pip-Pakete nötig)
* Ein unterstützter Paketmanager auf dem System (`pacman`, `apt`, `dnf` und/oder `flatpak`)
* Ausführungsrechte für das Skript:
  ```bash
  chmod +x setup/app_installer.py
  ```

---

<a id="3-schnellstart--befehle"></a>
## 3. Schnellstart & Befehle

### 3.1. Übersicht & vorhandene Listen anzeigen
Wird das Skript ohne Argumente aufgerufen, zeigt es die Kurzhilfe und alle verfügbaren `.applist`-Dateien an:
```bash
python3 setup/app_installer.py
```

### 3.2. Status prüfen (`check`)
Prüft, welche Pakete aus der Liste bereits installiert sind und welche noch fehlen:
```bash
# Einzelne Liste prüfen
python3 setup/app_installer.py check workstation.applist

# Alle vorhandenen Listen prüfen
python3 setup/app_installer.py check all

# Mit Wildcards / Mustern prüfen
python3 setup/app_installer.py check "workstation*"
```

### 3.3. Pakete installieren (`install`)
Installiert alle in der Liste definierten Programme, die noch nicht auf dem System vorhanden sind:
```bash
# Fehlende Pakete einer Liste installieren
python3 setup/app_installer.py install workstation.applist

# Alle Listen abarbeiten
python3 setup/app_installer.py install all
```

---

<a id="4-eigene-app-listen-erstellen-applist"></a>
## 4. Eigene App-Listen erstellen (*.applist)

App-Listen sind einfache Textdateien. Sie werden im Ordner [`setup/applists/`](../setup/applists/) (oder dem in `~/.applists/apps.config` konfigurierten Verzeichnis) abgelegt.

### 4.1. Format & Aufbau
* **Header / Typzeile**: Definiert den Paketmanager für alle nachfolgenden Zeilen:
  * `type=pacman`: Erzwingt `sudo pacman` (nur offizielle Arch-Repositories).
  * `type=yay` oder `type=paru`: Erzwingt den AUR-Helper `yay` bzw. `paru` (für offizielle Pakete und AUR).
  * `type=arch` oder `type=system`: Automatische Erkennung (nimmt `yay`/`paru`, falls installiert, sonst `sudo pacman`).
  * `type=flatpak`: Installiert Flatpaks von Flathub.
* **Inline-Präfix pro Zeile (Alternative)**: Du kannst den Manager auch direkt vor den Paketnamen schreiben, z. B. `pacman:firefox` oder `yay:brave-bin`.
* **Paketzeile**: `paketname;Optionale Beschreibung`
* **Kommentare**: Zeilen, die mit `#` beginnen, sowie Leerzeilen werden ignoriert.

### 4.2. Beispiel: `meine_apps.applist`

```text
# ==============================================================================
# Meine persönliche App-Liste mit pacman, yay und flatpak
# ==============================================================================

# 1. Offizielle Pakete gezielt über pacman installieren
type=pacman
firefox;Webbrowser
cmake;Build-System
gimp;Bildbearbeitung
filezilla;FTP-Client

# 2. AUR-Pakete gezielt über yay installieren
type=yay
brave-bin;Brave Browser aus dem Arch User Repository

# 3. Flatpaks von Flathub
type=flatpak
org.mozilla.Thunderbird;Thunderbird E-Mail
org.localsend.localsend_app;LocalSend Datentransfer
```

---

<a id="5-konfiguration-applistsappsconfig"></a>
## 5. Konfiguration (`~/.applists/apps.config`)

In der Datei `~/.applists/apps.config` können globale Einstellungen hinterlegt werden:

```ini
# Speicherort fuer alle *.applist-Dateien
applist_dir=~/Dev/toolbox/setup/applists

# Optional: Standard-Paketmanager fuer Arch Linux (pacman, yay oder paru)
# Wenn nicht gesetzt, wird automatisch yay -> paru -> pacman gewaehlt.
arch_manager=pacman
```

---

<a id="6-terminal-alias-einrichten-optional"></a>
## 6. Terminal-Alias einrichten (Optional)

Um das Installationsskript von überall aus bequem mit dem Befehl `apps` starten zu können:

### Für Fish Shell (`~/.config/fish/config.fish`):
```fish
alias apps="python3 ~/Dev/toolbox/setup/app_installer.py"
```

### Für Bash / Zsh (`~/.bashrc` bzw. `~/.zshrc`):
```bash
alias apps="python3 ~/Dev/toolbox/setup/app_installer.py"
```

Nach dem Neuladen des Terminals (`source ~/.bashrc` bzw. neues Fenster) genügt:
```bash
apps check workstation.applist
apps install workstation.applist
```
