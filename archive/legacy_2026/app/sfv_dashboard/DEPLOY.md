# Live-дашборд «Продажи на борту ПАО АК ЮТэйр» · Инструкция по публикации

Документ для **команды сервиса публикаций**. Описывает, что забрать,
куда положить, как запустить и как обеспечить связь с источником данных
(ClickHouse). Время развертывания «с нуля» — 15–30 минут.

---

## 1. Что забрать из репозитория

Из репозитория `Obligations` нужны **только** файлы из ниже-перечисленного
списка. Ничего другого тащить не надо.

```
app/
└── sfv_dashboard/
    ├── __init__.py
    ├── server.py                     ← FastAPI-приложение (точка входа ASGI)
    ├── queries.py                    ← все SQL-запросы к ClickHouse
    ├── requirements.txt              ← пиннинг runtime-зависимостей
    ├── .env.example                  ← шаблон переменных окружения
    ├── DEPLOY.md                     ← этот файл
    ├── README.md                     ← описание архитектуры (для разработчика)
    ├── core/
    │   ├── __init__.py
    │   └── clickhouse.py             ← подключение к CH (per-thread клиент)
    ├── static/
    │   ├── index.html                ← SPA: layout, фильтры, табы
    │   ├── app.js                    ← клиентская логика, Plotly-чарты
    │   └── style.css                 ← тёмная тема, адаптивная сетка
    └── deploy/
        ├── sfv-dashboard.service     ← готовый systemd unit
        ├── nginx.conf                ← готовый nginx site
        └── healthcheck.sh            ← скрипт мониторинга
```

> **Не нужно:** `data/`, `scripts/`, `notebooks/`, `docs/`, `setupv2/`,
> `venv/`, `__pycache__/` и любые остальные подпапки репозитория.
> Дашборд **читает** уже подготовленные данные из ClickHouse — ему не нужны
> ни Excel, ни Parquet, ни ETL-скрипты.

Целевая структура на сервере публикации:

```
/opt/sfv-dashboard/
├── app/
│   └── sfv_dashboard/                ← всё содержимое блока выше
├── venv/                             ← создаётся при установке
├── .env                              ← создаётся из .env.example, chmod 600
└── logs/                             ← создаётся вручную, owner www-data
```

---

## 2. Системные требования

| Компонент              | Версия                         |
|------------------------|--------------------------------|
| OS                     | Linux (Debian 11+/Ubuntu 22.04+/RHEL 8+) |
| Python                 | 3.10 — 3.12                    |
| pip                    | любой современный              |
| nginx (опционально)    | 1.18+                          |
| systemd                | да (для автозапуска)           |
| RAM                    | 256 МБ                         |
| CPU                    | 1 vCPU достаточно              |
| Дисковое место         | ≤ 200 МБ (включая venv)        |

Сетевой доступ — см. п. 5.

---

## 3. Установка

```bash
# 1. Создать каталог и положить код
sudo mkdir -p /opt/sfv-dashboard/{logs}
sudo chown -R www-data:www-data /opt/sfv-dashboard

# Скопировать app/sfv_dashboard/ из репо в /opt/sfv-dashboard/app/sfv_dashboard/
# (любым удобным способом: rsync, git clone + sparse, артефакт CI и т.д.)

# 2. Создать virtualenv и поставить зависимости
sudo -u www-data python3 -m venv /opt/sfv-dashboard/venv
sudo -u www-data /opt/sfv-dashboard/venv/bin/pip install --upgrade pip
sudo -u www-data /opt/sfv-dashboard/venv/bin/pip install \
    -r /opt/sfv-dashboard/app/sfv_dashboard/requirements.txt

# 3. Подготовить .env
sudo cp /opt/sfv-dashboard/app/sfv_dashboard/.env.example \
        /opt/sfv-dashboard/.env
sudo chown www-data:www-data /opt/sfv-dashboard/.env
sudo chmod 600 /opt/sfv-dashboard/.env
sudo nano /opt/sfv-dashboard/.env       # ← вписать актуальные секреты

# 4. Smoke-тест ДО systemd:
sudo -u www-data bash -c '
    cd /opt/sfv-dashboard &&
    set -a && . ./.env && set +a &&
    venv/bin/uvicorn app.sfv_dashboard.server:app --host 127.0.0.1 --port 8765
'
# В другом терминале:
curl -s http://127.0.0.1:8765/api/health | jq .
# Ожидаемо: {"status":"ok","ch_version":"24.x.x.x","table":"sfv.catering_items","rows":<N>}
# Затем Ctrl+C прервать.
```

