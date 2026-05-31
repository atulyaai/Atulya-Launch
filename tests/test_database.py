"""Database layer tests: init, CRUD, audit log, DNS, email, SSL."""
import tempfile
import unittest
from pathlib import Path
from typing import Any

from atulya_launch.web.database import init_db, connect, audit_log, reset_db


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_db()
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name)
        init_db(self.config_dir, force=True)

    def tearDown(self) -> None:
        import gc
        gc.collect()
        for f in Path(self.tmp.name).glob("panel.db*"):
            try:
                f.unlink()
            except Exception:
                pass
        self.tmp.cleanup()

    def test_init_db_creates_file(self) -> None:
        db_path: Path = self.config_dir / "panel.db"
        self.assertTrue(db_path.exists())

    def test_connect_executes_query(self) -> None:
        with connect() as cur:
            result: Any = cur.execute("SELECT 1 as x").fetchone()
            self.assertEqual(result["x"], 1)

    def test_users_table_exists(self) -> None:
        with connect() as cur:
            tables: list[Any] = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names: list[str] = [t["name"] for t in tables]
            self.assertIn("users", names)
            self.assertIn("sessions", names)
            self.assertIn("dns_zones", names)
            self.assertIn("dns_records", names)
            self.assertIn("email_accounts", names)
            self.assertIn("databases", names)
            self.assertIn("ssl_certs", names)
            self.assertIn("audit_log", names)
            self.assertIn("flash_messages", names)

    def test_audit_log_inserts(self) -> None:
        audit_log("testuser", "test.action", "ok", {"detail": "value"})
        with connect() as cur:
            row: Any = cur.execute("SELECT * FROM audit_log WHERE action = ?", ("test.action",)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["user"], "testuser")
            self.assertEqual(row["status"], "ok")

    def test_dns_zone_crud(self) -> None:
        with connect() as cur:
            cur.execute("INSERT INTO dns_zones (domain, soa_primary, soa_email, created_at) VALUES (?, ?, ?, ?)",
                        ("example.com", "ns1", "admin", "2026-01-01T00:00:00Z"))
            zone: Any = cur.execute("SELECT * FROM dns_zones WHERE domain = ?", ("example.com",)).fetchone()
            self.assertIsNotNone(zone)
            cur.execute("INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (zone["id"], "www", "A", "1.2.3.4", 3600, "2026-01-01T00:00:00Z"))
            recs: list[Any] = cur.execute("SELECT * FROM dns_records WHERE zone_id = ?", (zone["id"],)).fetchall()
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["type"], "A")

    def test_dns_zone_cascade_delete(self) -> None:
        with connect() as cur:
            cur.execute("INSERT INTO dns_zones (domain, soa_primary, soa_email, created_at) VALUES (?, ?, ?, ?)",
                        ("del.example.com", "ns1", "admin", "2026-01-01T00:00:00Z"))
            zone: Any = cur.execute("SELECT * FROM dns_zones WHERE domain = ?", ("del.example.com",)).fetchone()
            cur.execute("INSERT INTO dns_records (zone_id, name, type, value, ttl, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (zone["id"], "www", "A", "1.2.3.4", 3600, "2026-01-01T00:00:00Z"))
            cur.execute("DELETE FROM dns_zones WHERE id = ?", (zone["id"],))
            recs: list[Any] = cur.execute("SELECT * FROM dns_records WHERE zone_id = ?", (zone["id"],)).fetchall()
            self.assertEqual(len(recs), 0)

    def test_email_account_crud(self) -> None:
        with connect() as cur:
            cur.execute("INSERT INTO email_accounts (domain, mailbox, password_hash, quota_mb, created_at) VALUES (?, ?, ?, ?, ?)",
                        ("example.com", "user", "hash123", 1024, "2026-01-01T00:00:00Z"))
            acc: Any = cur.execute("SELECT * FROM email_accounts WHERE domain = ?", ("example.com",)).fetchone()
            self.assertIsNotNone(acc)
            self.assertEqual(acc["mailbox"], "user")

    def test_database_record_crud(self) -> None:
        with connect() as cur:
            cur.execute("INSERT INTO databases (name, db_type, username, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                        ("mydb", "mysql", "dbuser", "hash", "2026-01-01T00:00:00Z"))
            db: Any = cur.execute("SELECT * FROM databases WHERE name = ?", ("mydb",)).fetchone()
            self.assertIsNotNone(db)
            self.assertEqual(db["db_type"], "mysql")

    def test_ssl_cert_crud(self) -> None:
        with connect() as cur:
            cur.execute("INSERT INTO ssl_certs (domain, cert_path, key_path, issuer, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        ("ssl.example.com", "/cert.pem", "/key.pem", "Let's Encrypt", "2027-01-01", "2026-01-01T00:00:00Z"))
            cert: Any = cur.execute("SELECT * FROM ssl_certs WHERE domain = ?", ("ssl.example.com",)).fetchone()
            self.assertIsNotNone(cert)
            self.assertEqual(cert["issuer"], "Let's Encrypt")


if __name__ == "__main__":
    unittest.main()
