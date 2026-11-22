#!/usr/bin/env bash
# Один навантажувальний прогін певної версії коду в окремому оточенні Docker.
#
#   loadtest/bench.sh <назва> <версія> [параметри run.py]
#
#   <назва>   — папка результатів у loadtest/results/
#   <версія>  — "." (поточний код) або git-коміт, напр. 3e95fcd (код до ЛР №7)
#
# Приклад:  loadtest/bench.sh before-50 3e95fcd
#           loadtest/bench.sh after-300 . --users 300 --spawn-rate 20
#
# Оточення створюється в окремому проєкті docker compose (vet-crm-bench) з чистою базою
# в режимі sandbox і після прогону видаляється разом із даними. Основну систему не зачіпає,
# але порт HTTP_PORT (за замовчуванням 80) має бути вільним: спершу виконайте `docker compose down`.
set -euo pipefail

NAME="${1:?Вкажіть назву прогону}"
REF="${2:?Вкажіть версію: . або git-коміт}"
shift 2

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="vet-crm-bench"
PYTHON="${PYTHON:-python3}"
[ -x "$ROOT/.venv/bin/python" ] && PYTHON="$ROOT/.venv/bin/python"

if [ ! -f "$ROOT/.env" ]; then
  echo "Немає файлу .env — створіть його: python scripts/init_env.py" >&2
  exit 1
fi
PORT="$(grep -E '^HTTP_PORT=' "$ROOT/.env" | cut -d= -f2 || true)"
PORT="${PORT:-80}"

WORKTREE=""
SRC="$ROOT"
cleanup() {
  docker compose -p "$PROJECT" --project-directory "$SRC" -f "$SRC/docker-compose.yml" down -v --remove-orphans >/dev/null 2>&1 || true
  if [ -n "$WORKTREE" ]; then
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [ "$REF" != "." ]; then
  # Код іншої версії розгортається в тимчасову папку, робоча копія не змінюється
  WORKTREE="$(mktemp -d)/vet-crm-$REF"
  git -C "$ROOT" worktree add --detach "$WORKTREE" "$REF" >/dev/null
  cp "$ROOT/.env" "$WORKTREE/.env"
  SRC="$WORKTREE"
fi

echo "==> [$NAME] версія: $REF, збирання і запуск (sandbox, чиста база)"
APP_ENV=sandbox docker compose -p "$PROJECT" --project-directory "$SRC" -f "$SRC/docker-compose.yml" \
  up -d --build --wait --wait-timeout 240
docker compose -p "$PROJECT" --project-directory "$SRC" -f "$SRC/docker-compose.yml" ps --format "table {{.Name}}\t{{.Status}}"

echo "==> [$NAME] навантажувальний тест"
"$PYTHON" "$ROOT/loadtest/run.py" baseline --host "http://localhost:$PORT" --docker "$PROJECT" --name "$NAME" "$@"
