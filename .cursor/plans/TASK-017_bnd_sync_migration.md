# TASK-017: перенос ночной сборки корпуса БНД из todo в Obligations

## Контекст и цель
- Сейчас в `todo` каждую ночь в 01:00 cron запускает `tools/cron_catalog_rebuild.sh` → `tools/catalog_daily_rebuild.py`, который по очереди вызывает:
  1. `lotus-mcp/build_doc_catalog.py --auto` — каталог БНД (dflib, KEEP API) → `todo/webBI/doc-catalog.json` + `doc-catalog.state.json`;
  2. `lotus-mcp/download_bnd_corpus.py` — зеркало файлов БНД + РОТО + РПП → `todo/data/bnd_corpus/` (manifest.json, documents/…);
  3. `lotus-mcp/build_rpp_catalog.py` — каталог РПП (rppnew) → `todo/webBI/rpp-catalog.json`;
  4. отчёт в Telegram через очередь `todo/data/telegram-outbox/` (общий watcher todo).
- `todo` разбирается и в перспективе обнуляется. Это первый шаг: сборка корпуса, прогоны и Telegram-отчёт переезжают в Obligations.
- Корпус — вход конвейера PDFtoBPMN (ingestion, `10_ingestion.mdc`): Word-исходники БНД чище, чем OCR по PDF.

**Цель**: ночная сборка работает из Obligations, найденные ошибки зеркала исправлены, портал todo продолжает получать каталоги без перерыва.

## Решения human (23.09.2026)
- Код: `scripts/ingestion/bnd_sync/` (разрешение на новую папку в `scripts/` получено).
- Зеркало: перенести `todo/data/bnd_corpus` → `Obligations/data/bnd_corpus` через `mv` (тот же диск).
- Telegram: отправка напрямую через Bot API из Obligations; `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` копируются в `Obligations/.env`.
- Мусор (сироты 12 ГБ, `*.bloated` 2×2,4 ГБ): сначала карантин, удаление через неделю — решение human.
- Портал и docker остаются в todo; сборку/деплой портала можно запускать из Obligations. Полезные правила мультиагента todo для таких работ переносятся в Obligations (P0). На стороне портала обновить все пути, чтобы перенос корпуса ничего не сломал (P3). План в остальном согласован (23.09.2026, 09:50).
- 23.09.2026 12:15: отчёт перенесён из группы Telegram в личные сообщения от бота ДВК (Hermes, профиль `mm`, Mattermost team.utair.io) — Будник А.Н. (`budnik_an`), Лаврова Т.В. (`lavrova_tv`), Бачурина И.В. (`bachurina_iv`); в Telegram отчёт больше не отправляется. Переменные: `MATTERMOST_URL`, `MATTERMOST_TOKEN`, `BND_REPORT_MM_USERS`. Коммиты и пуши в Obligations и todo — делает агент по прямому поручению human.
- Допущение (явно): каталоги `doc-catalog.json`, `doc-catalog.state.json`, `rpp-catalog.json` — это входы портала, они продолжают писаться в `todo/webBI/`; docker-compose и backend не меняются. Корпус (зеркало файлов) портал не читает — проверено `rg` по backend/webBI/docker-compose.

## Жёсткие ограничения (не прерывать работу)
- Портал todo (docker, bind mount `./webBI:/app/webBI`) читает `doc-catalog.json`, `doc-catalog.state.json`, `rpp-catalog.json`; `backend/assistant.py` индексирует `doc-catalog.json`. Symlink наружу из bind mount в контейнере не работает → **каталоги продолжают писаться в `todo/webBI/`**. Путь задаётся переменной `BND_WEBBI_DIR` (дефолт — `/home/budnik_an/todo/webBI`).
- Скрипты в `todo` не правим и не удаляем до фазы P5. Откат на любом шаге = вернуть строку crontab todo.
- В одну ночь работает ровно один прогон: переключение crontab делается днём, между прогонами.
- Domino/KEEP — только чтение (как и сейчас). Никаких мутаций, Claude API не вызывается.
- Перед любой правкой в `todo` (только P5): `git pull`, прочитать `todo/.cursor/rules/` (урок D-0xx по TASK-011), запись в `todo/CHANGELOG.md`.

