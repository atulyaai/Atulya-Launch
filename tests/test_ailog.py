import unittest
import tempfile
import asyncio
from pathlib import Path

import httpx

from atulya_launch.ai import log_analyzer


def _make_client():
    from atulya_launch.web.app import create_app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://t", follow_redirects=False,
    )


class TestAILogAnalyzer(unittest.TestCase):
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

    # ─── Unit tests for log_analyzer module ──────────────────────────────────
    def test_heuristic_empty_logs(self) -> None:
        """Heuristic analysis with no logs should return low confidence."""
        logs = {"window_hours": 4, "sources": {}, "total_lines": 0}
        metrics = {"cpu_percent": 10, "mem_percent": 30, "disk_percent": 20, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertEqual(result["method"], "heuristic")
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertIn("root_causes", result)
        self.assertIn("suggested_fixes", result)

    def test_heuristic_detects_disk_full(self) -> None:
        """Heuristic should detect disk full from log pattern."""
        logs = {
            "window_hours": 4,
            "sources": {"nginx_error": ["2026/08/15 10:00:00 [error] writev() failed (28: No space left on device)"]},
            "total_lines": 1,
        }
        metrics = {"cpu_percent": 10, "mem_percent": 30, "disk_percent": 95, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertIn("disk_critical", [m["issue"] for m in result["metric_issues"]])
        self.assertTrue(any("disk" in c.lower() for c in result["root_causes"]))
        self.assertTrue(any("rotate" in f.lower() or "clean" in f.lower() for f in result["suggested_fixes"]))

    def test_heuristic_detects_upstream_down(self) -> None:
        """Heuristic should detect upstream down from log pattern."""
        logs = {
            "window_hours": 4,
            "sources": {"nginx_error": ["2026/08/15 10:00:00 [error] connect() failed (111: Connection refused) while connecting to upstream"]},
            "total_lines": 1,
        }
        metrics = {"cpu_percent": 10, "mem_percent": 30, "disk_percent": 20, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertTrue(any("upstream" in f["pattern"] for f in result["findings"]))
        self.assertTrue(any("upstream" in c.lower() or "php-fpm" in c.lower() for c in result["root_causes"]))

    def test_heuristic_detects_permission_denied(self) -> None:
        """Heuristic should detect permission denied from log pattern."""
        logs = {
            "window_hours": 4,
            "sources": {"nginx_error": ["2026/08/15 10:00:00 [crit] open() /var/www/index.php failed (13: Permission denied)"]},
            "total_lines": 1,
        }
        metrics = {"cpu_percent": 10, "mem_percent": 30, "disk_percent": 20, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertTrue(any("permission" in f["pattern"] for f in result["findings"]))
        self.assertTrue(any("permission" in c.lower() or "ownership" in c.lower() for c in result["root_causes"]))

    def test_heuristic_detects_mysql_down(self) -> None:
        """Heuristic should detect MySQL down from log pattern."""
        logs = {
            "window_hours": 4,
            "sources": {"php_error": ["2026/08/15 10:00:00 [error] PDO::__construct(): Connection refused (111)"]},
            "total_lines": 1,
        }
        metrics = {"cpu_percent": 10, "mem_percent": 30, "disk_percent": 20, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertTrue(any("mysql_down" in f["pattern"] for f in result["findings"]))
        self.assertTrue(any("mysql" in c.lower() or "mariadb" in c.lower() for c in result["root_causes"]))

    def test_heuristic_high_cpu(self) -> None:
        """Heuristic should flag high CPU from metrics."""
        logs = {"window_hours": 4, "sources": {}, "total_lines": 0}
        metrics = {"cpu_percent": 95, "mem_percent": 30, "disk_percent": 20, "load_1m": 0.5}
        result = log_analyzer.heuristic_analysis(logs, metrics)
        self.assertTrue(any(m["issue"] == "cpu_critical" for m in result["metric_issues"]))
        self.assertTrue(any("cpu" in c.lower() for c in result["root_causes"]))

    # ─── API endpoint tests ──────────────────────────────────────────────────
    def test_diagnose_endpoint_heuristic(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                return await c.get("/api/ai/diagnose?hours=1&use_llm=false", headers=self._headers(token))
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["method"], "heuristic")
        self.assertIn("confidence", body)
        self.assertIn("root_causes", body)
        self.assertIn("suggested_fixes", body)
        self.assertIn("metrics_snapshot", body)
        self.assertIn("log_sources_checked", body)

    def test_diagnose_endpoint_llm_false(self) -> None:
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                return await c.get("/api/ai/diagnose?use_llm=false", headers=self._headers(token))
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["method"], "heuristic")

    def test_diagnose_domain_endpoint(self):
        token = self._login_token()
        async def run():
            async with _make_client() as c:
                return await c.get("/api/ai/diagnose/nonexistent.example.com?use_llm=false", headers=self._headers(token))
        r = self._run(run())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["error"], "Site not found")


if __name__ == "__main__":
    unittest.main()