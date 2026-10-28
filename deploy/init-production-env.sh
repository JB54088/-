#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/production.env"

if [[ -e "$ENV_FILE" ]]; then
  echo "Refusing to overwrite deploy/production.env. Back it up or remove it intentionally first." >&2
  exit 1
fi

read_password() {
  local label="$1" value
  while true; do
    IFS= read -r -s -p "$label (16-128 letters/digits/_/-): " value
    printf '\n'
    if [[ "$value" =~ ^[A-Za-z0-9_-]{16,128}$ ]]; then
      PASSWORD_RESULT="$value"
      return
    fi
    echo "Use 16-128 characters from A-Z, a-z, 0-9, underscore, or hyphen."
  done
}

read_password "Initial admin01 password"; admin01="$PASSWORD_RESULT"
read_password "Initial admin02 password"; admin02="$PASSWORD_RESULT"
read_password "Initial sales01 password"; sales01="$PASSWORD_RESULT"
read_password "Initial sales02 password"; sales02="$PASSWORD_RESULT"
read_password "Initial sales03 password"; sales03="$PASSWORD_RESULT"

if [[ "$admin01" == "$admin02" || "$admin01" == "$sales01" || "$admin01" == "$sales02" || "$admin01" == "$sales03" || \
      "$admin02" == "$sales01" || "$admin02" == "$sales02" || "$admin02" == "$sales03" || \
      "$sales01" == "$sales02" || "$sales01" == "$sales03" || "$sales02" == "$sales03" ]]; then
  echo "Each account must have a different password. No environment file was written." >&2
  exit 1
fi

read -r -p "Browser origin [http://127.0.0.1:8080]: " app_origin
app_origin="${app_origin:-http://127.0.0.1:8080}"
if [[ ! "$app_origin" =~ ^https?://[^[:space:]]+$ ]]; then
  echo "Invalid browser origin. No environment file was written." >&2
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
POSTGRES_DB=customer_assets
POSTGRES_USER=customer_assets
POSTGRES_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_EXPIRE_MINUTES=720
INITIAL_ADMIN01_PASSWORD=$admin01
INITIAL_ADMIN02_PASSWORD=$admin02
INITIAL_SALES01_PASSWORD=$sales01
INITIAL_SALES02_PASSWORD=$sales02
INITIAL_SALES03_PASSWORD=$sales03
APP_ORIGIN=$app_origin
EXCEL_MAX_FILE_SIZE_MB=20
EXCEL_MAX_ROWS=50000
AI_PROVIDER=mock
AI_BASE_URL=
AI_API_KEY=
AI_MODEL=business-analysis-mock
AI_MOCK_MODE=true
EOF
chmod 600 "$ENV_FILE"
echo "Created deploy/production.env with mode 600. Keep it private; this script will not print the passwords."
