#!/usr/bin/env python3
"""Modul zur Konfiguration von Shell-Aliasen aus einer JSON-Konfigurationsdatei.

Liest Alias-Definitionen aus einer JSON-Datei ein und trägt fehlende Einträge
idempotent in die Konfigurationsdateien von Bash, Zsh und Fish ein.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import os
import pwd
import sys
from typing import List, Optional


@dataclass
class ShellTarget:
    """Repräsentiert eine Ziel-Shell-Konfigurationsdatei mit den zugehörigen Aliasen."""

    file_path: Path
    aliases: List[str]


class ShellConfigurator:
    """Verwaltet das Einlesen und Eintragen von Shell-Aliasen."""

    def __init__(self, config_file: Optional[Path] = None) -> None:
        """Initialisiert den Konfigurator mit dem Pfad zur Konfigurationsdatei."""
        if config_file:
            self.config_file = config_file
        else:
            self.config_file = Path(__file__).resolve().parent / "shell_config.json"

    def get_target_home_directory(self) -> Path:
        """Ermittelt das echte Benutzerverzeichnis, auch bei Ausführung mit Root-Rechten."""
        sudo_user = os.getenv("SUDO_USER")
        if sudo_user:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        return Path.home()

    def load_configuration(self) -> dict:
        """Liest die JSON-Konfiguration mit den Alias-Definitionen ein."""
        if not self.config_file.is_file():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {self.config_file}")

        content = self.config_file.read_text(encoding="utf-8")
        return json.loads(content)

    def merge_aliases(self, target: ShellTarget) -> int:
        """Fügt fehlende Aliase idempotent in die Zieldatei ein und gibt die Anzahl hinzugefügter Zeilen zurück."""
        if not target.file_path.exists():
            return 0

        try:
            current_content = target.file_path.read_text(encoding="utf-8")
        except OSError as error:
            print(f"[FEHLER] Datei konnte nicht gelesen werden ({target.file_path}): {error}")
            return 0

        missing_entries = [alias for alias in target.aliases if alias not in current_content]
        if not missing_entries:
            print(f"[INFO] Alle Aliase in {target.file_path.name} bereits vorhanden.")
            return 0

        lines_to_append: List[str] = []
        header_marker = "# private aliase"
        if header_marker not in current_content:
            lines_to_append.append(header_marker)
        lines_to_append.extend(missing_entries)

        try:
            with target.file_path.open("a", encoding="utf-8") as file_handle:
                file_handle.write("\n" + "\n".join(lines_to_append) + "\n")
            print(f"[INFO] {len(missing_entries)} Alias(e) in {target.file_path.name} ergänzt.")
            return len(missing_entries)
        except OSError as error:
            print(f"[FEHLER] Datei konnte nicht geschrieben werden ({target.file_path}): {error}")
            return 0

    def apply_aliases(self) -> bool:
        """Liest die Konfiguration und wendet die Aliase auf alle verfügbaren Shells an."""
        try:
            config_data = self.load_configuration()
        except Exception as error:
            print(f"[FEHLER] Fehler beim Laden der Konfiguration: {error}")
            return False

        home_dir = self.get_target_home_directory()
        posix_list = config_data.get("posix_aliases", [])
        fish_list = config_data.get("fish_aliases", [])

        targets = [
            ShellTarget(file_path=home_dir / ".bashrc", aliases=posix_list),
            ShellTarget(file_path=home_dir / ".zshrc", aliases=posix_list),
            ShellTarget(file_path=home_dir / ".config" / "fish" / "config.fish", aliases=fish_list),
        ]

        total_added = 0
        for target in targets:
            total_added += self.merge_aliases(target)

        print(f"[INFO] Shell-Konfiguration abgeschlossen. Insgesamt {total_added} neue Aliase eingetragen.")
        return True


def main() -> None:
    """Haupteinstiegspunkt für die eigenständige Ausführung."""
    configurator = ShellConfigurator()
    success = configurator.apply_aliases()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
