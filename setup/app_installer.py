#!/usr/bin/env python3
"""Batch-Installer und Status-Prüfer für Softwarepakete.

Dieses Werkzeug liest Paketlisten (*.applist) ein und überprüft,
ob die darin enthaltenen Softwarepakete auf dem System vorhanden sind
oder installiert diese über den passenden Paketmanager.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess
import sys
from typing import List, Optional


class PackageType(Enum):
    """Unterstützte Paket- und Distributionsarten."""

    ARCH = "arch"
    PACMAN = "pacman"
    YAY = "yay"
    PARU = "paru"
    DEBIAN = "debian"
    RPM = "rpm"
    FLATPAK = "flatpak"
    UNKNOWN = "unknown"


@dataclass
class PackageItem:
    """Repräsentiert ein einzelnes Paket aus einer App-Liste."""

    name: str
    description: str = ""
    package_type: PackageType = PackageType.UNKNOWN


@dataclass
class AppList:
    """Repräsentiert eine geparste Definitionsdatei mit Paketliste."""

    path: Path
    packages: List[PackageItem]


class PackageManager(ABC):
    """Abstrakte Basisklasse für die Verwaltung von Paketmanagern."""

    def __init__(self, display_label: str) -> None:
        """Initialisiert den Paketmanager mit einem Anzeigepräfix für die Ausgabe."""
        self.display_label = display_label

    @abstractmethod
    def is_available(self) -> bool:
        """Ermittelt, ob die erforderlichen Werkzeuge auf dem System vorhanden sind."""
        pass

    @abstractmethod
    def is_installed(self, package_name: str) -> bool:
        """Prüft, ob ein konkretes Paket auf dem Host-System installiert ist."""
        pass

    @abstractmethod
    def install(self, package_name: str) -> bool:
        """Führt den Installationsbefehl für ein Paket aus."""
        pass

    def post_install(self, package_name: str) -> None:
        """Optionale Nachbearbeitungsschritte nach erfolgreicher Installation."""
        pass


class ArchPackageManager(PackageManager):
    """Verwaltet Arch-Linux- und AUR-Pakete über yay, paru oder pacman."""

    def __init__(self, explicit_tool: Optional[str] = None) -> None:
        """Initialisiert den Arch-Paketmanager mit optional explizitem Werkzeug."""
        label = f"Arch ({explicit_tool})" if explicit_tool else "Arch-Paket"
        super().__init__(display_label=label)
        self.explicit_tool = explicit_tool
        self.pacman_executable: Optional[str] = shutil.which("pacman")
        self.aur_helper: Optional[str] = self._detect_aur_helper()

    def _detect_aur_helper(self) -> Optional[str]:
        """Ermittelt das zu verwendende AUR-Hilfsprogramm."""
        if self.explicit_tool in {"yay", "paru"}:
            return shutil.which(self.explicit_tool)
        if self.explicit_tool == "pacman":
            return None
        for helper in ("yay", "paru"):
            executable_path = shutil.which(helper)
            if executable_path:
                return executable_path
        return None

    def is_available(self) -> bool:
        """Prüft, ob das benötigte Werkzeug auf dem System verfügbar ist."""
        if self.explicit_tool in {"yay", "paru"}:
            return self.aur_helper is not None
        return self.pacman_executable is not None

    def is_installed(self, package_name: str) -> bool:
        """Prüft die Installation des Pakets über pacman."""
        if not self.is_available():
            return False

        # Exakte Paketprüfung via pacman -Qq ohne Versionsangabe
        result = subprocess.run(
            ["pacman", "-Qq", package_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def install(self, package_name: str) -> bool:
        """Installiert das Paket über den AUR-Helper oder sudo pacman."""
        if self.aur_helper:
            # AUR-Helper verwalten Benutzerrechte selbstständig
            command = [self.aur_helper, "-S", "--noconfirm", package_name]
        else:
            # Reines pacman benötigt Root-Rechte
            command = ["sudo", "pacman", "-S", "--noconfirm", package_name]

        process = subprocess.run(command, check=False)
        if process.returncode == 0:
            self.post_install(package_name)
            return True
        return False

    def post_install(self, package_name: str) -> None:
        """Startet spezielle Systemdienste, falls erforderlich."""
        if package_name == "teamviewer":
            print("\nStarte und aktiviere teamviewerd.service...")
            subprocess.run(["sudo", "systemctl", "enable", "teamviewerd"], check=False)
            subprocess.run(["sudo", "systemctl", "start", "teamviewerd"], check=False)


class DebianPackageManager(PackageManager):
    """Verwaltet DEB-Pakete über apt und dpkg-query."""

    def __init__(self) -> None:
        """Initialisiert den Debian-Paketmanager."""
        super().__init__(display_label="DEB-Paket")
        self.apt_executable: Optional[str] = shutil.which("apt")
        self.dpkg_executable: Optional[str] = shutil.which("dpkg-query")

    def is_available(self) -> bool:
        """Prüft das Vorhandensein von apt."""
        return self.apt_executable is not None

    def is_installed(self, package_name: str) -> bool:
        """Prüft den Installationsstatus über dpkg-query."""
        if not self.dpkg_executable:
            return False

        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return "ok installed" in result.stdout

    def install(self, package_name: str) -> bool:
        """Installiert das Paket mittels apt unter Root-Rechten."""
        command = ["sudo", "apt", "install", "-y", package_name]
        process = subprocess.run(command, check=False)
        return process.returncode == 0


class RpmPackageManager(PackageManager):
    """Verwaltet RPM-Pakete über dnf und rpm."""

    def __init__(self) -> None:
        """Initialisiert den RPM-Paketmanager."""
        super().__init__(display_label="RPM-Paket")
        self.dnf_executable: Optional[str] = shutil.which("dnf")
        self.rpm_executable: Optional[str] = shutil.which("rpm")

    def is_available(self) -> bool:
        """Prüft das Vorhandensein von dnf."""
        return self.dnf_executable is not None

    def is_installed(self, package_name: str) -> bool:
        """Prüft die Paketinstallation über den rpm-Befehl."""
        if not self.rpm_executable:
            return False

        result = subprocess.run(
            ["rpm", "-q", package_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def install(self, package_name: str) -> bool:
        """Installiert das RPM-Paket mittels dnf unter Root-Rechten."""
        command = ["sudo", "dnf", "install", "-y", package_name]
        process = subprocess.run(command, check=False)
        return process.returncode == 0


class FlatpakPackageManager(PackageManager):
    """Verwaltet Desktop-Anwendungen über Flatpak."""

    def __init__(self) -> None:
        """Initialisiert den Flatpak-Paketmanager."""
        super().__init__(display_label="Flatpak")
        self.flatpak_executable: Optional[str] = shutil.which("flatpak")

    def is_available(self) -> bool:
        """Prüft, ob flatpak auf dem System installiert ist."""
        return self.flatpak_executable is not None

    def is_installed(self, package_name: str) -> bool:
        """Überprüft, ob die App als Flatpak installiert ist."""
        if not self.is_available():
            return False

        # Exakte Prüfung über Applikations-ID
        direct_check = subprocess.run(
            ["flatpak", "info", package_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if direct_check.returncode == 0:
            return True

        # Fallback: Suche in der Liste installierter Flatpaks
        list_output = subprocess.run(
            ["flatpak", "list", "--app"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return package_name.lower() in list_output.stdout.lower()

    def install(self, package_name: str) -> bool:
        """Installiert das Flatpak über den konfigurierten Remote-Katalog."""
        command = ["flatpak", "install", "-y", package_name]
        process = subprocess.run(command, check=False)
        return process.returncode == 0


class PackageManagerFactory:
    """Fabrikklasse zur Bereitstellung der passenden Paketmanager-Instanz."""

    @staticmethod
    def create_manager(package_type: PackageType, default_arch_tool: Optional[str] = None) -> Optional[PackageManager]:
        """Gibt die konkrete Implementierung für den jeweiligen Pakettyp zurück."""
        if package_type == PackageType.PACMAN:
            return ArchPackageManager(explicit_tool="pacman")
        if package_type == PackageType.YAY:
            return ArchPackageManager(explicit_tool="yay")
        if package_type == PackageType.PARU:
            return ArchPackageManager(explicit_tool="paru")
        if package_type == PackageType.ARCH:
            return ArchPackageManager(explicit_tool=default_arch_tool)
        if package_type == PackageType.DEBIAN:
            return DebianPackageManager()
        if package_type == PackageType.RPM:
            return RpmPackageManager()
        if package_type == PackageType.FLATPAK:
            return FlatpakPackageManager()
        return None


class AppListParser:
    """Verantwortlich für das Einlesen und Interpretieren von .applist-Dateien."""

    @staticmethod
    def detect_host_system_package_type() -> PackageType:
        """Ermittelt den primären nativen Paketmanager des Host-Betriebssystems."""
        if shutil.which("pacman"):
            return PackageType.ARCH
        if shutil.which("apt"):
            return PackageType.DEBIAN
        if shutil.which("dnf"):
            return PackageType.RPM
        return PackageType.UNKNOWN

    @classmethod
    def detect_type(cls, header_line: str) -> PackageType:
        """Ermittelt den Pakettyp aus einer Definitions- oder Abschnittszeile."""
        header_clean = header_line.strip()

        # Unterstützung für [section] und type= Deklarationen
        if header_clean.startswith("[") and header_clean.endswith("]"):
            type_identifier = header_clean[1:-1].strip().lower()
        elif header_clean.startswith("type="):
            type_identifier = header_clean.split("=", 1)[1].strip().lower()
        else:
            return PackageType.UNKNOWN

        if type_identifier in {"system", "host", "native"}:
            return cls.detect_host_system_package_type()
        if type_identifier == "pacman":
            return PackageType.PACMAN
        if type_identifier == "yay":
            return PackageType.YAY
        if type_identifier == "paru":
            return PackageType.PARU
        if type_identifier in {"arch", "aur"}:
            return PackageType.ARCH
        if type_identifier in {"apt", "deb", "debian"}:
            return PackageType.DEBIAN
        if type_identifier in {"rpm", "dnf"}:
            return PackageType.RPM
        if type_identifier in {"flatpak", "flat", "flathub"}:
            return PackageType.FLATPAK

        return PackageType.UNKNOWN

    @classmethod
    def parse_file(cls, file_path: Path) -> AppList:
        """Liest eine App-Liste ein und extrahiert Pakete inklusive ihrer Zielumgebung."""
        if not file_path.is_file():
            raise FileNotFoundError(f"Die Datei '{file_path}' existiert nicht.")

        lines = file_path.read_text(encoding="utf-8").splitlines()
        current_type: PackageType = PackageType.UNKNOWN
        packages: List[PackageItem] = []

        for line in lines:
            clean_line = line.strip()

            # Kommentare und Leerzeilen überspringen
            if not clean_line or clean_line.startswith("#"):
                continue

            # Typ- oder Sektionswechsel prüfen
            detected_type = cls.detect_type(clean_line)
            if detected_type != PackageType.UNKNOWN:
                current_type = detected_type
                continue

            # Paketzeile auswerten: name;beschreibung
            parts = clean_line.split(";", 1)
            raw_package_name = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else ""

            # Optionales Typpräfix pro Zeile unterstützen (z. B. flatpak:org.mozilla.Thunderbird)
            package_type = current_type
            package_name = raw_package_name
            if ":" in raw_package_name and not raw_package_name.startswith("/"):
                prefix, potential_name = raw_package_name.split(":", 1)
                prefix_type = cls.detect_type(f"type={prefix}")
                if prefix_type != PackageType.UNKNOWN:
                    package_type = prefix_type
                    package_name = potential_name.strip()

            if package_name:
                packages.append(PackageItem(name=package_name, description=description, package_type=package_type))

        return AppList(path=file_path, packages=packages)


class ConfigManager:
    """Verwaltet die Konfiguration und den Suchpfad für App-Listen."""

    def __init__(self, base_directory: Optional[Path] = None) -> None:
        """Initialisiert Pfade zur Konfiguration in ~/.applists/apps.config."""
        self.base_dir = base_directory or (Path.home() / ".applists")
        self.config_file = self.base_dir / "apps.config"

    def ensure_config_directory(self) -> None:
        """Erstellt das Konfigurationsverzeichnis, falls es fehlt."""
        if not self.base_dir.exists():
            print(f"Erstelle Konfigurationsverzeichnis: {self.base_dir}")
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_applist_directory(self) -> Path:
        """Liest das Verzeichnis für App-Listen aus der Konfiguration oder fordert es an."""
        self.ensure_config_directory()

        if self.config_file.is_file():
            content = self.config_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("applist_dir="):
                    configured_path = Path(line.split("=", 1)[1].strip()).expanduser()
                    if configured_path.exists():
                        return configured_path

        # Ermittlung des Standardpfads: Bevorzuge existierenden applists-Ordner im Projekt
        project_applists = Path(__file__).resolve().parent.parent / "setup" / "applists"
        script_dir_applists = Path(__file__).resolve().parent / "applists"
        default_dir = project_applists if project_applists.exists() else (script_dir_applists if script_dir_applists.exists() else self.base_dir)

        if sys.stdin.isatty():
            print("\nEs ist noch kein Speicherort für App-Listen konfiguriert.")
            user_input = input(f">> Pfad zum Applisten-Ordner eingeben [{default_dir}]: ").strip()
            chosen_dir = Path(user_input).expanduser() if user_input else default_dir
        else:
            chosen_dir = default_dir

        chosen_dir.mkdir(parents=True, exist_ok=True)
        self.save_applist_directory(chosen_dir)
        return chosen_dir

    def get_preferred_arch_manager(self) -> Optional[str]:
        """Liest den bevorzugten Arch-Paketmanager (pacman, yay, paru) aus der Konfigurationsdatei."""
        if self.config_file.is_file():
            content = self.config_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("arch_manager="):
                    manager_name = line.split("=", 1)[1].strip().lower()
                    if manager_name in {"pacman", "yay", "paru"}:
                        return manager_name
        return None

    def save_applist_directory(self, target_directory: Path) -> None:
        """Schreibt den Pfad für App-Listen dauerhaft in die Konfigurationsdatei."""
        self.ensure_config_directory()
        formatted_entry = f"applist_dir={target_directory.resolve()}\n"
        self.config_file.write_text(formatted_entry, encoding="utf-8")


class AppInstallerCLI:
    """Kommandozeilen-Schnittstelle für den Anwendungs- und Paketprüfer."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """Initialisiert die CLI mit der Konfigurationsverwaltung."""
        self.config_manager = config_manager

    def show_help(self, applist_directory: Path) -> None:
        """Gibt Hilfetext und eine Übersicht aller verfügbaren App-Listen aus."""
        help_text = f"""
