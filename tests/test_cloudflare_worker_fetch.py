import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


def load_worker(monkeypatch, fetch_impl):
    fake_workers = ModuleType("workers")

    class WorkerEntrypoint:
        pass

    class Response:
        def __init__(self, body, status=200, headers=None):
            self.body = body
            self.status = status
            self.headers = headers or {}

    fake_workers.WorkerEntrypoint = WorkerEntrypoint
    fake_workers.Response = Response
    fake_workers.fetch = fetch_impl
    monkeypatch.setitem(sys.modules, "workers", fake_workers)

    source = Path(__file__).parents[1] / "cloudflare" / "worker.py"
    module_name = f"jarvis_worker_test_{id(fetch_impl)}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UpstreamResponse:
    ok = True
    status = 202

    async def text(self):
        return '[{"accepted":true}]'


def test_database_fetch_uses_python_worker_keyword_options(monkeypatch):
    calls = []

    async def fake_fetch(resource, **options):
        calls.append((resource, options))
        return UpstreamResponse()

    module = load_worker(monkeypatch, fake_fetch)
    worker = module.Default()
    worker.env = SimpleNamespace(
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SECRET_KEY="test-secret",
    )

    result = __import__("asyncio").run(worker._db("GET", "/operator_status?limit=1"))

    assert result == [{"accepted": True}]
    assert len(calls) == 1
    resource, options = calls[0]
    assert resource == "https://project.supabase.co/rest/v1/operator_status?limit=1"
    assert options["method"] == "GET"
    assert options["headers"]["apikey"] == "test-secret"


def test_market_data_proxy_uses_python_worker_keyword_options(monkeypatch):
    calls = []

    async def fake_fetch(resource, **options):
        calls.append((resource, options))
        return UpstreamResponse()

    module = load_worker(monkeypatch, fake_fetch)
    worker = module.Default()
    worker.env = SimpleNamespace(
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SECRET_KEY="test-secret",
        JARVIS_COLLECTOR_TOKEN="collector-secret",
        JARVIS_INGEST_TOKEN="ingest-secret",
    )
    raw = json.dumps({"provider": "deriv", "symbol": "EURUSD"})
    request = SimpleNamespace(
        url="https://jarvis-control-worker/market-data",
        method="POST",
        headers=SimpleNamespace(get=lambda key, default="": "Bearer collector-secret" if key == "authorization" else default),
        text=lambda: _async_value(raw),
    )

    response = __import__("asyncio").run(worker.fetch(request))

    assert response.status == 202
    assert len(calls) == 1
    resource, options = calls[0]
    assert resource == "https://project.supabase.co/functions/v1/market-data-ingest"
    assert options["method"] == "POST"
    assert options["headers"]["x-jarvis-ingest-token"] == "ingest-secret"
    assert options["body"] == raw


async def _async_value(value):
    return value

def test_runtime_heartbeat_uses_secret_key_only_in_apikey_header(monkeypatch):
    calls = []

    async def fake_fetch(resource, **options):
        calls.append((resource, options))
        return UpstreamResponse()

    module = load_worker(monkeypatch, fake_fetch)
    worker = module.Default()
    worker.env = SimpleNamespace(
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SECRET_KEY="test-secret",
    )

    result = __import__("asyncio").run(worker._runtime_ingest({
        "kind": "heartbeat",
        "worker_id": "cloudflare-control-worker",
        "worker_type": "cloudflare-python-worker",
        "software_version": "control-plane-only-v1",
        "health": "blocked",
        "details": {"kill_switch_engaged": True},
    }))

    assert result == [{"accepted": True}]
    resource, options = calls[0]
    assert resource == "https://project.supabase.co/functions/v1/jarvis-runtime-ingest"
    assert options["method"] == "POST"
    assert options["headers"]["apikey"] == "test-secret"
    assert "authorization" not in {key.lower() for key in options["headers"]}



class _SysModulesPatcher:
    def __init__(self):
        self._previous = []

    def setitem(self, mapping, key, value):
        sentinel = object()
        previous = mapping.get(key, sentinel)
        self._previous.append((mapping, key, previous, sentinel))
        mapping[key] = value

    def undo(self):
        for mapping, key, previous, sentinel in reversed(self._previous):
            if previous is sentinel:
                mapping.pop(key, None)
            else:
                mapping[key] = previous


class TestMarketAnalysisCollector(unittest.TestCase):
    def _load(self, fetch_impl):
        patcher = _SysModulesPatcher()
        module = load_worker(patcher, fetch_impl)
        self.addCleanup(patcher.undo)
        return module

    def test_collector_uses_machine_token_and_validates_result(self):
        calls = []

        class MarketResponse:
            ok = True
            status = 200

            async def text(self):
                return json.dumps({
                    "ok": True,
                    "provider": "Gate.io public spot REST",
                    "instrument": "BTCUSDT",
                    "timeframe": "5m",
                    "trust": "candidate_unverified",
                    "evidence_credit": False,
                    "live_orders": 0,
                })

        async def fake_fetch(resource, **options):
            calls.append((resource, options))
            return MarketResponse()

        module = self._load(fake_fetch)
        worker = module.Default()
        worker.env = SimpleNamespace(
            SUPABASE_URL="https://project.supabase.co",
            SUPABASE_SECRET_KEY="project-secret",
            JARVIS_INGEST_TOKEN="collector-token",
        )

        result = __import__("asyncio").run(worker._collect_market_analysis())

        self.assertEqual(result["status"], "collected")
        self.assertEqual(result["provider"], "Gate.io public spot REST")
        self.assertEqual(result["instrument"], "BTCUSDT")
        self.assertFalse(result["evidence_credit"])
        self.assertEqual(result["live_orders"], 0)
        self.assertEqual(len(calls), 1)
        resource, options = calls[0]
        self.assertEqual(resource, "https://project.supabase.co/functions/v1/market-analysis")
        self.assertEqual(options["method"], "POST")
        self.assertEqual(options["headers"]["apikey"], "project-secret")
        self.assertEqual(options["headers"]["x-jarvis-ingest-token"], "collector-token")
        self.assertEqual(options["body"], "{}")

    def test_collector_skips_when_machine_token_is_missing(self):
        calls = []

        async def fake_fetch(resource, **options):
            calls.append((resource, options))
            return UpstreamResponse()

        module = self._load(fake_fetch)
        worker = module.Default()
        worker.env = SimpleNamespace(
            SUPABASE_URL="https://project.supabase.co",
            SUPABASE_SECRET_KEY="project-secret",
        )

        result = __import__("asyncio").run(worker._collect_market_analysis())

        self.assertEqual(result, {"status": "skipped_not_configured"})
        self.assertEqual(calls, [])

    def test_collector_cadence_is_five_minutes(self):
        from datetime import datetime, timezone

        async def fake_fetch(resource, **options):
            return UpstreamResponse()

        module = self._load(fake_fetch)
        self.assertTrue(module.should_collect_market_analysis(
            datetime(2026, 11, 19, 6, 10, tzinfo=timezone.utc)
        ))
        self.assertTrue(module.should_collect_market_analysis(
            datetime(2026, 11, 19, 6, 15, tzinfo=timezone.utc)
        ))
        self.assertFalse(module.should_collect_market_analysis(
            datetime(2026, 11, 19, 6, 11, tzinfo=timezone.utc)
        ))
