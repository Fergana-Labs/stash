#!/usr/bin/env bash
set -euo pipefail

KEY_FILE="${INTEGRATIONS_ENCRYPTION_KEY_FILE:-/app/.secrets/integrations_encryption_key}"

generate_key() {
    python - <<'PY'
import base64
import secrets

print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
PY
}

if [ -z "${INTEGRATIONS_ENCRYPTION_KEY:-}" ]; then
    mkdir -p "$(dirname "$KEY_FILE")"

    if [ ! -s "$KEY_FILE" ]; then
        umask 077
        tmp="${KEY_FILE}.$$"
        generate_key > "$tmp"
        mv "$tmp" "$KEY_FILE"
        echo "[secrets] Generated integrations encryption key at ${KEY_FILE}."
    fi

    INTEGRATIONS_ENCRYPTION_KEY="$(cat "$KEY_FILE")"
    export INTEGRATIONS_ENCRYPTION_KEY
fi

exec "$@"
