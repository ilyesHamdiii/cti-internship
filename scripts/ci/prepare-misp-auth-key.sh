#!/usr/bin/env bash
set -euo pipefail

read_env_value() {
  local key="$1"
  if [ -f .env ]; then
    awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' .env
  fi
}

MISP_ADMIN_EMAIL="${MISP_ADMIN_EMAIL:-$(read_env_value MISP_ADMIN_EMAIL)}"
MISP_ADMIN_KEY="${MISP_ADMIN_KEY:-$(read_env_value MISP_ADMIN_KEY)}"

: "${MISP_ADMIN_EMAIL:?MISP_ADMIN_EMAIL is required}"
: "${MISP_ADMIN_KEY:?MISP_ADMIN_KEY is required}"

for attempt in $(seq 1 12); do
  if docker compose exec -T \
    -e MISP_ADMIN_EMAIL="$MISP_ADMIN_EMAIL" \
    -e MISP_ADMIN_KEY="$MISP_ADMIN_KEY" \
    misp bash -lc '
      set -euo pipefail
      cd /var/www/MISP/app
      Console/cake user change_authkey "$MISP_ADMIN_EMAIL" "$MISP_ADMIN_KEY"
      curl -ksSf \
        -H "Authorization: $MISP_ADMIN_KEY" \
        -H "Accept: application/json" \
        https://localhost/users/view/me >/tmp/misp-user.json
      python3 - <<'"'"'PY'"'"'
import json
from pathlib import Path

data = json.loads(Path("/tmp/misp-user.json").read_text())
user = data.get("User", data.get("user", data))
print(f"misp_auth_user={user.get('email', 'unknown')}")
PY
    '; then
    exit 0
  fi

  echo "MISP API key preparation failed on attempt ${attempt}; retrying..."
  sleep 10
done

echo "MISP API key preparation failed after all retry attempts." >&2
exit 1