## Не входит в scope
- Логика классификации документов, дедуп версий, состав полей каталогов — переносятся как есть.
- Синхронизация `/etc/hosts` (`todo/tools/sync-utair-hosts.sh`) — не переносится: не относится к сборке и каждую ночь пропускается (нет NOPASSWD sudo). Упомянуть в risks.
- Портал, `webBI/*.html`, `backend/app.py`, общий Telegram-watcher todo — не трогаем.
- Индексация корпуса в RAG / ChromaDB — отдельная задача.

## Целевая структура
```
scripts/ingestion/bnd_sync/
  __init__.py
  build_doc_catalog.py      ← todo/lotus-mcp/build_doc_catalog.py
  build_rpp_catalog.py      ← todo/lotus-mcp/build_rpp_catalog.py
  download_bnd_corpus.py    ← todo/lotus-mcp/download_bnd_corpus.py
  tg_report.py              ← todo/tools/tg_report.py
  run_nightly.py            ← todo/tools/catalog_daily_rebuild.py
  cron_nightly.sh           ← todo/tools/cron_catalog_rebuild.sh
tests/test_bnd_sync.py
data/bnd_corpus/            ← mv из todo (в .gitignore через data/)
data/bnd_sync/logs/         ← логи прогонов (в .gitignore через data/)
data/bnd_sync/quarantine/   ← карантин сирот (P4)
```
Переменные окружения (`Obligations/.env`): `DOMINO_*` (есть), `DFLIB_*` (скопировать, если заданы в todo), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (скопировать), `BND_WEBBI_DIR`, `BND_CORPUS_ROOT` (дефолт `Obligations/data/bnd_corpus`).

## Фазы

### P0. Правило для работ с порталом todo из Obligations
1. `.cursor/rules/60_todo_portal.mdc` (не alwaysApply; подключается по description и автоматически при правке `scripts/ingestion/bnd_sync/**`): выжимка из `todo/.cursor/rules/` — `docker-db.mdc` (стоп-команды по `kk.db`, `--no-cache` только с согласия, сборка только сервиса `backend`, `down && up` вместо `restart`), `subagent-governance.mdc` (HTML `webBI/` — только Publisher-субагент по `todo/.cursor/skills/webbi-publisher/SKILL.md`, стратегия деплоя, curl 200 до доклада), `changelog.mdc` (запись в `todo/CHANGELOG.md`), `mcp-readonly.mdc`, `portal-assistant-readonly.mdc`, `windows-hosts-dns.mdc`, контракт каталогов БНД/РПП. Первоисточник — `todo/.cursor/rules/`, перед правкой todo их читать → verify: каждое правило выжимки ссылается на исходный файл; human подтверждает (`.cursor/rules/**` — HUMAN ONLY, файл создаётся по прямому поручению human).

Исключение из лимита «≤3 файлов, ≤150 строк» (требует подтверждения human): в P1 файлы переносятся **как есть** (~2 400 строк копии). Лимит применяется к правкам относительно оригинала: diff каждого файла против todo-версии должен трассироваться к пунктам плана.

### P1. Перенос как есть + параметризация путей + прямой Telegram (без переключения)
1. Скопировать 6 файлов в `scripts/ingestion/bnd_sync/` → verify: `diff` с оригиналами пуст до правок.
2. Пути: `OUTPUT`, `STATE_FILE` (doc), `OUTPUT` (rpp), `CATALOG_PATH`, `STATE_PATH`, `RPP_CATALOG_PATH`, `CORPUS_ROOT` (corpus), `TODO_ROOT`/`LOG_DIR` (оркестратор) — через `BND_WEBBI_DIR` / `BND_CORPUS_ROOT` / корень Obligations; `.env` — из корня Obligations → verify: `rg "todo" scripts/ingestion/bnd_sync` находит только дефолт `BND_WEBBI_DIR`.
3. `project_root` в manifest = корень Obligations; относительные пути `data/bnd_corpus/...` сохраняются → verify: unit-тест на построение пути.
4. Telegram: `_send_telegram_outbox` → `POST https://api.telegram.org/bot<token>/sendMessage` (httpx, таймаут, ретрай 3×, ошибка логируется, прогон не падает) → verify: ручная отправка тестового сообщения (с разрешения human).
5. Проверка без записи в боевые каталоги: `BND_WEBBI_DIR=<tmp с копией текущих каталогов и state>` → `build_doc_catalog.py --incremental` и `build_rpp_catalog.py` → verify: число документов и ключи совпадают с `todo/webBI/*.json` сегодняшнего прогона (±изменения в Domino за день, перечислить). `download_bnd_corpus.py --dry-run` против копии state → verify: CORPUS REPORT без ошибок.

