"""Unit tests for collector helper functions."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytz
import yaml

import vandaq_collector as collector


@pytest.fixture
def minimal_collector_config(tmp_path):
    return {
        "logs": {
            "log_dir": str(tmp_path),
            "log_file": "test.log",
            "log_level": "INFO",
            "logger_name": "test",
        },
        "connect_string": "sqlite:///:memory:",
        "submissions": {
            "submit_file_timezone": "US/Pacific",
        },
    }


def test_load_config_file(tmp_path):
    cfg_path = tmp_path / "collector.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "logs": {"log_dir": str(tmp_path), "log_file": "x.log"},
                "connect_string": "sqlite:///",
            }
        )
    )
    loaded = collector.load_config_file(str(cfg_path))
    assert loaded["connect_string"] == "sqlite:///"


def test_get_time_from_submit_filename_utc(tmp_path):
    collector.config = {
        "submissions": {},
        "logs": {"log_dir": str(tmp_path)},
    }
    path = "/data/submit_van1_20250108_095052_PST_.sbm"
    result = collector.get_time_from_submit_filename(path)

    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.year == 2025
    assert result.month == 1
    assert result.day == 8
    assert result.hour == 9
    assert result.minute == 50
    assert result.second == 52


def test_get_time_from_submit_filename_with_timezone(minimal_collector_config):
    collector.config = minimal_collector_config
    path = "/data/submit_van1_20250108_095052_PST_.sbm"
    result = collector.get_time_from_submit_filename(path)

    expected = datetime(2025, 1, 8, 9, 50, 52, tzinfo=pytz.timezone("US/Pacific"))
    assert result == expected


def test_get_time_from_submit_filename_no_match(minimal_collector_config):
    collector.config = minimal_collector_config
    assert collector.get_time_from_submit_filename("/data/no_timestamp.sbm") is None


def test_get_submission_files_sorted(tmp_path, minimal_collector_config, monkeypatch):
    collector.config = minimal_collector_config
    older = tmp_path / "submit_van1_20250101_120000_PST_.sbm"
    newer = tmp_path / "submit_van1_20250108_095052_PST_.sbm"
    older.write_text("")
    newer.write_text("")

    import time

    old_time = time.time() - 100
    new_time = time.time()
    import os

    os.utime(older, (old_time, old_time))
    os.utime(newer, (new_time, new_time))

    files = collector.get_submission_files(str(tmp_path), "submit_*.sbm")
    assert len(files) == 2
    assert Path(files[0]["filename"]).name == newer.name
    assert files[0]["filetime"] > files[1]["filetime"]
