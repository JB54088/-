#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-$PROJECT_DIR/.tools/cloudflared}"
TUNNEL_LOG="${TUNNEL_LOG:-/tmp/customer-assets-cloudflared.log}"
CAFFEINATE_LOG="${CAFFEINATE_LOG:-/tmp/customer-assets-caffeinate.log}"

cd "$PROJECT_DIR"

if [[ ! -x "$CLOUDFLARED_BIN" ]]; then
  echo "找不到 cloudflared：$CLOUDFLARED_BIN" >&2
  echo "请先安装 Apple 芯片版 cloudflared，或设置 CLOUDFLARED_BIN。" >&2
  exit 1
fi

docker compose up -d

if ! pgrep -f 'caffeinate -dimsu' >/dev/null 2>&1; then
  nohup caffeinate -dimsu >"$CAFFEINATE_LOG" 2>&1 </dev/null &
fi

tunnel_pattern='cloudflared tunnel --no-autoupdate --protocol http2 --url http://127\.0\.0\.1:3000'
if ! pgrep -f "$tunnel_pattern" >/dev/null 2>&1; then
  : >"$TUNNEL_LOG"
  nohup "$CLOUDFLARED_BIN" tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:3000 >"$TUNNEL_LOG" 2>&1 </dev/null &
else
  echo "检测到已有 Quick Tunnel 进程，未重复启动。"
  exit 0
fi

for _ in {1..30}; do
  if grep -Eo 'https://[^[:space:]]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -1; then
    echo ""
    echo "Quick Tunnel 已启动；保持这个 Mac 开机并联网即可。"
    exit 0
  fi
  sleep 1
done

echo "Tunnel 尚未输出公网地址，请查看日志：$TUNNEL_LOG" >&2
exit 1
