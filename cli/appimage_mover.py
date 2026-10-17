#!/usr/bin/env python3
""" Bereinigt heruntergeladene AppImage-Dateien in ~/Downloads, entfernt Versionssuffixe,
verschiebt sie nach ~/software und setzt Ausführungsrechte (chmod 0o755).
"""

import os
import re
import shutil
from pathlib import Path
from typing import List


class AppImageMover:
    """Verwaltet das Suchen, Bereinigen und Verschieben von AppImage-Dateien."""

    def __init__(
        self,
        downloads_dir: Path | None = None,
        target_dir: Path | None = None,
    ) -> None:
        """Initialisiert Quell- und Zielverzeichnis für AppImages."""
        self.downloads_dir: Path = downloads_dir or (Path.home() / "Downloads")
        self.target_dir: Path = target_dir or (Path.home() / "software")

    @staticmethod
    def clean_filename(filename: str) -> str:
        """Entfernt Versionsnummern und Trennzeichen vor der Dateiendung .AppImage."""
        sBuffy: str = filename.replace(".AppImage", "")
        # Trennt beim ersten Auftreten von '-', '.' oder '_', dem direkt eine Ziffer folgt
        parts: List[str] = re.split(r"[-._](?=\d)", sBuffy, maxsplit=1)
        clean_base: str = parts[0] if parts and parts[0] else sBuffy
        return f"{clean_base}.AppImage"

    def run(self) -> int:
        """Sucht alle AppImages im Download-Ordner, benennt sie um und verschiebt sie."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        found_files: List[Path] = sorted(self.downloads_dir.glob("*.AppImage"))

        if not found_files:
            print("Keine .AppImage-Dateien in ~/Downloads gefunden.")
            return 0

        iBuffy: int = 0
        for source_file in found_files:
            clean_name: str = self.clean_filename(source_file.name)
            destination_path: Path = self.target_dir / clean_name

            print(f"Benenne um: '{source_file.name}' -> '{clean_name}'")
            shutil.move(str(source_file), str(destination_path))
            os.chmod(destination_path, 0o755)
            print(f"Bereitgestellt unter: {destination_path}")
            iBuffy += 1

        print(f"Fertig: {iBuffy} AppImage-Datei(en) verschoben.")
        return iBuffy


def main() -> None:
    """Einstiegspunkt für die Kommandozeilenausführung."""
    print("--- AppImage Mover startet ---")
    mover = AppImageMover()
    mover.run()
    print("--- Vorgang abgeschlossen ---")


if __name__ == "__main__":
    main()
