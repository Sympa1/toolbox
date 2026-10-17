#!/usr/bin/env python3
# ==============================================================================
# KDE Plasma Wallpaper Changer (Daemon & systemd-Benutzerdienst)
# Zweck: Autonomer Hintergrund-Daemon und systemd-Benutzerdienst für KDE Plasma 6,
#        der das Wallpaper anhand von IP-Standort und Sonnenstand automatisch alle 5 Minuten
#        prüft und direkt bei der Benutzeranmeldung sofort aktualisiert.
# ==============================================================================

import argparse
import configparser
import json
import logging
import math
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


class DayPeriod(Enum):
    """
    Repräsentiert die vier definierten Tagesabschnitte für die Wallpaper-Auswahl.
    """
    MORNING = "morning"
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"


@dataclass(frozen=True)
class LocationCoordinates:
    """
    Kapselt geografische Koordinaten und optionale Ortsangaben.
    """
    latitude: float
    longitude: float
    city: Optional[str] = None
    country: Optional[str] = None


@dataclass(frozen=True)
class SolarTimes:
    """
    Hält die berechneten Zeitpunkte für Sonnenaufgang und Sonnenuntergang in lokaler Zeitzone.
    """
    sunrise: datetime
    sunset: datetime


@dataclass(frozen=True)
class ScheduleOffsets:
    """
    Definiert die Vor- und Nachlaufzeiten in Minuten relativ zum Sonnenstand.
    """
    morning_before_sunrise_minutes: int
    morning_after_sunrise_minutes: int
    evening_before_sunset_minutes: int
    evening_after_sunset_minutes: int


@dataclass(frozen=True)
class DaySchedule:
    """
    Definiert die exakten Zeitgrenzen der vier Tagesabschnitte für den aktuellen Tag.
    """
    morning_start: datetime
    morning_end: datetime
    evening_start: datetime
    evening_end: datetime


class WallpaperServiceConfig:
    """
    Liest, validiert und kapselt die Einstellungen aus der Konfigurationsdatei.
    """

    def __init__(self, config_file_path: Path) -> None:
        """
        Initialisiert die Konfiguration und liest die INI-Datei ein.

        :param config_file_path: Pfad zur INI-Konfigurationsdatei.
        """
        self.config_path = config_file_path.expanduser().resolve()
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {self.config_path}")

        self._parser = configparser.ConfigParser()
        self._parser.read(self.config_path, encoding="utf-8")

    def get_wallpaper_path(self, period: DayPeriod) -> Path:
        """
        Gibt den aufgelösten Dateipfad des Wallpapers für den jeweiligen Tagesabschnitt zurück.

        :param period: Der gewünschte Tagesabschnitt.
        :return: Vollständiger Dateipfad zum Hintergrundbild.
        """
        raw_path = self._parser.get("wallpapers", period.value, fallback="")
        if not raw_path:
            raise ValueError(f"Kein Pfad für Wallpaper '{period.value}' konfiguriert.")
        return Path(raw_path).expanduser().resolve()

    def get_schedule_offsets(self) -> ScheduleOffsets:
        """
        Liest die konfigurierten Zeit-Offsets in Minuten aus der Konfigurationsdatei.

        :return: Datenobjekt mit den definierten Zeit-Offsets.
        """
        return ScheduleOffsets(
            morning_before_sunrise_minutes=self._parser.getint("offsets", "morning_before_sunrise_minutes", fallback=30),
            morning_after_sunrise_minutes=self._parser.getint("offsets", "morning_after_sunrise_minutes", fallback=60),
            evening_before_sunset_minutes=self._parser.getint("offsets", "evening_before_sunset_minutes", fallback=60),
            evening_after_sunset_minutes=self._parser.getint("offsets", "evening_after_sunset_minutes", fallback=30),
        )

    def is_auto_ip_enabled(self) -> bool:
        """
        Prüft, ob die automatische IP-Standortbestimmung aktiv ist.

        :return: True, falls IP-Ortung aktiviert ist.
        """
        return self._parser.getboolean("location", "auto_ip", fallback=True)

    def get_cache_ttl_hours(self) -> int:
        """
        Gibt die Cache-Gültigkeit für Standortdaten in Stunden zurück.

        :return: Gültigkeitsdauer in Stunden.
        """
        return self._parser.getint("location", "cache_ttl_hours", fallback=24)

    def get_fallback_coordinates(self) -> LocationCoordinates:
        """
        Gibt die konfigurierten Notfall-Koordinaten zurück.

        :return: Notfall-Koordinatenobjekt.
        """
        return LocationCoordinates(
            latitude=self._parser.getfloat("location", "fallback_latitude", fallback=0.0),
            longitude=self._parser.getfloat("location", "fallback_longitude", fallback=0.0),
            city=self._parser.get("location", "fallback_city", fallback="ExampleCity"),
            country=self._parser.get("location", "fallback_country", fallback="ExampleCountry"),
        )

    def get_check_interval_seconds(self) -> int:
        """
        Gibt das Prüfintervall der Hintergrundschleife in Sekunden zurück (Standard: 300s = 5 Min).

        :return: Intervall in Sekunden.
        """
        return self._parser.getint("general", "check_interval_seconds", fallback=300)

    def get_log_level(self) -> str:
        """
        Gibt das konfigurierte Logging-Level zurück.

        :return: String-Repräsentation des Logging-Levels.
        """
        return self._parser.get("general", "log_level", fallback="INFO").upper()


