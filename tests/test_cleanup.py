from pathlib import Path
import pytest
from utils.file_manager import create_job, cleanup_job
from utils.cleanup import cleanup_stale_jobs
from utils.security import check_file_size
from utils.errors import SecurityValidationError


def test_file_size_guard(tmp_path: Path):
    item = tmp_path / "payload.bin"
    item.write_bytes(b"12345")
    assert check_file_size(item, max_bytes=5) == 5
    with pytest.raises(SecurityValidationError):
        check_file_size(item, max_bytes=4)


def test_temporary_job_cleanup(tmp_path: Path):
    job = create_job(temp_root=tmp_path)
    (job / "tmp.dat").write_text("temporary")
    cleanup_job(job)
    assert not job.exists()


def test_stale_jobs_cleanup_only_removes_old_job_directories(tmp_path: Path):
    old = tmp_path / "job_old"
    old.mkdir()
    (old / "x").write_text("x")
    unrelated = tmp_path / "keep"
    unrelated.mkdir()
    cleanup_stale_jobs(tmp_path, older_than_seconds=0)
    assert not old.exists()
    assert unrelated.exists()
