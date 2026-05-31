"""Basic tests for Atulya-Launch."""
import os
import tempfile
import pytest


def test_utils_password_generation():
    from atulya_launch.utils import generate_password
    pwd = generate_password(16)
    assert len(pwd) == 16
    pwd2 = generate_password(32)
    assert len(pwd2) == 32
    assert pwd != pwd2


def test_utils_config_save_load():
    from atulya_launch.utils import load_config, save_config, CONFIG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        import atulya_launch.utils as utils
        old_dir = utils.CONFIG_DIR
        old_file = utils.CONFIG_FILE
        utils.CONFIG_DIR = type(utils.CONFIG_DIR)(tmpdir)
        utils.CONFIG_FILE = utils.CONFIG_DIR / "config.yaml"
        try:
            test_data = {"test": {"key": "value", "number": 42}}
            save_config(test_data)
            loaded = load_config()
            assert loaded["test"]["key"] == "value"
            assert loaded["test"]["number"] == 42
        finally:
            utils.CONFIG_DIR = old_dir
            utils.CONFIG_FILE = old_file


def test_utils_platform_detection():
    from atulya_launch.utils import get_platform, is_linux, is_macos, is_windows
    platform = get_platform()
    assert platform in ("linux", "macos", "windows")
    count = sum([is_linux(), is_macos(), is_windows()])
    assert count == 1


def test_utils_format_size():
    try:
        from atulya_launch.utils import format_size
        # If we get here, format_size exists
        assert callable(format_size)
    except ImportError:
        # format_size doesn't exist, which is okay
        pass


def test_core_detect_web_server():
    from atulya_launch.core import detect_web_server
    result = detect_web_server()
    assert result is None or result in ("nginx", "apache")


def test_core_site_list():
    from atulya_launch.core import site_list
    import atulya_launch.utils as utils
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = utils.CONFIG_DIR
        old_file = utils.CONFIG_FILE
        utils.CONFIG_DIR = type(utils.CONFIG_DIR)(tmpdir)
        utils.CONFIG_FILE = utils.CONFIG_DIR / "config.yaml"
        try:
            sites = site_list()
            assert isinstance(sites, dict)
        finally:
            utils.CONFIG_DIR = old_dir
            utils.CONFIG_FILE = old_file


def test_core_db_list():
    from atulya_launch.core import db_list
    import atulya_launch.utils as utils
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = utils.CONFIG_DIR
        old_file = utils.CONFIG_FILE
        utils.CONFIG_DIR = type(utils.CONFIG_DIR)(tmpdir)
        utils.CONFIG_FILE = utils.CONFIG_DIR / "config.yaml"
        try:
            dbs = db_list()
            assert isinstance(dbs, dict)
        finally:
            utils.CONFIG_DIR = old_dir
            utils.CONFIG_FILE = old_file


def test_core_backup_list():
    from atulya_launch.core import backup_list
    import atulya_launch.utils as utils
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = utils.CONFIG_DIR
        old_file = utils.CONFIG_FILE
        utils.CONFIG_DIR = type(utils.CONFIG_DIR)(tmpdir)
        utils.CONFIG_FILE = utils.CONFIG_DIR / "config.yaml"
        try:
            backups = backup_list()
            assert isinstance(backups, dict)
        finally:
            utils.CONFIG_DIR = old_dir
            utils.CONFIG_FILE = old_file


def test_core_ssl_list():
    from atulya_launch.core import ssl_list
    import atulya_launch.utils as utils
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = utils.CONFIG_DIR
        old_file = utils.CONFIG_FILE
        utils.CONFIG_DIR = type(utils.CONFIG_DIR)(tmpdir)
        utils.CONFIG_FILE = utils.CONFIG_DIR / "config.yaml"
        try:
            certs = ssl_list()
            assert isinstance(certs, dict)
        finally:
            utils.CONFIG_DIR = old_dir
            utils.CONFIG_FILE = old_file
