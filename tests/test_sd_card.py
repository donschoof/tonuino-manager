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


def test_renumber_folders_closes_gaps(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3"], "03": ["001.mp3"], "07": ["001.mp3"]})

    card.renumber_folders()

    assert names(tmp_path) == ["01", "02", "03"]
    assert sorted(card.folders) == [1, 2, 3]


def test_purge_removes_foreign_items_and_empty_folders(tmp_path):
    card = make_card(tmp_path, {"02": ["001.mp3", "notes.txt", "._001.mp3"], "05": [], "advert": ["0001.mp3"]})
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / "System Volume Information").mkdir()

    preview = card.preview_purge()
    assert preview.root_files == ["readme.txt"]
    assert preview.root_dirs == ["System Volume Information"]
    assert preview.foreign_items_in_folders == 2

    card.purge()

    assert names(tmp_path) == ["01", "advert"]
    assert names(tmp_path / "01") == ["001.mp3"]


def test_create_folder_validates_range(tmp_path):
    card = make_card(tmp_path, {"01": ["001.mp3"]})
    with pytest.raises(ValueError):
        card.create_folder(100)
    with pytest.raises(FileExistsError):
        card.create_folder(1)
