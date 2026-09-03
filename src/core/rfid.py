"""
RFID-Karten-Verwaltung fuer Tonuino
Unterstuetzt ACR122U NFC/RFID-Lesegeraet
"""

import struct
from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum


@dataclass
class RFIDCard:
    """Repraesentiert eine RFID-Karte"""
    uid: str
    card_type: str = ""
    atr: str = ""

    @property
    def uid_bytes(self) -> bytes:
        """Gibt die UID als Bytes zurueck"""
        return bytes.fromhex(self.uid)


@dataclass
class TonuinoCardData:
    """Repraesentiert die auf einer Karte gespeicherten Tonuino-Einstellungen"""
    folder: int
    mode: int
    special: int = 0
    special2: int = 0

    @property
    def is_admin(self) -> bool:
        """True, wenn es sich um eine Admin-Karte handelt (mode == admin_card, folder == 0)"""
        return self.mode == 0xFF


class CardType(Enum):
    """Unterstuetzte Kartentypen (entspricht den PICC-Typen aus TonUINO-TNG/chip_card.cpp:
    MIFARE_MINI, MIFARE_1K, MIFARE_4K, MIFARE_UL)"""
    MIFARE_MINI = "MIFARE Mini"
    MIFARE_CLASSIC_1K = "MIFARE Classic 1K"
    MIFARE_CLASSIC_4K = "MIFARE Classic 4K"
    MIFARE_ULTRALIGHT = "MIFARE Ultralight / NTAG"
    UNKNOWN = "Unbekannt"


