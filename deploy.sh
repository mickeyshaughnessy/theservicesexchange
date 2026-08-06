#!/usr/bin/env bash
# Production deploy: commit already on origin/main → pull on server → restart.
# See DEPLOYMENT_NOTES.md for the full playbook.

set -euo pipefail

SERVER="${RSE_PROD_SERVER:-root@143.110.131.237}"
SSH_KEY="${RSE_SSH_KEY:-$HOME/.ssh/id_ed25519}"
DEPLOY_PATH="${RSE_DEPLOY_PATH:-/var/www/theservicesexchange}"
SERVICE_NAME="theservicesexchange.service"
ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT"

echo "==> Preflight (git + quality)"
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
  echo "    WARN: dirty working tree — deploy will use whatever is already on origin/main"
  echo "    Commit and push first if you meant to ship local changes."
  git status -sb || true
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [[ "$BRANCH" != "main" ]]; then
  echo "    WARN: you are on branch '$BRANCH' (playbook expects main)"
fi

echo "    py_compile…"
python3 -m py_compile api_server.py handlers.py utils.py
echo "    py_compile ok"

if [[ -f ".env" ]]; then
  echo "==> scp .env"
  scp -i "$SSH_KEY" .env "${SERVER}:${DEPLOY_PATH}/.env"
fi

echo "==> Server git pull + restart"
ssh -i "$SSH_KEY" "$SERVER" bash -s <<ENDSSH
set -euo pipefail
cd ${DEPLOY_PATH}
echo "  before: \$(git rev-parse --short HEAD) (\$(git branch --show-current))"
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "  stashing local dirty files…"
  git stash push -m "deploy.sh auto-stash \$(date -u +%Y%m%dT%H%M%SZ)" || true
fi
git fetch origin main
git pull --ff-only origin main
echo "  after:  \$(git rev-parse --short HEAD)"
if systemctl list-unit-files | grep -q ${SERVICE_NAME}; then
  systemctl restart ${SERVICE_NAME}
  sleep 2
  systemctl is-active ${SERVICE_NAME}
else
  echo "  WARN: ${SERVICE_NAME} not found"
fi
ENDSSH

echo "==> Smoke"
if curl -fsS --max-time 10 "https://rse-api.com:5003/ping" >/dev/null 2>&1 \
  || curl -fsS --max-time 10 "https://rse-api.com:5003/stats" >/dev/null 2>&1; then
  echo "  API ok"
else
  echo "  WARN: API smoke failed — check journalctl on server"
fi

# Optional Grok note (never fails the deploy)
if command -v grok >/dev/null 2>&1 && [[ "${RSE_DEPLOY_GROK_FEATURES:-0}" == "1" ]]; then
  echo "==> Grok next-features (RSE_DEPLOY_GROK_FEATURES=1)"
  bash "${ROOT}/scripts/prod/suggest_next_features.sh" || echo "  (skipped — grok failed)"
else
  echo "==> Tip: RSE_DEPLOY_GROK_FEATURES=1 ./deploy.sh  → run Grok 3-feature suggestions after deploy"
fi

echo ""
echo "Deploy complete. Playbook: DEPLOYMENT_NOTES.md"
