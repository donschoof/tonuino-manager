"""
Lautstaerke-Angleichung (Normalisierung) fuer Tonuino-Tracks.

Gemessen wird die integrierte Lautheit (LUFS, EBU R128) mit FFmpegs
loudnorm-Filter im Analysemodus. Angeglichen wird je Track mit einer festen
Verstaerkung (Zielwert minus Messwert) - nicht mit loudnorm im Dynamikmodus,
das die Lautstaerke innerhalb eines Tracks veraendern wuerde. Das Neu-Kodieren
ist noetig, weil der TonUINO (DFPlayer) ReplayGain-Tags ignoriert.

Diese Datei enthaelt nur die reine Logik (Konstanten, Auswertung, Rechnung);
die FFmpeg-Aufrufe stehen im AudioConverter.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Optional

# Ziel-Lautheit: ueblich fuer Sprache/Musik auf kleinen Lautsprechern
TARGET_LUFS = -16.0
# Abweichungen darunter lohnen das verlustbehaftete Neu-Kodieren nicht
TOLERANCE_LU = 1.0
# Spitzenpegel-Grenze nach der Verstaerkung (dBFS), schuetzt vor Uebersteuern
TRUE_PEAK_DB = -1.5

_STANDARD_BITRATES_KBPS = [96, 112, 128, 160, 192, 224, 256, 320]


@dataclass
class LoudnessResult:
    """Messergebnis eines Tracks"""
    integrated: Optional[float]  # LUFS; None bei Stille/nicht messbar
    true_peak: Optional[float] = None  # dBTP


def _to_float(value) -> Optional[float]:
    """Wandelt einen loudnorm-Wert ("-23.4", "-inf") in eine Zahl; None, wenn unbrauchbar"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_loudnorm_output(stderr: str) -> LoudnessResult:
    """Liest das JSON am Ende der FFmpeg-Ausgabe (loudnorm print_format=json)"""
    blocks = re.findall(r"\{[^{}]*\}", stderr)
    if not blocks:
        raise ValueError("Keine Lautheits-Messwerte in der FFmpeg-Ausgabe gefunden")
    data = json.loads(blocks[-1])
    return LoudnessResult(
        integrated=_to_float(data.get("input_i")),
        true_peak=_to_float(data.get("input_tp")),
    )


def gain_for(result: LoudnessResult, target: float = TARGET_LUFS,
             tolerance: float = TOLERANCE_LU) -> Optional[float]:
    """Noetige Verstaerkung in dB, um den Zielwert zu erreichen. None, wenn nichts
    zu tun ist (Track liegt schon innerhalb der Toleranz) oder nicht messbar ist."""
    if result.integrated is None:
        return None
    gain = target - result.integrated
    if abs(gain) <= tolerance:
        return None
    return round(gain, 1)


def limiter_level(true_peak_db: float = TRUE_PEAK_DB) -> float:
    """Lineare Grenze fuer FFmpegs alimiter (z.B. -1.5 dBFS -> 0.84)"""
    return 10 ** (true_peak_db / 20)


def pick_bitrate_kbps(source_bps: Optional[int]) -> int:
    """Kleinste Standard-Bitrate (kbit/s), die die Quelle nicht verschlechtert;
    192, wenn die Quell-Bitrate unbekannt ist"""
    if not source_bps:
        return 192
    kbps = source_bps / 1000
    for candidate in _STANDARD_BITRATES_KBPS:
        if candidate >= kbps - 1:
            return candidate
    return _STANDARD_BITRATES_KBPS[-1]
