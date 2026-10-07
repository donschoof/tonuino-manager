import hashlib
import io
import os

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


# ---- Download-Pruefsumme -------------------------------------------------

class FakeResponse(io.BytesIO):
    def __init__(self, data, content_length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if content_length is None else content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run_download(monkeypatch, data, digest, content_length=None):
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda request, timeout=None: FakeResponse(data, content_length),
    )
    info = updater.UpdateInfo(
        version="9.9.9", release_notes="", release_url="", asset_url="https://example.invalid/x",
        asset_name="../Tonuino-Manager-9.9.9-Setup.exe", asset_size=len(data), asset_digest=digest,
    )
    downloader = updater.UpdateDownloader(info)
    done, errors = [], []
    downloader.completed.connect(done.append)
    downloader.error.connect(errors.append)
    downloader.run()  # synchron statt per start()
    return done, errors


def test_expected_sha256_parsing():
    assert updater.expected_sha256("sha256:ABCDEF") == "abcdef"
    assert updater.expected_sha256("md5:abc") == ""
    assert updater.expected_sha256("") == ""


def test_download_with_matching_digest_succeeds(monkeypatch):
    data = b"installer-bytes"
    done, errors = run_download(monkeypatch, data, "sha256:" + hashlib.sha256(data).hexdigest())
    assert not errors and len(done) == 1
    # Nur der Dateiname zaehlt, nicht der '../'-Anteil des Asset-Namens
    assert os.path.basename(done[0]) == "Tonuino-Manager-9.9.9-Setup.exe"
    assert open(done[0], "rb").read() == data
    os.remove(done[0])
    os.rmdir(os.path.dirname(done[0]))


def test_download_with_wrong_digest_is_rejected_and_removed(monkeypatch):
    done, errors = run_download(monkeypatch, b"tampered", "sha256:" + "0" * 64)
    assert not done and errors and "Pruefsumme" in errors[0]


def test_download_without_digest_still_works(monkeypatch):
    done, errors = run_download(monkeypatch, b"data", "")
    assert len(done) == 1 and not errors
    os.remove(done[0])
    os.rmdir(os.path.dirname(done[0]))


def test_truncated_download_is_rejected(monkeypatch):
    done, errors = run_download(monkeypatch, b"abc", "", content_length=100)
    assert not done and errors and "unvollstaendig" in errors[0]
