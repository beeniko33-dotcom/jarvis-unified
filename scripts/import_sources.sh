#!/usr/bin/env bash
# Import each source repository beneath sources/<repo> without squashing history.
# Run from a clean clone of jarvis-unified with GitHub access to all seven repos.
set -euo pipefail

OWNER="beeniko33-dotcom"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if ! git subtree -h >/dev/null 2>&1; then
  echo "ERROR: git subtree is required. Install/enable the git-subtree command." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree must be clean before importing source history." >&2
  exit 1
fi

# Repository name | default branch
SOURCES=(
  "jarvis-trader-ecosystem|main"
  "jarvis-ai-trading-system|main"
  "jarvis-trader|main"
  "jarvistrader|main"
  "quantum-peak-pro|main"
  "jarvis-ai|master"
  "advanced-scraper|main"
)

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r repo branch <<< "$entry"
  prefix="sources/$repo"
  remote="jarvis-source-$repo"
  url="git@github.com:$OWNER/$repo.git"

  if [[ -e "$prefix" ]]; then
    echo "SKIP: $prefix already exists; inspect it before rerunning."
    continue
  fi

  if git remote get-url "$remote" >/dev/null 2>&1; then
    configured="$(git remote get-url "$remote")"
    if [[ "$configured" != "$url" ]]; then
      echo "ERROR: remote $remote points to unexpected URL: $configured" >&2
      exit 1
    fi
  else
    git remote add "$remote" "$url"
  fi

  echo "Fetching $OWNER/$repo ($branch)..."
  git fetch --no-tags "$remote" "$branch"

  echo "Importing $repo into $prefix with full commit history..."
  # Deliberately omit --squash: the source ancestry is retained.
  git subtree add --prefix="$prefix" "$remote" "$branch" \
    --message="migration: import $repo with full Git history"
done

echo "All available source repositories imported under sources/."
echo "Verify with: git log --oneline --graph --all --decorate"
