#!/usr/bin/env python3
# ==============================================================================
# Discord Notifier Skript
# Zweck: Sendet Statusberichte an einen Discord-Kanal via Webhook.
# ==============================================================================

import sys
import json
import urllib.request
import urllib.error
import configparser
from pathlib import Path
from abc import ABC, abstractmethod

class Notifier(ABC):
    """
    Abstrakte Basisklasse (Interface) für alle Benachrichtigungsdienste.
    Erlaubt es, später einfach andere Dienste wie Telegram hinzuzufügen.
    """
    @abstractmethod
    def send_message(self, message: str) -> None:
        """
        Sendet eine Textnachricht an den konfigurierten Dienst.
        """
        pass

class DiscordNotifier(Notifier):
    """
    Klasse zur Kapselung der Discord-Webhook-API.
    """
    def __init__(self, webhook_url: str):
        """
        Initialisiert den Discord-Notifier mit der Webhook-URL.
        """
        self.webhook_url = webhook_url

    def send_message(self, message: str) -> None:
        """
        Sendet eine Nachricht an den Discord-Webhook über einen HTTP-POST-Request.
        """
        # Daten-Dictionary für Discord erstellen (Discord erwartet das JSON-Feld 'content')
        payload = {"content": message}
        
        try:
            # JSON in String umwandeln und in Bytes (UTF-8) kodieren
            json_data = json.dumps(payload).encode("utf-8")
            
            # HTTP Request vorbereiten (POST wird durch das Vorhandensein von 'data' impliziert)
            request = urllib.request.Request(
                url=self.webhook_url,
                data=json_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BackupNotifier/1.0"
                }
            )
            
            # Request absenden und Antwort empfangen
            with urllib.request.urlopen(request) as response:
                response.read()  # Antwort lesen (bei 204 No Content leer, aber schließt die Verbindung sauber)
                
        except urllib.error.HTTPError as error:
            # Fehler, die vom Server zurückgemeldet werden (z. B. 404 Webhook nicht gefunden oder 400 Bad Request)
            print(f"HTTP-Fehler beim Senden der Discord-Nachricht: {error.code} - {error.reason}", file=sys.stderr)
            raise
        except urllib.error.URLError as error:
            # Netzwerkfehler (z. B. keine Internetverbindung oder DNS-Fehler)
            print(f"Netzwerk-Fehler beim Senden der Discord-Nachricht: {error.reason}", file=sys.stderr)
            raise
        except Exception as error:
            # Alle anderen unerwarteten Fehler abfangen
            print(f"Unerwarteter Fehler beim Senden der Discord-Nachricht: {error}", file=sys.stderr)
            raise

def main() -> None:
    # Pfad zur INI-Datei relativ zum Skript bestimmen
    config_file = Path(__file__).parent / "notifier.ini"
    
    if not config_file.exists():
        print(f"Fehler: Konfigurationsdatei nicht gefunden unter: {config_file}", file=sys.stderr)
        sys.exit(1)
        
    # INI-Datei einlesen
    config = configparser.ConfigParser()
    try:
        config.read(config_file, encoding="utf-8")
        webhook_url = config.get("discord", "webhook_url", fallback=None)
    except Exception as error:
        print(f"Fehler beim Lesen der Konfigurationsdatei: {error}", file=sys.stderr)
        sys.exit(1)
        
    # Überprüfen, ob die URL konfiguriert wurde und kein Platzhalter ist
    if not webhook_url or "DEIN_WEBHOOK_TOKEN" in webhook_url:
        print("Fehler: Discord Webhook-URL ist in notifier.ini nicht oder ungültig konfiguriert!", file=sys.stderr)
        sys.exit(1)
        
    # Prüfen, ob eine Nachricht als Argument an das Skript übergeben wurde
    if len(sys.argv) < 2:
        print("Verwendung: python discord_notifier.py \"Deine Nachricht\"", file=sys.stderr)
        # Tipp: Für Zeilenumbrüche im Terminal nutze: python discord_notifier.py $'Zeile 1\nZeile 2'
        sys.exit(1)
        
    # Das erste Argument nach dem Skriptnamen als Nachricht verwenden
    # Hinweis: Um Zeilenumbrüche (\n) direkt aus dem Terminal zu senden, nutze:
    # python discord_notifier.py $'Zeile 1\nZeile 2'
    # Alternativ kannst du \n im Skript übersetzen lassen mit:
    # message = sys.argv[1].replace("\\n", "\n")
    message = sys.argv[1]
    
    # Notifier initialisieren und Nachricht senden
    notifier = DiscordNotifier(webhook_url)
    try:
        notifier.send_message(message)
        print("Nachricht erfolgreich an Discord gesendet.")
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    main()