### P2. Исправления зеркала
1. **Дубли при перекачке**: при повторной закачке изменившегося документа файл перезаписывается на месте (атомарно через `.tmp` + `os.replace`). Суффикс `_<unid8>` добавляется только при реальной коллизии имён разных `source_unid` внутри одной папки, и ставится **перед последним расширением** (`Path.stem`/`suffix`), не после первой точки → verify: unit-тесты (перекачка того же unid → одно имя; два разных unid с одинаковым именем → `name_<unid8>.ext`; `РИ-В5.072-01 (…).pdf` не портится).
2. **Переезд документа между процессами/системами**: если `dir` документа в state отличается от нового, старая папка переносится в новую (или в карантин, если новая уже есть), а не остаётся сиротой → verify: unit-тест на смену `process_code`.
3. **Отчёт**: «изменений нет» только при `changed_docs == 0` и `downloaded == 0`; иначе «изменилось N документов, скачано M файлов». В отчёт добавить размер зеркала на диске (сейчас `mb` = только скачанное за прогон, вводит в заблуждение) → verify: unit-тест `format_telegram`.
4. **Атомарная запись каталогов**: сейчас `os.rename(OUTPUT → .bak)` + запись — окно, когда портал не находит файл. Заменить на `copy → .bak` + запись во временный файл + `os.replace` → verify: unit-тест/ревью diff.

### P3. Переключение (днём, с участием human)
1. Предусловия: P1+P2 PASS у validator; окно не ближе 2 часов до 01:00 и после завершения ночного прогона (`cron.log` todo: «финиш»).
2. `mv /home/budnik_an/todo/data/bnd_corpus /home/budnik_an/Obligations/data/bnd_corpus` → verify: `manifest.json` читается, выборочно 20 путей из manifest существуют.
3. crontab: закомментировать строку `cron_catalog_rebuild.sh` (с пометкой «перенесено в Obligations TASK-017, дата»), добавить `0 1 * * * /home/budnik_an/Obligations/scripts/ingestion/bnd_sync/cron_nightly.sh` → verify: `crontab -l`.
4. Ручной прогон `cron_nightly.sh` → verify: exit 0, CORPUS REPORT `failed: 0`, сообщение пришло в Telegram, `https://10.96.96.47:8050/qms/qms-process-map` показывает актуальную дату.
5. Symlink `todo/data/bnd_corpus → /home/budnik_an/Obligations/data/bnd_corpus` (страховка для неучтённых читателей на хосте; `data/bnd_corpus/` в .gitignore todo) → verify: `ls todo/data/bnd_corpus/manifest.json`.
6. Пути на стороне портала (todo, по правилам todo: `git pull`, CHANGELOG):
   - `.cursor/skills/vks-transcripts/references/официальный-бланк-протокола.md` — абсолютные пути к корпусу → Obligations;
   - `webBI/qms-process-map.html:570` «Обновляется скриптом lotus-mcp/build_doc_catalog.py» → новый путь (только через Publisher-субагента);
   - `README.md`, `docs/DOMINO_KEEP_API.md`, комментарии `tools/sync-utair-hosts.sh`, `tools/fetch_kk_docs.py` — ссылки на новое место;
   - запись в `todo/CHANGELOG.md` «Изменено: сборка корпуса БНД перенесена в Obligations».
   → verify: `rg "todo/data/bnd_corpus|lotus-mcp/(build_doc_catalog|build_rpp_catalog|download_bnd_corpus)" todo --glob '!CHANGELOG.md' --glob '!data/**' --glob '!logs/**'` находит только старые скрипты (удаляются в P5); `curl` карты процессов → 200.
