#!/usr/bin/env python3
# ==============================================================================
# Restore-Skript für Debian Server (data_sync, MariaDB, Portainer)
# Zweck: Interaktive Wiederherstellung der Anwendungsdaten aus Backups
# ==============================================================================

import subprocess
from pathlib import Path
import logging
import configparser
import re
from logging.handlers import RotatingFileHandler

class RestoreManager:
    """
    Verwaltet den Wiederherstellungs-Prozess für die API-Umgebung.

    Diese Klasse liest die verfügbaren Backup-Zeitstempel aus, lässt den Benutzer
    interaktiv eine Version wählen und führt die Wiederherstellung von MariaDB,
    API-Uploads und Portainer durch.
    """

    def __init__(self, backup_root: str, project_root: str):
        """
        Initialisiert den Restore-Manager mit den Ziel- und Projektpfaden.

        :param backup_root: Hauptordner für Backups (z.B. '~/Bkup').
        :param project_root: Projekt-Verzeichnis auf dem Host (z.B. '~/Dev/data_sync').
        """
        self.backup_root = Path(backup_root).expanduser().resolve()
        self.project_root = Path(project_root).expanduser().resolve()
        
        # Logging initialisieren (Konsole + rotierende restore.log)
        self.setup_logging()

        # Pfad zur INI-Konfigurationsdatei für Docker-Backups
        self.config_file = Path(__file__).parent / "backup_config.ini"
        self.containers_to_backup = self.load_backup_config()

    def setup_logging(self) -> None:
        """
        Richtet das Logging-System ein.
        Leitet alle Ausgaben sowohl auf die Konsole als auch in 'restore.log' um.
        """
        detailed_log_file = self.backup_root / "restore.log"
        
        self.logger = logging.getLogger("RestoreManager")
        self.logger.setLevel(logging.INFO)
        
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        
        # Handler für die Konsole
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Handler für die Logdatei
        file_handler = RotatingFileHandler(
            detailed_log_file, 
            maxBytes=1024 * 1024, 
            backupCount=3, 
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def find_available_backups(self) -> list[str]:
        """
        Scannt das Backup-Verzeichnis nach gültigen Sicherungs-Zeitstempeln.

        Sucht nach SQL-Dateien und Archiven (MariaDB, Docker-Backups, Uploads) und ermittelt
        deren Zeitstempel. Gibt eine sortierte Liste aller gefundenen Zeitstempel zurück.
        """
        self.logger.info(f"Scanne Backup-Verzeichnis: {self.backup_root}")
        if not self.backup_root.exists():
            self.logger.error("Backup-Verzeichnis existiert nicht!")
            return []

        # RegExp-Muster zur Extraktion des Zeitstempels (YYYY-MM-DD_HH-MM-SS)
        patterns = [
            re.compile(r"mariadb_backup_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.sql"),
            re.compile(r"uploads_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.tar\.gz")
        ]
        glob_patterns = ["mariadb_backup_*.sql", "uploads_*.tar.gz"]

        # Dynamisch Muster für alle konfigurierten Docker-Container hinzufügen
        for item in self.containers_to_backup:
            container = item["container"]
            patterns.append(re.compile(rf"{container}_backup_(\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}})\.tar\.gz"))
            glob_patterns.append(f"{container}_backup_*.tar.gz")

        timestamps = set()

        # Alle Dateimuster durchsuchen
        for glob_pattern in glob_patterns:
            for file_path in self.backup_root.glob(glob_pattern):
                for regex in patterns:
                    match = regex.match(file_path.name)
                    if match:
                        timestamps.add(match.group(1))

        # Sortiert absteigend (neueste Backups zuerst)
        return sorted(list(timestamps), reverse=True)

    def restore_database(self, timestamp: str) -> None:
        """
        Spielt den SQL-Dump in den laufenden MariaDB-Container ein.

        :param timestamp: Der auszuwählende Zeitstempel des Backups.
        """
        sql_file = self.backup_root / f"mariadb_backup_{timestamp}.sql"
        if not sql_file.exists():
            self.logger.warning(f"Kein MariaDB-Backup für Zeitstempel {timestamp} gefunden. Überspringe DB-Restore.")
            return

        self.logger.info(f"Starte Wiederherstellung der MariaDB-Datenbank aus {sql_file.name}...")
        cmd = [
            "docker", "exec", "-i", "mariadb",
            "mariadb",
            "-udata_sync_user",
            "-p4B^ryG%xz8XSh*&8oR",
            "data_sync"
        ]

        try:
            with open(sql_file, "r", encoding="utf-8") as f:
                subprocess.run(cmd, stdin=f, check=True)
            self.logger.info("[SUCCESS] MariaDB-Datenbank erfolgreich wiederhergestellt.")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Fehler beim Einspielen des SQL-Dumps: {error}")
            raise

    def restore_api_uploads(self, timestamp: str) -> None:
        """
        Entpackt die gesicherten API-Uploads wieder in das Projektverzeichnis.

        :param timestamp: Der auszuwählende Zeitstempel des Backups.
        """
        archive_file = self.backup_root / f"uploads_{timestamp}.tar.gz"
        if not archive_file.exists():
            self.logger.warning(f"Kein API-Uploads-Backup für Zeitstempel {timestamp} gefunden. Überspringe Uploads-Restore.")
            return

        uploads_dir = self.project_root / "data_sync.API"
        target_uploads = uploads_dir / "uploads"
        
        self.logger.info(f"Starte Wiederherstellung der API-Uploads aus {archive_file.name}...")

        # Zielverzeichnis bereinigen, falls es existiert, um verwaiste Dateien zu vermeiden
        if target_uploads.exists():
            self.logger.info(f"Bereinige verwaiste Upload-Dateien in: {target_uploads.name}")
            try:
                import shutil
                shutil.rmtree(target_uploads)
            except OSError as error:
                self.logger.error(f"Fehler bei der Bereinigung des Upload-Verzeichnisses: {error}")
                raise

        # Zielverzeichnis erstellen, falls es gelöscht wurde
        uploads_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "tar", "-xzf", str(archive_file),
            "-C", str(uploads_dir)
        ]

        try:
            subprocess.run(cmd, check=True)
            self.logger.info("[SUCCESS] API-Uploads erfolgreich wiederhergestellt.")
        except subprocess.CalledProcessError as error:
            self.logger.error(f"Fehler beim Entpacken der API-Uploads: {error}")
            raise

    def load_backup_config(self) -> list[dict[str, str]]:
        """
        Lädt die Liste der zu sichernden Docker-Container und Volumes aus der INI-Konfigurationsdatei.
        Erstellt eine Standard-Konfiguration mit Portainer, falls die Datei noch nicht existiert.
        
        :return: Eine Liste von Dictionaries mit den Schlüsseln 'name', 'container' und 'volume'.
        """
        # Falls die Konfigurationsdatei nicht existiert, erstellen wir eine Standardversion mit Portainer
        if not self.config_file.exists():
            self.logger.info(f"Konfigurationsdatei nicht gefunden. Erstelle Standard-Konfiguration unter {self.config_file.name}")
            config = configparser.ConfigParser()
            config["mariadb"] = {"enabled": "true"}
            config["uploads"] = {"enabled": "true"}
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
        
        containers = []
        for section in config.sections():
            # Spezielle Komponenten überspringen, da sie separat wiederhergestellt werden
            if section in ["mariadb", "uploads"]:
                continue

            # Optionaler Schalter zur Deaktivierung einzelner Container
            if not config.getboolean(section, "enabled", fallback=True):
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
        return containers

    def restore_docker_containers(self, timestamp: str) -> None:
        """
        Stoppt alle konfigurierten Docker-Container, leert die Volumes/Host-Pfade
        und entpackt die jeweiligen Backups.
        
        :param timestamp: Der auszuwählende Zeitstempel des Backups.
        """
        if not self.containers_to_backup:
            self.logger.info("Keine Docker-Container zur Wiederherstellung konfiguriert.")
            return

        for item in self.containers_to_backup:
            name = item["name"]
            container = item["container"]
            volume = item["volume"]
            
            archive_file = f"{container}_backup_{timestamp}.tar.gz"
            archive_path = self.backup_root / archive_file
            
            if not archive_path.exists():
                self.logger.warning(
                    f"Kein Backup für Container '{container}' ({name}) mit Zeitstempel {timestamp} gefunden. "
                    "Überspringe Wiederherstellung für diesen Container."
                )
                continue

            self.logger.info(f"Starte Wiederherstellung von Container '{container}' aus {archive_file}...")

            try:
                # Container stoppen, um Dateizugriffe zu blockieren
                self.logger.info(f"Stoppe Container '{container}'...")
                try:
                    subprocess.run(["docker", "stop", container], check=True)
                    container_existed = True
                except subprocess.CalledProcessError:
                    self.logger.warning(f"Container '{container}' konnte nicht gestoppt werden (existiert möglicherweise nicht).")
                    container_existed = False

                # Hilfscontainer löscht alten Inhalt und entpackt Backup
                self.logger.info(f"Starte Hilfscontainer zum Leeren und Entpacken des Volumes '{volume}'...")
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{volume}:/dest",
                    "-v", f"{self.backup_root}:/backup",
                    "alpine",
                    "sh", "-c", f"rm -rf /dest/* && tar -xzf /backup/{archive_file} -C /dest"
                ]
                subprocess.run(cmd, check=True)
                self.logger.info(f"[SUCCESS] Container '{container}' erfolgreich wiederhergestellt.")
                
            except subprocess.CalledProcessError as error:
                self.logger.error(f"Fehler bei der Wiederherstellung von Container '{container}': {error}")
                raise
            finally:
                # Sicherstellen, dass der Container am Ende wieder läuft (sofern er zuvor existiert hat)
                if 'container_existed' in locals() and container_existed:
                    self.logger.info(f"Starte Container '{container}' wieder...")
                    subprocess.run(["docker", "start", container], check=True)

    def run_interactive(self) -> None:
        """
        Führt den interaktiven Restore-Prozess im Terminal aus.
        """
        print("\n" + "=" * 50)
        print("    DOCKER SERVER RESTORE MANAGER")
        print("=" * 50)
        
        timestamps = self.find_available_backups()
        if not timestamps:
            print("[INFO] Keine Backups zur Wiederherstellung gefunden.")
            return

        print("\nVerfügbare Backups:")
        for idx, ts in enumerate(timestamps, 1):
            print(f"  [{idx}] Backup vom {ts.replace('_', ' um ')}")
            
        print("\n[0] Abbrechen")
        
        try:
            selection = input("\nBitte wähle die Nummer des Backups aus: ")
            if not selection.isdigit():
                print("[ERROR] Ungültige Eingabe.")
                return
                
            val = int(selection)
            if val == 0:
                print("Restore abgebrochen.")
                return
                
            if val < 1 or val > len(timestamps):
                print("[ERROR] Ungültige Auswahl.")
                return
                
            chosen_timestamp = timestamps[val - 1]
            print(f"\nAusgewähltes Backup-Datum: {chosen_timestamp.replace('_', ' um ')}")
            
            # Neue Menüabfrage zur Auswahl der Komponenten
            print("\nWelche Komponenten möchtest du wiederherstellen?")
            print("  [1] Alle Komponenten (Datenbank, Docker-Container & Uploads)")
            print("  [2] Nur MariaDB-Datenbank")
            print("  [3] Nur Docker-Container")
            print("  [4] Nur API-Uploads")
            print("  [0] Abbrechen")
            
            comp_selection = input("\nBitte wähle eine Option: ")
            if not comp_selection.isdigit():
                print("[ERROR] Ungültige Eingabe.")
                return
                
            comp_val = int(comp_selection)
            if comp_val == 0:
                print("Restore abgebrochen.")
                return
                
            if comp_val < 1 or comp_val > 4:
                print("[ERROR] Ungültige Auswahl.")
                return
                
            confirm = input("\nBist du sicher? Die gewählten aktuellen Daten werden überschrieben! (ja/nein): ")
            if confirm.lower() not in ["ja", "j", "yes", "y"]:
                print("Restore abgebrochen.")
                return
                
            # Führe die gewählten Wiederherstellungen aus
            if comp_val == 1:
                self.restore_docker_containers(chosen_timestamp)
                self.restore_api_uploads(chosen_timestamp)
                self.restore_database(chosen_timestamp)
            elif comp_val == 2:
                self.restore_database(chosen_timestamp)
            elif comp_val == 3:
                self.restore_docker_containers(chosen_timestamp)
            elif comp_val == 4:
                self.restore_api_uploads(chosen_timestamp)
                
            print("\n[SUCCESS] Wiederherstellung erfolgreich abgeschlossen!")
            
        except KeyboardInterrupt:
            print("\nRestore interaktiv abgebrochen.")
        except Exception as error:
            self.logger.critical(f"FATAL: Wiederherstellung abgebrochen: {error}")


if __name__ == "__main__":
    # Konfiguration identisch zum Backup-Skript
    restore_manager = RestoreManager(
        backup_root="~/Bkup",
        project_root="~/Docker/Data Sync"
    )
    restore_manager.run_interactive()
