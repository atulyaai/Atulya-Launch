import tempfile
import unittest
from pathlib import Path

from atulya_launch.web.database import init_db, reset_db
from atulya_launch.web import mail_service


class TestMailService(unittest.TestCase):
    def setUp(self) -> None:
        reset_db()
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        init_db(Path(self.tmp.name), force=True)

    def tearDown(self) -> None:
        import gc
        reset_db()
        gc.collect()
        self.tmp.cleanup()

    def test_create_account_applies_domain_plan(self) -> None:
        account = mail_service.create_account("example.com", "admin", "Admin1234", 512)

        self.assertEqual(account["domain"], "example.com")
        self.assertEqual(account["mailbox"], "admin")
        self.assertEqual(account["quota_mb"], 512)
        self.assertTrue(account["apply"]["ok"])
        self.assertTrue(account["apply"]["dry_run"])
        self.assertIn("virtual_mailboxes", account["apply"]["files"][0])
        self.assertTrue(any("postfix" in command for command in account["apply"]["commands"]))
        self.assertTrue(any("dovecot" in command for command in account["apply"]["commands"]))

    def test_delete_account_applies_domain_plan(self) -> None:
        account = mail_service.create_account("example.com", "ops", "Admin1234")

        result = mail_service.delete_account(account["id"])

        self.assertEqual(result["domain"], "example.com")
        self.assertEqual(mail_service.list_accounts("example.com"), [])
        self.assertTrue(result["apply"]["ok"])


if __name__ == "__main__":
    unittest.main()
