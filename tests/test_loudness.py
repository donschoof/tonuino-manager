import subprocess

import pytest

from core import loudness
from core.audio_converter import AudioConverter

LOUDNORM_STDERR = """
[Parsed_loudnorm_0 @ 000001]
{
	"input_i" : "-28.25",
	"input_tp" : "-24.49",
	"input_lra" : "0.00",
	"input_thresh" : "-38.25",
	"output_i" : "-16.52",
	"target_offset" : "0.52"
}
"""


def test_parse_loudnorm_output():
    result = loudness.parse_loudnorm_output(LOUDNORM_STDERR)
    assert result.integrated == -28.25
    assert result.true_peak == -24.49


def test_parse_loudnorm_output_silence_is_not_measurable():
    result = loudness.parse_loudnorm_output('{"input_i": "-inf", "input_tp": "-inf"}')
    assert result.integrated is None


def test_parse_loudnorm_output_without_json_raises():
    with pytest.raises(ValueError):
        loudness.parse_loudnorm_output("no json here")


def test_gain_for_returns_difference_to_target():
    assert loudness.gain_for(loudness.LoudnessResult(integrated=-28.0)) == 12.0
    assert loudness.gain_for(loudness.LoudnessResult(integrated=-10.0)) == -6.0


def test_gain_for_skips_tracks_within_tolerance_and_silence():
    assert loudness.gain_for(loudness.LoudnessResult(integrated=-16.4)) is None
    assert loudness.gain_for(loudness.LoudnessResult(integrated=-15.2)) is None
    assert loudness.gain_for(loudness.LoudnessResult(integrated=None)) is None


def test_limiter_level_matches_true_peak_setting():
    assert loudness.limiter_level(-6.0) == pytest.approx(0.501, abs=0.001)
    assert 0.8 < loudness.limiter_level() < 0.9


def test_pick_bitrate_never_lowers_quality_and_defaults_to_192():
    assert loudness.pick_bitrate_kbps(None) == 192
    assert loudness.pick_bitrate_kbps(128000) == 128
    assert loudness.pick_bitrate_kbps(130000) == 160
    assert loudness.pick_bitrate_kbps(320000) == 320
    assert loudness.pick_bitrate_kbps(500000) == 320


@pytest.fixture(scope="module")
def converter():
    c = AudioConverter()
    if not c.is_available:
        pytest.skip("FFmpeg nicht verfuegbar")
    return c


def make_tone(converter, path, volume_db):
    subprocess.run(
        [converter.ffmpeg_path, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-af", f"volume={volume_db}dB", "-metadata", "title=Testtrack",
         "-codec:a", "libmp3lame", "-b:a", "128k", str(path)],
        capture_output=True, check=True,
    )


def test_apply_gain_reaches_target_and_keeps_tags(converter, tmp_path):
    from mutagen.easyid3 import EasyID3

    source = tmp_path / "001.mp3"
    out = tmp_path / "out.mp3"
    make_tone(converter, source, -30)

    measured = converter.measure_loudness(str(source))
    gain = loudness.gain_for(measured)
    assert gain is not None and gain > 0

    converter.apply_gain(str(source), str(out), gain, 128)

    after = converter.measure_loudness(str(out))
    assert after.integrated == pytest.approx(loudness.TARGET_LUFS, abs=loudness.TOLERANCE_LU)
    assert EasyID3(str(out))["title"] == ["Testtrack"]
    # ein zweiter Durchlauf waere ueberfluessig
    assert loudness.gain_for(after) is None
