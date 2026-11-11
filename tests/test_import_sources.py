import subprocess
from pathlib import Path

from core.import_sources import repo_has_tracked_changes


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_repo_has_tracked_changes_ignores_untracked_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")

    tracked = repo / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial commit")

    assert repo_has_tracked_changes(repo) is False

    (repo / "scratch.txt").write_text("temporary\n", encoding="utf-8")
    assert repo_has_tracked_changes(repo) is False

    tracked.write_text("modified\n", encoding="utf-8")
    assert repo_has_tracked_changes(repo) is True
