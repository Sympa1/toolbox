# KDE Plasma Wallpaper Changer (Daemon & systemd-Benutzerdienst)

Ein leichtgewichtiger, autonomer Hintergrunddienst für **KDE Plasma 6**, der das Desktop-Hintergrundbild automatisch anhand des aktuellen Sonnenstands anpasst.

### Was ist der Wallpaper Changer: Daemon oder Dienst/Service?
Der Wallpaper Changer kombiniert beides:
* **Auf Prozessebene ein Daemon:** Das Python-Skript [`wallpaper_changer.py`](wallpaper_changer.py) läuft im Dauerbetrieb als Hintergrund-Daemon mit einer 5-Minuten-Prüfschleife und fängt Prozess-Signale (`SIGTERM`, `SIGINT`) sauber ab.
* **Auf Systemebene ein systemd-Benutzerdienst (User Service):** Verwaltet über [`kde-wallpaper-changer.service`](kde-wallpaper-changer.service) und `systemd --user`. Dadurch startet der Prozess automatisch beim Login in KDE (`graphical-session.target`), wird bei Abstürzen neu gestartet (`Restart=on-failure`) und schreibt seine Logs ins Journal (`journalctl --user`).
* **Zusätzlicher CLI-Modus:** Das Skript kann auch unabhängig vom Daemon/Dienst als einmaliges Terminal-Werkzeug ausgeführt werden (z. B. `--once`, `--status` oder `--dry-run`).

---

## Übersicht der Dateien

| Datei | Beschreibung |
| :--- | :--- |
| [`wallpaper_changer.py`](wallpaper_changer.py) | Python-Daemon & CLI-Tool (Sonnenstandsberechnung, IP-Ortung, 5-Minuten-Schleife) |
| [`wallpaper_config.ini`](wallpaper_config.ini) | Konfigurationsdatei für Bildpfade, Zeitfenster (Offsets) und Intervalle |
| [`kde-wallpaper-changer.service`](kde-wallpaper-changer.service) | systemd-Benutzerdienst-Vorlage (`systemd --user`) |
| [`setup_service.sh`](setup_service.sh) | Installations- und Verwaltungsskript (Einrichten, Status, Deinstallation) |

---

## Voraussetzungen

* **Betriebssystem:** Linux mit `systemd`
* **Desktop-Umgebung:** KDE Plasma 6 (Werkzeug `plasma-apply-wallpaperimage` standardmäßig vorhanden)
* **Python:** Python 3.9+ (verwendet **ausschließlich die Python-Standardbibliothek**, keine externen `pip`-Pakete notwendig)
* **Internetverbindung:** Zur einmaligen Standortbestimmung via IP (gepuffert für 24 Stunden; Offline-Fallback vorhanden)

---

## Funktionsweise & Architektur

1. **Daemon-Betrieb & Service-Integration:**
   * Sobald du dich in KDE anmeldest, startet `systemd --user` den Dienst über `graphical-session.target`.
   * **Sofortige Aktualisierung:** Beim Start prüft und setzt der Daemon das Wallpaper **direkt**, noch bevor die reguläre Wartezeit beginnt.
   * Danach schläft die Hintergrundschleife im 5-Minuten-Takt (`check_interval_seconds = 300`) unterbrechbar und wacht für den nächsten Abgleich auf.
   * Reagiert sauber und verzögerungsfrei auf `SIGTERM`/`SIGINT` bei Abmeldung, Neustart oder Dienststopp.

2. **Astronomische Berechnung (Zero Dependencies):**
   * Berechnet Sonnenaufgang und Sonnenuntergang exakt nach dem Standard-Algorithmus der **NOAA**.
   * Reine Trigonometrie über `math` und `datetime` – vollkommen unabhängig von externen Bibliotheken.

3. **Standortbestimmung & Caching:**
   * Ermittelt Breiten- und Längengrad automatisch über die externe IP.
   * Speichert die Koordinaten in `~/.cache/wallpaper-changer/location_cache.json` (Standard-Gültigkeit: 24 Stunden).
   * Bei Internetausfall greift der Dienst auf den Cache oder konfigurierte Notfallkoordinaten zurück.

4. **Tagesabschnitte:**
   * **Morgens (`morning`)**: Standardmäßig 30 Minuten vor Sonnenaufgang bis 1 Stunde danach.
   * **Tagsüber (`day`)**: Zwischen Morgens und Abends.
   * **Abends (`evening`)**: Standardmäßig 1 Stunde vor Sonnenuntergang bis 30 Minuten danach.
   * **Nachts (`night`)**: Zwischen Abends und Morgens.

5. **Schonung der Desktop-Oberfläche & Live-Zustandsabgleich:**
   * Vor dem Aufruf von `plasma-apply-wallpaperimage` prüft das Skript über `~/.config/plasma-org.kde.plasma.desktop-appletsrc`, ob das Zielbild auf allen Bildschirmen bereits aktiv ist.
   * Bleibt der Tagesabschnitt gleich und das Bild ist unverändert aktiv, findet kein erneuter Aufruf statt (verhindert Bildschirmflackern).
   * Wird das Hintergrundbild vom Benutzer manuell in KDE geändert, erkennt der Dienst beim nächsten periodischen Check die Abweichung und stellt das zeitlich korrekte Wallpaper automatisch wieder her.
   * Kann die Plasma-Konfigurationsdatei nicht gelesen werden, dient eine interne Cache-Datei (`~/.cache/wallpaper-changer/last_wallpaper.txt`) als robuster Fallback.

