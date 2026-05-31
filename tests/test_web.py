"""Integration tests for the web application."""
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        import gc
        gc.collect()
        for f in Path(self.tmp.name).glob("panel.db*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def _make_app(self) -> Any:
        from atulya_launch.web.database import init_db, connect, reset_db
        reset_db()
        init_db(self.config_dir, force=True)
        from atulya_launch.web.auth import create_user
        create_user("admin", "admin123", "admin", skip_policy=True)
        from atulya_launch.web.app import create_app
        return create_app()

    def _get_client(self, app: Any) -> Any:
        try:
            from httpx import AsyncClient, ASGITransport
        except ImportError:
            self.skipTest("httpx not installed")
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True)

    def test_login_page_renders(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/login", follow_redirects=False)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Atulya Launch", resp.text)
        asyncio.run(run())

    def test_login_redirects_unauthenticated(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/dashboard", follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("/login", resp.headers.get("location", ""))
        asyncio.run(run())

    def test_login_post_valid(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("session_token", resp.cookies)
        asyncio.run(run())

    def test_login_post_invalid(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("error=1", resp.headers.get("location", ""))
        asyncio.run(run())

    def test_dashboard_after_login(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", resp.cookies)
            resp2 = await client.get("/dashboard")
            self.assertEqual(resp2.status_code, 200)
            self.assertIn("Dashboard", resp2.text)
            self.assertIn("Signed in successfully.", resp2.text)
        asyncio.run(run())

    def test_ssh_terminal_page_after_login(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", resp.cookies)
            resp2 = await client.get("/ssh-terminal")
            self.assertEqual(resp2.status_code, 200)
            self.assertIn("SSH Terminal", resp2.text)
            self.assertIn("/ws/ssh?session_id=", resp2.text)
        asyncio.run(run())

    def test_cookie_post_requires_csrf(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            login_resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", login_resp.cookies)
            resp = await client.post("/dns/zone/create", data={"domain": "csrf.example.com"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 403)
        asyncio.run(run())

    def test_cookie_post_accepts_csrf_form_token(self) -> None:
        import asyncio
        from atulya_launch.web.app import csrf
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            login_resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            token = login_resp.cookies["session_token"]
            resp = await client.post(
                "/dns/zone/create",
                data={"domain": "csrf-ok.example.com", "_csrf_token": csrf.generate(token)},
                follow_redirects=False,
            )
            self.assertIn(resp.status_code, (302, 307))
        asyncio.run(run())

    def test_api_login_valid(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("token", data)
        asyncio.run(run())

    def test_api_login_invalid(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            self.assertEqual(resp.status_code, 401)
        asyncio.run(run())

    def test_api_sites_requires_auth(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/api/sites")
            self.assertEqual(resp.status_code, 401)
        asyncio.run(run())

    def test_api_sites_with_token(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            token = login_resp.json()["token"]
            resp = await client.get("/api/sites", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(resp.status_code, 200)
        asyncio.run(run())

    def test_logout(self) -> None:
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", resp.cookies)
            resp2 = await client.get("/logout", follow_redirects=False)
            self.assertIn(resp2.status_code, (302, 307))
        asyncio.run(run())

    def test_production_mode_rejects_default_admin_password(self) -> None:
        from atulya_launch import core
        from atulya_launch.web.database import reset_db
        reset_db()
        core._set_config_dir(self.config_dir)
        with patch.dict("os.environ", {"ATULYA_PRODUCTION": "1"}, clear=False):
            from atulya_launch.web.app import create_app
            with self.assertRaises(RuntimeError):
                create_app()

    def test_router_status_has_no_import_errors(self) -> None:
        app = self._make_app()
        self.assertGreaterEqual(len(getattr(app.state, "api_routers_registered", [])), 1)
        self.assertEqual(getattr(app.state, "api_router_errors", []), [])


if __name__ == "__main__":
    unittest.main()
