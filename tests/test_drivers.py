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
        self.assertIn(["systemctl", "reload", "bind9"], result.commands)

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


if __name__ == "__main__":
    unittest.main()