---

## Schritt-für-Schritt-Anleitung

### Schritt 1: Eigene Bilder in `wallpaper_config.ini` eintragen
Öffne [`wallpaper_config.ini`](wallpaper_config.ini) und ersetze die Beispielpfade durch deine echten Bilddateien:

```ini
[wallpapers]
morning = /pfad/zu/deinem/wallpaper_morning.jpg
day     = /pfad/zu/deinem/wallpaper_day.jpg
evening = /pfad/zu/deinem/wallpaper_evening.jpg
night   = /pfad/zu/deinem/wallpaper_night.jpg
```
*(Die Tilde `~` für dein Home-Verzeichnis wird unterstützt, z. B. `~/Bilder/morgen.jpg`)*

Optional können in der Datei auch die Offsets (Vorlauf-/Nachlaufzeiten) angepasst werden:
```ini
[offsets]
morning_before_sunrise_minutes = 30   # Startet X Minuten vor Sonnenaufgang
morning_after_sunrise_minutes = 60    # Endet X Minuten nach Sonnenaufgang (Beginn Tag)
evening_before_sunset_minutes = 60    # Startet X Minuten vor Sonnenuntergang (Ende Tag)
evening_after_sunset_minutes = 30     # Endet X Minuten nach Sonnenuntergang (Beginn Nacht)
```

---

### Schritt 2: Funktion im Terminal testen (ohne Installation)
Stelle sicher, dass die Skripte ausführbar sind (`chmod +x *.sh *.py`) und teste die Logik:

```bash
# 1. Statusbericht anzeigen (Standort, heutige Sonnenzeiten, Zeitfenster, aktiver Abschnitt):
python3 wallpaper_changer.py --status

# 2. Trockenlauf (simuliert den Ablauf, ohne das Wallpaper tatsächlich zu verändern):
python3 wallpaper_changer.py --once --dry-run

# 3. Einmaliger echter Durchlauf (setzt das Bild sofort einmalig):
python3 wallpaper_changer.py --once

# 4. Gezieltes Testen eines bestimmten Bildes:
python3 wallpaper_changer.py --test-period morning
python3 wallpaper_changer.py --test-period day
python3 wallpaper_changer.py --test-period evening
python3 wallpaper_changer.py --test-period night
```

---

### Schritt 3: Dienst aktivieren

#### Option A: Automatische Einrichtung über das Skript (Empfohlen)
```bash
./setup_service.sh install
```
*Das Skript ermittelt den aktuellen Pfad dynamisch, richtet die Service-Datei unter `~/.config/systemd/user/` ein und startet den Dienst sofort.*

#### Option B: Manuelle Einrichtung
Falls du die Schritte selbst ausführen möchtest:
```bash
# 1. Benutzerverzeichnis für systemd anlegen
mkdir -p ~/.config/systemd/user

# 2. Service-Datei kopieren und Pfade anpassen
sed "s|/pfad/zum/repository/services/wallpaper|$(pwd)|g" \
    kde-wallpaper-changer.service > ~/.config/systemd/user/kde-wallpaper-changer.service

# 3. systemd Konfiguration neu einlesen
systemctl --user daemon-reload

# 4. Dienst aktivieren und sofort starten
systemctl --user enable --now kde-wallpaper-changer.service
```

---

### Schritt 4: Dienst verwalten & überwachen (`systemctl` & `journalctl`)

Die Steuerung kann wahlweise direkt mit den systemeigenen `systemctl --user`-Befehlen oder über das Hilfsskript [`setup_service.sh`](setup_service.sh) erfolgen.

#### Direkte `systemctl`-Befehle

```bash
# Status und die letzten Meldungen prüfen:
systemctl --user status kde-wallpaper-changer.service

# Dienst neu starten (z. B. nach Code-Updates oder Anpassung der wallpaper_config.ini):
systemctl --user restart kde-wallpaper-changer.service

# Dienst manuell starten:
systemctl --user start kde-wallpaper-changer.service

# Dienst vorübergehend stoppen:
systemctl --user stop kde-wallpaper-changer.service

# Autostart beim KDE-Login aktivieren (sofort starten falls nicht aktiv):
systemctl --user enable --now kde-wallpaper-changer.service

# Autostart beim KDE-Login deaktivieren und sofort stoppen:
systemctl --user disable --now kde-wallpaper-changer.service

# systemd-Konfiguration neu laden (nach manueller Änderung der .service-Datei):
systemctl --user daemon-reload
```

#### Logs auswerten mit `journalctl`

```bash
# Live-Logs im Terminal fortlaufend mitlesen (Follow-Modus):
journalctl --user -u kde-wallpaper-changer.service -f

# Die letzten 50 Zeilen anzeigen:
journalctl --user -u kde-wallpaper-changer.service -n 50 --no-pager

# Alle Logs seit dem letzten Systemstart anzeigen:
journalctl --user -u kde-wallpaper-changer.service -b
```

#### Verwaltung über das Hilfsskript

```bash
# Status über Skript abfragen:
./setup_service.sh status

# Dienst vollständig stoppen und systemd-Datei entfernen:
./setup_service.sh uninstall
```
