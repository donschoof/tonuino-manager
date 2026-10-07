from core import updater


def test_parse_version():
    assert updater.parse_version("v1.4.0") == (1, 4, 0)
    assert updater.parse_version("garbage") == (0, 0, 0)


def test_is_newer_version():
    assert updater.is_newer_version("v1.10.0", "1.9.9")
    assert not updater.is_newer_version("v1.4.0", "1.4.0")


def test_select_asset_windows(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    assets = [
        {"name": "Tonuino-Manager-1.5.0-portable.exe"},
        {"name": "Tonuino-Manager-1.5.0-Setup.exe"},
    ]
    assert updater.select_asset(assets)["name"].endswith("-Setup.exe")
