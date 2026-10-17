#!/usr/bin/env python3
"""System-Setup- und Provisioning-Werkzeug für Linux Workstations.

Richtet ein neu installiertes System automatisiert ein:
- Installation von Systempaketen über app_installer.py
- Git-Identität und sichere GitHub-SSH-Schlüsselverwaltung
- Globale CLI-Tools via npm
- Idempotente Shell-Konfiguration über shell_configurator.py
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import getpass
import json
import os
import pwd
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request


@dataclass
class ExecutionResult:
    """Protokolleintrag für einen ausgeführten Systembefehl."""

    command: List[str]
    success: bool
    return_code: int


class CommandRunner:
    """Führt Systembefehle mit oder ohne Root-Rechte aus und protokolliert die Ergebnisse."""

    def __init__(self) -> None:
        """Initialisiert die Ausführungsliste."""
        self.history: List[ExecutionResult] = []

    def get_invoking_user_name(self) -> str:
        """Ermittelt den echten Benutzernamen (beachtet SUDO_USER)."""
        return os.getenv("SUDO_USER") or os.getenv("USER") or "root"

    def get_invoking_user_home(self) -> Path:
        """Ermittelt das echte Home-Verzeichnis des aufrufenden Benutzers."""
        sudo_user = os.getenv("SUDO_USER")
        if sudo_user:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        return Path.home()

    def run(self, command: List[str], use_sudo: bool = False) -> bool:
        """Führt einen Befehl im System aus."""
        full_command = ["sudo"] + command if use_sudo else command
        print(f"\n[INFO] Führe aus: {' '.join(full_command)}")

        try:
            process = subprocess.run(full_command, check=True)
            self.history.append(ExecutionResult(command=full_command, success=True, return_code=0))
            return True
        except subprocess.CalledProcessError as error:
            print(f"[FEHLER] Befehl fehlgeschlagen: {' '.join(full_command)} (Exit-Code: {error.returncode})")
            self.history.append(ExecutionResult(command=full_command, success=False, return_code=error.returncode))
            return False

    def run_as_user(self, command: List[str]) -> bool:
        """Führt einen Befehl als regulärer Benutzer aus, selbst wenn das Skript via sudo läuft."""
        sudo_user = os.getenv("SUDO_USER")
        current_user = os.getenv("USER")

        if sudo_user and current_user == "root":
            user_command = ["sudo", "-u", sudo_user] + command
        else:
            user_command = command

        print(f"\n[INFO] Führe als Benutzer aus: {' '.join(user_command)}")
        try:
            subprocess.run(user_command, check=True)
            self.history.append(ExecutionResult(command=user_command, success=True, return_code=0))
            return True
        except subprocess.CalledProcessError as error:
            print(f"[FEHLER] Benutzerbefehl fehlgeschlagen: {' '.join(user_command)} (Exit-Code: {error.returncode})")
            self.history.append(ExecutionResult(command=user_command, success=False, return_code=error.returncode))
            return False

    def print_summary(self) -> None:
        """Gibt eine übersichtliche Zusammenfassung aller protokollierten Befehle aus."""
        total = len(self.history)
        failed = [item for item in self.history if not item.success]
        successful = total - len(failed)

        print("\n=== AUSFÜHRUNGS-LOG (ZUSAMMENFASSUNG) ===")
        print(f"Gesamtbefehle: {total}")
        print(f"Erfolgreich:   {successful}")
        print(f"Fehlgeschlagen:{len(failed)}")

        if failed:
            print("\nFehlgeschlagene Befehle:")
            for entry in failed:
                print(f"- ({entry.return_code}) {' '.join(entry.command)}")
        else:
            print("\nAlle protokollierten Befehle wurden erfolgreich ausgeführt.")


class GitHubSshManager:
    """Verwaltet die Erstellung von SSH-Schlüsseln und deren Registrierung bei GitHub."""

    def __init__(self, command_runner: CommandRunner) -> None:
        """Initialisiert den SSH-Manager mit Pfaden zu ~/.ssh/github."""
        self.runner = command_runner
        self.home_dir = self.runner.get_invoking_user_home()
        self.ssh_dir = self.home_dir / ".ssh"
        # Individueller Schlüsselname gemäß Benutzeranforderung
        self.private_key = self.ssh_dir / "github"
        self.public_key = self.ssh_dir / "github.pub"
        self.ssh_config = self.ssh_dir / "config"

    def ensure_ssh_directory(self) -> None:
        """Erstellt das .ssh-Verzeichnis mit den korrekten Rechten (0700)."""
        if not self.ssh_dir.exists():
            self.ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            os.chmod(self.ssh_dir, 0o700)

    def generate_ssh_key(self, email: str) -> bool:
        """Erzeugt einen Ed25519 SSH-Schlüssel, falls dieser noch nicht existiert."""
        self.ensure_ssh_directory()

        if self.private_key.exists():
            print(f"[INFO] SSH-Schlüssel '{self.private_key}' existiert bereits. Überspringe Neugenerierung.")
            return True

        print(f"\n[INFO] Erzeuge neuen Ed25519 SSH-Schlüssel: {self.private_key}")
        command = [
            "ssh-keygen",
            "-t", "ed25519",
            "-C", email,
            "-f", str(self.private_key),
            "-N", ""  # Ohne Passphrase fuer automatisierte Ablaeufe
        ]
        success = self.runner.run_as_user(command)
        if success and self.private_key.exists():
            os.chmod(self.private_key, 0o600)
            if self.public_key.exists():
                os.chmod(self.public_key, 0o644)
            return True
        return False

    def configure_ssh_client(self) -> None:
        """Richtet ~/.ssh/config ein, damit github.com automatisch ~/.ssh/github verwendet."""
        self.ensure_ssh_directory()
        config_block = f"\nHost github.com\n    HostName github.com\n    User git\n    IdentityFile {self.private_key}\n    IdentitiesOnly yes\n"

        existing_content = ""
        if self.ssh_config.exists():
            try:
                existing_content = self.ssh_config.read_text(encoding="utf-8")
            except OSError as error:
                print(f"[WARNUNG] Konnte ~/.ssh/config nicht lesen: {error}")

        if str(self.private_key) not in existing_content:
            try:
                with self.ssh_config.open("a", encoding="utf-8") as file_handle:
                    file_handle.write(config_block)
                os.chmod(self.ssh_config, 0o600)
                print(f"[INFO] GitHub Host-Eintrag in {self.ssh_config} ergänzt.")
            except OSError as error:
                print(f"[FEHLER] Konnte {self.ssh_config} nicht schreiben: {error}")
        else:
            print("[INFO] SSH-Konfiguration für github.com bereits vorhanden.")

    def upload_key_to_github(self, token: str) -> bool:
        """Lädt den öffentlichen Schlüssel über die GitHub REST-API hoch."""
        if not self.public_key.exists():
            print(f"[FEHLER] Öffentlicher Schlüssel '{self.public_key}' existiert nicht.")
            return False

        public_key_text = self.public_key.read_text(encoding="utf-8").strip()
        hostname = socket.gethostname()
        key_title = f"{hostname} ({datetime.now().strftime('%Y-%m-%d')})"

        api_url = "https://api.github.com/user/keys"
        payload = json.dumps({"title": key_title, "key": public_key_text}).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Setup-Script-SSH-Provisioner"
        }

        request = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request) as response:
                if response.status == 201:
                    print(f"[ERFOLG] SSH-Schlüssel erfolgreich auf GitHub als '{key_title}' hinterlegt!")
                    return True
        except urllib.error.HTTPError as http_error:
            if http_error.code == 422:
                print("[HINWEIS] Dieser SSH-Schlüssel ist bereits in deinem GitHub-Konto hinterlegt.")
                return True
            if http_error.code == 401:
                print("[FEHLER] Authentifizierung fehlgeschlagen. Token ungültig oder unzureichende Rechte.")
                return False
            print(f"[FEHLER] GitHub API-Fehler ({http_error.code}): {http_error.reason}")
            return False
        except Exception as error:
            print(f"[FEHLER] Netzwerk- oder Verbindungsfehler zur GitHub-API: {error}")
            return False

        return False

    def test_github_connection(self) -> None:
        """Prüft die SSH-Authentifizierung mit GitHub."""
        print("\n[INFO] Teste GitHub-SSH-Verbindung...")
        test_command = ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new", "git@github.com"]
        # ssh -T zu github.com beendet immer mit Exit-Code 1 ("Hi username! You've successfully authenticated..."),
        # daher pruefen wir die Textausgabe
        result = subprocess.run(test_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        output_lower = result.stdout.lower()
        if "successfully authenticated" in output_lower:
            print(f"[ERFOLG] {result.stdout.strip()}")
        else:
            print(f"[HINWEIS] Rückmeldung von GitHub:\n{result.stdout.strip()}")

    def copy_public_key_to_clipboard(self) -> bool:
        """Kopiert den öffentlichen Schlüssel in die Zwischenablage via wl-copy, xclip, xsel oder OSC 52."""
        if not self.public_key.exists():
            return False

        key_content = self.public_key.read_text(encoding="utf-8").strip()

        # Versuch 1: Wayland Clipboard via wl-copy
        if shutil.which("wl-copy"):
            try:
                subprocess.run(["wl-copy"], input=key_content, text=True, check=True)
                return True
            except Exception:
                pass

        # Versuch 2: X11 Clipboard via xclip
        if shutil.which("xclip"):
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=key_content, text=True, check=True)
                return True
            except Exception:
                pass

        # Versuch 3: X11 Clipboard via xsel
        if shutil.which("xsel"):
            try:
                subprocess.run(["xsel", "--clipboard", "--input"], input=key_content, text=True, check=True)
                return True
            except Exception:
                pass

        # Versuch 4: OSC 52 Terminal Escape Sequence (wird direkt im Terminal verarbeitet)
        try:
            import base64
            encoded = base64.b64encode(key_content.encode("utf-8")).decode("ascii")
            sys.stdout.write(f"\033]52;c;{encoded}\a")
            sys.stdout.flush()
            return True
        except Exception:
            return False

    def manual_browser_setup(self) -> None:
        """Führt den Benutzer durch das Hinterlegen des Schlüssels im Browser mit automatischer Zwischenablage."""
        if not self.public_key.exists():
            print(f"[FEHLER] Öffentlicher Schlüssel '{self.public_key}' nicht gefunden.")
            return

        key_content = self.public_key.read_text(encoding="utf-8").strip()
        copied = self.copy_public_key_to_clipboard()

        print("\n" + "=" * 70)
        print("  MANUELLE SSH-SCHLÜSSEL EINRICHTUNG FÜR GITHUB")
        print("=" * 70)

        if copied:
            print("\n[ERFOLG] Der öffentliche Schlüssel wurde automatisch in deine ZWISCHENABLAGE kopiert!")
        else:
            print("\n[INFO] Bitte markiere und kopiere den folgenden öffentlichen Schlüssel:")

        print("\nDein öffentlicher SSH-Schlüssel (~/.ssh/github.pub):")
        print("-" * 70)
        print(key_content)
        print("-" * 70)

        github_url = "https://github.com/settings/keys"
        # OSC 8 Hyperlink fuer moderne Terminals + Klartext
        clickable_link = f"\033]8;;{github_url}\033\\{github_url}\033]8;;\033\\"
        hostname = socket.gethostname()

        print("\nSCHRITT-FÜR-SCHRITT ANLEITUNG:")
        print(f"  1. Öffne GitHub im Browser: {clickable_link} (Strg + Klick)")
        print("  2. Klicke oben rechts auf den grünen Button 'New SSH key'.")
        print(f"  3. Vergib einen Titel (z. B. '{hostname}').")
        print("  4. Klicke in das Textfeld 'Key', drücke Strg + V (Einfügen) und klicke auf 'Add SSH key'.")

        input("\n>> Drücke ENTER, sobald du den Schlüssel auf GitHub gespeichert hast (oder Strg+C zum Abbrechen)...")
        self.test_github_connection()

    def setup(self, email: str) -> None:
        """Führt den gesamten Ablauf zur SSH-Einrichtung durch."""
        print("\n=== PHASE 2: GITHUB SSH ZUGANG EINRICHTEN ===")
        key_generated = self.generate_ssh_key(email)
        if not key_generated:
            print("[FEHLER] SSH-Schlüssel konnte nicht erstellt werden. Überspringe GitHub-Setup.")
            return

        self.configure_ssh_client()

        print("\nWie möchtest du den SSH-Schlüssel bei GitHub hinterlegen?")
        print("  [1] Im Browser (Schlüssel wird in Zwischenablage kopiert + direkter Link)")
        print("  [2] Automatisch per GitHub Personal Access Token (PAT)")
        user_choice = input("Deine Wahl (1/2) [Standard: 1]: ").strip()

        if user_choice == "2":
            print("\n(Benötigte Token-Berechtigung: 'admin:public_key' oder 'write:public_key' auf https://github.com/settings/tokens)")
            token_input = getpass.getpass("GitHub Personal Access Token eingeben (oder ENTER für Browser-Weg): ").strip()
            if token_input:
                upload_ok = self.upload_key_to_github(token_input)
                if upload_ok:
                    self.test_github_connection()
                    return
            print("[INFO] Wechsle zur Browser-Methode...")

        self.manual_browser_setup()


class RemoteServerSshManager:
    """Ermöglicht das Hinzufügen von Remote-Servern per eigenem SSH-Schlüssel, SSH-Config und Shell-Alias."""

    def __init__(self, command_runner: CommandRunner) -> None:
        """Initialisiert den Server-Manager mit dem Befehlsausführer."""
        self.runner = command_runner
        self.home_dir = self.runner.get_invoking_user_home()
        self.ssh_dir = self.home_dir / ".ssh"
        self.ssh_config = self.ssh_dir / "config"
        self.shell_config_file = Path(__file__).resolve().parent / "shell_config.json"

    def ensure_server_ssh_key(self, alias_name: str, host: str, user: str) -> Path:
        """Erzeugt einen dedizierten Ed25519-Schlüssel für diesen Server (~/.ssh/<alias>), falls noch nicht vorhanden."""
        self.ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        private_key = self.ssh_dir / alias_name
        public_key = self.ssh_dir / f"{alias_name}.pub"

        if private_key.exists():
            print(f"[INFO] SSH-Schlüssel '{private_key}' existiert bereits. Verwende vorhandenen Schlüssel.")
            return private_key

        print(f"\n[INFO] Erzeuge dedizierten SSH-Schlüssel für Server '{alias_name}': {private_key}")
        comment = f"{user}@{host} ({alias_name})"
        command = [
            "ssh-keygen",
            "-t", "ed25519",
            "-C", comment,
            "-f", str(private_key),
            "-N", ""
        ]
        success = self.runner.run_as_user(command)
        if success and private_key.exists():
            os.chmod(private_key, 0o600)
            if public_key.exists():
                os.chmod(public_key, 0o644)

        return private_key

    def copy_public_key_to_server(self, public_key: Path, host: str, user: str, port: int) -> bool:
        """Überträgt den öffentlichen Schlüssel auf den Remote-Server (fragt bei Bedarf nach Passwort)."""
        if not public_key.exists():
            print(f"[FEHLER] Öffentlicher Schlüssel '{public_key}' nicht gefunden.")
            return False

        print(f"\n[INFO] Übertrage SSH-Schlüssel an {user}@{host}:{port}...")

        # Prüfe ob sshpass vorhanden ist, um ein abgefragtes Passwort diskret zu übergeben
        sshpass_bin = shutil.which("sshpass")

        if sshpass_bin:
            password = getpass.getpass(f"SSH-Passwort für {user}@{host} eingeben (wird sofort danach vergessen): ")
            if not password:
                print("[INFO] Kein Passwort eingegeben. Versuche direkte Authentifizierung...")
                cmd = [
                    "ssh-copy-id",
                    "-i", str(public_key),
                    "-p", str(port),
                    "-o", "StrictHostKeyChecking=accept-new",
                    f"{user}@{host}"
                ]
                return self.runner.run_as_user(cmd)

            # Sichere, flüchtige Übergabe des Passworts via Umgebungsvariable
            temp_env = os.environ.copy()
            temp_env["SSHPASS"] = password
            cmd = [
                sshpass_bin,
                "-e",
                "ssh-copy-id",
                "-i", str(public_key),
                "-p", str(port),
                "-o", "StrictHostKeyChecking=accept-new",
                f"{user}@{host}"
            ]
            try:
                print("[INFO] Führe Schlüssel-Übertragung aus...")
                subprocess.run(cmd, env=temp_env, check=True)
                print("[ERFOLG] SSH-Schlüssel erfolgreich auf den Server übertragen!")
                return True
            except subprocess.CalledProcessError as error:
                print(f"[FEHLER] Übertragung des SSH-Schlüssels fehlgeschlagen: {error}")
                return False
            finally:
                # Passwort sofort aus Speicher und Umgebung entfernen
                del temp_env
                del password
        else:
            # Native interaktive Passwortabfrage von ssh-copy-id
            print("[INFO] Falls nötig, wird jetzt das SSH-Passwort des Servers abgefragt:")
            cmd = [
                "ssh-copy-id",
                "-i", str(public_key),
                "-p", str(port),
                "-o", "StrictHostKeyChecking=accept-new",
                f"{user}@{host}"
            ]
            return self.runner.run_as_user(cmd)

    def add_ssh_config_entry(self, alias_name: str, host: str, user: str, port: int, private_key: Path) -> bool:
        """Trägt den Host-Eintrag in ~/.ssh/config ein, damit 'ssh alias' funktioniert."""
        config_dir = self.ssh_config.parent
        config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        config_entry = (
            f"\nHost {alias_name}\n"
            f"    HostName {host}\n"
            f"    User {user}\n"
            f"    Port {port}\n"
            f"    IdentityFile {private_key}\n"
            f"    IdentitiesOnly yes\n"
        )

        existing_content = ""
        if self.ssh_config.exists():
            try:
                existing_content = self.ssh_config.read_text(encoding="utf-8")
            except OSError as error:
                print(f"[WARNUNG] Konnte {self.ssh_config} nicht lesen: {error}")

        if f"Host {alias_name}\n" in existing_content:
            print(f"[INFO] Ein Eintrag für Host '{alias_name}' existiert bereits in {self.ssh_config}.")
            return False

        try:
            with self.ssh_config.open("a", encoding="utf-8") as file_handle:
                file_handle.write(config_entry)
            os.chmod(self.ssh_config, 0o600)
            print(f"[INFO] Host-Eintrag '{alias_name}' in {self.ssh_config} eingetragen.")
            return True
        except OSError as error:
            print(f"[FEHLER] Konnte {self.ssh_config} nicht schreiben: {error}")
            return False

    def add_shell_alias(self, alias_name: str) -> None:
        """Fügt einen Direkt-Befehl (Alias) zur shell_config.json hinzu (z. B. 'srv01' -> 'ssh srv01')."""
        if not self.shell_config_file.is_file():
            return

        try:
            config_content = json.loads(self.shell_config_file.read_text(encoding="utf-8"))
            posix_alias = f'alias {alias_name}="ssh {alias_name}"'
            fish_alias = f'alias {alias_name} "ssh {alias_name}"'

            if posix_alias not in config_content.get("posix_aliases", []):
                config_content.setdefault("posix_aliases", []).append(posix_alias)

            if fish_alias not in config_content.get("fish_aliases", []):
                config_content.setdefault("fish_aliases", []).append(fish_alias)

            self.shell_config_file.write_text(json.dumps(config_content, indent=2), encoding="utf-8")
            print(f"[INFO] Shell-Alias '{alias_name}' in {self.shell_config_file.name} hinterlegt.")
        except Exception as error:
            print(f"[WARNUNG] Konnte Shell-Alias nicht in {self.shell_config_file.name} speichern: {error}")

    def prompt_add_servers(self) -> None:
        """Fragt interaktiv ab, ob und welche Server hinzugefügt werden sollen."""
        print("\n=== SERVER PER SSH & ALIAS HINZUFÜGEN ===")

        while True:
            add_choice = input("\nMöchtest du per Alias und SSH einen Server hinzufügen? (j/N): ").strip().lower()
            if add_choice not in {"j", "ja", "y", "yes"}:
                break

            alias_name = input("Name des Alias (z. B. srv01, backup-box): ").strip()
            if not alias_name:
                print("[WARNUNG] Alias-Name darf nicht leer sein. Abgebrochen.")
                continue

            host = input(f"Server IP-Adresse oder Domain für '{alias_name}': ").strip()
            if not host:
                print("[WARNUNG] Server-Adresse darf nicht leer sein. Abgebrochen.")
                continue

            default_user = self.runner.get_invoking_user_name()
            user_input = input(f"Benutzername auf dem Server [{default_user}]: ").strip()
            user = user_input if user_input else default_user

            port_input = input("SSH-Port [22]: ").strip()
            port = int(port_input) if port_input.isdigit() else 22

            # 1. Dedizierten SSH-Schlüssel für diesen Server erzeugen (~/.ssh/<alias_name>)
            private_key = self.ensure_server_ssh_key(alias_name=alias_name, host=host, user=user)
            public_key = Path(f"{private_key}.pub")

            # 2. Public Key an den Server übertragen
            key_copied = self.copy_public_key_to_server(public_key=public_key, host=host, user=user, port=port)

            # 3. Host-Eintrag in ~/.ssh/config anlegen
            self.add_ssh_config_entry(alias_name=alias_name, host=host, user=user, port=port, private_key=private_key)

            # 4. Shell-Alias hinterlegen (damit z. B. 'srv01' direkt verbindet)
            self.add_shell_alias(alias_name=alias_name)

            # 5. Verbindung testen
            if key_copied:
                print(f"\n[INFO] Teste schlüssellose Verbindung zu '{alias_name}'...")
                test_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", alias_name, "echo 'SSH-Verbindung erfolgreich hergestellt!'"]
                test_result = subprocess.run(test_cmd, check=False)
                if test_result.returncode == 0:
                    print(f"[ERFOLG] Du kannst dich ab sofort einfach mit 'ssh {alias_name}' (oder direkt '{alias_name}') verbinden!")
                else:
                    print(f"[HINWEIS] Verbindung konnte nicht sofort verifiziert werden. Bitte manuell 'ssh {alias_name}' testen.")


class AntigravityCliInstaller:
    """Installiert die Google Antigravity CLI (agy) über das offizielle Installationsskript."""

    def __init__(self, command_runner: CommandRunner) -> None:
        """Initialisiert den Antigravity-Installer mit dem Befehlsausführer."""
        self.runner = command_runner
        self.installer_url = "https://antigravity.google/cli/install.sh"

    def install(self) -> bool:
        """Führt das offizielle Installationsskript für die Antigravity CLI aus."""
        print("\n=== PHASE 3: ANTIGRAVITY CLI INSTALLATION ===")
        home_dir = self.runner.get_invoking_user_home()
        agy_binary = home_dir / ".local" / "bin" / "agy"

        # Prüfe ob agy bereits vorhanden und ausführbar ist
        if agy_binary.is_file() and os.access(agy_binary, os.X_OK):
            print(f"[INFO] Antigravity CLI ist bereits unter '{agy_binary}' installiert.")
            choice = input("Möchtest du Antigravity CLI aktualisieren / neu installieren? (j/N): ").strip().lower()
            if choice not in {"j", "ja", "y", "yes"}:
                return True

        if not shutil.which("curl"):
            print("[FEHLER] 'curl' wird für die Installation benötigt, ist jedoch nicht verfügbar.")
            return False

        print(f"[INFO] Lade Antigravity CLI von {self.installer_url} herunter und installiere...")
        # Offizielles Shell-Skript im Benutzerkontext ausführen
        install_command = f"curl -fsSL {self.installer_url} | bash"
        success = self.runner.run_as_user(["bash", "-c", install_command])

        if success:
            print("[ERFOLG] Antigravity CLI wurde erfolgreich installiert! Aufrufbar über 'agy'.")
            return True

        print("[FEHLER] Installation der Antigravity CLI ist fehlgeschlagen.")
        return False


class SystemSetupApp:
    """Hauptanwendung zur Koordination des gesamten System-Setups."""

    def __init__(self) -> None:
        """Initialisiert alle benötigten Subsysteme."""
        self.runner = CommandRunner()
        self.ssh_manager = GitHubSshManager(command_runner=self.runner)
        self.server_manager = RemoteServerSshManager(command_runner=self.runner)
        self.antigravity_installer = AntigravityCliInstaller(command_runner=self.runner)

    def run_package_installation(self) -> None:
        """Führt die Paketinstallation über app_installer.py und workstation.applist aus."""
        print("\n=== PHASE 1: SYSTEMPAKETE VIA APP_INSTALLER ===")
        script_dir = Path(__file__).resolve().parent
        installer_script = script_dir / "app_installer.py"
        applist_file = script_dir / "applists" / "workstation.applist"

        if not installer_script.is_file():
            print(f"[FEHLER] Installer '{installer_script}' nicht gefunden.")
            return

        if not applist_file.is_file():
            print(f"[FEHLER] Definitionsdatei '{applist_file}' nicht gefunden.")
            return

        # Führt die Installation der definierten Pakete aus
        command = [sys.executable, str(installer_script), "install", str(applist_file)]
        self.runner.run(command, use_sudo=False)

    def configure_git_identity(self) -> str:
        """Fragt Git-Benutzerdaten ab und setzt globale Einstellungen."""
        print("\n=== GIT IDENTITÄT KONFIGURIEREN ===")
        while True:
            git_name = input("Git Name (user.name): ").strip()
            if git_name:
                break
            print("Name darf nicht leer sein.")

        while True:
            git_email = input("Git E-Mail (user.email): ").strip()
            if git_email:
                break
            print("E-Mail darf nicht leer sein.")

        self.runner.run_as_user(["git", "config", "--global", "user.name", git_name])
        self.runner.run_as_user(["git", "config", "--global", "user.email", git_email])
        return git_email

    def configure_shell_aliases(self) -> None:
        """Lagert die Shell-Konfiguration an shell_configurator.py aus."""
        print("\n=== PHASE 4: SHELL-ALIASE EINRICHTEN ===")
        configurator_script = Path(__file__).resolve().parent / "shell_configurator.py"

        if configurator_script.is_file():
            self.runner.run_as_user([sys.executable, str(configurator_script)])
        else:
            print(f"[FEHLER] Shell-Konfigurator '{configurator_script}' nicht gefunden.")

    def run(self) -> None:
        """Führt alle Phasen des System-Setups nacheinander aus."""
        # Phase 1: Pakete installieren
        self.run_package_installation()

        # Phase 2: Git Identity + GitHub SSH Key
        email = self.configure_git_identity()
        self.ssh_manager.setup(email=email)

        # Server per SSH & Alias hinzufügen
        self.server_manager.prompt_add_servers()

        # Phase 3: Antigravity CLI
        self.antigravity_installer.install()

        # Phase 4: Shell-Aliase über shell_configurator.py
        self.configure_shell_aliases()

        # Zusammenfassung
        self.runner.print_summary()
        print("\n=== INSTALLATION ERFOLGREICH ABGESCHLOSSEN ===")

        user_choice = input("\nMöchtest du den Rechner jetzt neu starten? (j/N): ").strip().lower()
        if user_choice in {"j", "ja", "y", "yes"}:
            self.runner.run(["reboot"], use_sudo=True)


def main() -> None:
    """Startet die Setup-Anwendung."""
    try:
        app = SystemSetupApp()
        app.run()
    except KeyboardInterrupt:
        print("\nSetup vom Benutzer abgebrochen.")
        sys.exit(1)


if __name__ == "__main__":
    main()