class RFIDReader:
    """ACR122U RFID-Leser Interface"""
    
    # ACR122U APDU Commands
    CMD_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    CMD_READ_BLOCK = [0xFF, 0xB0, 0x00]
    CMD_WRITE_BLOCK = [0xFF, 0xD6, 0x00]
    CMD_AUTH_KEY_A = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00]
    CMD_LOAD_KEY = [0xFF, 0x82, 0x00, 0x00, 0x06]
    
    # Standard Keys
    DEFAULT_KEY_A = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    NDEF_KEY_A = [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5]
    MAD_KEY_A = [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5]
    
    def __init__(self):
        self._context = None
        self._card = None
        self._hresult = None
        self._reader_available = False
        self._direct_mode = False
        self._scard_available = self._check_scard()
    
    def _check_scard(self) -> bool:
        """Prueft ob pyscard verfuegbar ist"""
        try:
            import smartcard
            return True
        except ImportError:
            return False
    
    @property
    def is_available(self) -> bool:
        """Gibt zurueck ob der Reader verfuegbar ist"""
        return self._scard_available and self._reader_available
    
    @property
    def scard_available(self) -> bool:
        """Gibt zurueck ob pyscard verfuegbar ist"""
        return self._scard_available
    
    def get_readers(self) -> List[str]:
        """Gibt alle verfuegbaren Reader zurueck"""
        if not self._scard_available:
            return []
        
        try:
            from smartcard.System import readers
            return [str(r) for r in readers()]
        except Exception:
            return []
    
    def connect(self, reader_index: int = 0) -> bool:
        """Verbindet mit dem RFID-Reader (Reader-Bereitschaft, auch ohne Karte)"""
        if not self._scard_available:
            return False
        
        try:
            from smartcard.System import readers
            from smartcard.scard import SCARD_SHARE_DIRECT, SCARD_SHARE_SHARED
            
            reader_list = readers()
            if reader_index >= len(reader_list):
                return False
            
            self._reader = reader_list[reader_index]
            self._card = self._reader.createConnection()
            
            # Versuche zuerst mit SCARD_SHARE_SHARED (benötigt Karte für Kommunikation)
            try:
                self._card.connect(mode=SCARD_SHARE_SHARED)
                self._reader_available = True
                return True
            except Exception as e:
                error_str = str(e).lower()
                if "removed" in error_str or "no card" in error_str or "0x80100069" in error_str:
                    # Keine Karte aufgelegt - versuche Reader mit SCARD_SHARE_DIRECT zu aktivieren
                    try:
                        self._card.connect(mode=SCARD_SHARE_DIRECT)
                        self._reader_available = True
                        self._direct_mode = True
                        return True
                    except Exception:
                        self._reader_available = True
                        return True
                print(f"Verbindungsfehler: {e}")
                self._reader_available = False
                return False
            
        except Exception as e:
            print(f"Verbindungsfehler: {e}")
            self._reader_available = False
            return False
    
    def disconnect(self):
        """Trennt die Verbindung zum Reader"""
        if self._card:
            try:
                from smartcard.scard import SCARD_UNPOWER_CARD
                self._card.disconnect(SCARD_UNPOWER_CARD)
            except Exception:
                pass
        self._card = None
        self._reader_available = False

    def is_reader_present(self) -> bool:
        """Prueft ob der verbundene Reader noch physisch vorhanden ist (z.B. nicht
        per USB abgezogen wurde) - unabhaengig davon, ob gerade eine Karte aufliegt.
        Im Gegensatz zu is_card_present(), das nur Kommunikationsfehler mit einer
        (fehlenden) Karte behandelt, fragt dies den aktuellen PC/SC-Reader-Status
        direkt beim Betriebssystem ab."""
        if not self._reader_available or not getattr(self, '_reader', None):
            return False
        return str(self._reader) in self.get_readers()
    
    def is_card_present(self) -> bool:
        """Prueft ob eine Karte auf dem Reader liegt.

        Stellt bei jedem Aufruf die Verbindung selbst wieder her, falls die
        Kommunikation fehlschlaegt (z.B. weil eine Karte entfernt wurde) -
        damit eine anschliessend neu aufgelegte Karte automatisch erkannt
        wird, ohne dass der Reader manuell neu verbunden werden muss.
        """
        if not self._reader_available or not self._card:
            return False

        try:
            response, sw1, sw2 = self._transmit(self.CMD_GET_UID)
            if sw1 == 0x90 and sw2 == 0x00:
                self._direct_mode = False
                return True
            return False
        except Exception:
            pass

        # Kommunikation fehlgeschlagen (z.B. Karte entfernt, oder wir sind noch
        # im DIRECT-Modus ohne Karte) - Verbindung neu aufbauen und erneut pruefen
        try:
            from smartcard.scard import SCARD_SHARE_SHARED, SCARD_SHARE_DIRECT
        except ImportError:
            return False

        try:
            self._card.disconnect()
        except Exception:
            pass

        try:
            self._card.connect(mode=SCARD_SHARE_SHARED)
            self._direct_mode = False
            response, sw1, sw2 = self._transmit(self.CMD_GET_UID)
            return sw1 == 0x90 and sw2 == 0x00
        except Exception:
            # Immer noch keine Karte - Reader im DIRECT-Modus "warm" halten,
            # damit der naechste is_card_present()-Aufruf wieder sauber greift
            try:
                self._card.connect(mode=SCARD_SHARE_DIRECT)
                self._direct_mode = True
            except Exception:
                pass
            return False
    
    def _get_status(self):
        """Holt den Status des Readers"""
        from smartcard.scard import (
            SCardEstablishContext, SCARD_SCOPE_USER,
            SCardListReaders, SCardGetStatusChange,
            SCARD_STATE_UNAWARE
        )
        
        if not self._context:
            hresult, self._context = SCardEstablishContext(SCARD_SCOPE_USER)
        
        if hresult != 0:
            return hresult, None, [], []
        
        hresult, readers = SCardListReaders(self._context, [])
        
        if hresult != 0 or not readers:
            return hresult, self._context, readers, []
        
        reader_states = []
        for reader in readers:
            reader_states.append((reader, SCARD_STATE_UNAWARE))
        
        hresult, new_states = SCardGetStatusChange(
            self._context, 100, reader_states
        )
        
        return hresult, self._context, readers, new_states
    
    def wait_for_card(self, timeout_ms: int = 5000) -> bool:
        """Wartet auf eine Karte"""
        if not self._reader_available:
            return False
        
        try:
            from smartcard.scard import (
                SCardGetStatusChange, SCARD_STATE_PRESENT
            )
            
            import time
            start_time = time.time()
            
            while (time.time() - start_time) * 1000 < timeout_ms:
                if self.is_card_present():
                    return True
                time.sleep(0.1)
            
            return False
            
        except Exception:
            return False

    def get_card_uid(self) -> Optional[str]:
        """Liest die UID einer Karte"""
        if not self._reader_available:
            return None
        
        try:
            from smartcard.util import toHexString
            
            response, sw1, sw2 = self._transmit(self.CMD_GET_UID)
            
            if sw1 == 0x90 and sw2 == 0x00:
                # response ist eine Liste von Bytes
                uid = "".join(f"{b:02X}" for b in response)
                return uid
            
            return None
            
        except Exception as e:
            print(f"Fehler beim Lesen der UID: {e}")
            return None
    
    def get_card_atr(self) -> Optional[str]:
        """Liest die ATR (Answer To Reset) einer Karte"""
        if not self._card:
            return None
        
        try:
            from smartcard.util import toHexString
            atr = self._card.getATR()
            return toHexString(atr).replace(" ", "")
        except Exception:
            return None
    
    # PC/SC Part 3 Supplement: Historische Bytes kontaktloser Speicherkarten enthalten
    # die Registered-Application-Provider-ID A0 00 00 03 06 (PC/SC Workgroup) gefolgt vom
    # Standard-Byte 03 (ISO/IEC 14443 A, Teil 3) und "00" + Card-Name-Byte, z.B.:
    # ...A0 00 00 03 06 03 00 01... = MIFARE Classic 1K, ...00 02... = 4K, ...00 03... = Ultralight/NTAG
    _ATR_CARDNAME_MARKER = "A0000003060300"
    _ATR_CARDNAME_MAP = {
        "01": CardType.MIFARE_CLASSIC_1K,
        "02": CardType.MIFARE_CLASSIC_4K,
        "03": CardType.MIFARE_ULTRALIGHT,  # deckt auch NTAG213/215/216 ab (identische PC/SC-Kennung)
        "26": CardType.MIFARE_MINI,
    }

    def detect_card_type(self) -> CardType:
        """Erkennt den Kartentyp anhand der ATR (Card-Name-Byte, PC/SC Part 3)"""
        atr = self.get_card_atr()
        if not atr:
            return CardType.UNKNOWN

        atr = atr.upper()
        idx = atr.find(self._ATR_CARDNAME_MARKER)
        if idx != -1:
            name_byte = atr[idx + len(self._ATR_CARDNAME_MARKER):idx + len(self._ATR_CARDNAME_MARKER) + 2]
            if name_byte in self._ATR_CARDNAME_MAP:
                return self._ATR_CARDNAME_MAP[name_byte]

        return CardType.UNKNOWN

    def is_classic_card(self, card_type: CardType) -> bool:
        """MIFARE-Classic-Familie: sektorbasiert, benoetigt Schluessel-Authentifizierung"""
        return card_type in (CardType.MIFARE_MINI, CardType.MIFARE_CLASSIC_1K, CardType.MIFARE_CLASSIC_4K)
    
    def _transmit(self, apdu: List[int]) -> Tuple[List[int], int, int]:
        """Sendet ein APDU zum Reader"""
        # pyscard erwartet Liste oder String
        data, sw1, sw2 = self._card.transmit(list(apdu))
        return list(data), sw1, sw2
    
    def read_block(self, block: int, key: List[int] = None) -> Optional[bytes]:
        """Liest einen Datenblock von der Karte"""
        if not self._reader_available:
            return None
        
        try:
            if key:
                if not self._authenticate(block, key):
                    return None
            
            cmd = self.CMD_READ_BLOCK + [block, 0x10]
            response, sw1, sw2 = self._transmit(cmd)
            
            if sw1 == 0x90 and sw2 == 0x00:
                return bytes(response)
            
            return None
            
        except Exception as e:
            print(f"Fehler beim Lesen von Block {block}: {e}")
            return None
    
    def write_block(self, block: int, data: bytes, key: List[int] = None) -> bool:
        """Schreibt einen Datenblock auf die Karte"""
        if not self._reader_available:
            return False
        
        if len(data) != 16:
            raise ValueError("Daten muessen genau 16 Bytes sein")
        
        try:
            if key:
                if not self._authenticate(block, key):
                    return False
            
            cmd = self.CMD_WRITE_BLOCK + [block, 0x10] + list(data)
            response, sw1, sw2 = self._transmit(cmd)
            
            return sw1 == 0x90 and sw2 == 0x00
            
        except Exception as e:
            print(f"Fehler beim Schreiben von Block {block}: {e}")
            return False
    
    KEY_TYPE_A = 0x60
    KEY_TYPE_B = 0x61

    def _authenticate(self, block: int, key: List[int], key_type: int = KEY_TYPE_A) -> bool:
        """Authentifiziert sich an einem Block (Standard PC/SC Pseudo-APDU, siehe ACR122U API)"""
        try:
            # Key in den Volatile-Speicher des Readers laden (Slot 0)
            # FF 82 00 00 06 [6-Byte Key]
            load_cmd = [0xFF, 0x82, 0x00, 0x00, 0x06] + list(key)
            response, sw1, sw2 = self._transmit(load_cmd)

            if sw1 != 0x90 or sw2 != 0x00:
                return False

            # General Authenticate: FF 86 00 00 05 01 00 [Block] [KeyType] [KeySlot]
            auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, key_type, 0x00]
            response, sw1, sw2 = self._transmit(auth_cmd)

            return sw1 == 0x90 and sw2 == 0x00

        except Exception as e:
            print(f"Authentifizierungsfehler: {e}")
            return False

    def _write_ntag_page(self, page: int, data: List[int]) -> bool:
        """Schreibt 4 Bytes auf eine Ultralight/NTAG-Seite (Page), ohne Authentifizierung"""
        if not self._reader_available or not self._card:
            return False

        if len(data) != 4:
            raise ValueError("Page muss genau 4 Bytes enthalten")

        try:
            # Update Binary (Ultralight/NTAG Page-Write): FF D2 00 [Page] 00 [4 Bytes Data]
            cmd = [0xFF, 0xD2, 0x00, page, 0x00] + data
            response, sw1, sw2 = self._transmit(cmd)

            if sw1 == 0x90 and sw2 == 0x00:
                return True

            print(f"Ultralight/NTAG Write auf Page {page} fehlgeschlagen: SW1={hex(sw1)}, SW2={hex(sw2)}")
            return False

        except Exception as e:
            print(f"Fehler beim Schreiben der Page {page}: {e}")
            return False

    def _read_ntag_page(self, page: int) -> Optional[List[int]]:
        """Liest 4 Bytes von einer Ultralight/NTAG-Seite (Page), ohne Authentifizierung"""
        if not self._reader_available or not self._card:
            return None

        try:
            # Read Binary (Ultralight/NTAG Page-Read): FF B0 00 [Page] 00 04
            cmd = [0xFF, 0xB0, 0x00, page, 0x00, 0x04]
            response, sw1, sw2 = self._transmit(cmd)

            if sw1 == 0x90 and sw2 == 0x00 and response:
                return list(response)

            return None

        except Exception:
            return None

    def _write_ultralight_block(self, start_page: int, data: bytes) -> bool:
        """Schreibt einen 16-Byte-Block als 4 Ultralight/NTAG-Pages (je 4 Bytes)"""
        for i in range(4):
            chunk = list(data[i * 4:i * 4 + 4])
            if not self._write_ntag_page(start_page + i, chunk):
                return False
        return True

    def _read_ultralight_block(self, start_page: int) -> Optional[bytes]:
        """Liest einen 16-Byte-Block aus 4 Ultralight/NTAG-Pages (je 4 Bytes)"""
        result: List[int] = []
        for i in range(4):
            page_data = self._read_ntag_page(start_page + i)
            if page_data is None:
                return None
            result.extend(page_data)
        return bytes(result)

    # Original TonUINO-Kartenformat (siehe tonuino/TonUINO-TNG, src/constants.hpp
    # und src/chip_card.cpp): 4-Byte Cookie, gefolgt von Version/Folder/Mode/Special/Special2.
    # MIFARE Classic (Mini/1K/4K): Block 4 (Sektor 1, Block 0), mit Key-A-Authentifizierung.
    # MIFARE Ultralight/NTAG21x: Pages 8-11 (wie in TonUINO-TNG chip_card.cpp), ohne Authentifizierung.
    TONUINO_COOKIE = [0x13, 0x37, 0xB3, 0x47]
    TONUINO_VERSION = 0x01
    TONUINO_CLASSIC_BLOCK = 4
    TONUINO_ULTRALIGHT_START_PAGE = 8

    # Eine Admin-Karte ist keinem Ordner zugeordnet (folder=0) und traegt den
    # reservierten Mode-Wert admin_card=0xFF (siehe chip_card.hpp: pmode_t), statt
    # eines der regulaeren Wiedergabemodi 1-5.
    ADMIN_CARD_MODE = 0xFF

    def _build_tonuino_block(self, folder_index: int, mode: int, special: int, special2: int) -> bytes:
        # 4 (Cookie) + 5 (Version/Folder/Mode/Special/Special2) + 7 (Padding) = 16 Bytes
        return bytes(
            self.TONUINO_COOKIE
            + [self.TONUINO_VERSION, folder_index, mode, special, special2]
            + [0x00] * 7
        )

    def _write_tonuino_block(self, block_data: bytes, key: List[int] = None) -> bool:
        """Schreibt einen fertigen 16-Byte Tonuino-Block, passend zum erkannten Kartentyp"""
        if not self._reader_available:
            return False

        card_type = self.detect_card_type()

        try:
            if self.is_classic_card(card_type):
                return self.write_block(self.TONUINO_CLASSIC_BLOCK, block_data, key or self.DEFAULT_KEY_A)

            if card_type == CardType.MIFARE_ULTRALIGHT:
                return self._write_ultralight_block(self.TONUINO_ULTRALIGHT_START_PAGE, block_data)

            # Unbekannter Kartentyp (z.B. ATR nicht erkannt): MIFARE Classic zuerst versuchen -
            # die Authentifizierung schlaegt auf anderen Kartentypen sauber fehl (kein Risiko),
            # danach Ultralight/NTAG als zweite Moeglichkeit.
            if self.write_block(self.TONUINO_CLASSIC_BLOCK, block_data, key or self.DEFAULT_KEY_A):
                return True
            return self._write_ultralight_block(self.TONUINO_ULTRALIGHT_START_PAGE, block_data)

        except Exception as e:
            print(f"Fehler beim Schreiben der Tonuino-Karte: {e}")
            return False

    def write_tonuino_card(
        self,
        folder_index: int,
        mode: int = 2,
        special: int = 0,
        special2: int = 0,
        key: List[int] = None
    ) -> bool:
        """Schreibt eine Tonuino-Kartenkonfiguration fuer einen Ordner, passend zum erkannten Kartentyp"""
        if folder_index < 1 or folder_index > 99:
            raise ValueError("Folder-Index muss zwischen 1 und 99 liegen")

        if mode < 1 or mode > 255:
            raise ValueError("Mode muss zwischen 1 und 255 liegen")

        block_data = self._build_tonuino_block(folder_index, mode, special, special2)
        return self._write_tonuino_block(block_data, key)

    def write_admin_card(self, key: List[int] = None) -> bool:
        """Programmiert eine TonUINO-Admin-Karte (folder=0, mode=admin_card)"""
        block_data = self._build_tonuino_block(0, self.ADMIN_CARD_MODE, 0, 0)
        return self._write_tonuino_block(block_data, key)

    def read_tonuino_card(self, key: List[int] = None) -> Optional[TonuinoCardData]:
        """Liest die Tonuino-Kartenkonfiguration, passend zum erkannten Kartentyp"""
        if not self._reader_available:
            return None

        card_type = self.detect_card_type()

        try:
            if self.is_classic_card(card_type):
                data = self.read_block(self.TONUINO_CLASSIC_BLOCK, key or self.DEFAULT_KEY_A)
            elif card_type == CardType.MIFARE_ULTRALIGHT:
                data = self._read_ultralight_block(self.TONUINO_ULTRALIGHT_START_PAGE)
            else:
                data = self.read_block(self.TONUINO_CLASSIC_BLOCK, key or self.DEFAULT_KEY_A)
                if not data:
                    data = self._read_ultralight_block(self.TONUINO_ULTRALIGHT_START_PAGE)

            if data and len(data) >= 9 and list(data[0:4]) == self.TONUINO_COOKIE:
                return TonuinoCardData(
                    folder=data[5],
                    mode=data[6],
                    special=data[7],
                    special2=data[8]
                )
            return None

        except Exception as e:
            print(f"Fehler beim Lesen der Tonuino-Karte: {e}")
            return None
    
    def format_card(self, key: List[int] = None) -> bool:
        """Formattiert eine Karte"""
        if not self._reader_available:
            return False
        
        try:
            empty_block = bytes(16)
            for block in range(0, 64):
                if block % 4 == 3:
                    continue
                if not self.write_block(block, empty_block, key):
                    return False
            return True
            
        except Exception as e:
            print(f"Fehler beim Formattieren: {e}")
            return False