************************************************************************
Nutzung: app_installer.py [check|install] [datei.applist]
Nutzung: app_installer.py [check|install] ["muster*"]
Nutzung: app_installer.py [check|install] ["datei1.applist datei2.applist"]
Nutzung: app_installer.py [check|install] all

Befehl 1:
  check       Prüft, ob die aufgelisteten Pakete bereits installiert sind
  install     Installiert fehlende Pakete aus der Liste

Befehl 2:
  dateiname   Eine oder mehrere Listen (mit oder ohne Wildcards/Glob)
  all         Alle vorhandenen *.applist-Dateien abarbeiten
************************************************************************

Gefundene App-Listen in {applist_directory}:
--"""
        print(help_text)
        found_any = False
        if applist_directory.is_dir():
            for file_path in sorted(applist_directory.glob("*.applist")):
                print(f"  {file_path.name}")
                found_any = True

        if not found_any:
            print("  (Keine *.applist Dateien vorhanden)")
        print("--\n")

    def resolve_applists(self, argument_target: str, applist_directory: Path) -> List[Path]:
        """Löst das Zielargument (Dateiname, Glob, all oder Direktpfad) zu Dateipfaden auf."""
        resolved_files: List[Path] = []
        tokens = argument_target.split()

        for token in tokens:
            if token.lower() == "all":
                resolved_files.extend(sorted(applist_directory.glob("*.applist")))
                continue

            # Direkte relative oder absolute Pfadangabe prüfen
            direct_candidate = Path(token).expanduser()
            if direct_candidate.is_file():
                resolved_files.append(direct_candidate)
                continue

            # Suche im konfigurierten Applisten-Verzeichnis
            glob_candidates = sorted(applist_directory.glob(token))
            if glob_candidates:
                resolved_files.extend(glob_candidates)
            else:
                # Prüfe mit angehängter .applist Endung
                with_extension = sorted(applist_directory.glob(f"{token}.applist"))
                if with_extension:
                    resolved_files.extend(with_extension)
                else:
                    print(f"[WARNUNG] Keine passende Datei für '{token}' in '{applist_directory}' gefunden.")

        # Duplikate unter Beibehaltung der Reihenfolge entfernen
        unique_files: List[Path] = []
        for path in resolved_files:
            resolved_abs = path.resolve()
            if resolved_abs not in [p.resolve() for p in unique_files]:
                unique_files.append(path)

        return unique_files

    def process_list(self, app_list: AppList, command: str) -> None:
        """Verarbeitet eine geladene App-Liste entsprechend dem gewählten Befehl."""
        print(f"\nVerarbeite Liste: {app_list.path}")

        if not app_list.packages:
            print("  (Keine Paketeinträge in dieser Liste gefunden)")
            return

        # Cache für Manager-Instanzen, um wiederholte Instanziierung zu vermeiden
        managers: dict[PackageType, Optional[PackageManager]] = {}
        arch_default_tool = self.config_manager.get_preferred_arch_manager()

        for package in app_list.packages:
            if package.package_type == PackageType.UNKNOWN:
                print(f"[WARNUNG] Kein Pakettyp für '{package.name}' definiert. Überspringe...")
                continue

            if package.package_type not in managers:
                managers[package.package_type] = PackageManagerFactory.create_manager(
                    package.package_type, default_arch_tool=arch_default_tool
                )

            manager = managers[package.package_type]
            if not manager:
                print(f"[FEHLER] Kein Manager für '{package.package_type.value}' vorhanden.")
                continue

            if not manager.is_available():
                print(f"Paketmanager für '{package.package_type.value}' ist auf diesem System nicht verfügbar (Paket: {package.name}).")
                continue

            installed = manager.is_installed(package.name)
            label = f"{manager.display_label}: {package.name}"

            if installed:
                print(f"{label:<60} bereits installiert")
            else:
                if command == "check":
                    print(f"{label:<60} nicht installiert")
                elif command == "install":
                    print(f"{label:<60} installiere...")
                    success = manager.install(package.name)
                    if not success:
                        print(f"[FEHLER] Installation von '{package.name}' fehlgeschlagen.")

    def run(self, arguments: List[str]) -> int:
        """Haupteinstiegspunkt für die Kommandozeilenausführung."""
        applist_dir = self.config_manager.get_applist_directory()

        if len(arguments) < 2:
            self.show_help(applist_dir)
            return 0

        command = arguments[0].lower()
        if command not in {"check", "install"}:
            print(f"[FEHLER] Unbekannter Befehl: '{command}'. Erlaubt sind 'check' oder 'install'.")
            self.show_help(applist_dir)
            return 1

        target_argument = " ".join(arguments[1:])
        target_files = self.resolve_applists(target_argument, applist_dir)

        if not target_files:
            print(f"Keine passenden App-Listen für '{target_argument}' gefunden.")
            return 1

        for target_file in target_files:
            try:
                parsed_list = AppListParser.parse_file(target_file)
                self.process_list(parsed_list, command)
            except Exception as error:
                print(f"[FEHLER] Fehler beim Verarbeiten von '{target_file}': {error}")

        return 0


def main() -> None:
    """Startet die CLI-Anwendung mit den übergebenen Parametern."""
    config_manager = ConfigManager()
    cli = AppInstallerCLI(config_manager=config_manager)
    exit_code = cli.run(sys.argv[1:])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