class LocationProvider:
    """
    Ermittelt geografische Koordinaten über die externe IP mit Dateicache und Fallback.
    """

    PRIMARY_API_URL = "http://ip-api.com/json/"
    SECONDARY_API_URL = "https://freeipapi.com/api/json"

    def __init__(self, cache_file_path: Path, cache_ttl_hours: int, fallback_coords: LocationCoordinates) -> None:
        """
        Initialisiert den Standortanbieter mit Cache-Pfad und Fallback-Koordinaten.

        :param cache_file_path: Pfad zur lokalen JSON-Cache-Datei.
        :param cache_ttl_hours: Maximale Gültigkeit des Caches in Stunden.
        :param fallback_coords: Notfallkoordinaten bei Verbindungsausfall.
        """
        self.cache_file_path = cache_file_path
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.fallback_coordinates = fallback_coords
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_coordinates(self, auto_ip_enabled: bool = True) -> LocationCoordinates:
        """
        Beschafft die Standortkoordinaten (Cache -> Online-API -> Fallback).

        :param auto_ip_enabled: Gibt an, ob Online-Abfragen durchgeführt werden dürfen.
        :return: Gefundene oder Notfall-Standortdaten.
        """
        if not auto_ip_enabled:
            self.logger.info("Auto-IP deaktiviert, nutze Fallback-Koordinaten.")
            return self.fallback_coordinates

        cached_location = self._load_from_cache()
        if cached_location is not None:
            self.logger.debug("Gültige Standortdaten aus dem lokalen Cache geladen.")
            return cached_location

        online_location = self._fetch_from_apis()
        if online_location is not None:
            self._save_to_cache(online_location)
            return online_location

        self.logger.warning("Standort konnte online nicht ermittelt werden. Verwende Fallback-Koordinaten.")
        return self.fallback_coordinates

    def _load_from_cache(self) -> Optional[LocationCoordinates]:
        """
        Liest den Standort aus der Cache-Datei, sofern diese existiert und nicht veraltet ist.

        :return: Geladene Koordinaten oder None bei Ablauf/Fehler.
        """
        if not self.cache_file_path.is_file():
            return None

        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)

            cached_timestamp = datetime.fromisoformat(data["timestamp"])
            now = datetime.now(timezone.utc)

            # Prüfen, ob der Cache noch innerhalb der erlaubten Lebensdauer liegt
            if now - cached_timestamp < self.cache_ttl:
                return LocationCoordinates(
                    latitude=float(data["latitude"]),
                    longitude=float(data["longitude"]),
                    city=data.get("city"),
                    country=data.get("country"),
                )
            self.logger.debug("Lokaler Standort-Cache ist abgelaufen.")
        except Exception as error:
            # Bei unlesbarem Cache still ignorieren und neu anfragen
            self.logger.debug("Cache konnte nicht gelesen werden: %s", error)

        return None

    def _save_to_cache(self, coordinates: LocationCoordinates) -> None:
        """
        Speichert aktuelle Koordinaten mit Zeitstempel in der lokalen Cache-Datei.

        :param coordinates: Zu speichernde Standortdaten.
        """
        try:
            self.cache_file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "city": coordinates.city,
                "country": coordinates.country,
            }
            with open(self.cache_file_path, "w", encoding="utf-8") as file_handle:
                json.dump(payload, file_handle, indent=2)
            self.logger.debug("Standort erfolgreich im Cache abgelegt.")
        except OSError as error:
            self.logger.warning("Cache-Datei konnte nicht geschrieben werden: %s", error)

    def _fetch_from_apis(self) -> Optional[LocationCoordinates]:
        """
        Fragt nacheinander die primäre und sekundäre Geolocation-API ab.

        :return: Ermittelte Koordinaten oder None bei Fehlschlag.
        """
        # Primäre Abfrage über ip-api.com
        try:
            req = urllib.request.Request(self.PRIMARY_API_URL, headers={"User-Agent": "KdeWallpaperChanger/1.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                if result.get("status") == "success":
                    return LocationCoordinates(
                        latitude=float(result["lat"]),
                        longitude=float(result["lon"]),
                        city=result.get("city"),
                        country=result.get("country"),
                    )
        except Exception as error:
            self.logger.debug("Primäre IP-API fehlgeschlagen: %s", error)

        # Sekundäre Abfrage über freeipapi.com
        try:
            req = urllib.request.Request(self.SECONDARY_API_URL, headers={"User-Agent": "KdeWallpaperChanger/1.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "latitude" in result and "longitude" in result:
                    return LocationCoordinates(
                        latitude=float(result["latitude"]),
                        longitude=float(result["longitude"]),
                        city=result.get("cityName"),
                        country=result.get("countryName"),
                    )
        except Exception as error:
            self.logger.debug("Sekundäre IP-API fehlgeschlagen: %s", error)

        return None


class SolarCalculator:
    """
    Berechnet Sonnenauf- und -untergangszeiten nach dem astronomischen Standard-Algorithmus der NOAA.
    Funktioniert komplett ohne externe Bibliotheken über reine Trigonometrie.
    """

    OFFICIAL_ZENITH_DEGREES = 90.833333  # Standard-Zenithwinkel inklusive 34' Refraktion und 16' Sonnenradius

    def calculate_solar_times(self, coordinates: LocationCoordinates, date: Optional[datetime] = None) -> SolarTimes:
        """
        Berechnet Auf- und Untergangszeiten für einen bestimmten Tag in der lokalen Systemzeitzone.

        :param coordinates: Geografische Koordinaten des Standorts.
        :param date: Referenztag (Standard: heute).
        :return: SolarTimes-Objekt mit lokalen Auf- und Untergangszeiten.
        """
        reference_date = date or datetime.now()
        julian_century = self._calculate_julian_century(reference_date.year, reference_date.month, reference_date.day)
        declination, equation_of_time = self._calculate_sun_geometry(julian_century)

        # Wahrer Sonnenmittag in UTC (Minuten ab 00:00 UTC)
        solar_noon_utc_minutes = 720.0 - (4.0 * coordinates.longitude) - equation_of_time

        # Stundenwinkel (Hour Angle) für den Aufgang/Untergang berechnen
        lat_rad = math.radians(coordinates.latitude)
        declin_rad = math.radians(declination)
        zenith_rad = math.radians(self.OFFICIAL_ZENITH_DEGREES)

        cos_hour_angle = (math.cos(zenith_rad) - math.sin(lat_rad) * math.sin(declin_rad)) / (
            math.cos(lat_rad) * math.cos(declin_rad)
        )

        # Grenzfälle bei Polartag oder Polarnacht abfangen
        if cos_hour_angle > 1.0:
            # Polarnacht: Sonne geht nicht auf
            hour_angle_degrees = 0.0
        elif cos_hour_angle < -1.0:
            # Polartag: Sonne geht nicht unter
            hour_angle_degrees = 180.0
        else:
            hour_angle_degrees = math.degrees(math.acos(cos_hour_angle))

        # Aufgangs- und Untergangsminuten in UTC
        sunrise_minutes_utc = solar_noon_utc_minutes - (4.0 * hour_angle_degrees)
        sunset_minutes_utc = solar_noon_utc_minutes + (4.0 * hour_angle_degrees)

        base_utc = datetime(reference_date.year, reference_date.month, reference_date.day, tzinfo=timezone.utc)
        sunrise_utc = base_utc + timedelta(minutes=sunrise_minutes_utc)
        sunset_utc = base_utc + timedelta(minutes=sunset_minutes_utc)

        # Automatische Umwandlung in die lokale Zeitzone des Systems (beachtet Sommer-/Winterzeit)
        local_timezone = datetime.now().astimezone().tzinfo
        return SolarTimes(
            sunrise=sunrise_utc.astimezone(local_timezone),
            sunset=sunset_utc.astimezone(local_timezone),
        )

    def _calculate_julian_century(self, year: int, month: int, day: int) -> float:
        """
        Berechnet das Julianische Jahrhundert bezogen auf die Epoche J2000.0.

        :param year: Kalenderjahr.
        :param month: Monat (1-12).
        :param day: Tag des Monats.
        :return: Julianisches Jahrhundert als Float.
        """
        if month <= 2:
            year -= 1
            month += 12
        a_val = math.floor(year / 100)
        b_val = 2 - a_val + math.floor(a_val / 4)
        julian_day = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b_val - 1524.5
        return (julian_day - 2451545.0) / 36525.0

    def _calculate_sun_geometry(self, julian_century: float) -> Tuple[float, float]:
        """
        Ermittelt die Sonnendeklination in Grad und die Zeitgleichung (Equation of Time) in Minuten.

        :param julian_century: Julianisches Jahrhundert.
        :return: Tupel aus (Deklination in Grad, Zeitgleichung in Minuten).
        """
        t = julian_century
        geom_mean_long_sun = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
        geom_mean_anom_sun = 357.52911 + t * (35999.05029 - 0.0001537 * t)
        eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

        anom_rad = math.radians(geom_mean_anom_sun)
        equation_of_center = (
            math.sin(anom_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
            + math.sin(2.0 * anom_rad) * (0.019993 - 0.000101 * t)
            + math.sin(3.0 * anom_rad) * 0.000289
        )

        true_longitude = geom_mean_long_sun + equation_of_center
        apparent_longitude = true_longitude - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t))

        mean_obliquity = 23.0 + (26.0 + ((21.448 - t * (46.815 + t * (0.00059 - t * 0.001813)))) / 60.0) / 60.0
        corrected_obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * t))

        sin_declination = math.sin(math.radians(corrected_obliquity)) * math.sin(math.radians(apparent_longitude))
        declination = math.degrees(math.asin(sin_declination))

        var_y = math.tan(math.radians(corrected_obliquity / 2.0)) ** 2
        long_rad = math.radians(geom_mean_long_sun)
        equation_of_time = 4.0 * math.degrees(
            var_y * math.sin(2.0 * long_rad)
            - 2.0 * eccentricity * math.sin(anom_rad)
            + 4.0 * eccentricity * var_y * math.sin(anom_rad) * math.cos(2.0 * long_rad)
            - 0.5 * var_y * var_y * math.sin(4.0 * long_rad)
            - 1.25 * eccentricity * eccentricity * math.sin(2.0 * anom_rad)
        )

        return declination, equation_of_time


class DayScheduleClassifier:
    """
    Unterteilt den Tag anhand von Sonnenzeiten und Offsets in die vier Tagesabschnitte.
    """

    def calculate_schedule(self, solar_times: SolarTimes, offsets: ScheduleOffsets) -> DaySchedule:
        """
        Berechnet die genauen Start- und Endzeitpunkte der Abschnitte.

        :param solar_times: Sonnenauf- und -untergangszeiten.
        :param offsets: Konfigurierte Zeitdifferenzen in Minuten.
        :return: DaySchedule mit den Intervallgrenzen.
        """
        # Morgens beginnt X Minuten vor Aufgang und endet Y Minuten nach Aufgang
        morning_start = solar_times.sunrise - timedelta(minutes=offsets.morning_before_sunrise_minutes)
        morning_end = solar_times.sunrise + timedelta(minutes=offsets.morning_after_sunrise_minutes)

        # Abends beginnt X Minuten vor Untergang und endet Y Minuten nach Untergang
        evening_start = solar_times.sunset - timedelta(minutes=offsets.evening_before_sunset_minutes)
        evening_end = solar_times.sunset + timedelta(minutes=offsets.evening_after_sunset_minutes)

        return DaySchedule(
            morning_start=morning_start,
            morning_end=morning_end,
            evening_start=evening_start,
            evening_end=evening_end,
        )

    def determine_period(self, current_time: datetime, schedule: DaySchedule) -> DayPeriod:
        """
        Ordnet einen gegebenen Zeitstempel dem passenden Tagesabschnitt zu.

        :param current_time: Zu prüfender Zeitstempel.
        :param schedule: Gültiger Zeitplan für den Tag.
        :return: Zugehöriger DayPeriod-Wert.
        """
        if schedule.morning_start <= current_time < schedule.morning_end:
            return DayPeriod.MORNING
        if schedule.morning_end <= current_time < schedule.evening_start:
            return DayPeriod.DAY
        if schedule.evening_start <= current_time < schedule.evening_end:
            return DayPeriod.EVENING

        # Außerhalb von Morgen, Tag und Abend ist definitionsgemäß Nacht
        return DayPeriod.NIGHT


class PlasmaWallpaperDetector:
    """
    Ermittelt das aktuell in KDE Plasma konfigurierte Hintergrundbild
    durch Auswertung der Konfigurationsdatei 'plasma-org.kde.plasma.desktop-appletsrc'.
    """

    def __init__(self, config_file_path: Optional[Path] = None) -> None:
        """
        Initialisiert den Detektor mit dem Pfad zur Plasma-Konfigurationsdatei.

        :param config_file_path: Optionaler Pfad zur desktop-appletsrc (Standard: ~/.config/...).
        """
        self.config_file_path = (
            config_file_path.expanduser().resolve()
            if config_file_path
            else Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_active_wallpaper_paths(self) -> list[Path]:
        """
        Liest alle konfigurierten Hintergrundbilder der Desktop-Containments aus der Plasma-Konfiguration.

        :return: Liste der ermittelten Bildpfade.
        """
        if not self.config_file_path.is_file():
            self.logger.debug("Plasma-Konfigurationsdatei existiert nicht: %s", self.config_file_path)
            return []

        wallpaper_paths: list[Path] = []
        try:
            current_section = ""
            with open(self.config_file_path, "r", encoding="utf-8", errors="replace") as file_handle:
                for raw_line in file_handle:
                    line = raw_line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line
                        continue

                    # Nur Abschnitte für Desktop-Wallpaper-Bilder analysieren
                    if (
                        current_section.startswith("[Containments][")
                        and "[Wallpaper]" in current_section
                        and current_section.endswith("[General]")
                    ):
                        if line.startswith("Image="):
                            raw_image_value = line[len("Image="):].strip()
                            resolved_path = self._normalize_wallpaper_entry(raw_image_value)
                            if resolved_path is not None:
                                wallpaper_paths.append(resolved_path)
        except OSError as error:
            self.logger.warning("Konnte Plasma-Konfiguration nicht lesen: %s", error)
            return []

        return wallpaper_paths

    def _normalize_wallpaper_entry(self, raw_entry: str) -> Optional[Path]:
        """
        Bereinigt URL-Präfixe und Sonderzeichen aus dem Bildpfad.

        :param raw_entry: Roher Pfad- oder URL-String aus der Konfigurationsdatei.
        :return: Normalisierter Dateipfad oder None bei leerem Eintrag.
        """
        cleaned = raw_entry.strip()
        if not cleaned:
            return None

        # Entfernt file://-Schema, das KDE Plasma typischerweise voranstellt
        if cleaned.startswith("file://"):
            cleaned = cleaned[7:]

        cleaned = urllib.parse.unquote(cleaned)
        try:
            return Path(cleaned).expanduser().resolve()
        except Exception:
            return Path(cleaned)

    def is_wallpaper_active(self, target_image_path: Path) -> Optional[bool]:
        """
        Prüft, ob das angegebene Wallpaper auf allen Desktops in KDE Plasma aktiv ist.

        :param target_image_path: Erwarteter Pfad des Ziel-Wallpapers.
        :return: True, wenn auf allen Bildschirmen aktiv; False, wenn abweichend; None bei Lesefehler oder fehlender Datei.
        """
        active_paths = self.get_active_wallpaper_paths()
        if not active_paths:
            return None

        resolved_target = target_image_path.expanduser().resolve()
        # Prüfen, ob alle gefundenen Bildschirme das Zielbild anzeigen
        return all(active_path == resolved_target for active_path in active_paths)


class KdeWallpaperApplier:
    """
    Setzt das Hintergrundbild in KDE Plasma über das offizielle CLI-Werkzeug.
    Verhindert unnötiges Bildschirmflackern durch Abgleich mit dem Live-Zustand in KDE Plasma.
    """

    COMMAND_NAME = "plasma-apply-wallpaperimage"

    def __init__(
        self,
        state_file_path: Path,
        detector: Optional[PlasmaWallpaperDetector] = None,
    ) -> None:
        """
        Initialisiert den Wallpaper-Applier mit dem Pfad zur Statusdatei und optionalem Detektor.

        :param state_file_path: Datei zum Zwischenspeichern des aktuell gesetzten Bildes.
        :param detector: Optionaler Detektor für Live-Zustandsabfragen aus KDE Plasma.
        """
        self.state_file_path = state_file_path
        self.detector = detector or PlasmaWallpaperDetector()
        self.logger = logging.getLogger(self.__class__.__name__)

    def apply_wallpaper(self, image_path: Path, force: bool = False) -> bool:
        """
        Setzt das angegebene Bild als Wallpaper, falls es sich geändert hat oder force aktiv ist.

        :param image_path: Absoluter Pfad zur Bilddatei.
        :param force: Erzwingt das Setzen auch bei unverändertem Pfad.
        :return: True bei erfolgreicher Ausführung, False bei Fehler oder Abbruch.
        """
        if not image_path.is_file():
            self.logger.error("Wallpaper-Datei existiert nicht: %s", image_path)
            return False

        if not force:
            # Primäre Live-Prüfung gegen die tatsächliche KDE Plasma Konfiguration
            is_active_in_plasma = self.detector.is_wallpaper_active(image_path)
            if is_active_in_plasma is True:
                self.logger.info("Wallpaper unverändert in KDE Plasma aktiv (%s). Überspringe Wechsel.", image_path.name)
                return True
            elif is_active_in_plasma is None:
                # Sekundärer Fallback über die lokale Statusdatei, falls Plasma-Config nicht lesbar ist
                last_applied_wallpaper = self._get_last_applied_wallpaper()
                if last_applied_wallpaper == str(image_path):
                    self.logger.info("Wallpaper unverändert aktiv (%s) [Cache-Fallback]. Überspringe Wechsel.", image_path.name)
                    return True

        self.logger.info("Aktualisiere KDE Wallpaper auf: %s", image_path)
        try:
            subprocess.run(
                [self.COMMAND_NAME, str(image_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self._save_last_applied_wallpaper(str(image_path))
            self.logger.info("Wallpaper erfolgreich geändert.")
            return True
        except FileNotFoundError:
            self.logger.error("Das Werkzeug '%s' wurde nicht im Systempfad gefunden.", self.COMMAND_NAME)
            return False
        except subprocess.CalledProcessError as error:
            self.logger.error("Fehler beim Ausführen von '%s': %s", self.COMMAND_NAME, error.stderr.strip())
            return False

    def _get_last_applied_wallpaper(self) -> Optional[str]:
        """
        Liest den Pfad des zuletzt gesetzten Wallpapers aus der Statusdatei.

        :return: Pfad als String oder None.
        """
        if self.state_file_path.is_file():
            try:
                return self.state_file_path.read_text(encoding="utf-8").strip()
            except OSError as error:
                self.logger.debug("Statusdatei konnte nicht gelesen werden: %s", error)
        return None

    def _save_last_applied_wallpaper(self, image_path_str: str) -> None:
        """
        Speichert den Pfad des neu gesetzten Wallpapers in der Statusdatei.

        :param image_path_str: Bildpfad als String.
        """
        try:
            self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_file_path.write_text(image_path_str, encoding="utf-8")
        except OSError as error:
            self.logger.warning("Statusdatei konnte nicht aktualisiert werden: %s", error)


class WallpaperManager:
    """
    Fassade / Orchestrator: Koordiniert Konfiguration, Standort, Berechnung, Bildwechsel
    und den Lebenszyklus des Hintergrunddienstes.
    """

    def __init__(self, config_file: Optional[Path] = None) -> None:
        """
        Initialisiert den Manager mit allen benötigten Subsystemen.

        :param config_file: Optionaler Pfad zur Konfigurationsdatei.
        """
        default_config = Path(__file__).parent / "wallpaper_config.ini"
        self.config = WallpaperServiceConfig(config_file or default_config)

        self._setup_logging(self.config.get_log_level())
        self.logger = logging.getLogger(self.__class__.__name__)

        cache_directory = Path.home() / ".cache" / "wallpaper-changer"
        cache_directory.mkdir(parents=True, exist_ok=True)

        self.location_provider = LocationProvider(
            cache_file_path=cache_directory / "location_cache.json",
            cache_ttl_hours=self.config.get_cache_ttl_hours(),
            fallback_coords=self.config.get_fallback_coordinates(),
        )
        self.solar_calculator = SolarCalculator()
        self.classifier = DayScheduleClassifier()
        self.applier = KdeWallpaperApplier(state_file_path=cache_directory / "last_wallpaper.txt")

        # Event zum unterbrechbaren Schlafen in der Hintergrundschleife
        self._stop_event = threading.Event()

    def _setup_logging(self, log_level_str: str) -> None:
        """
        Konfiguriert das Logging-Format und die Ausgabeschwelle.

        :param log_level_str: Name des Logging-Levels (z. B. INFO).
        """
        numeric_level = getattr(logging, log_level_str, logging.INFO)
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def print_status(self) -> None:
        """
        Gibt eine detaillierte Statusübersicht auf der Konsole aus, ohne das Wallpaper zu verändern.
        """
        coords = self.location_provider.get_coordinates(auto_ip_enabled=self.config.is_auto_ip_enabled())
        solar = self.solar_calculator.calculate_solar_times(coords)
        schedule = self.classifier.calculate_schedule(solar, self.config.get_schedule_offsets())
        now = datetime.now().astimezone()
        current_period = self.classifier.determine_period(now, schedule)
        wallpaper_path = self.config.get_wallpaper_path(current_period)

        print("=" * 60)
        print("  KDE Wallpaper Changer - Statusbericht")
        print("=" * 60)
        print(f"Aktuelle Zeit:          {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"Standort:               {coords.city or 'Unbekannt'}, {coords.country or 'Unbekannt'}")
        print(f"Koordinaten:            Breite {coords.latitude:.4f}, Länge {coords.longitude:.4f}")
        print("-" * 60)
        print(f"Sonnenaufgang:          {solar.sunrise.strftime('%H:%M:%S')}")
        print(f"Sonnenuntergang:        {solar.sunset.strftime('%H:%M:%S')}")
        print("-" * 60)
        print("Zeitplan für heute:")
        print(f"  Morgen  (morning):    {schedule.morning_start.strftime('%H:%M')} - {schedule.morning_end.strftime('%H:%M')}")
        print(f"  Tag     (day):        {schedule.morning_end.strftime('%H:%M')} - {schedule.evening_start.strftime('%H:%M')}")
        print(f"  Abend   (evening):    {schedule.evening_start.strftime('%H:%M')} - {schedule.evening_end.strftime('%H:%M')}")
        print(f"  Nacht   (night):      {schedule.evening_end.strftime('%H:%M')} - {schedule.morning_start.strftime('%H:%M')}")
        print("-" * 60)
        print(f"Aktiver Tagesabschnitt: {current_period.value.upper()}")
        print(f"Zugeordnetes Wallpaper: {wallpaper_path}")
        print(f"Datei vorhanden:        {'Ja' if wallpaper_path.is_file() else 'NEIN (Pfad ungültig!)'}")
        print("=" * 60)

    def update_wallpaper(self, force: bool = False, dry_run: bool = False) -> bool:
        """
        Führt den regulären Ablauf aus: Standort laden, Zeiten berechnen, Bild setzen.

        :param force: Erzwingt das Setzen auch bei unverändertem Wallpaper.
        :param dry_run: Führt keine Änderung an KDE durch, simuliert nur.
        :return: True bei Erfolg, False bei Fehler.
        """
        coords = self.location_provider.get_coordinates(auto_ip_enabled=self.config.is_auto_ip_enabled())
        solar = self.solar_calculator.calculate_solar_times(coords)
        schedule = self.classifier.calculate_schedule(solar, self.config.get_schedule_offsets())
        now = datetime.now().astimezone()
        period = self.classifier.determine_period(now, schedule)
        wallpaper_path = self.config.get_wallpaper_path(period)

        self.logger.info(
            "Aktueller Abschnitt: '%s' (Sonne: Auf %s, Unter %s)",
            period.value,
            solar.sunrise.strftime("%H:%M"),
            solar.sunset.strftime("%H:%M"),
        )

        if dry_run:
            self.logger.info("[Dry-Run] Würde Bild setzen: %s", wallpaper_path)
            return True

        return self.applier.apply_wallpaper(wallpaper_path, force=force)

    def test_specific_period(self, period_name: str, force: bool = True, dry_run: bool = False) -> bool:
        """
        Ermöglicht das gezielte Testen eines bestimmten Tagesabschnitts (z. B. zur Bildprüfung).

        :param period_name: Name des Abschnitts ('morning', 'day', 'evening', 'night').
        :param force: Wallpaper sofort anwenden.
        :param dry_run: Führt keine Änderung an KDE durch, simuliert nur.
        :return: True bei Erfolg.
        """
        try:
            period = DayPeriod(period_name.lower())
        except ValueError:
            valid_names = ", ".join([p.value for p in DayPeriod])
            self.logger.error("Ungültiger Abschnitt '%s'. Erlaubt sind: %s", period_name, valid_names)
            return False

        wallpaper_path = self.config.get_wallpaper_path(period)
        self.logger.info("Test-Modus aktiv: Ziel-Wallpaper für '%s' -> %s", period.value, wallpaper_path)

        if dry_run:
            self.logger.info("[Dry-Run] Würde Test-Bild setzen: %s", wallpaper_path)
            return True

        return self.applier.apply_wallpaper(wallpaper_path, force=force)

    def stop_service(self) -> None:
        """
        Signalisiert der Hintergrundschleife, dass der Dienst beendet werden soll.
        """
        self.logger.info("Beenden-Signal empfangen. Stoppe Wallpaper Dienst...")
        self._stop_event.set()

    def run_service(self, interval_seconds: Optional[int] = None, dry_run: bool = False) -> None:
        """
        Startet den Hintergrunddienst mit Dauerschleife.
        Führt sofort bei Dienststart (z. B. bei der Benutzeranmeldung) eine Prüfung durch
        und wartet danach im konfigurierten Intervall (z. B. 300 Sekunden).

        :param interval_seconds: Optionales benutzerdefiniertes Prüfintervall in Sekunden.
        :param dry_run: Simuliert die Wallpaper-Änderung ohne Ausführung.
        """
        sleep_duration = interval_seconds or self.config.get_check_interval_seconds()
        self.logger.info(
            "Starte KDE Wallpaper Dienst (Prüfintervall: %d Sekunden / %.1f Minuten)",
            sleep_duration,
            sleep_duration / 60.0,
        )

        # Signal-Handler für sauberes Beenden durch systemd registrieren
        signal.signal(signal.SIGTERM, lambda signum, frame: self.stop_service())
        signal.signal(signal.SIGINT, lambda signum, frame: self.stop_service())

        # WICHTIG: Direkt bei Anmeldung/Dienststart einmalig sofort prüfen und setzen!
        self.logger.info("Erster Prüflauf bei Dienststart (Benutzeranmeldung)...")
        try:
            self.update_wallpaper(force=False, dry_run=dry_run)
        except Exception as error:
            self.logger.error("Fehler beim ersten Prüflauf: %s", error)

        # Dauerschleife mit 5-Minuten-Timer
        while not self._stop_event.is_set():
            # Unterbrechbares Schlafen (reagiert sofort auf SIGTERM von systemd)
            if self._stop_event.wait(timeout=sleep_duration):
                break

            self.logger.debug("Regulärer periodischer Prüflauf startet...")
            try:
                self.update_wallpaper(force=False, dry_run=dry_run)
            except Exception as error:
                self.logger.error("Fehler im periodischen Prüflauf: %s", error)

        self.logger.info("KDE Wallpaper Dienst ordnungsgemäß beendet.")


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Erstellt den Kommandozeilen-Parser für die verschiedenen Ausführungsmodi.

    :return: Konfigurierter ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="KDE Plasma Wallpaper Changer – Daemon und systemd-Benutzerdienst basierend auf IP-Standort und Sonnenzeiten.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pfad zu einer benutzerdefinierten Konfigurationsdatei (Standard: wallpaper_config.ini).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Führt nur eine einzelne Prüfung durch, anstatt als dauerhafter Daemon/Hintergrunddienst zu laufen.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Zeigt aktuelle Standort- und Sonnenzeitdaten sowie den aktiven Abschnitt an.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Erzwingt das Anwenden des Hintergrundbildes, auch wenn es bereits aktiv ist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuliert den Vorgang, ohne das Hintergrundbild tatsächlich zu wechseln.",
    )
    parser.add_argument(
        "--test-period",
        choices=["morning", "day", "evening", "night"],
        help="Setzt sofort das Wallpaper für den angegebenen Tagesabschnitt (zum Testen).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Überschreibt das Prüfintervall der Hintergrundschleife in Sekunden (z. B. für Tests).",
    )
    return parser


def main() -> int:
    """
    Haupteinstiegspunkt des Skripts.

    :return: Exit-Code (0 für Erfolg, 1 für Fehler).
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        manager = WallpaperManager(config_file=args.config)

        if args.status:
            manager.print_status()
            return 0

        if args.test_period:
            success = manager.test_specific_period(args.test_period, force=True, dry_run=args.dry_run)
            return 0 if success else 1

        if args.once:
            success = manager.update_wallpaper(force=args.force, dry_run=args.dry_run)
            return 0 if success else 1

        # Standard-Modus: Dauerhafte Hintergrundschleife für den systemd-Dienst
        manager.run_service(interval_seconds=args.interval, dry_run=args.dry_run)
        return 0
    except Exception as error:
        print(f"Kritischer Fehler: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
