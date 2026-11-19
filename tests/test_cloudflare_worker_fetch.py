import importlib.util
import json
import sys
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


def test_market_analysis_collector_uses_machine_token_and_validates_result(monkeypatch):
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

    module = load_worker(monkeypatch, fake_fetch)
    worker = module.Default()
    worker.env = SimpleNamespace(
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SECRET_KEY="project-secret",
        JARVIS_INGEST_TOKEN="collector-token",
    )

    result = __import__("asyncio").run(worker._collect_market_analysis())

    assert result == {
        "status": "collected",
        "provider": "Gate.io public spot REST",
        "instrument": "BTCUSDT",
        "timeframe": "5m",
        "trust": "candidate_unverified",
        "evidence_credit": False,
        "live_orders": 0,
    }
    assert len(calls) == 1
    resource, options = calls[0]
    assert resource == "https://project.supabase.co/functions/v1/market-analysis"
    assert options["method"] == "POST"
    assert options["headers"]["apikey"] == "project-secret"
    assert options["headers"]["x-jarvis-ingest-token"] == "collector-token"
    assert options["body"] == "{}"


def test_market_analysis_collector_skips_when_machine_token_is_missing(monkeypatch):
    calls = []

    async def fake_fetch(resource, **options):
        calls.append((resource, options))
        return UpstreamResponse()

    module = load_worker(monkeypatch, fake_fetch)
    worker = module.Default()
    worker.env = SimpleNamespace(
        SUPABASE_URL="https://project.supabase.co",
        SUPABASE_SECRET_KEY="project-secret",
    )

    result = __import__("asyncio").run(worker._collect_market_analysis())

    assert result == {"status": "skipped_not_configured"}
    assert calls == []


def test_market_analysis_schedule_runs_every_five_minutes():
    from datetime import datetime, timezone

    module = load_worker(__import__("pytest").MonkeyPatch(), lambda *a, **k: None)
    assert module.should_collect_market_analysis(datetime(2026, 11, 19, 6, 10, tzinfo=timezone.utc))
    assert module.should_collect_market_analysis(datetime(2026, 11, 19, 6, 15, tzinfo=timezone.utc))
    assert not module.should_collect_market_analysis(datetime(2026, 11, 19, 6, 11, tzinfo=timezone.utc))
