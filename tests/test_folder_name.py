"""Manuell vergebener Ordnername im ID3-Frame TXXX:TONUINO_FOLDER_NAME"""

import pytest

pytest.importorskip("mutagen")

from core.metadata import MetadataManager  # noqa: E402


@pytest.fixture
def mp3(tmp_path):
    # MPEG-1 Layer III, 128 kbit/s, 44,1 kHz: Frame = 417 Bytes
    frame = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(413)
    path = tmp_path / "001.mp3"
    path.write_bytes(frame * 8)
    return str(path)


def test_no_folder_name_by_default(mp3):
    manager = MetadataManager()
    manager.write_metadata(mp3, album="Album")
    metadata = manager.read_metadata(mp3)
    assert metadata.folder_name == ""
    assert metadata.album == "Album"


def test_folder_name_roundtrip_and_reset(mp3):
    manager = MetadataManager()
    assert manager.write_metadata(mp3, album="Album", folder_name="Mein Ordner")
    metadata = manager.read_metadata(mp3)
    assert metadata.folder_name == "Mein Ordner"
    assert metadata.album == "Album"  # Album-Tag bleibt unangetastet

    # None laesst den Frame unveraendert (z.B. beim Bearbeiten anderer Tags)
    manager.write_metadata(mp3, title="Lied")
    assert manager.read_metadata(mp3).folder_name == "Mein Ordner"

    # leerer String entfernt ihn
    manager.write_metadata(mp3, folder_name="")
    assert manager.read_metadata(mp3).folder_name == ""
