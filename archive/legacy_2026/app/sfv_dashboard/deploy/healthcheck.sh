#!/usr/bin/env bash
# Простой healthcheck дашборда. Возвращает exit 0 если жив, иначе 1.
# Можно подвязать к Zabbix/мониторингу или systemd timer.

set -uo pipefail

URL="${1:-http://127.0.0.1:8765/api/health}"

resp="$(curl -fsS --max-time 10 "$URL" 2>/dev/null)" || {
    echo "DOWN: $URL не отвечает"
    exit 1
}

# Ожидаем JSON {"status":"ok","ch_version":"...","table":"sfv.catering_items","rows":N}
if echo "$resp" | grep -q '"status":"ok"'; then
    rows="$(echo "$resp" | grep -oE '"rows":[0-9]+' | head -1 | cut -d: -f2)"
    echo "OK: dashboard alive, ${rows:-?} rows in source table"
    exit 0
else
    echo "DEGRADED: $resp"
    exit 1
fi
