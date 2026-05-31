"""Tests for new v0.3.0, v0.4.0, and v1.0.0 features."""
import os
import json
import tempfile
import pytest
import unittest
from pathlib import Path
from typing import Any

from atulya_launch.web.database import init_db, connect, audit_log, reset_db


class _DBTestBase(unittest.TestCase):
    """Base class that initializes a test database with a default admin user."""
    def setUp(self) -> None:
        reset_db()
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmp.name)
        init_db(self.config_dir, force=True)
        from atulya_launch.web.auth import create_user
        with connect() as cur:
            row = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()
            if row["c"] == 0:
                create_user("admin", "admin", skip_policy=True)

    def tearDown(self) -> None:
        import gc
        gc.collect()
        for f in Path(self.tmp.name).glob("panel.db*"):
            try:
                f.unlink()
            except Exception:
                pass
        self.tmp.cleanup()


# ─── v0.3.0: Migration Import ────────────────────────────────────────────────

class TestMigrations(_DBTestBase):
    def test_migration_sources_defined(self) -> None:
        from atulya_launch.core import MIGRATION_SOURCES
        assert "cpanel" in MIGRATION_SOURCES
        assert "plesk" in MIGRATION_SOURCES
        assert "hestiacp" in MIGRATION_SOURCES

    def test_migration_import_missing_file(self) -> None:
        from atulya_launch.core import migration_import
        result = migration_import("cpanel", "/nonexistent/file.tar.gz")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_migration_import_unknown_source(self) -> None:
        from atulya_launch.core import migration_import
        result = migration_import("unknown_source", "test.tar")
        assert result["ok"] is False
        assert "unknown source" in result["error"]

    def test_migration_list(self) -> None:
        from atulya_launch.core import migration_list
        result = migration_list()
        assert isinstance(result, list)


# ─── v0.3.0: Reseller Plans ──────────────────────────────────────────────────

class TestPlans(_DBTestBase):
    def test_plan_create_and_list(self) -> None:
        from atulya_launch.core import plan_create, plan_list, plan_delete
        plan_create("test_plan", sites_limit=5, disk_limit_mb=1024, db_limit=3, email_limit=10, price_monthly=9.99)
        plans = plan_list()
        names = [p["name"] for p in plans]
        assert "test_plan" in names
        for p in plans:
            if p["name"] == "test_plan":
                plan_delete(p["id"])
                break

    def test_plan_delete(self) -> None:
        from atulya_launch.core import plan_create, plan_list, plan_delete
        plan_create("del_test")
        plans = plan_list()
        for p in plans:
            if p["name"] == "del_test":
                plan_delete(p["id"])
                break
        plans = plan_list()
        names = [p["name"] for p in plans]
        assert "del_test" not in names

    def test_plan_assign(self) -> None:
        from atulya_launch.core import plan_create, plan_list, plan_assign, plan_user_get, plan_delete
        plan_create("assign_plan")
        plan_id = None
        plans = plan_list()
        for p in plans:
            if p["name"] == "assign_plan":
                plan_id = p["id"]
                break
        assert plan_id is not None
        with connect() as cur:
            user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
        assert user is not None
        plan_assign(user["id"], plan_id)
        user_plan = plan_user_get(user["id"])
        assert user_plan is not None
        plan_delete(plan_id)

    def test_check_user_limits(self) -> None:
        from atulya_launch.core import check_user_limits
        with connect() as cur:
            user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
        result = check_user_limits(user["id"])
        assert "allowed" in result


# ─── v0.3.0: WordPress Installer ─────────────────────────────────────────────

class TestWordPress(_DBTestBase):
    def test_wordpress_creates_site(self) -> None:
        from atulya_launch.core import wordpress_install, site_delete
        domain = "wp-test-" + os.urandom(4).hex() + ".example.com"
        result = wordpress_install(domain)
        assert isinstance(result, dict)
        assert "domain" in result
        site_delete(domain)


# ─── v0.4.0: App Deployment ──────────────────────────────────────────────────

class TestDeploy(_DBTestBase):
    def test_deploy_app_and_list(self) -> None:
        from atulya_launch.core import deploy_app, deploy_list, deploy_delete
        name = "test-app-" + os.urandom(4).hex()
        result = deploy_app(name, name + ".example.com", app_type="node", entry_point="server.js", port=4000)
        assert result["ok"] is True
        apps = deploy_list()
        names = [a["name"] for a in apps]
        assert name in names
        for a in apps:
            if a["name"] == name:
                deploy_delete(a["id"])
                break

    def test_deploy_delete(self) -> None:
        from atulya_launch.core import deploy_app, deploy_list, deploy_delete
        name = "del-app-" + os.urandom(4).hex()
        deploy_app(name, name + ".example.com")
        apps = deploy_list()
        for a in apps:
            if a["name"] == name:
                deploy_delete(a["id"])
                break
        apps = deploy_list()
        names = [a["name"] for a in apps]
        assert name not in names

    def test_deploy_start_stop(self) -> None:
        from atulya_launch.core import deploy_app, deploy_list, deploy_start, deploy_stop, deploy_delete
        name = "ctl-app-" + os.urandom(4).hex()
        deploy_app(name, name + ".example.com", app_type="node", entry_point="app.js", port=4001)
        apps = deploy_list()
        app_id = None
        for a in apps:
            if a["name"] == name:
                app_id = a["id"]
                break
        assert app_id is not None
        result = deploy_start(app_id)
        assert result["ok"] is True
        result = deploy_stop(app_id)
        assert result["ok"] is True
        deploy_delete(app_id)


