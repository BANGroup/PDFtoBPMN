# SFV Catering · Live-дашборд

Интерактивный дашборд по бортовому питанию ЮТэйр поверх ClickHouse `sfv.catering_items`.
Все агрегации считаются «вживую» на стороне CH, фронт ходит за ними по REST API.

## Стек

| Слой         | Технология                            |
|--------------|---------------------------------------|
| Хранилище    | ClickHouse 24.x · `sfv.catering_items` |
| Backend      | FastAPI 0.128 + clickhouse-driver 0.2 |
| Сервер       | Uvicorn (`uvloop` + `httptools`)       |
| Frontend     | SPA · Plotly.js 2.35 (CDN)             |

## Структура

```
app/sfv_dashboard/
├── __init__.py
├── README.md                ← этот файл
├── server.py                ← FastAPI приложение, все /api/* роуты
├── queries.py               ← SQL-агрегаторы (контракт: Filters → JSON)
├── core/
│   └── clickhouse.py        ← клиент CH + загрузка .env
└── static/
    ├── index.html           ← SPA: разметка, табы, фильтры
    ├── style.css            ← тёмная тема, layout
    └── app.js               ← вся клиентская логика + Plotly-виджеты
```

## Что внутри (виджеты)

**Таб «Обзор»:**
- 9 KPI-карточек (выручка, загрузка, sell-through, возврат, покрытие дней, средний чек, ...)
- Динамика по неделям (Σ выручка + sell-through % + возврат % с легендой)
- Heatmap **месяц × день недели** — средняя выручка/накладную, число накладных в подписи
- Heatmap **категория × месяц** — распределение выручки

**Таб «SKU»:**
- **Парето** топ-30 SKU по выручке + накопленная доля (80%-линия)
- Категории — выручка и эффективность (sell-through vs return)
- **Quadrant**: средняя загрузка vs sell-through, размер = выручка
- Сортируемая таблица всех SKU

**Таб «Рейсы»:**
- Bar-чарт: загрузка/продажа + средняя выручка/накладную
- Heatmap **рейс × SKU** — выручка, фильтр `n ≥ 10` (без шумовых пар)
- Таблица аномалий sell-through по рейсам (Z-score)

**Таб «Паттерны»:**
- Гэпы в потоке данных (непрерывные периоды без накладных)
- Outlier-недели по возврату (|Z| ≥ 1.5)
- Day-of-week pattern
- Помесячная динамика (выручка + возврат)
- Жизненный цикл SKU (Gantt-диаграмма first/last seen)

Все виджеты пересчитываются при изменении фильтров: **дата, рейс, категория, SKU**.

## Конфигурация

Переменные читаются из `Obligations/.env`:

```
CLICKHOUSE_HOST=10.95.19.132
CLICKHOUSE_PORT=9000
CLICKHOUSE_USER=...
CLICKHOUSE_PASSWORD=...
CLICKHOUSE_DATABASE=default     # необязательно, БД переопределяется в SQL
```

## Запуск

### dev / разработка

```bash
cd /home/budnik_an/Obligations
./venv/bin/uvicorn app.sfv_dashboard.server:app \
    --host 127.0.0.1 --port 8765 --reload
```

Открыть `http://127.0.0.1:8765/`.

### production / внутренняя сеть

Для публикации во внутреннем сегменте (любая машина, имеющая сетевой доступ
к ClickHouse-инстансу 10.95.19.132 и к интернету для CDN Plotly):

```bash
cd /home/budnik_an/Obligations
./venv/bin/uvicorn app.sfv_dashboard.server:app \
    --host 0.0.0.0 --port 8765 --workers 2 \
    --log-level info --access-log
```

Если Plotly из CDN недоступен (закрытая сеть), скачать `plotly-2.35.2.min.js`
локально и заменить `<script src="https://cdn.plot.ly/...">` в `index.html`.

### systemd unit (опционально)

```ini
# /etc/systemd/system/sfv-dashboard.service
[Unit]
Description=SFV Catering Dashboard (FastAPI + ClickHouse)
After=network.target

[Service]
Type=simple
User=budnik_an
WorkingDirectory=/home/budnik_an/Obligations
Environment="PATH=/home/budnik_an/Obligations/venv/bin:/usr/bin"
ExecStart=/home/budnik_an/Obligations/venv/bin/uvicorn \
    app.sfv_dashboard.server:app \
    --host 0.0.0.0 --port 8765 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sfv-dashboard
sudo systemctl status sfv-dashboard
```

### nginx-proxy (опционально)

```nginx
server {
    listen 80;
    server_name sfv-dashboard.utair.ru;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }
}
```

## API

| Эндпоинт                          | Описание                                |
|-----------------------------------|-----------------------------------------|
| `GET /api/health`                 | пинг + версия CH + кол-во строк         |
| `GET /api/lookups`                | списки рейсов / категорий / SKU / range |
| `GET /api/kpi`                    | KPI-карточки                             |
| `GET /api/weekly`                 | динамика по неделям                     |
| `GET /api/heatmap/month-dow`      | хитмэп месяц × день недели              |
| `GET /api/heatmap/category-month` | хитмэп категория × месяц                |
| `GET /api/sku/pareto?top=30`      | топ-N SKU по выручке + cum_share        |
| `GET /api/sku/table`              | таблица SKU с метриками                 |
| `GET /api/sku/lifecycle`          | first/last_seen для Gantt               |
| `GET /api/categories`             | свод по категориям                      |
| `GET /api/flights/summary`        | таблица рейсов с z-score                |
| `GET /api/flights/heatmap?min_n=10` | хитмэп рейс × SKU (выручка)            |
| `GET /api/dow`                    | паттерн по дню недели                   |
| `GET /api/monthly`                | помесячная динамика                     |
| `GET /api/gaps`                   | пробелы в данных                        |
| `GET /api/return-outliers?threshold_z=1.5` | аномальные недели по возврату    |

**Общие query-параметры (фильтры):**
- `date_from`, `date_to` (YYYY-MM-DD)
- `flight_out` (int)
- `item_category` (str)
- `item_sku` (str)

Пример:
```
GET /api/kpi?date_from=2025-06-01&date_to=2025-12-31&item_category=Газировка
```

## Особенности реализации

1. **CH-анализатор** старый (`enable_analyzer=0`) — намеренно, потому что новый
   анализатор CH 24.4+ строго ругается на конфликт `alias = column_name`
   (например `sum(revenue) AS revenue`). Старый анализатор отлично справляется
   с нашими запросами, разница в производительности на этих объёмах нулевая.
2. **`%(name)s`-параметры**: `clickhouse-driver` использует `%`-формат для
   подстановки. Поэтому в SQL форматные строки CH (`formatDateTime(x, '%Y-%m')`)
   нужно экранировать удвоением: `'%%Y-%%m'`.
3. **Item-уровень для KPI**: KPI и срезы считаются по `loaded_qty/sold_qty/revenue`
   позиций, а не из дублированных полей `ship_*_total`. Это даёт корректные
   цифры при фильтрации по SKU/категории.
4. **Heatmap рейс × SKU** требует `n ≥ 10` пар наблюдений (защита от шума).
   Параметр меняется через `?min_n=N`.

## Дальнейшие шаги (нерасскрытое)

- Drill-down по клику на ячейку хитмэпа (открывать детальный тултип)
- Сохранение пресетов фильтров (URL hash)
- Экспорт SKU-таблицы в CSV
- Cohort-анализ рейсов (как меняется sell-through во времени)
- Подключение PAX-load → выручка/PAX (когда данные появятся)
