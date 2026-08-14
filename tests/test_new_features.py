import unittest
import tempfile
import asyncio
from pathlib import Path

import httpx


def _make_client():
    from atulya_launch.web.app import create_app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://t", follow_redirects=False,
    )


class TestNewFeatures(unittest.TestCase):
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

    # ─── AI predictive engine ────────────────────────────────────────────
    def test_ai_predict_endpoint(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                return await c.get("/api/ai/predict?hours=24", headers=self._headers(token))
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("overall_risk", body)
        self.assertIn("metrics", body)
        self.assertIn("suggested_actions", body)
        self.assertIn("cpu_percent", body["metrics"])

    def test_ai_history_records(self) -> None:
        from atulya_launch.ai import predictive
        sample = predictive.sample_metrics()
        predictive.record_sample(sample)
        history = predictive.get_history(hours=24)
        self.assertGreaterEqual(len(history), 1)
        self.assertIn("cpu_percent", history[-1])

    def test_ai_forecast_and_risk(self) -> None:
        from atulya_launch.ai import predictive
        current = {"cpu_percent": 95, "mem_percent": 50, "disk_percent": 40,
                   "load_1m": 2, "bytes_sent": 0, "bytes_recv": 0}
        hist = [{"cpu_percent": 30, "mem_percent": 50, "disk_percent": 40,
                 "load_1m": 1, "bytes_sent": 0, "bytes_recv": 0}]
        report = predictive.evaluate(current, hist)
        self.assertEqual(report["overall_risk"], "critical")
        cpu_risk = [r for r in report["risks"] if r["key"] == "cpu_percent"][0]
        self.assertEqual(cpu_risk["risk"], "critical")
        self.assertEqual(cpu_risk["action"], "restart_heavy_process")

    def test_ai_health_no_deps(self) -> None:
        # The engine must work even on Windows (no loadavg) without crashing.
        from atulya_launch.web.api.healthdashboard import _get_load_average
        load = _get_load_average()
        self.assertIn("load_1m", load)

    # ─── DNSSEC ──────────────────────────────────────────────────────────
    def test_dnssec_enable_list(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/dnssec", json={"domain": "example.com", "algorithm": "ecdsap256sha256"}, headers=self._headers(token))
                listing = await c.get("/api/dnssec", headers=self._headers(token))
                return r, listing
        r, listing = self._run(run())
        self.assertEqual(r.status_code, 200)
        zones = listing.json()["zones"]
        self.assertTrue(any(z["domain"] == "example.com" and z["enabled"] for z in zones))

    # ─── Addon domains ───────────────────────────────────────────────────
    def test_addon_domain_requires_root_site(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/addon-domains", json={"domain": "shop.nonexistent.io", "root_domain": "nonexistent.io"}, headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 400)

    # ─── Site publisher ──────────────────────────────────────────────────
    def test_site_publisher_templates(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.get("/api/site-publisher/templates", headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertIn("coming_soon", r.json()["templates"])

    # ─── Email auth (SPF/DMARC) ──────────────────────────────────────────
    def test_email_auth_defaults(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.get("/api/email-auth/defaults/example.com", headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["spf"].startswith("v=spf1"))
        self.assertTrue(body["dmarc"].startswith("v=DMARC1"))

    def test_email_auth_upsert(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/email-auth", json={
                    "domain": "mail.example.com",
                    "spf": "v=spf1 mx -all",
                    "dmarc": "v=DMARC1; p=none",
                }, headers=self._headers(token))
                listing = await c.get("/api/email-auth", headers=self._headers(token))
                return r, listing
        r, listing = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(x["domain"] == "mail.example.com" for x in listing.json()["records"]))

    # ─── Feature manager ─────────────────────────────────────────────────
    def test_feature_manager_group_crud(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/feature-manager/groups", json={
                    "id": "basic", "name": "Basic Hosting", "features": ["sites", "files", "backups"]}, headers=self._headers(token))
                listing = await c.get("/api/feature-manager/groups", headers=self._headers(token))
                return r, listing
        r, listing = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(g["id"] == "basic" for g in listing.json()["groups"]))

    def test_feature_manager_bad_feature_rejected(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/feature-manager/groups", json={
                    "id": "bad", "name": "Bad", "features": ["nonexistent_feature"]}, headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 400)

    def test_ip_pool_allocate(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.post("/api/feature-manager/ips", json={"ip": "192.168.0.10", "assigned_to": "client1", "pool": "dedicated"}, headers=self._headers(token))
                listing = await c.get("/api/feature-manager/ips", headers=self._headers(token))
                return r, listing
        r, listing = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(x["ip"] == "192.168.0.10" for x in listing.json()["ips"]))

    # ─── Versioned API v1 ───────────────────────────────────────────────
    def test_v1_meta(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                r = await c.get("/api/v1/meta", headers=self._headers(token))
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["api_version"], "v1")
        self.assertIn("modules", body)

    def test_openapi_spec_version(self) -> None:
        async def run():
            async with _make_client() as c:
                r = await c.get("/openapi.json")
                return r
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["openapi"], "3.1.0")

    # ─── Unified 2FA ─────────────────────────────────────────────────────
    def test_twofa_unified_store(self) -> None:
        from atulya_launch.web import twofa_store
        self.assertFalse(twofa_store.is_enabled("admin"))
        twofa_store.start_setup("admin")
        result = twofa_store.enable("admin", "000000")
        self.assertFalse(result.get("ok"))
        self.assertFalse(twofa_store.is_enabled("admin"))
        twofa_store.disable("admin", "000000")

    def test_twofa_api_status(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                return await c.get("/api/2fa/status", headers=self._headers(token))
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertIn("enabled", r.json())


if __name__ == "__main__":
    unittest.main()