Если `health` ответил `status:ok` и `rows > 0` — связь с БД есть, можно
ставить под systemd (п. 4).

---

## 4. Автозапуск под systemd

```bash
sudo cp /opt/sfv-dashboard/app/sfv_dashboard/deploy/sfv-dashboard.service \
        /etc/systemd/system/sfv-dashboard.service

sudo systemctl daemon-reload
sudo systemctl enable --now sfv-dashboard
sudo systemctl status  sfv-dashboard       # проверить — Active: running
sudo journalctl -u sfv-dashboard -f        # смотреть логи в realtime
```

Перезапуск после правки `.env` или кода:

```bash
sudo systemctl restart sfv-dashboard
```

---

## 5. Связь с базой данных (ClickHouse)

Дашборд **полностью stateless**: он не хранит у себя никаких данных,
все запросы выполняются «вживую» к ClickHouse. Если БД доступна — дашборд
работает; если нет — отдаёт `5xx`.

### 5.1 Что нужно от сети / firewall

С хоста, где живёт дашборд, должна быть открыта **исходящая** TCP-связь:

| Назначение            | Адрес              | Порт | Протокол       |
|-----------------------|--------------------|------|----------------|
| ClickHouse (native)   | `10.95.19.132`     | 9000 | TCP (бинарный) |

Проверка с сервера публикации:

```bash
# 1) сетевой уровень
nc -zv 10.95.19.132 9000
# expected: Connection to 10.95.19.132 9000 port [tcp/*] succeeded!

# 2) прикладной уровень — без установки клиентов:
sudo -u www-data /opt/sfv-dashboard/venv/bin/python - <<'PY'
import os
from dotenv import load_dotenv
from clickhouse_driver import Client
load_dotenv("/opt/sfv-dashboard/.env")
c = Client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ.get("CLICKHOUSE_PORT", 9000)),
    user=os.environ["CLICKHOUSE_USER"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
    database=os.environ.get("CLICKHOUSE_DATABASE","default"),
    connect_timeout=10,
)
print("CH version:", c.execute("SELECT version()")[0][0])
print("rows in source table:", c.execute("SELECT count() FROM sfv.catering_items")[0][0])
PY
```

Если оба запроса прошли — связь полностью работоспособна.

### 5.2 Креды ClickHouse

Передаются **исключительно** через `.env`. Путь — `/opt/sfv-dashboard/.env`,
права `600`, владелец `www-data`. Внутри ровно 5 ключей:

```
CLICKHOUSE_HOST=10.95.19.132
CLICKHOUSE_PORT=9000
CLICKHOUSE_USER=<логин>
CLICKHOUSE_PASSWORD=<пароль>
CLICKHOUSE_DATABASE=default
```

Никаких других переменных дашборду не требуется. **Не** хранить пароль
в git, в systemd unit, в логах nginx и в URL.

### 5.3 Источник данных

Дашборд читает одну таблицу: `sfv.catering_items` (денормализованный
снимок 60 еженедельных Excel-отчётов от поставщика). За её актуализацию
отвечает отдельный ETL-пайплайн (`scripts/analytics/02_etl_sfv.py`
+ `07_load_to_clickhouse.py` в репозитории). Команде публикации
эти скрипты **не нужны** — дашборд просто читает уже залитые данные.

Контракт таблицы (читать только, никаких прав на запись не требуется):

```
sfv.catering_items
├── shipment_id        UInt64
├── shipment_date      Date
├── flight_out         Nullable(Int32)
├── item_sku           LowCardinality(String)
├── item_name          String
├── item_category      LowCardinality(String)
├── loaded_qty         UInt32
├── sold_qty           UInt32
├── returned_qty       Int32
├── price              Float64
├── revenue            Float64
└── return_pct         Float64
```

