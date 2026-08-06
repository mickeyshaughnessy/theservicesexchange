#!/usr/bin/env bash
# Weekly Buy-a-Robot catalog refresh for production cron.
# Install (on prod):
#   15 4 * * 1  /var/www/theservicesexchange/scripts/catalog/run_weekly_catalog_update.sh >> /var/log/rse-catalog-update.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin:${HOME}/.grok/bin:${PATH}"
export RSE_CATALOG_UPLOAD="${RSE_CATALOG_UPLOAD:-1}"
export RSE_CATALOG_USE_GROK="${RSE_CATALOG_USE_GROK:-1}"

# Load optional secrets (XAI_API_KEY, etc.) without printing them
if [[ -f /etc/rse/catalog.env ]]; then
  # shellcheck disable=SC1091
  set -a
  source /etc/rse/catalog.env
  set +a
fi
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

LOG_PREFIX="[rse-catalog $(date -u +%Y-%m-%dT%H:%M:%SZ)]"
echo "${LOG_PREFIX} starting"

PY="${ROOT}/venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
"$PY" scripts/catalog/update_robots_catalog.py

echo "${LOG_PREFIX} finished ok"
