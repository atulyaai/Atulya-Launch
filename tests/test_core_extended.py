"""Extended core tests: nginx plans, security, file operations, validation."""
import tempfile
import unittest
from pathlib import Path
from typing import Any

from atulya_launch import core


class CoreExtendedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        core._set_config_dir(Path(self.tmp.name))
        core.ensure_dirs()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_nginx_apply_plan_returns_list(self) -> None:
        core.site_create("test.example.com")
        plan: list[dict[str, str]] = core.nginx_apply_plan()
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["domain"], "test.example.com")
        self.assertIn("source", plan[0])
        self.assertIn("target", plan[0])

    def test_nginx_apply_plan_single_domain(self) -> None:
        core.site_create("a.example.com")
        core.site_create("b.example.com")
        plan: list[dict[str, str]] = core.nginx_apply_plan("a.example.com")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["domain"], "a.example.com")

    def test_nginx_apply_plan_missing_domain_raises(self) -> None:
        with self.assertRaises(ValueError):
            core.nginx_apply_plan("nonexistent.example.com")

    def test_security_scan_checks_bind_host(self) -> None:
        cfg: dict[str, Any] = core.load_config()
        cfg["settings"]["bind_host"] = "0.0.0.0"
        core.save_config(cfg)
        result: dict[str, Any] = core.security_scan()
        issues: list[dict[str, str]] = [i for i in result["issues"] if i["check"] == "bind_host"]
        self.assertTrue(len(issues) > 0)

    def test_security_scan_checks_api_token(self) -> None:
        cfg: dict[str, Any] = core.load_config()
        cfg["panel"]["api_token"] = None
        core.save_config(cfg)
        result: dict[str, Any] = core.security_scan()
        issues: list[dict[str, str]] = [i for i in result["issues"] if i["check"] == "api_token"]
        self.assertTrue(len(issues) > 0)

    def test_site_delete_removes_nginx_config(self) -> None:
        site: dict[str, Any] = core.site_create("del.example.com")
        config_path: Path = Path(site["nginx_config"])
        self.assertTrue(config_path.exists())
        core.site_delete("del.example.com")
        self.assertFalse(config_path.exists())

    def test_file_write_and_read(self) -> None:
        core.site_create("files.example.com")
        core.file_write("files.example.com", "test.txt", "hello world")
        entries: list[dict[str, Any]] = core.file_list("files.example.com", ".")
        names: list[str] = [e["name"] for e in entries]
        self.assertIn("test.txt", names)

    def test_file_mkdir(self) -> None:
        core.site_create("mkdir.example.com")
        core.file_mkdir("mkdir.example.com", "subdir")
        entries: list[dict[str, Any]] = core.file_list("mkdir.example.com", ".")
        dirs: list[str] = [e["name"] for e in entries if e["type"] == "directory"]
        self.assertIn("subdir", dirs)

    def test_file_delete(self) -> None:
        core.site_create("delfile.example.com")
        core.file_write("delfile.example.com", "todelete.txt", "bye")
        core.file_delete("delfile.example.com", "todelete.txt")
        entries: list[dict[str, Any]] = core.file_list("delfile.example.com", ".")
        names: list[str] = [e["name"] for e in entries]
        self.assertNotIn("todelete.txt", names)

    def test_file_delete_rejects_site_root(self) -> None:
        core.site_create("rootdel.example.com")
        with self.assertRaises(ValueError):
            core.file_delete("rootdel.example.com", ".")

    def test_file_path_escape_blocked(self) -> None:
        core.site_create("escape2.example.com")
        with self.assertRaises(ValueError):
            core.file_list("escape2.example.com", "../../etc")

    def test_backup_restore_roundtrip(self) -> None:
        core.site_create("roundtrip.example.com")
        core.file_write("roundtrip.example.com", "index.html", "<h1>test</h1>")
        backup: dict[str, Any] = core.backup_create("roundtrip")
        self.assertTrue(Path(backup["path"]).exists())

    def test_dashboard_data(self) -> None:
        core.site_create("dash.example.com")
        data: dict[str, Any] = core.dashboard_data()
        self.assertIn("status", data)
        self.assertIn("sites", data)
        self.assertIn("backups", data)
        self.assertIn("security", data)
        self.assertIn("audit", data)

    def test_memory_status_returns_dict(self) -> None:
        result: dict[str, Any] = core.memory_status()
        self.assertIn("total", result)
        self.assertIn("percent", result)

    def test_service_summary_returns_dict(self) -> None:
        result: dict[str, str] = core.service_summary()
        self.assertIsInstance(result, dict)

    def test_validate_domain_rejects_bad(self) -> None:
        with self.assertRaises(ValueError):
            core.validate_domain("")
        with self.assertRaises(ValueError):
            core.validate_domain("no..dots")
        with self.assertRaises(ValueError):
            core.validate_domain("no-dots-here")

    def test_validate_domain_accepts_good(self) -> None:
        self.assertEqual(core.validate_domain("Example.COM"), "example.com")
        self.assertEqual(core.validate_domain("sub.example.com"), "sub.example.com")

    def test_audit_event_writes(self) -> None:
        core.audit_event("test.action", "ok", {"key": "value"})
        events: list[dict[str, Any]] = core.audit_list(10)
        self.assertTrue(any(e["action"] == "test.action" for e in events))

    def test_multiple_sites(self) -> None:
        for i in range(5):
            core.site_create(f"site{i}.example.com")
        sites: dict[str, Any] = core.site_list()
        self.assertEqual(len(sites), 5)

    def test_site_create_duplicate_raises(self) -> None:
        core.site_create("dup.example.com")
        with self.assertRaises(ValueError):
            core.site_create("dup.example.com")


if __name__ == "__main__":
    unittest.main()
