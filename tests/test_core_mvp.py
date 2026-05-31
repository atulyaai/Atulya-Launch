"""Core MVP tests: panel init, auth, sites, backup, files, security."""
import tempfile
import unittest
from pathlib import Path
from typing import Any

from atulya_launch import core


class CoreMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        core._set_config_dir(Path(self.tmp.name))
        core.ensure_dirs()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_panel_init_generates_token(self) -> None:
        result: dict[str, Any] = core.panel_init(rotate_token=True)
        self.assertEqual(result["admin_user"], "admin")
        self.assertTrue(result["api_token"])
        self.assertTrue(result["generated_password"])

    def test_login_generates_session_token(self) -> None:
        core.panel_init(admin_password="secret", rotate_token=True)
        token: str | None = core.login("admin", "secret")
        self.assertTrue(token)
        self.assertTrue(core.validate_session(token))
        self.assertIsNone(core.login("admin", "wrong"))

    def test_site_create_generates_webroot_and_nginx_config(self) -> None:
        site: dict[str, Any] = core.site_create("example.local")
        self.assertEqual(site["domain"], "example.local")
        self.assertTrue(Path(site["web_root"]).exists())
        self.assertTrue(Path(site["nginx_config"]).exists())

    def test_site_create_rejects_unsafe_webroot(self) -> None:
        with self.assertRaises(ValueError):
            core.site_create("escape.local", web_root=str(Path(self.tmp.name).parent))

    def test_backup_create_writes_archive(self) -> None:
        core.site_create("backup.local")
        backup: dict[str, Any] = core.backup_create("unit")
        self.assertTrue(Path(backup["path"]).exists())
        self.assertGreater(backup["size"], 0)

    def test_backup_restore_restores_archive(self) -> None:
        core.site_create("restore.local")
        backup: dict[str, Any] = core.backup_create("restore-unit")
        Path(core.site_get("restore.local")["web_root"], "index.html").unlink()
        result: dict[str, Any] = core.backup_restore(backup["name"])
        self.assertEqual(result["name"], "restore-unit")
        self.assertTrue(Path(core.site_get("restore.local")["web_root"], "index.html").exists())

    def test_security_scan_returns_score(self) -> None:
        result: dict[str, Any] = core.security_scan()
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 0)

    def test_file_manager_stays_inside_site_root(self) -> None:
        core.site_create("files.local")
        written: dict[str, Any] = core.file_write("files.local", "docs/readme.txt", "hello")
        self.assertTrue(Path(written["path"]).exists())
        entries: list[dict[str, Any]] = core.file_list("files.local", "docs")
        self.assertEqual(entries[0]["name"], "readme.txt")
        with self.assertRaises(ValueError):
            core.file_write("files.local", "../escape.txt", "nope")

    def test_nginx_apply_plan(self) -> None:
        core.site_create("nginx.local")
        plan: list[dict[str, str]] = core.nginx_apply_plan("nginx.local")
        self.assertEqual(plan[0]["domain"], "nginx.local")
        self.assertIn("/etc/nginx/sites-available", plan[0]["target"])

    def test_audit_records_write_actions(self) -> None:
        core.panel_init()
        core.site_create("audit.local")
        events: list[dict[str, Any]] = core.audit_list()
        self.assertTrue(any(event["action"] == "site.create" for event in events))


if __name__ == "__main__":
    unittest.main()
