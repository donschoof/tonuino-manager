from pathlib import Path

import pytest

from core.sd_card import SDCard


def make_card(root: Path, layout: dict) -> SDCard:
    """layout: {"01": ["001.mp3", ...], ...} - Dateiinhalt ist der Dateiname"""
    for folder, files in layout.items():
        (root / folder).mkdir()
        for name in files:
            (root / folder / name).write_bytes(name.encode())
    card = SDCard(str(root))
    card.scan()
    return card


def names(path: Path):
    return sorted(p.name for p in path.iterdir())


def test_scan_detects_folders_and_tracks(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3"], "mp3": ["0001.mp3"], "misc": []})

    assert card.is_valid_tonuino
    assert list(card.folders) == [1]
    assert card.folders[1].track_count == 2
    assert "mp3" in card.special_folders


def test_scan_ignores_appledouble_files(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "._001.mp3"]})
    assert [t.filename for t in card.folders[1].tracks] == ["001.mp3"]


def test_reorder_tracks_swaps_files(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3", "003.mp3"]})
    folder = card.folders[1]
    first, second, third = folder.tracks

    card.reorder_tracks(folder, [third, first, second])

    assert names(tmp_path / "01") == ["001.mp3", "002.mp3", "003.mp3"]
    assert (tmp_path / "01" / "001.mp3").read_bytes() == b"003.mp3"
    assert (tmp_path / "01" / "002.mp3").read_bytes() == b"001.mp3"
    assert [t.index for t in folder.tracks] == [1, 2, 3]


def test_delete_tracks_closes_gaps(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3", "003.mp3"]})
    folder = card.folders[1]

    card.delete_tracks(folder, [folder.tracks[1]])

    assert names(tmp_path / "01") == ["001.mp3", "002.mp3"]
    assert (tmp_path / "01" / "002.mp3").read_bytes() == b"003.mp3"


def test_reorder_failure_restores_original_names(tmp_path, monkeypatch):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3", "003.mp3"]})
    folder = card.folders[1]
    tracks = list(folder.tracks)

    real_rename = Path.rename
    failed = []

    def failing_rename(self, target):
        # Zweiter Schritt (temporaer -> final) scheitert einmalig an der zweiten Datei
        if not failed and self.name.startswith(".tmp_") and Path(target).name == "002.mp3":
            failed.append(True)
            raise PermissionError("gesperrt")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing_rename)

    with pytest.raises(PermissionError):
        card.reorder_tracks(folder, [tracks[2], tracks[0], tracks[1]])

    monkeypatch.undo()
    assert names(tmp_path / "01") == ["001.mp3", "002.mp3", "003.mp3"]
    assert (tmp_path / "01" / "001.mp3").read_bytes() == b"001.mp3"
    assert (tmp_path / "01" / "003.mp3").read_bytes() == b"003.mp3"


def test_purge_removes_foreign_items_and_empty_folders(tmp_path):
    card = make_card(tmp_path, {"02": ["001.mp3", "notes.txt", "._001.mp3"], "05": [], "advert": ["0001.mp3"]})
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / "System Volume Information").mkdir()

    preview = card.preview_purge()
    assert preview.root_files == ["readme.txt"]
    assert preview.root_dirs == ["System Volume Information"]
    assert preview.foreign_items_in_folders == 2

    card.purge()

    assert names(tmp_path) == ["02", "advert"]
    assert names(tmp_path / "02") == ["001.mp3"]


