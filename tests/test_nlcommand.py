import unittest
import tempfile
import asyncio
from pathlib import Path

import httpx

from atulya_launch.ai import nlcommand


def _make_client():
    from atulya_launch.web.app import create_app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://t", follow_redirects=False,
    )


class TestNLCommandEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import os
        cls.config_dir = Path(tempfile.mkdtemp())
        os.environ["PANEL_CONFIG_DIR"] = str(cls.config_dir)
        from atulya_launch.web import database as db
        db.reset_db()
        db.init_db(cls.config_dir, force=True)
        from atulya_launch.web.auth import create_user
        create_user("admin", "admin123", "admin", skip_policy=True)

    def _run(self, coro):
        return asyncio.run(coro)

    def _login_token(self) -> str:
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
                return r.json()["token"]
        return self._run(run())

    def _headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ─── Parsing ─────────────────────────────────────────────────────────
    def test_parse_wordpress_site(self) -> None:
        intent = nlcommand.parse_intent("create a WordPress site example.com with redis cache and SSL")
        self.assertEqual(intent.action, "CREATE_SITE")
        self.assertEqual(intent.domain, "example.com")
        self.assertEqual(intent.app, "wordpress")
        self.assertTrue(intent.wants_cache)
        self.assertEqual(intent.wants_cache, "redis")
        self.assertTrue(intent.wants_ssl)
        self.assertTrue(intent.wants_db)
        self.assertGreaterEqual(intent.confidence, 0.5)

    def test_parse_delete_site(self) -> None:
        intent = nlcommand.parse_intent("please delete the site old.example.net")
        self.assertEqual(intent.action, "DELETE_SITE")
        self.assertEqual(intent.domain, "old.example.net")

    def test_parse_standalone_ssl(self) -> None:
        intent = nlcommand.parse_intent("enable Let's Encrypt SSL on secure.example.io")
        self.assertEqual(intent.action, "ENABLE_SSL")
        self.assertEqual(intent.domain, "secure.example.io")
        self.assertTrue(intent.wants_ssl)
        self.assertFalse(intent.wants_cache)

    def test_parse_php_version(self) -> None:
        intent = nlcommand.parse_intent("create site with PHP 8.2 api.example.com")
        self.assertEqual(intent.php_version, "8.2")
        self.assertTrue(intent.wants_php)

    def test_parse_app_aliases(self) -> None:
        self.assertEqual(nlcommand.parse_intent("setup wp blog.example.com").app, "wordpress")
        self.assertEqual(nlcommand.parse_intent("deploy nextcloud cloud.example.com").app, "nextcloud")

    # ─── Plan assembly ───────────────────────────────────────────────────
    def test_wordpress_plan_order(self) -> None:
        intent = nlcommand.parse_intent("create wordpress shop.example.com with redis and https cert")
        plan = nlcommand.assemble_plan(intent)
        names = [s.name for s in plan.steps]
        self.assertEqual(
            names,
            ["provision_site", "configure_php_fpm", "create_database", "install_app", "enable_cache", "issue_ssl", "reload_web"],
        )

    def test_static_site_plan_minimal(self) -> None:
        intent = nlcommand.parse_intent("create a plain static site blog2.example.org")
        plan = nlcommand.assemble_plan(intent)
        self.assertEqual([s.name for s in plan.steps], ["provision_site"])

    def test_delete_plan(self) -> None:
        intent = nlcommand.parse_intent("delete old.example.net")
        plan = nlcommand.assemble_plan(intent)
        self.assertEqual([s.name for s in plan.steps], ["remove_site"])

    # ─── Dry-run execution ───────────────────────────────────────────────
    def test_apply_plan_dry_run(self) -> None:
        intent = nlcommand.parse_intent("create wordpress wp.example.com")
        plan = nlcommand.assemble_plan(intent)
        result = nlcommand.apply_plan(plan, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["results"]), len(plan.steps))
        for item in result["results"]:
            self.assertTrue(item["dry_run"])

    def test_apply_plan_executes_no_crash(self) -> None:
        # Non-destructive? site create touches disk; use a throwaway domain that
        # stays in a temp config dir. Server UX: real provisioning won't run on
        # Windows, but the executor must not raise unhandled exceptions.
        intent = nlcommand.parse_intent("create a site nltest-{0}.example.com".format("x"))
        plan = nlcommand.assemble_plan(intent)
        result = nlcommand.apply_plan(plan, dry_run=False, stop_on_error=True)
        self.assertIsInstance(result, dict)
        self.assertIn("results", result)
        for item in result["results"]:
            self.assertIn("ok", item)

    # ─── HTTP endpoint ───────────────────────────────────────────────────
    def test_command_endpoint_dry_run(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/ai/command", json={
                    "command": "set up WordPress on cmd.example.com with SSL",
                    "dry_run": True,
                }, headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["dry_run"])
        self.assertIn("CREATE_SITE", body["intent"])
        self.assertIn("cmd.example.com", body["intent"])
        self.assertGreaterEqual(len(body["results"]), 1)

    def test_command_endpoint_empty_rejected(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/ai/command", json={"command": "  ", "dry_run": True},
                                 headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()