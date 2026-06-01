import unittest

from atulya_launch.drivers import BindZone, get_platform_driver


class TestPlatformDrivers(unittest.TestCase):
    def test_linux_driver_plans_bind_zone(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.dns.apply_zone(
            BindZone(
                domain="example.com",
                serial=2026053101,
                records=[{"name": "@", "type": "A", "value": "127.0.0.1", "ttl": 3600}],
            )
        )
        self.assertTrue(result.ok)
        self.assertIn("/etc/bind/zones/db.example.com", result.files)
        self.assertIn("/etc/bind/named.conf.local", result.files)
        self.assertIn(["named-checkzone", "example.com", "/etc/bind/zones/db.example.com"], result.commands)
        self.assertIn(["rndc", "reload", "example.com"], result.commands)

    def test_linux_driver_plans_bind_zone_delete(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.dns.delete_zone("example.com")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "bind.delete_zone")
        self.assertIn("/etc/bind/zones/db.example.com", result.files)
        self.assertIn("/etc/bind/named.conf.local", result.files)
        self.assertIn(["rndc", "reload"], result.commands)

    def test_windows_driver_uses_caddy_scaffold(self) -> None:
        driver = get_platform_driver("windows", dry_run=True)
        result = driver.web.apply_site("example.com", "example.com { respond ok }")
        self.assertTrue(result.ok)
        self.assertEqual(driver.web.name, "caddy")
        self.assertTrue(result.files[0].endswith("example.com.conf"))

    def test_macos_driver_uses_homebrew_plan(self) -> None:
        driver = get_platform_driver("macos", dry_run=True)
        result = driver.packages.install(["caddy"])
        self.assertTrue(result.ok)
        self.assertEqual(result.commands, [["brew", "install", "caddy"]])


class TestLinuxDatabaseDriver(unittest.TestCase):
    def test_mysql_create_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.databases.create("appdb", "mysql")
        self.assertTrue(result.ok)
        self.assertEqual(
            result.commands,
            [["mysql", "-e", "CREATE DATABASE IF NOT EXISTS `appdb`"]],
        )

    def test_mysql_drop_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.databases.drop("appdb", "mysql")
        self.assertTrue(result.ok)
        self.assertEqual(
            result.commands,
            [["mysql", "-e", "DROP DATABASE IF EXISTS `appdb`"]],
        )

    def test_postgres_create_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.databases.create("appdb", "postgresql")
        self.assertTrue(result.ok)
        self.assertEqual(result.commands, [["sudo", "-u", "postgres", "createdb", "appdb"]])

    def test_unknown_db_type_rejected(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.databases.create("appdb", "oracle")
        self.assertFalse(result.ok)
        self.assertIn("unsupported", result.message)


class TestLinuxSslDriver(unittest.TestCase):
    def test_letsencrypt_issue_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.ssl.issue_letsencrypt("example.com", "admin@example.com")
        self.assertTrue(result.ok)
        cmd = result.commands[0]
        self.assertEqual(cmd[0], "certbot")
        self.assertIn("-d", cmd)
        self.assertIn("example.com", cmd)
        # nginx reload is appended
        self.assertTrue(any("nginx" in c for c in result.commands))

    def test_letsencrypt_staging_flag(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.ssl.issue_letsencrypt("example.com", "a@b.com", staging=True)
        self.assertTrue("--staging" in result.commands[0])

    def test_renew_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.ssl.renew("example.com")
        self.assertTrue(result.ok)
        self.assertIn(["certbot", "renew", "--cert-name", "example.com"], result.commands)


class TestLinuxFirewallDriver(unittest.TestCase):
    def test_allow_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.firewall.allow(443)
        self.assertTrue(result.ok)
        self.assertEqual(result.commands, [["ufw", "allow", "443/tcp"]])

    def test_allow_udp(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.firewall.allow(53, proto="udp")
        self.assertEqual(result.commands, [["ufw", "allow", "53/udp"]])

    def test_deny_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.firewall.deny(23)
        self.assertEqual(result.commands, [["ufw", "deny", "23/tcp"]])

    def test_enable_force_flag(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.firewall.enable()
        self.assertEqual(result.commands, [["ufw", "--force", "enable"]])

    def test_status_and_list(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        self.assertEqual(driver.firewall.status().commands, [["ufw", "status"]])
        self.assertEqual(driver.firewall.list_rules().commands, [["ufw", "status", "numbered"]])


class TestWebServerDriverExtensions(unittest.TestCase):
    def test_test_config_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.web.test_config()
        self.assertTrue(result.ok)
        self.assertEqual(result.commands, [["nginx", "-t"]])

    def test_detect_plan(self) -> None:
        driver = get_platform_driver("linux", dry_run=True)
        result = driver.web.detect()
        self.assertTrue(result.ok)
        self.assertEqual(result.commands, [["nginx", "-v"]])


class TestDriverRejectsNonLinux(unittest.TestCase):
    """On non-Linux, core helpers must still return friendly errors (not crash)."""

    def test_core_firewall_status_off_linux(self) -> None:
        import sys
        from atulya_launch import core
        if sys.platform == "linux":
            self.skipTest("linux-only behavior")
        result = core.firewall_status()
        self.assertFalse(result.get("active"))


if __name__ == "__main__":
    unittest.main()
