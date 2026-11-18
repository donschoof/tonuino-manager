"""Tracks mit Text nach der Nummer (001_Titel.mp3), wie sie der DFPlayer abspielt"""
from pathlib import Path

from core.sd_card import SDCard
from tests.test_sd_card import make_card, names


def filenames(folder):
    return [t.filename for t in folder.tracks]


def test_text_after_number_is_a_normal_track(tmp_path):
    card = make_card(tmp_path, {"01": ["002 b.mp3", "001_a.mp3", "003-c.MP3"]})
    folder = card.folders[1]
    assert [t.index for t in folder.tracks] == [1, 2, 3]
    assert filenames(folder) == ["001_a.mp3", "002 b.mp3", "003-c.MP3"]
    assert not any(t.off_schema for t in folder.tracks)
    assert names(tmp_path / "01") == ["001_a.mp3", "002 b.mp3", "003-c.MP3"]  # Einlesen benennt nichts um


def test_other_names_stay_off_schema(tmp_path):
    card = make_card(tmp_path, {"01": ["0007_Lied.mp3", "01 - Titel.mp3", "1_a.mp3", "intro.mp3", ".tmp_001_a.mp3",
                                       "._001_a.mp3", "001_a.txt"]})
    assert card.folders[1].tracks == []


def test_exact_name_wins_over_text_and_second_file_stays_visible(tmp_path):
    (tmp_path / "01").mkdir()
    for name in ("001 a.mp3", "001.mp3", "001_b.mp3", "002_c.mp3"):
        (tmp_path / "01" / name).write_bytes(name.encode())
    card = SDCard(str(tmp_path), show_all_mp3=True)
    card.scan()
    folder = card.folders[1]
    assert filenames(folder) == ["001.mp3", "002_c.mp3"]
    assert sorted(t.filename for t in folder.extra_tracks) == ["001 a.mp3", "001_b.mp3"]
    assert all(t.off_schema for t in folder.extra_tracks)


def test_deleting_from_the_middle_renumbers_and_keeps_content(tmp_path):
    card = make_card(tmp_path, {"01": ["001_a.mp3", "002_b.mp3", "003_c.mp3"]})
    folder = card.folders[1]
    card.delete_tracks(folder, [folder.tracks[1]])
    assert names(tmp_path / "01") == ["001.mp3", "002.mp3"]
    assert (tmp_path / "01" / "001.mp3").read_bytes() == b"001_a.mp3"
    assert (tmp_path / "01" / "002.mp3").read_bytes() == b"003_c.mp3"


def test_deleting_the_last_track_keeps_other_names(tmp_path):
    card = make_card(tmp_path, {"01": ["001_a.mp3", "002_b.mp3"]})
    folder = card.folders[1]
    card.delete_tracks(folder, [folder.tracks[1]])
    assert names(tmp_path / "01") == ["001_a.mp3"]


def test_reordering_swaps_content(tmp_path):
    card = make_card(tmp_path, {"01": ["001_a.mp3", "002_b.mp3"]})
    folder = card.folders[1]
    card.reorder_tracks(folder, [folder.tracks[1], folder.tracks[0]])
    assert (tmp_path / "01" / "001.mp3").read_bytes() == b"002_b.mp3"
    assert (tmp_path / "01" / "002.mp3").read_bytes() == b"001_a.mp3"


def test_new_track_does_not_reuse_a_number_with_text(tmp_path):
    make_card(tmp_path, {"01": ["001_a.mp3", "002.mp3", "notes.txt"]})
    assert SDCard.track_numbers_on_disk(Path(tmp_path / "01")) == {1, 2}


def test_purge_keeps_folder_and_files(tmp_path):
    card = make_card(tmp_path, {"01": ["001_a.mp3", "002_b.mp3"]})
    card.purge()
    assert names(tmp_path / "01") == ["001_a.mp3", "002_b.mp3"]
