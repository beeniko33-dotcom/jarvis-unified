#!/usr/bin/env python3
"""Read-only diagnostic for Jarvis Unified's optional Supabase backend."""
from __future__ import annotations

import argparse
import json
import sys

from research.postgres_evidence_store import PostgresEvidenceStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn-env", default="JARVIS_DATABASE_URL",
        help="environment variable containing the server-side Postgres DSN",
    )
    args = parser.parse_args()
    import os

    dsn = os.environ.get(args.dsn_env)
    if not dsn:
        parser.error(f"required environment variable is not set: {args.dsn_env}")
    try:
        result = PostgresEvidenceStore(dsn).diagnostic()
    except Exception as exc:
        # Do not print exception strings: drivers may echo connection details.
        print(json.dumps({
            "status": "unavailable",
            "error_type": type(exc).__name__,
            "message": "Connection or read-only schema diagnostic failed; details withheld.",
            "writes_performed": False,
        }, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "healthy" else 2


if __name__ == "__main__":
    sys.exit(main())