# ─── v0.4.0: Cron Jobs ───────────────────────────────────────────────────────

class TestCron(_DBTestBase):
    def test_cron_create_and_list(self) -> None:
        from atulya_launch.core import cron_create, cron_list, cron_delete
        with connect() as cur:
            user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
        cron_create(user["id"], "echo hello", "0 * * * *")
        jobs = cron_list()
        assert len(jobs) >= 1
        for j in jobs:
            cron_delete(j["id"])

    def test_cron_toggle(self) -> None:
        from atulya_launch.core import cron_create, cron_list, cron_toggle, cron_delete
        with connect() as cur:
            user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
        cron_create(user["id"], "echo test", "*/5 * * * *")
        jobs = cron_list()
        for j in jobs:
            if j["command"] == "echo test":
                cron_toggle(j["id"], 0)
                break
        jobs = cron_list()
        for j in jobs:
            if j["command"] == "echo test":
                assert j["enabled"] == 0
                cron_delete(j["id"])
                break

    def test_cron_delete(self) -> None:
        from atulya_launch.core import cron_create, cron_list, cron_delete
        with connect() as cur:
            user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
        cron_create(user["id"], "echo delete_me", "0 0 * * *")
        jobs = cron_list()
        for j in jobs:
            if j["command"] == "echo delete_me":
                cron_delete(j["id"])
                break
        jobs = cron_list()
        assert not any(j["command"] == "echo delete_me" for j in jobs)


# ─── v0.4.0: Log Viewer ──────────────────────────────────────────────────────

class TestLogs(unittest.TestCase):
    def test_log_sources_list(self) -> None:
        from atulya_launch.core import log_list_sources
        sources = log_list_sources()
        assert isinstance(sources, list)
        keys = [s["key"] for s in sources]
        assert "nginx_access" in keys
        assert "panel" in keys

    def test_log_view_panel(self) -> None:
        from atulya_launch.core import log_view
        result = log_view("panel", lines=10)
        assert "ok" in result
        assert isinstance(result.get("lines"), list)

    def test_log_view_unknown_source(self) -> None:
        from atulya_launch.core import log_view
        result = log_view("nonexistent_source")
        assert result["ok"] is False
        assert "unknown" in result["error"]


# ─── v1.0.0: Security Audit ──────────────────────────────────────────────────

class TestSecurityAudit(_DBTestBase):
    def test_comprehensive_security_audit_returns_results(self) -> None:
        from atulya_launch.core import comprehensive_security_audit
        result = comprehensive_security_audit()
        assert "score" in result
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

    def test_security_audit_score_range(self) -> None:
        from atulya_launch.core import comprehensive_security_audit
        result = comprehensive_security_audit()
        assert 0 <= result["score"] <= 100


# ─── v1.0.0: Load Testing ────────────────────────────────────────────────────

class TestLoadTest(unittest.TestCase):
    def test_load_test_runs(self) -> None:
        from atulya_launch.core import load_test
        result = load_test("http://127.0.0.1:1", requests=2, concurrency=1)
        assert "ok" in result
        assert result["total_requests"] == 2

    def test_load_test_summary_keys(self) -> None:
        from atulya_launch.core import load_test
        result = load_test("http://127.0.0.1:2", requests=3, concurrency=1)
        for key in ("target", "total_requests", "concurrency", "success", "errors", "total_time", "avg_time", "requests_per_sec"):
            assert key in result


# ─── v1.0.0: Multi-Server ────────────────────────────────────────────────────

class TestServers(_DBTestBase):
    def test_server_create_and_list(self) -> None:
        from atulya_launch.core import server_create, server_list, server_delete
        name = "test-server-" + os.urandom(4).hex()
        result = server_create(name, "192.168.1.1", port=22, username="root", auth_type="password", auth_data="secret")
        assert result["ok"] is True
        servers = server_list()
        names = [s["name"] for s in servers]
        assert name in names
        for s in servers:
            if s["name"] == name:
                server_delete(s["id"])
                break

    def test_server_list_returns_list(self) -> None:
        from atulya_launch.core import server_list
        result = server_list()
        assert isinstance(result, list)


# ─── v1.0.0: Branding ────────────────────────────────────────────────────────

class TestBranding(_DBTestBase):
    def test_branding_set_and_get(self) -> None:
        from atulya_launch.core import branding_set, branding_get, branding_delete
        branding_set("test_key", "test_value")
        val = branding_get("test_key")
        assert val == "test_value"
        branding_delete("test_key")

    def test_branding_get_default(self) -> None:
        from atulya_launch.core import branding_get
        val = branding_get("nonexistent_key", default="fallback")
        assert val == "fallback"

    def test_branding_get_all(self) -> None:
        from atulya_launch.core import branding_set, branding_get_all, branding_delete
        branding_set("k1", "v1")
        branding_set("k2", "v2")
        all_b = branding_get_all()
        assert "k1" in all_b
        assert "k2" in all_b
        branding_delete("k1")
        branding_delete("k2")

    def test_branding_delete(self) -> None:
        from atulya_launch.core import branding_set, branding_get, branding_delete
        branding_set("temp_key", "temp_val")
        branding_delete("temp_key")
        val = branding_get("temp_key")
        assert val is None
