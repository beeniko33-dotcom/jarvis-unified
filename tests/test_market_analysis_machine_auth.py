from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_market_analysis_handler_verifies_users_and_machine_collectors():
    source = (ROOT / "supabase" / "functions" / "market-analysis" / "index.ts").read_text()
    config = (ROOT / "supabase" / "config.toml").read_text()

    assert "[functions.market-analysis]" in config
    assert "verify_jwt = false" in config.split("[functions.market-analysis]", 1)[1]
    assert "x-jarvis-ingest-token" in source
    assert "tokenMatches" in source
    assert '"/auth/v1/user"' in source
    assert "isAllowlistedOperator(userId)" in source
    assert "jwtClaims" not in source
    assert "order_authorized: false" in source
    assert "live_execution: false" in source
