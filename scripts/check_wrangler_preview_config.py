"""Validate that Workers Builds can discover the root Wrangler preview config."""
import json
from pathlib import Path

config_path = Path("wrangler.jsonc")
config = json.loads(config_path.read_text(encoding="utf-8"))
assert config.get("name") == "jarvis-control-worker"
assert config.get("main") == "cloudflare/worker.py"
assert (Path("cloudflare") / "worker.py").is_file()
assert isinstance(config.get("previews"), dict)
assert config.get("preview_urls") is True
print("root Wrangler preview configuration is discoverable and valid")
