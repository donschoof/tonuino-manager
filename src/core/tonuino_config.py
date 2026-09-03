"""
Tonuino Konfigurationsdatei-Verwaltung
Liest und schreibt die tonuio.cfg Datei
"""

import configparser
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class PlayMode(Enum):
    """Wiedergabemodi für Tonuio"""
    Hörspiel = "hörspiel"          # Zufällige Wiedergabe eines Tracks
    Album = "album"                # Alle Tracks nacheinander
    Party = "party"                # Zufällige Wiedergabe aller Tracks
    Einzel = "einzel"              # Einzelnen Track wiedergeben
    Hörbuch = "hörbuch"            # Fortschritt speichern
    Admin = "admin"                # Admin-Funktionen
    Hörspiel_classic = "hörspiel_classic"  # Klassisches Hörspiel
    Album_classic = "album_classic"  # Klassisches Album
    Party_classic = "party_classic"  # Klassische Party


@dataclass
class TonuinoConfig:
    """Tonuio Konfiguration"""
    # Globale Einstellungen
    volume_max: int = 25
    volume_min: int = 5
    volume_start: int = 10
    eq_mode: int = 1  # 0=Normal, 1=Pop, 2=Rock, 3=Jazz, 4=Classic, 5=Bass
    standby_timer: int = 0  # 0=Aus, 1=5min, 2=10min, 3=15min, 4=30min, 5=60min
    button_lock: bool = False
    
    # Ordnerspezifische Einstellungen
    folder_settings: Dict[int, Dict[str, Any]] = field(default_factory=dict)


class TonuinoConfigManager:
    """Verwaltet die tonuio.cfg Datei"""
    
    def __init__(self, sd_card_path: str):
        self.sd_path = Path(sd_card_path)
        self.config_file = self.sd_path / "tonuio.cfg"
        self._config_parser = configparser.ConfigParser()
        self._config = TonuinoConfig()
    
    def load(self) -> bool:
        """Laedt die Konfiguration von der SD-Karte"""
        if not self.config_file.exists():
            return False
        
        try:
            self._config_parser.read(self.config_file, encoding='utf-8')
            self._parse_config()
            return True
        except Exception as e:
            print(f"Fehler beim Laden der Konfiguration: {e}")
            return False
    
    def save(self) -> bool:
        """Speichert die Konfiguration auf der SD-Karte"""
        try:
            self._build_config()
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self._config_parser.write(f)
            
            return True
        except Exception as e:
            print(f"Fehler beim Speichern der Konfiguration: {e}")
            return False
    
    def _parse_config(self):
        """Parst die geladene Konfiguration"""
        # Globale Einstellungen
        if 'global' in self._config_parser:
            global_section = self._config_parser['global']
            self._config.volume_max = global_section.getint('volume_max', 25)
            self._config.volume_min = global_section.getint('volume_min', 5)
            self._config.volume_start = global_section.getint('volume_start', 10)
            self._config.eq_mode = global_section.getint('eq_mode', 1)
            self._config.standby_timer = global_section.getint('standby_timer', 0)
            self._config.button_lock = global_section.getboolean('button_lock', False)
        
        # Ordnerspezifische Einstellungen
        for section in self._config_parser.sections():
            if section.startswith('folder'):
                try:
                    folder_num = int(section.replace('folder', ''))
                    folder_config = {}
                    
                    if 'mode' in self._config_parser[section]:
                        folder_config['mode'] = self._config_parser[section]['mode']
                    if 'track' in self._config_parser[section]:
                        folder_config['track'] = self._config_parser[section].getint('track', 0)
                    if 'first_track' in self._config_parser[section]:
                        folder_config['first_track'] = self._config_parser[section].getint('first_track', 1)
                    if 'last_track' in self._config_parser[section]:
                        folder_config['last_track'] = self._config_parser[section].getint('last_track', 99)
                    
                    self._config.folder_settings[folder_num] = folder_config
                except ValueError:
                    continue
    
    def _build_config(self):
        """Erstellt die Konfiguration fuer das Speichern"""
        self._config_parser.clear()
        
        # Globale Einstellungen
        self._config_parser['global'] = {
            'volume_max': str(self._config.volume_max),
            'volume_min': str(self._config.volume_min),
            'volume_start': str(self._config.volume_start),
            'eq_mode': str(self._config.eq_mode),
            'standby_timer': str(self._config.standby_timer),
            'button_lock': str(self._config.button_lock)
        }
        
        # Ordnerspezifische Einstellungen
        for folder_num, settings in self._config.folder_settings.items():
            section = f'folder{folder_num:02d}'
            self._config_parser[section] = {}
            
            if 'mode' in settings:
                self._config_parser[section]['mode'] = settings['mode']
            if 'track' in settings:
                self._config_parser[section]['track'] = str(settings['track'])
            if 'first_track' in settings:
                self._config_parser[section]['first_track'] = str(settings['first_track'])
            if 'last_track' in settings:
                self._config_parser[section]['last_track'] = str(settings['last_track'])
    
    @property
    def config(self) -> TonuinoConfig:
        """Gibt die aktuelle Konfiguration zurück"""
        return self._config
    
    def get_folder_mode(self, folder_index: int) -> Optional[str]:
        """Gibt den Wiedergabemodus für einen Ordner zurück"""
        if folder_index in self._config.folder_settings:
            return self._config.folder_settings[folder_index].get('mode')
        return None
    
    def set_folder_mode(self, folder_index: int, mode: str):
        """Setzt den Wiedergabemodus für einen Ordner"""
        if folder_index not in self._config.folder_settings:
            self._config.folder_settings[folder_index] = {}
        self._config.folder_settings[folder_index]['mode'] = mode
    
    def set_folder_track_range(self, folder_index: int, first_track: int, last_track: int):
        """Setzt den Track-Bereich für einen Ordner"""
        if folder_index not in self._config.folder_settings:
            self._config.folder_settings[folder_index] = {}
        self._config.folder_settings[folder_index]['first_track'] = first_track
        self._config.folder_settings[folder_index]['last_track'] = last_track
    
    def remove_folder_settings(self, folder_index: int):
        """Entfernt die Einstellungen für einen Ordner"""
        if folder_index in self._config.folder_settings:
            del self._config.folder_settings[folder_index]
    
    def create_default_config(self) -> bool:
        """Erstellt eine Standard-Konfiguration"""
        self._config = TonuinoConfig()
        return self.save()
    
    def is_config_present(self) -> bool:
        """Prüft ob eine Konfigurationsdatei vorhanden ist"""
        return self.config_file.exists()

