#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" != 1 || "$1" != '--legacy' ]]; then
    echo '[停止] 此脚本仅启动旧音乐 Docker 模板。当前国画 R25 发布请使用 r25/ 中的发布流程。' >&2
    echo '如需明确启动旧模板，请运行：./scripts/start.sh --legacy' >&2
    exit 64
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
    echo "[失败] 缺少 .env，请先执行：cp .env.example .env"
    exit 1
fi

docker compose \
    --profile legacy \
    --env-file .env \
    -f docker-compose.yml \
    -f docker-compose.gpu.yml \
    up -d