def test_purge_keeps_folder_numbers_but_closes_track_gaps(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3"], "03": ["002.mp3", "005.mp3"], "07": ["001.mp3"]})

    card.purge()

    assert names(tmp_path) == ["01", "03", "07"]
    assert sorted(card.folders) == [1, 3, 7]
    assert names(tmp_path / "03") == ["001.mp3", "002.mp3"]
    assert (tmp_path / "03" / "002.mp3").read_bytes() == b"005.mp3"


def test_purge_handles_foreign_folder_named_like_a_track(tmp_path):
    card = make_card(tmp_path, {"01": ["002.mp3"]})
    (tmp_path / "01" / "001.mp3").mkdir()

    card.purge()

    assert names(tmp_path / "01") == ["001.mp3"]
    assert (tmp_path / "01" / "001.mp3").is_file()
    assert (tmp_path / "01" / "001.mp3").read_bytes() == b"002.mp3"


def test_close_track_gaps_renumbers_and_keeps_order(tmp_path):
    card = make_card(tmp_path, {"01": ["002.mp3", "005.mp3", "009.mp3"]})
    folder = card.folders[1]
    assert card.has_track_gaps(folder)

    assert card.close_track_gaps(folder) is True

    assert names(tmp_path / "01") == ["001.mp3", "002.mp3", "003.mp3"]
    assert [(tmp_path / "01" / n).read_bytes() for n in ("001.mp3", "002.mp3", "003.mp3")] == [b"002.mp3", b"005.mp3", b"009.mp3"]
    assert not card.has_track_gaps(folder)
    assert card.close_track_gaps(folder) is False


def test_close_track_gaps_does_not_rename_without_gaps(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3"]})
    folder = card.folders[1]
    mtimes = {p.name: p.stat().st_mtime_ns for p in (tmp_path / "01").iterdir()}

    assert card.close_track_gaps(folder) is False

    assert {p.name: p.stat().st_mtime_ns for p in (tmp_path / "01").iterdir()} == mtimes
    assert [t.index for t in folder.tracks] == [1, 2]


def test_delete_last_track_needs_no_renaming(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3", "002.mp3", "003.mp3"]})
    folder = card.folders[1]

    card.delete_tracks(folder, [folder.tracks[2]])

    assert names(tmp_path / "01") == ["001.mp3", "002.mp3"]
    assert [t.filename for t in folder.tracks] == ["001.mp3", "002.mp3"]


def test_special_folders_list_all_mp3_files_with_four_digit_and_alpha_names(tmp_path):
    card = make_card(tmp_path, {
        "01": ["001.mp3"],
        "mp3": ["0010_Intro.mp3", "0003.mp3", "0001.mp3", "zeta.mp3", "._0001.mp3", "notes.txt", "0100.MP3"],
        "advert": ["0002.mp3"],
    })

    mp3 = card.special_folders["mp3"]
    assert [t.filename for t in mp3.tracks] == ["0001.mp3", "0003.mp3", "0010_Intro.mp3", "0100.MP3", "zeta.mp3"]
    assert [t.number for t in mp3.tracks] == ["0001", "0003", "0010", "0100", ""]
    assert [t.index for t in mp3.tracks][:4] == [1, 3, 10, 100]
    assert card.special_folders["advert"].track_count == 1
    # normale Ordner behalten das strenge Schema
    assert card.folders[1].track_count == 1


def test_special_folder_track_display_names(tmp_path):
    card = make_card(tmp_path, {"mp3": ["0007_Intro.mp3", "zeta.mp3"]})
    intro, zeta = card.special_folders["mp3"].tracks

    assert intro.display_name == "0007_Intro.mp3"
    intro.title = "Willkommen"
    assert intro.display_name == "0007 - Willkommen"
    assert zeta.display_name == "zeta.mp3"
    zeta.title = "Ohne Nummer"
    assert zeta.display_name == "Ohne Nummer"


def test_normal_track_display_name_is_unchanged(tmp_path):
    card = make_card(tmp_path, {"01": ["002.mp3"]})
    track = card.folders[1].tracks[0]
    assert track.display_name == "002.mp3"
    track.title = "Lied"
    assert track.display_name == "002 - Lied"


def test_track_row_columns(tmp_path):
    card = make_card(tmp_path, {"01": ["002.mp3"]})
    track = card.folders[1].tracks[0]
    assert (track.number_label, track.title_label, track.album) == ("002", "002.mp3", "")
    track.title = "Lied"
    track.album = "Mein Album"
    assert (track.number_label, track.title_label, track.album) == ("002", "Lied", "Mein Album")


def test_purge_leaves_system_folder_files_untouched(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3"], "mp3": ["0001.mp3", "0007_Intro.mp3", "notes.txt"]})

    card.purge()

    assert names(tmp_path / "mp3") == ["0001.mp3", "0007_Intro.mp3"]


def test_create_folder_validates_range(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3"]})
    with pytest.raises(ValueError):
        card.create_folder(100)
    with pytest.raises(FileExistsError):
        card.create_folder(1)
