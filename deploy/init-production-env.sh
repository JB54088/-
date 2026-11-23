#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ -e "$ENV_FILE" ]]; then
  echo "Refusing to overwrite .env. Back it up or remove it intentionally first." >&2
  exit 1
fi

read_password() {
  local label="$1" value
  while true; do
    IFS= read -r -s -p "$label (exactly 11 characters: letters/digits/_/-): " value
    printf '\n'
    if [[ "$value" =~ ^[A-Za-z0-9_-]{11}$ ]]; then
      PASSWORD_RESULT="$value"
      return
    fi
    echo "Use exactly 11 characters from A-Z, a-z, 0-9, underscore, or hyphen."
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

read -r -p "Aliyun RDS host (e.g. pgm-xxxx.pg.rds.aliyuncs.com): " rds_url
read -r -p "Aliyun RDS port [5432]: " rds_port
rds_port="${rds_port:-5432}"
read -r -p "Aliyun RDS database name [customer_assets]: " rds_db
rds_db="${rds_db:-customer_assets}"
read -r -p "Aliyun RDS username: " rds_user
IFS= read -r -s -p "Aliyun RDS password: " rds_pwd
printf '\n'
read -r -p "Aliyun RDS CA filename in deploy/certs/ (optional, press Enter to skip): " rds_ca_name
rds_ca_file=""
if [[ -n "$rds_ca_name" ]]; then
  rds_ca_file="/app/certs/$rds_ca_name"
fi

read -r -p "Aliyun OSS bucket name (optional, press Enter to skip): " oss_bucket
read -r -p "Aliyun OSS region [oss-cn-beijing]: " oss_region
oss_region="${oss_region:-oss-cn-beijing}"
oss_ak_id=""
oss_ak_secret=""
if [[ -n "$oss_bucket" ]]; then
  read -r -p "Aliyun AccessKey ID: " oss_ak_id
  IFS= read -r -s -p "Aliyun AccessKey Secret: " oss_ak_secret
  printf '\n'
fi

umask 077
cat > "$ENV_FILE" <<EOF
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
AI_MODEL=business-analysis-mock

# Aliyun RDS PostgreSQL
ALIYUN_RDS_URL=$rds_url
ALIYUN_RDS_PORT=$rds_port
ALIYUN_RDS_DB_NAME=$rds_db
ALIYUN_RDS_USERNAME=$rds_user
ALIYUN_RDS_PWD=$rds_pwd
ALIYUN_RDS_CA_FILE=$rds_ca_file

# Aliyun OSS
OSS_BUCKET_NAME=$oss_bucket
ALIYUN_ACCESS_KEY_ID=$oss_ak_id
ALIYUN_ACCESS_KEY=$oss_ak_secret
ALIYUN_OSS_REGION=$oss_region
OSS_INTERNAL=true
EOF
chmod 600 "$ENV_FILE"
echo "Created .env with mode 600. Keep it private; this script will not print secrets."
