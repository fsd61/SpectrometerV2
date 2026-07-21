#!/usr/bin/env bash
#
# push_to_origin.sh — push the SpectrometerV2 migration work to origin.
#
# Usage:
#   ./push_to_origin.sh            # push the feature branch + tag (default, safe)
#   ./push_to_origin.sh main       # fast-forward main to the branch, push main + tag
#   ./push_to_origin.sh /path/to/repo [branch|main]   # explicit repo path
#
set -euo pipefail

BRANCH="sprint-1-skeleton"
TAG="baseline-v1.0"
REMOTE="origin"

# --- resolve arguments: optional repo path, optional mode ---
MODE="branch"
REPO="."
for arg in "$@"; do
  case "$arg" in
    branch|main) MODE="$arg" ;;
    *) REPO="$arg" ;;
  esac
done

cd "$REPO"
# move to the repo root regardless of where we were invoked
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
echo ">> Repository: $REPO_ROOT"

# --- preflight checks ---
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "!! Not a git working tree: $REPO_ROOT" >&2; exit 1
fi
if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "!! Local branch '$BRANCH' not found." >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "!! Working tree has uncommitted changes — commit or stash first." >&2
  git status --short; exit 1
fi

echo ">> Verifying remote '$REMOTE' is reachable..."
if ! git ls-remote --exit-code "$REMOTE" >/dev/null 2>&1; then
  echo "!! Cannot reach remote '$REMOTE':"
  git remote get-url "$REMOTE" || true
  echo "   Fix it, e.g.:  git remote set-url $REMOTE <reachable-url-or-path>" >&2
  exit 1
fi

# --- push ---
if [ "$MODE" = "main" ]; then
  echo ">> Fast-forwarding main to $BRANCH and pushing..."
  git switch main
  if ! git merge --ff-only "$BRANCH"; then
    echo "!! main cannot fast-forward from $BRANCH (it has diverged)." >&2
    echo "   Push the branch instead:  ./push_to_origin.sh branch" >&2
    exit 1
  fi
  git push "$REMOTE" main
else
  echo ">> Pushing branch '$BRANCH'..."
  git push -u "$REMOTE" "$BRANCH"
fi

echo ">> Pushing tag '$TAG'..."
git push "$REMOTE" "$TAG"

echo ">> Done. Remote now has:"
git ls-remote --heads --tags "$REMOTE" | grep -E "$BRANCH|main|$TAG" || true

