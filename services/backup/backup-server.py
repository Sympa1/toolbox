#!/usr/bin/env python3
# ==============================================================================
# Backup-Skript für Debian Server (data_sync, MariaDB, Portainer)
# Zweck: Automatisierte, konsistente Sicherung der Anwendungsdaten und Container
#
# Einrichtung als Cronjob (crontab -e):
# 0 3 * * * /usr/bin/python3 /pfad/zu/linux-toolbox/services/backup/backup-server.py >> ~/Bkup/cron_output.log 2>&1
# ==============================================================================

import subprocess
from pathlib import Path
from datetime import datetime
import logging
import configparser
from logging.handlers import RotatingFileHandler

class BackupManager:
    """
    Verwaltet den vollständigen Backup-Prozess für die API-Umgebung.

    Diese Klasse ist dafür verantwortlich, MariaDB-Dumps zu erstellen, API-Dateien zu
    archivieren, das Portainer-Volume konsistent zu sichern, die erzeugten Dateien zu
    validieren und alte Sicherungen sowie Logeinträge automatisch zu bereinigen.
    """

    def __init__(self, backup_root: str, project_root: str):
        """
        Initialisiert den Backup-Manager mit den Ziel- und Projektpfaden und
        richtet das Logging-System ein.

        :param backup_root: Hauptordner für Backups (z.B. '~/Bkup').
        :param project_root: Projekt-Verzeichnis auf dem Host (z.B. '~/Dev/data_sync').
        """
        # .expanduser() wandelt ~ in den absoluten Home-Pfad des Linux-Benutzers um
        self.backup_root = Path(backup_root).expanduser().resolve()
        self.project_root = Path(project_root).expanduser().resolve()
        
        # Verzeichnis erstellen, damit Log-Dateien direkt angelegt werden können
        self.backup_root.mkdir(parents=True, exist_ok=True)
        
        # Eindeutiger Zeitstempel für diesen Lauf (verhindert Überschreibungen bei Parallelstarts)
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Pfad zur permanenten Log-Zusammenfassung im Backup-Verzeichnis
        self.log_file = self.backup_root / "backup_summary.log"
        
        # Logging initialisieren (Konsole + rotierende backup.log)
        self.setup_logging()

        # Pfad zur INI-Konfigurationsdatei für Server- und Docker-Backups
        self.config_file = Path(__file__).parent / "backup_config.ini"
        self.mariadb_enabled = True
        self.uploads_enabled = True
        self.containers_to_backup = self.load_backup_config()

    def setup_logging(self) -> None:
        """
        Richtet das Logging-System ein.
        Leitet alle Ausgaben sowohl auf die Konsole als auch in 'backup.log' um.
        """
        detailed_log_file = self.backup_root / "backup.log"
        
        # Logger für diese Klasse definieren
        self.logger = logging.getLogger("BackupManager")
        self.logger.setLevel(logging.INFO)
        
        # Bestehende Handler entfernen (verhindert doppelte Logs bei Mehrfachinitialisierung)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        # Format definieren: [Datum Uhrzeit] [Level] Nachricht
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        
        # Handler für die Konsole (stdout)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Handler für die detaillierte Logdatei (max 1 MB pro Datei, 3 Backups rotierend)
        file_handler = RotatingFileHandler(
            detailed_log_file, 
            maxBytes=1024 * 1024, 
            backupCount=3, 
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def create_directories(self) -> None:
        """
        Erstellt das Zielverzeichnis für die Backups.
        
        Verhindert Fehler beim Schreiben der Backup-Dateien, falls das
        Zielverzeichnis noch nicht auf der Festplatte existiert.
        """
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Backup-Verzeichnis bereit: {self.backup_root}")

    def backup_database(self) -> None:
        """
        Erstellt einen konsistenten SQL-Dump der MariaDB-Datenbank.
        
        Nutzt 'mariadb-dump' innerhalb des laufenden Containers. Die Ausgabe wird direkt
        auf den Host umgeleitet, um temporären Speicherplatz im Container zu sparen.
        """
        self.logger.info("Starte MariaDB-Backup...")
        sql_file = self.backup_root / f"mariadb_backup_{self.timestamp}.sql"
        
        # Aufruf des Dump-Befehls im Container (ohne -t Flag, um Pipe-Redirects zu ermöglichen)
        cmd = [
            "docker", "exec", "-i", "mariadb",
            "mariadb-dump",
            "-udata_sync_user",
            "-p4B^ryG%xz8XSh*&8oR",
            "data_sync"
        ]

        try:
            # stdout wird in die physische Datei auf dem Host umgeleitet
            with open(sql_file, "w", encoding="utf-8") as f:
                subprocess.run(cmd, stdout=f, check=True)
            self.logger.info(f"Datenbank-Backup gespeichert unter: {sql_file.name}")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Fehler beim Ausführen von mariadb-dump: {error}")
            raise

    def backup_api_uploads(self) -> None:
        """
        Packt den Uploads-Ordner der API in ein tar.gz-Archiv.
        
        Wechselt mit dem -C Parameter in das übergeordnete Verzeichnis, damit im
        Archiv relative Pfade gespeichert werden. Das erleichtert einen späteren Restore.
        """
        self.logger.info("Starte Sicherung der API-Uploads...")
        archive_file = self.backup_root / f"uploads_{self.timestamp}.tar.gz"
        uploads_dir = self.project_root
        
        # Überspringt den Schritt, falls die API noch keine Uploads erhalten hat
        if not (uploads_dir / "uploads").exists():
            self.logger.warning(f"Der Ordner 'uploads' wurde unter {uploads_dir} nicht gefunden. Überspringe Sicherung.")
            return

        cmd = [
            "tar", "-czf", str(archive_file),
            "-C", str(uploads_dir),
            "uploads"
        ]

        try:
            subprocess.run(cmd, check=True)
            self.logger.info(f"API-Uploads gesichert unter: {archive_file.name}")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Fehler beim Packen der API-Uploads: {error}")
            raise

    def load_backup_config(self) -> list[dict[str, str]]:
        """
        Lädt die Konfiguration für MariaDB, API-Uploads und Docker-Container aus der INI-Datei.
        Erstellt eine Standard-Konfiguration, falls die Datei noch nicht existiert.
        
        :return: Eine Liste von Dictionaries mit den Schlüsseln 'name', 'container' und 'volume'.
        """
        # Falls die Konfigurationsdatei nicht existiert, erstellen wir eine Standardversion
        if not self.config_file.exists():
            self.logger.info(f"Konfigurationsdatei nicht gefunden. Erstelle Standard-Konfiguration unter {self.config_file.name}")
            config = configparser.ConfigParser()
            config["mariadb"] = {
                "enabled": "true"
            }
            config["uploads"] = {
                "enabled": "true"
            }
            config["portainer"] = {
                "container": "portainer",
                "volume": "portainer_data"
            }
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    config.write(f)
            except Exception as error:
                self.logger.error(f"Konnte Standard-Konfigurationsdatei nicht erstellen: {error}")
                
        config = configparser.ConfigParser()
        try:
            config.read(self.config_file, encoding="utf-8")
        except Exception as error:
            self.logger.error(f"Fehler beim Lesen der Konfigurationsdatei: {error}")
            return []

        # Schalter für MariaDB und Uploads auslesen (Standard: aktiviert)
        self.mariadb_enabled = config.getboolean("mariadb", "enabled", fallback=True)
        self.uploads_enabled = config.getboolean("uploads", "enabled", fallback=True)
        
        containers = []
        for section in config.sections():
            # Spezielle Komponenten überspringen, da sie separat gesteuert werden
            if section in ["mariadb", "uploads"]:
                continue

            # Optionaler Schalter zur Deaktivierung einzelner Container
            if not config.getboolean(section, "enabled", fallback=True):
                self.logger.info(f"Container '{section}' ist in der Konfiguration deaktiviert.")
                continue

            container = config[section].get("container")
            volume = config[section].get("volume")
            if container and volume:
                containers.append({
                    "name": section,
                    "container": container,
                    "volume": volume
                })
            else:
                self.logger.warning(
                    f"Ungültiger Eintrag in Konfigurationsdatei [{section}]: "
                    f"container='{container}', volume='{volume}'"
                )
        self.containers_to_backup = containers
        return containers

    def backup_docker_containers(self) -> None:
        """
        Sichert alle konfigurierten Docker-Volumes nacheinander in einer Schleife.
        
        Stoppt jeden Container kurzzeitig während des Backups, um Inkonsistenzen zu vermeiden.
        """
        if not self.containers_to_backup:
            self.logger.info("Keine Docker-Container zur Sicherung konfiguriert.")
            return

        for item in self.containers_to_backup:
            name = item["name"]
            container = item["container"]
            volume = item["volume"]
            
            self.logger.info(f"Starte Sicherung für Container '{container}' (Beschreibung: {name}, Volume: '{volume}')...")
            archive_file = f"{container}_backup_{self.timestamp}.tar.gz"

            try:
                # Stoppen des Containers zur Vermeidung von Race Conditions
                self.logger.info(f"Stoppe Container '{container}'...")
                subprocess.run(["docker", "stop", container], check=True)

                # Hilfscontainer liest das Volume/den Host-Pfad und schreibt das Archiv auf den Host
                self.logger.info(f"Starte Hilfscontainer für Volume-Kopie von '{volume}'...")
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{volume}:/source",
                    "-v", f"{self.backup_root}:/backup",
                    "alpine",
                    "tar", "-czf", f"/backup/{archive_file}",
                    "-C", "/source", "."
                ]
                subprocess.run(cmd, check=True)
                self.logger.info(f"Container '{container}' erfolgreich gesichert unter: {archive_file}")
                
            except subprocess.CalledProcessError as error:
                self.logger.error(f"Fehler bei der Sicherung von Container '{container}': {error}")
                raise
            except Exception as error:
                self.logger.error(f"Unerwarteter Fehler bei der Sicherung von Container '{container}': {error}")
                raise
            finally:
                # finally-Block sichert ab, dass der Container auch bei Fehlern wieder startet
                self.logger.info(f"Starte Container '{container}' wieder...")
                subprocess.run(["docker", "start", container], check=True)

    def write_log(self, status: str, details: list[str]) -> None:
        """
        Schreibt das Ergebnis des Backup-Laufs in die Log-Datei im Backup-Verzeichnis.

        Die Einträge werden an das Dateiende angehängt. So bleibt die Historie erhalten,
        obwohl die eigentlichen Backup-Dateien bei Erfolg überschrieben/bereinigt werden.
        """
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{self.timestamp}] STATUS: {status}\n")
                for detail in details:
                    f.write(f"  - {detail}\n")
                f.write("-" * 80 + "\n")
            self.logger.info(f"Zusammenfassung in Logdatei geschrieben: {self.log_file.name}")
        except Exception as error:
            self.logger.error(f"Konnte Zusammenfassung nicht in Log schreiben: {error}")

    def send_notification(self, status: str, details: list[str]) -> None:
        """
        Sendet eine Benachrichtigung via discord_notifier.py, falls ein Fehler oder
        eine Warnung aufgetreten ist.
        """
        # Benachrichtigung nur senden, wenn das Backup nicht erfolgreich war
        if status == "SUCCESS":
            return

        emoji = "⚠️" if status == "WARNING" else "🚨"
        header = f"{emoji} **Backup-Status: {status}**"
        time_info = f"Zeitpunkt: {self.timestamp}"
        
        # Details übersichtlich formatieren
        formatted_details = "\n".join(f"• {detail}" for detail in details)
        message = f"{header}\n{time_info}\n\n**Details aus dem Summary-Log:**\n{formatted_details}"
        
        # Pfad zum Notifier-Skript auflösen
        notifier_script = Path(__file__).parent / "discord_notifier.py"
        
        # Für Bash-ANSI-C-Quoting ($'...') einfache Anführungszeichen maskieren
        # und Backslashes verdoppeln.
        escaped_message = message.replace("\\", "\\\\").replace("'", "\\'")
        
        # Befehl für die Ausführung über die Shell zusammensetzen
        cmd = f'python3 "{notifier_script}" $\'{escaped_message}\''
        
        self.logger.info(f"Sende Discord-Benachrichtigung für Status {status}...")
        try:
            # shell=True ist notwendig für das $'...' Bash-Quoting
            subprocess.run(cmd, shell=True, check=True)
            self.logger.info("Discord-Benachrichtigung erfolgreich gesendet.")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Fehler beim Aufrufen des Discord-Notifiers: {error}")

    def validate_backups(self) -> list[str]:
        """
        Überprüft die Existenz und Plausibilität der neu erstellten Backups.

        Klassifiziert die Ergebnisse in:
        - Defekt/0 Bytes (wirft Exception -> bricht Prozess ab, altes Backup bleibt sicher)
        - Leer/Nur Struktur (erzeugt eine Warnung im Log, lässt den Prozess aber weiterlaufen)
        - Erfolgreich mit Inhalt (Standardfall)
        """
        self.logger.info("Validiere neu erstellte Backup-Dateien...")
        log_details = []
        
        # Grenzwerte (in Bytes) zur Erkennung von leeren Dumps/Archiven:
        # SQL: Dump unter 1 KB ist defekt. Unter 2.5 KB enthält er vermutlich nur Header-Kommentare.
        # Gzip: Archiv unter 40 Bytes ist defekt. Unter 50 Bytes ist es ein leeres Gzip-Archiv.
        checks = []
        if self.mariadb_enabled:
            checks.append((self.backup_root / f"mariadb_backup_{self.timestamp}.sql", 1024, 2500, "MariaDB-Datenbank"))
        
        # Docker-Backups dynamisch zur Prüfung hinzufügen
        for item in self.containers_to_backup:
            container = item["container"]
            checks.append((
                self.backup_root / f"{container}_backup_{self.timestamp}.tar.gz",
                100, 200, f"Docker-Volume ({container})"
            ))
        
        # API-Uploads nur prüfen, falls in Konfiguration aktiviert und der Ordner auf dem Host existiert
        if self.uploads_enabled and (self.project_root / "uploads").exists():
            uploads_archive = self.backup_root / f"uploads_{self.timestamp}.tar.gz"
            checks.append((uploads_archive, 100, 200, "API-Uploads"))

        if not checks:
            msg = "Keine Backup-Komponenten zur Validierung konfiguriert."
            self.logger.info(msg)
            log_details.append(msg)
            return log_details

        for file_path, fail_limit, warn_limit, desc in checks:
            if not file_path.exists():
                raise FileNotFoundError(f"Backup-Datei existiert nicht: {file_path.name}")
                
            file_size = file_path.stat().st_size
            
            # Kritischer Fehler (z.B. Verbindungsabbruch oder volle Platte während des Schreibens)
            if file_size < fail_limit:
                raise ValueError(
                    f"Backup-Datei {file_path.name} ({desc}) ist beschädigt oder leer "
                    f"(Größe: {file_size} Bytes, erwartet mindestens: {fail_limit} Bytes)."
                )
            
            # Warnung (Backup lief durch, aber der gesicherte Ordner/die Datenbank war leer)
            elif file_size < warn_limit:
                msg = f"{file_path.name} ({desc}): {file_size} Bytes [WARNUNG: Datei ist leer / enthält keine Nutzdaten]"
                self.logger.warning(msg)
                log_details.append(msg)
            
            # Regulärer Erfolg
            else:
                msg = f"{file_path.name} ({desc}): {file_size} Bytes [OK: Enthält Daten]"
                self.logger.info(msg)
                log_details.append(msg)
                
        return log_details

    def clean_old_backups(self) -> None:
        """
        Löscht ältere Backup-Dateien aus dem Backup-Verzeichnis.
        
        Sorgt dafür, dass nur das soeben validierte, aktuelle Backup behalten wird.
        """
        self.logger.info("Bereinige ältere Backups...")
        patterns = []
        if self.mariadb_enabled:
            patterns.append("mariadb_backup_*.sql")
        if self.uploads_enabled:
            patterns.append("uploads_*.tar.gz")
        
        # Dynamisch Suchmuster für alle konfigurierten Container hinzufügen
        for item in self.containers_to_backup:
            container = item["container"]
            patterns.append(f"{container}_backup_*.tar.gz")
        
        for pattern in patterns:
            # Sortierung erfolgt alphabetisch. Da Dateinamen YYYY-MM-DD enthalten,
            # entspricht dies einer exakten chronologischen Sortierung.
            files = sorted(self.backup_root.glob(pattern))
            
            # Alle Dateien außer der neuesten (letztes Element im sortierten Array) löschen
            if len(files) > 1:
                for old_file in files[:-1]:
                    try:
                        old_file.unlink()
                        self.logger.info(f"Ältere Datei gelöscht: {old_file.name}")
                    except OSError as error:
                        self.logger.error(f"Konnte {old_file.name} nicht löschen: {error}")

    def prune_log_file(self, keep_days: int = 30) -> None:
        """
        Entfernt Logbucheinträge aus der Zusammenfassung, die älter als X Tage sind.

        Verhindert das unbegrenzte Anwachsen der Logdatei auf dem Server.

        :param keep_days: Aufbewahrungszeitraum der Logeinträge in Tagen.
        """
        if not self.log_file.exists():
            return

        self.logger.info(f"Bereinige Logeinträge, die älter als {keep_days} Tage sind...")
        now = datetime.now()
        
        try:
            content = self.log_file.read_text(encoding="utf-8")
            
            # Splits anhand der Trennlinie trennen die Log-Blöcke voneinander
            separator = "-" * 80 + "\n"
            blocks = content.split(separator)
            
            kept_blocks = []
            for block in blocks:
                block_stripped = block.strip()
                if not block_stripped:
                    continue
                
                try:
                    # Zeitstempel aus dem Format '[YYYY-MM-DD_HH-MM-SS]' auslesen
                    start_idx = block_stripped.find("[")
                    end_idx = block_stripped.find("]")
                    if start_idx != -1 and end_idx != -1:
                        timestamp_str = block_stripped[start_idx + 1:end_idx]
                        entry_date = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                        age_in_days = (now - entry_date).days
                        
                        # Nur Einträge behalten, deren Alter unter dem Grenzwert liegt
                        if age_in_days < keep_days:
                            kept_blocks.append(block_stripped)
                except (ValueError, IndexError):
                    # Defekte/manuell bearbeitete Einträge zur Sicherheit behalten
                    kept_blocks.append(block_stripped)
            
            # Datei mit den gefilterten Einträgen neu schreiben
            if kept_blocks:
                new_content = "\n".join(kept_blocks) + "\n" + separator
                self.log_file.write_text(new_content, encoding="utf-8")
            else:
                # Falls gar kein Eintrag übrig bleibt, Logdatei entfernen
                self.log_file.unlink(missing_ok=True)
                
            self.logger.info("Logbereinigung erfolgreich abgeschlossen.")
        except Exception as error:
            self.logger.error(f"Fehler bei der Bereinigung der Logdatei: {error}")

    def run(self) -> None:
        """
        Führt die gesamte Backup-Pipeline nacheinander aus.
        
        Kapselt den Ablauf in einer Fehlerüberwachung, um sicherzustellen, dass
        alte Backups bei Problemen als Fallback erhalten bleiben.
        """
        try:
            self.create_directories()
            
            if self.mariadb_enabled:
                self.backup_database()
            else:
                self.logger.info("MariaDB-Backup ist in der Konfiguration deaktiviert. Überspringe Schritt.")

            if self.uploads_enabled:
                self.backup_api_uploads()
            else:
                self.logger.info("API-Uploads-Backup ist in der Konfiguration deaktiviert. Überspringe Schritt.")

            self.backup_docker_containers()
            
            # Erst validieren, dann Status ermitteln (Erfolg vs. Warnung)
            log_details = self.validate_backups()
            has_warnings = any("WARNUNG" in detail for detail in log_details)
            status = "WARNING" if has_warnings else "SUCCESS"
            
            # Log schreiben
            self.write_log(status, log_details)
            
            # Benachrichtigung bei Warnungen senden
            self.send_notification(status, log_details)
            
            # Alte Backups nur löschen, wenn kein Fehler und keine Warnungen aufgetreten sind
            if status == "SUCCESS":
                self.clean_old_backups()
            else:
                self.logger.warning("Alte Backups wurden aufgrund von Warnungen beim aktuellen Lauf nicht gelöscht!")
            
            # Log-Historie aufräumen
            self.prune_log_file(keep_days=30)
            
            self.logger.info("Backup-Prozess vollständig und fehlerfrei beendet!")
        except Exception as error:
            error_msg = str(error)
            self.logger.critical(f"Backup-Prozess wurde aufgrund eines Fehlers abgebrochen: {error_msg}")
            self.logger.critical("Ältere Backups wurden zur Sicherheit NICHT gelöscht!")
            
            # Fehlgeschlagenen Lauf im permanenten Log protokollieren
            details = [f"Fehler beim Backup-Lauf: {error_msg}", "Ältere Backups wurden nicht gelöscht."]
            self.write_log("FATAL", details)
            
            # Benachrichtigung bei schwerwiegenden Fehlern senden
            self.send_notification("FATAL", details)


if __name__ == "__main__":
    # Konfiguration der Backup- und Projektpfade (unterstützt ~ für Home-Verzeichnis)
    backup_manager = BackupManager(
        backup_root="~/Bkup",
        project_root="~/Docker/Data Sync"
    )
    backup_manager.run()
