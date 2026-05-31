import tempfile
import unittest
from pathlib import Path


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_app(self):
        from atulya_launch.web.database import init_db, connect, reset_db
        reset_db()
        init_db(self.config_dir, force=True)
        from atulya_launch.web.auth import create_user
        create_user("admin", "admin123", "admin")
        from atulya_launch.web.app import create_app
        return create_app()

    def _get_client(self, app):
        try:
            from httpx import AsyncClient, ASGITransport
        except ImportError:
            self.skipTest("httpx not installed")
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True)

    def test_login_page_renders(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/login", follow_redirects=False)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Atulya Launch", resp.text)
        asyncio.run(run())

    def test_login_redirects_unauthenticated(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/dashboard", follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("/login", resp.headers.get("location", ""))
        asyncio.run(run())

    def test_login_post_valid(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("session_token", resp.cookies)
        asyncio.run(run())

    def test_login_post_invalid(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
            self.assertIn(resp.status_code, (302, 307))
            self.assertIn("error=1", resp.headers.get("location", ""))
        asyncio.run(run())

    def test_dashboard_after_login(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", resp.cookies)
            resp2 = await client.get("/dashboard")
            self.assertEqual(resp2.status_code, 200)
            self.assertIn("Dashboard", resp2.text)
        asyncio.run(run())

    def test_api_login_valid(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("token", data)
        asyncio.run(run())

    def test_api_login_invalid(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            self.assertEqual(resp.status_code, 401)
        asyncio.run(run())

    def test_api_sites_requires_auth(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.get("/api/sites")
            self.assertEqual(resp.status_code, 401)
        asyncio.run(run())

    def test_api_sites_with_token(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            token = login_resp.json()["token"]
            resp = await client.get("/api/sites", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(resp.status_code, 200)
        asyncio.run(run())

    def test_logout(self):
        import asyncio
        app = self._make_app()
        client = self._get_client(app)
        async def run():
            resp = await client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
            self.assertIn("session_token", resp.cookies)
            resp2 = await client.get("/logout", follow_redirects=False)
            self.assertIn(resp2.status_code, (302, 307))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