7. Следующее утро: проверить ночной прогон и Telegram.
- Откат: вернуть строку crontab todo, `mv` зеркала обратно.

### P4. Карантин мусора
1. Режим `--report-orphans`: список файлов на диске, которых нет в manifest (кроме `_archive/`), с суммарным объёмом → verify: ~7 800 файлов / ~12 ГБ (сверка с разбором 23.09).
2. `--quarantine-orphans`: перенос сирот и `*.bloated` в `data/bnd_sync/quarantine/<дата>/` с сохранением относительных путей → verify: после переноса все пути manifest существуют; прогон incremental — `downloaded` не вырос (сироты не были нужны).
3. Удаление карантина — через 7 дней, только по команде human.

### P5. Уборка todo (отдельно, после 7 зелёных ночей)
- В `todo`: удалить `tools/cron_catalog_rebuild.sh`, `tools/catalog_daily_rebuild.py`, `lotus-mcp/build_doc_catalog.py`, `build_rpp_catalog.py`, `download_bnd_corpus.py`; оставить `tools/tg_report.py` (используют другие прогоны — проверить `rg`), `download_bnd_files.py` (устаревший предшественник — решение human). Запись в `todo/CHANGELOG.md`. Коммит делает human.

## Verify итоговый
- `pytest tests/test_bnd_sync.py` — PASS.
- 7 ночных прогонов из Obligations: exit 0, Telegram-отчёт пришёл, портал показывает дату прогона.
- Размер `data/bnd_corpus` ≈ размер файлов manifest (без сирот).

## Risks
- Каталоги по-прежнему пишутся в `todo/webBI/` — зависимость остаётся до переезда портала (осознанно).
- `todo/webBI/doc-catalog.json` отслеживается git в todo — изменения после ночного прогона продолжат появляться в `git status` todo (как и сейчас).
- Синхронизация `/etc/hosts` не переносится; если corp-DNS начнёт отдавать неверные адреса, сборка упадёт на авторизации — это будет видно в Telegram-отчёте.
- Токен Telegram-бота дублируется в двух `.env` до P5.
- `tools/fetch_kk_docs.py` в todo копирует логику `fetch_attachment` — не зависит от переноса, но исправления P2 туда не попадут.
- Мастер-PDF РОТО (ds=dflib) по-прежнему в `external_files` — сохранено поведение todo; включить закачку — отдельное решение.
- Унаследовано от todo (не правилось): повтор ключа `doc_sm` в `build_doc_catalog.py` (побеждает последний — так каталог собирается и сейчас); zip-вложения с одинаковым именем у двух unid одного документа перетирают разделы друг друга; при сбое came/employeesreader прежние файлы выпадают из manifest; в dry-run раздутый state переименовывается в `.bloated`.
- Вложения, исчезнувшие из карточки (unid больше нет в каталоге), остаются на диске — их соберёт `--report-orphans` (P4).
- `--limit` выполняет перенос папок/карантин, но не сохраняет state — использовать только для смок-тестов.
- `.gitignore:81` (`test_*.py`) игнорирует `tests/test_bnd_sync.py` — при коммите нужен `git add -f`.
- До переключения crontab у прогонов todo и Obligations разные lock-файлы: ручной запуск Obligations не ставить на 01:00–01:15.

## Ownership
- `scripts/ingestion/bnd_sync/**`, `tests/test_bnd_sync.py` — coder.
- `crontab`, `mv` зеркала — выполняет агент в P3 после явного «да» human.
- `.env` / `.env.example` (ключи Telegram, `BND_WEBBI_DIR`) и одно тестовое сообщение — согласованы human 23.09.2026 («в остальном согласовано»), выполнены в P1.
- `.cursor/rules/60_todo_portal.mdc` — создаётся по прямому поручению human (23.09.2026).
- `docs/CURRENT_STATE.md`, `docs/DECISIONS.md` (новое решение о переносе) — scribe.
- `todo/**` — только P5, по правилам todo.
