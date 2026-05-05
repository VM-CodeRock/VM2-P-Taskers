#!/bin/sh
# entrypoint.sh — clone or update the repo, configure git, then exec the API.
set -e

REPO_URL="${REPO_URL:-https://github.com/vm-coderock/VM2-P-Taskers.git}"
REPO_PATH="${REPO_PATH:-/repo}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-vm2@changeis.com}"
GIT_USER_NAME="${GIT_USER_NAME:-VM2 Projects API}"

# Inject token into clone URL if available
AUTH_URL="$REPO_URL"
if [ -n "$GITHUB_TOKEN" ]; then
  AUTH_URL=$(echo "$REPO_URL" | sed "s#https://#https://x-access-token:${GITHUB_TOKEN}@#")
fi

if [ ! -d "$REPO_PATH/.git" ]; then
  echo "[entrypoint] Cloning $REPO_URL → $REPO_PATH"
  git clone --depth 50 "$AUTH_URL" "$REPO_PATH"
else
  echo "[entrypoint] Pulling latest in $REPO_PATH"
  git -C "$REPO_PATH" remote set-url origin "$AUTH_URL"
  git -C "$REPO_PATH" fetch origin main
  git -C "$REPO_PATH" reset --hard origin/main
fi

git -C "$REPO_PATH" config user.email "$GIT_USER_EMAIL"
git -C "$REPO_PATH" config user.name "$GIT_USER_NAME"

# Make scripts importable
export PYTHONPATH="$REPO_PATH/scripts:${PYTHONPATH:-}"

echo "[entrypoint] Starting API on port ${PORT:-8000}"
exec "$@"
