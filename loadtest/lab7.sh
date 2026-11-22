#!/usr/bin/env bash
# Повний порівняльний експеримент ЛР №7: «ДО» (код ЛР №6) проти «ПІСЛЯ» (поточний код).
#
#   loadtest/lab7.sh            # ~16 хвилин
#   BEFORE=3e95fcd loadtest/lab7.sh
#
# Прогони:
#   before-50 / after-50                    — профіль ЛР №4: 50 VUsers, розгін 5/с, 3 хв
#   before-300 / after-300-nocache / after-300 — навантаження ЛР №6: 300 VUsers, розгін 20/с, 3 хв;
#                                              «nocache» — усі оптимізації, крім Redis, щоб оцінити внесок кешу
set -euo pipefail
cd "$(dirname "$0")/.."
BEFORE="${BEFORE:-3e95fcd}"
PYTHON="python3"
[ -x .venv/bin/python ] && PYTHON=".venv/bin/python"

echo "Зупиняю основну систему, щоб звільнити порт"
docker compose down >/dev/null 2>&1 || true

HEAVY=(--users 300 --spawn-rate 20)
loadtest/bench.sh before-50 "$BEFORE"
loadtest/bench.sh after-50 .
loadtest/bench.sh before-300 "$BEFORE" "${HEAVY[@]}"
CACHE_ENABLED=false loadtest/bench.sh after-300-nocache . "${HEAVY[@]}"
loadtest/bench.sh after-300 . "${HEAVY[@]}"

"$PYTHON" loadtest/compare.py --out lab7-profile-lab4 --title "ЛР №7: ДО і ПІСЛЯ оптимізації (профіль ЛР №4, 50 VUsers)" \
  before-50 after-50
"$PYTHON" loadtest/compare.py --out lab7-300-users --title "ЛР №7: ДО і ПІСЛЯ оптимізації (300 VUsers)" \
  before-300 after-300-nocache after-300

echo
echo "Готово. Звіти: loadtest/results/lab7-profile-lab4.md і loadtest/results/lab7-300-users.md"
echo "Повернути основну систему: docker compose up -d --build"
