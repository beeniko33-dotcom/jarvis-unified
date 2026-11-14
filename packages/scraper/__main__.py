"""Command-line entry point for one-page public metadata extraction."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from typing import Sequence

from . import SafeFetchError, extract_page_metadata


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch one authorized public page and print bounded metadata."
    )
    parser.add_argument("url", help="HTTP(S) URL to a page you are authorized to access")
    args = parser.parse_args(argv)
    try:
        result = extract_page_metadata(args.url)
    except SafeFetchError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
