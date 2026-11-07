from pathlib import Path
import shutil
import subprocess
import pytest
from converters.video_converter import convert, info

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools are not installed")


def test_mp4_to_gif(tmp_path: Path):
    source = tmp_path / "sample.mp4"
    result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=0.4", "-pix_fmt", "yuv420p", str(source)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip("This FFmpeg build does not include a sample video encoder")
    assert info(source)["streams"]
    output = convert(source, "gif", tmp_path / "out", timeout=30)
    assert output.is_file() and output.stat().st_size > 0
