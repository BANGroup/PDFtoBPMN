#!/usr/bin/env bash
# Ночная обработка канона (TASK-021, направление C): запуск после bnd_sync (01:00).
# Cron: 15 3 * * * /home/budnik_an/Obligations/poc/canon_assembly/reeng/cron_nightly_canon.sh (после validator post-gate)
# Лог: data/canon_reeng/live/logs/YYYYMMDD_HHMMSS.log, отчёт: data/canon_reeng/live/reports/latest.md
# Выход: 0 успех, 2 уже идёт, 3 bnd_sync не завершился. Сборка без Word (py-движок); Word (PowerShell из WSL) — только проверка открытия готовых.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/mnt/c/Windows/System32/WindowsPowerShell/v1.0"
REPO_ROOT="/home/budnik_an/Obligations"
LOG_DIR="${REPO_ROOT}/data/canon_reeng/live/logs"
mkdir -p "${LOG_DIR}"
cd "${REPO_ROOT}"
PY="${REPO_ROOT}/venv/bin/python3"
[ -x "${PY}" ] || PY="/usr/bin/python3"
exec "${PY}" "${REPO_ROOT}/poc/canon_assembly/reeng/nightly_canon.py" "$@" >> "${LOG_DIR}/$(date +%Y%m%d_%H%M%S).log" 2>&1
