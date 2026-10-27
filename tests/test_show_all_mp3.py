from pathlib import Path

from core.sd_card import SDCard


LAYOUT = {
    "01": ["001.mp3", "002.mp3", "intro.mp3", "0007_Lied.mp3", "._002.mp3", "notes.txt"],
    "02": ["track.mp3"],
}


def make_card(root: Path, show_all: bool) -> SDCard:
    for folder, files in LAYOUT.items():
        (root / folder).mkdir()
        for name in files:
            (root / folder / name).write_bytes(name.encode())
    card = SDCard(str(root), show_all_mp3=show_all)
    card.scan()
    return card


def test_default_behaves_as_before(tmp_path):
    card = make_card(tmp_path, show_all=False)

    assert [t.filename for t in card.folders[1].all_tracks] == ["001.mp3", "002.mp3"]
    assert card.folders[1].extra_tracks == []
    assert card.folders[2].all_tracks == []


def test_extra_mp3s_are_listed_after_schema_tracks_and_off_schema(tmp_path):
    card = make_card(tmp_path, show_all=True)
    folder = card.folders[1]

    assert [t.filename for t in folder.tracks] == ["001.mp3", "002.mp3"]
    # Nummerierte zuerst, Dateien ohne Ziffern am Ende; Schatten-/Textdateien fehlen
    assert [t.filename for t in folder.extra_tracks] == ["0007_Lied.mp3", "intro.mp3"]
    assert [t.off_schema for t in folder.all_tracks] == [False, False, True, True]
    assert folder.track_count == 2
    assert [t.filename for t in card.folders[2].extra_tracks] == ["track.mp3"]


def test_toggle_after_scan_updates_folders(tmp_path):
    card = make_card(tmp_path, show_all=False)

    card.set_show_all_mp3(True)
    assert len(card.folders[1].extra_tracks) == 2

    card.set_show_all_mp3(False)
    assert card.folders[1].extra_tracks == []


def test_editing_never_touches_extra_files(tmp_path):
    card = make_card(tmp_path, show_all=True)
    folder = card.folders[1]

    card.delete_tracks(folder, [folder.tracks[0]])

    assert sorted(p.name for p in (tmp_path / "01").iterdir()) == [
        "._002.mp3", "0007_Lied.mp3", "001.mp3", "intro.mp3", "notes.txt"
    ]
    assert [t.filename for t in folder.extra_tracks] == ["0007_Lied.mp3", "intro.mp3"]


def test_hidden_leftovers_are_not_listed(tmp_path):
    card = make_card(tmp_path, show_all=True)
    (tmp_path / "01" / ".tmp_001.mp3").write_bytes(b"x")

    card.set_show_all_mp3(True)

    assert ".tmp_001.mp3" not in [t.filename for t in card.folders[1].extra_tracks]


def test_system_folders_unchanged_by_option(tmp_path):
    (tmp_path / "mp3").mkdir()
    (tmp_path / "mp3" / "0001.mp3").write_bytes(b"x")
    (tmp_path / "mp3" / "Intro.mp3").write_bytes(b"x")
    card = SDCard(str(tmp_path), show_all_mp3=True)
    card.scan()

    folder = card.special_folders["mp3"]
    assert [t.filename for t in folder.tracks] == ["0001.mp3", "Intro.mp3"]
    assert folder.extra_tracks == []
    assert not any(t.off_schema for t in folder.tracks)


def test_extra_tracks_can_be_deleted_without_renaming_schema_tracks(tmp_path):
    card = make_card(tmp_path, show_all=True)
    folder = card.folders[1]
    intro = next(t for t in folder.extra_tracks if t.filename == "intro.mp3")

    card.delete_tracks(folder, [intro])

    assert not (tmp_path / "01" / "intro.mp3").exists()
    assert [t.filename for t in folder.tracks] == ["001.mp3", "002.mp3"]
    assert [t.filename for t in folder.extra_tracks] == ["0007_Lied.mp3"]


def test_deleting_schema_and_extra_tracks_together(tmp_path):
    card = make_card(tmp_path, show_all=True)
    folder = card.folders[1]
    intro = next(t for t in folder.extra_tracks if t.filename == "intro.mp3")

    card.delete_tracks(folder, [folder.tracks[0], intro])

    assert [t.filename for t in folder.tracks] == ["001.mp3"]
    assert (tmp_path / "01" / "0007_Lied.mp3").exists()
    assert [t.filename for t in folder.extra_tracks] == ["0007_Lied.mp3"]
