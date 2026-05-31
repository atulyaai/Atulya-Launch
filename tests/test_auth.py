"""Authentication tests: password hashing, user CRUD, session management."""
import tempfile
import unittest
from pathlib import Path
from typing import Any

from atulya_launch.web.database import init_db, reset_db
from atulya_launch.web.auth import (
    hash_password, verify_password, create_user, authenticate,
    validate_session, destroy_session
)


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_db()
        self.tmp = tempfile.TemporaryDirectory()
        init_db(Path(self.tmp.name), force=True)

    def tearDown(self) -> None:
        import gc
        gc.collect()
        for f in Path(self.tmp.name).glob("panel.db*"):
            try:
                f.unlink()
            except Exception:
                pass
        self.tmp.cleanup()

    def test_hash_and_verify_password(self) -> None:
        pw: str = "secure_password_123"
        hashed: str = hash_password(pw)
        self.assertTrue(verify_password(pw, hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_hash_password_deterministic_with_same_salt(self) -> None:
        import secrets
        salt: bytes = secrets.token_bytes(16)
        h1: str = hash_password("test", salt)
        h2: str = hash_password("test", salt)
        self.assertEqual(h1, h2)

    def test_create_user_and_authenticate(self) -> None:
        create_user("testadmin", "pass123", "admin", skip_policy=True)
        result: dict[str, Any] | None = authenticate("testadmin", "pass123")
        self.assertIsNotNone(result)
        self.assertIn("token", result)
        self.assertEqual(result["user"]["username"], "testadmin")
        self.assertEqual(result["user"]["role"], "admin")

    def test_authenticate_wrong_password(self) -> None:
        create_user("user1", "correct", "user", skip_policy=True)
        result: dict[str, Any] | None = authenticate("user1", "wrong")
        self.assertIsNone(result)

    def test_authenticate_unknown_user(self) -> None:
        result: dict[str, Any] | None = authenticate("nobody", "pass")
        self.assertIsNone(result)

    def test_validate_session_valid(self) -> None:
        create_user("sessuser", "pass", "admin", skip_policy=True)
        result: dict[str, Any] = authenticate("sessuser", "pass")
        token: str = result["token"]
        session: dict[str, Any] | None = validate_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["username"], "sessuser")

    def test_validate_session_invalid(self) -> None:
        self.assertIsNone(validate_session("fake_token"))
        self.assertIsNone(validate_session(None))
        self.assertIsNone(validate_session(""))

    def test_destroy_session(self) -> None:
        create_user("delsess", "pass", "admin", skip_policy=True)
        result: dict[str, Any] = authenticate("delsess", "pass")
        token: str = result["token"]
        self.assertIsNotNone(validate_session(token))
        destroy_session(token)
        self.assertIsNone(validate_session(token))

    def test_multiple_users(self) -> None:
        create_user("admin1", "pass1", "admin", skip_policy=True)
        create_user("user1", "pass2", "user", skip_policy=True)
        r1: dict[str, Any] | None = authenticate("admin1", "pass1")
        r2: dict[str, Any] | None = authenticate("user1", "pass2")
        self.assertIsNotNone(r1)
        self.assertIsNotNone(r2)
        self.assertEqual(r1["user"]["role"], "admin")
        self.assertEqual(r2["user"]["role"], "user")


if __name__ == "__main__":
    unittest.main()
