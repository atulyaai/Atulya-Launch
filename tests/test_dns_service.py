import tempfile
import unittest
from pathlib import Path

from atulya_launch.web.database import init_db, reset_db
from atulya_launch.web import dns_service


class TestDnsService(unittest.TestCase):
    def setUp(self) -> None:
        reset_db()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        init_db(Path(self.tmp.name), force=True)

    def tearDown(self) -> None:
        import gc
        reset_db()
        gc.collect()
        self.tmp.cleanup()

    def test_dns_zone_record_and_apply_plan(self) -> None:
        zone = dns_service.create_zone("example.com")
        self.assertEqual(zone["domain"], "example.com")

        record = dns_service.add_record("example.com", "A", "@", "127.0.0.1")
        self.assertEqual(record["content"], "127.0.0.1")

        zones = dns_service.list_zones()
        self.assertIn("example.com", zones)
        self.assertEqual(len(zones["example.com"]["records"]), 1)

        apply = dns_service.apply_zone("example.com")
        self.assertTrue(apply["ok"])
        self.assertTrue(apply["dry_run"])
        self.assertIn("db.example.com", apply["files"][0])

    def test_dns_delete_zone(self) -> None:
        dns_service.create_zone("delete.example.com")
        self.assertTrue(dns_service.delete_zone("delete.example.com"))
        self.assertNotIn("delete.example.com", dns_service.list_zones())


if __name__ == "__main__":
    unittest.main()
