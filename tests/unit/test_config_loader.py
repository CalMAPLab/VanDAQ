"""Tests for common.config_loader."""

import yaml

from config_loader import deep_merge, load_yaml_config, local_overlay_path


def test_local_overlay_path():
    assert local_overlay_path("/etc/foo.yaml") == "/etc/foo.local.yaml"
    assert local_overlay_path("/etc/foo.yml") == "/etc/foo.local.yml"


def test_deep_merge_nested():
    base = {"logs": {"log_dir": "/a", "level": "INFO"}, "connect_string": "sqlite:///"}
    override = {"logs": {"log_dir": "/b"}}
    assert deep_merge(base, override) == {
        "logs": {"log_dir": "/b", "level": "INFO"},
        "connect_string": "sqlite:///",
    }


def test_load_yaml_config_merges_local(tmp_path):
    base = tmp_path / "collector.yaml"
    local = tmp_path / "collector.local.yaml"
    base.write_text(yaml.dump({"connect_string": "sqlite:///", "queue": {"name": "/q"}}))
    local.write_text(yaml.dump({"connect_string": "postgresql://secret@localhost/db"}))

    loaded = load_yaml_config(str(base))
    assert loaded["connect_string"] == "postgresql://secret@localhost/db"
    assert loaded["queue"]["name"] == "/q"
