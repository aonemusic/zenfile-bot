from pathlib import Path
import shutil
import wave
import pytest
from converters.audio_converter import convert, info

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools are not installed")


def test_wav_to_mp3(tmp_path: Path):
    source = tmp_path / "tone.wav"
    with wave.open(str(source), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 8000)
    output = convert(source, "mp3", tmp_path / "out", timeout=30)
    assert output.is_file() and output.stat().st_size > 0
    assert info(output)["format"]["duration"]
