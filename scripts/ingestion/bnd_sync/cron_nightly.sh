#!/usr/bin/env bash
# Ночная сборка каталогов БНД (doc-catalog.json) + РПП (rpp-catalog.json)
# и RAG-зеркала файлов (data/bnd_corpus/) из WSL Ubuntu-22.04 cron.
#
# Каталоги пишутся в BND_WEBBI_DIR (дефолт /home/budnik_an/todo/webBI — их
# читает портал через bind mount). Отчёт — личными сообщениями от бота ДВК
# в Mattermost (BND_REPORT_MM_USERS).
#
# Cron: 0 1 * * * /home/budnik_an/Obligations/scripts/ingestion/bnd_sync/cron_nightly.sh
# Лог:  /home/budnik_an/Obligations/data/bnd_sync/logs/YYYYMMDD_HHMMSS.log
#       /home/budnik_an/Obligations/data/bnd_sync/logs/cron.log  (вывод самого cron'а)
#
# Поведение:
#   - синхронный запуск python-оркестратора (cron ждёт окончания);
#   - PID-lock через flock — параллельный второй запуск отметается;
#   - выход 0 при успехе, 1 при ошибке build, 2 если процесс уже идёт.

set -euo pipefail

# Cron-окружение урезает PATH. Для python3 нужен /usr/bin.
export PATH="/usr/local/bin:/usr/bin:/bin"

REPO_ROOT="/home/budnik_an/Obligations"
LOG_DIR="${REPO_ROOT}/data/bnd_sync/logs"
LOCK_FILE="${LOG_DIR}/.lock"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/${TS}.cron.log"

mkdir -p "${LOG_DIR}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] bnd_sync: уже выполняется, выходим" \
    | tee -a "${LOG_DIR}/cron.log"
  exit 2
fi

{
  echo "[$(date -Iseconds)] bnd_sync: старт"
  cd "${REPO_ROOT}"

  if /usr/bin/python3 "${REPO_ROOT}/scripts/ingestion/bnd_sync/run_nightly.py" \
       >> "${LOG_FILE}" 2>&1; then
    echo "[$(date -Iseconds)] bnd_sync: финиш OK"
    EXIT=0
  else
    EXIT=$?
    echo "[$(date -Iseconds)] bnd_sync: ОШИБКА exit=${EXIT} (лог: ${LOG_FILE})"
  fi
  exit "${EXIT}"
} | tee -a "${LOG_DIR}/cron.log"
