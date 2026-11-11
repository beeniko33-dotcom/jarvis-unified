from __future__ import annotations

import subprocess
from pathlib import Path


def repo_has_tracked_changes(repo_path: str | Path) -> bool:
    """Return True when the repo has tracked modifications, staged files, or conflicts.

    Untracked files are intentionally ignored because generated artifacts like
    poetry.lock can exist without preventing a safe source-import operation.
    """
    repo = Path(repo_path).resolve()
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git status failed for {repo}: {result.stderr.strip() or result.stdout.strip()}")
    return bool(result.stdout.strip())