Минимально достаточные права пользователя CH:

```sql
GRANT SELECT ON sfv.catering_items TO <логин>;
```

---

## 6. Публикация наружу через nginx

```bash
sudo cp /opt/sfv-dashboard/app/sfv_dashboard/deploy/nginx.conf \
        /etc/nginx/sites-available/sfv-dashboard.conf

# Заменить server_name в файле на реальный DNS-алиас интранет-портала.
sudo nano /etc/nginx/sites-available/sfv-dashboard.conf

sudo ln -sf /etc/nginx/sites-available/sfv-dashboard.conf \
            /etc/nginx/sites-enabled/sfv-dashboard.conf

sudo nginx -t && sudo systemctl reload nginx
```

После этого дашборд доступен по `http://<dns-имя>/`.
Если интранет-портал требует HTTPS — добавьте блок `listen 443 ssl;`
с корпоративным сертификатом (TLS-разверткой занимается команда
публикации, к коду дашборда отношения не имеет).

---

## 7. Мониторинг

### Healthcheck-эндпоинт

`GET /api/health` всегда возвращает `200 OK` с JSON, если дашборд
сам жив **и** добрался до ClickHouse:

```json
{
  "status": "ok",
  "ch_version": "24.10.x.x",
  "table": "sfv.catering_items",
  "rows": 84231
}
```

Если ClickHouse недоступен — будет `5xx` или JSON с ошибкой.
Этого достаточно для blackbox-мониторинга (Zabbix HTTP-агент,
Prometheus blackbox-exporter и т.п.).

### Готовый скрипт

```bash
/opt/sfv-dashboard/app/sfv_dashboard/deploy/healthcheck.sh
# exit 0 = OK, exit 1 = DOWN/DEGRADED
```

---

## 8. Чек-лист после публикации

- [ ] `systemctl status sfv-dashboard` → `Active: running`
- [ ] `curl http://127.0.0.1:8765/api/health` → `status:"ok"`, `rows > 0`
- [ ] `curl http://<dns>/api/health` → то же, через nginx
- [ ] Открыть `http://<dns>/` в браузере: видно шапку «Продажи на борту…»
- [ ] Все 4 вкладки (Обзор / SKU / Рейсы / Паттерны) рендерят виджеты
      без ошибок «Ошибка обновления: API …»
- [ ] Применение фильтра (любая дата/категория) перестраивает виджеты
- [ ] `journalctl -u sfv-dashboard --since "5 minutes ago"` — нет тррейсов
- [ ] Передать DNS-адрес интернет-портала владельцу продукта

---

## 9. Обновление версии

```bash
# 1) Положить новые файлы поверх (rsync / git pull / артефакт CI).
# 2) Если изменились зависимости — переустановить:
sudo -u www-data /opt/sfv-dashboard/venv/bin/pip install \
    --upgrade -r /opt/sfv-dashboard/app/sfv_dashboard/requirements.txt
# 3) Перезапустить:
sudo systemctl restart sfv-dashboard
# 4) Проверить healthcheck.
```

`.env` при обновлении **не трогать**.

---

## 10. Откат

systemd unit и `.env` остаются прежними; код версионируется отдельно.
Простейший откат — вернуть предыдущую копию каталога `app/sfv_dashboard/`
и `systemctl restart sfv-dashboard`. Состояния у приложения нет, миграций
БД оно не делает — откат полностью безопасен.

---

## 11. Контакты по вопросам

| Тема                         | Кому                                           |
|------------------------------|------------------------------------------------|
| Код / SQL / виджеты          | владелец репозитория `Obligations`             |
| Доступ к ClickHouse          | команда DWH (10.95.19.132)                     |
| Источник Excel-отчётов       | поставщик данных (см. договор)                 |
| ETL / актуализация таблицы   | владелец `scripts/analytics/*` в репозитории   |
| Публикация / DNS / TLS       | команда сервиса публикаций (вы)                |
