# Решения проекта PDFtoBPMN v2.1

> Append-only. Scribe добавляет. Orchestrator читает перед каждым планом.
> Изменить решение = добавить новое с пометкой "supersedes D-NNN".

## D-001: Graph as SSOT (18.03.2026)
**Контекст:** 410 документов СМК — нужна машиночитаемая модель организации, а не просто парсинг PDF.
**Решение:** Organizational knowledge graph — единственный источник истины. BPMN, RAG, RACI, KPI — views из графа.
**Отклонено:** Два отдельных контура (Knowledge Base + Process Model), ProcessSpec как промежуточный формат.
**Вернуться если:** graph population оказывается unreliable на реальных документах.

## D-002: Knowledge graph НЕ убран из MVP (18.03.2026)
**Контекст:** Ранее было решение убрать graph из MVP. Пересмотрено: граф — это продукт, не компонент RAG.
**Решение:** NetworkX + SQLite в MVP. BPMN и management views рендерятся из графа. LightRAG оценивается в POC.
**Отклонено:** Metadata-rich chunks в ChromaDB как единственный storage.
**Supersedes:** Решение об убирании graph из MVP.

## D-003: OCR — POC решает (18.03.2026)
**Контекст:** EasyOCR vs RapidOCR. Оба через Docling. Tesseract исключён.
**Решение:** POC на 10 документах, 5 сценариев, Levenshtein ≥95%/≥90%. Победитель — единственный OCR.
**Отклонено:** Tesseract (слабый на русском + таблицы).

## D-004: LLM стратегия — Cursor + Claude API (18.03.2026)
**Контекст:** Нет локального LLM 72B/32B. GPU только для Qwen VL-7B.
**Решение:** Dev: Cursor AI (Opus/Composer/Auto). Batch: Claude API sonnet-4-6 (~$210). VLM: Qwen VL-7B.
**Отклонено:** Qwen 72B/32B локально, LangGraph Platform/Cloud.

## D-005: 4 агента + hooks enforcement (18.03.2026)
**Контекст:** Helicomponents паттерн: архитектор → исполнитель → ревьюер → верификатор.
**Решение:** Orchestrator (Opus 0.2), Coder (Auto/Composer 0.4), Validator (Composer 0.0), Scribe (Composer 0.0). Hooks блокируют без handoff.
**Отклонено:** 3 агента (scribe + validator в одном), 7 агентов.

## D-006: Handoff protocol H1-H9 (18.03.2026)
**Контекст:** Без формализованных handoff'ов агенты дрейфуют, state рассинхронизируется.
**Решение:** 9 handoff'ов, каждый записывается в LangGraph. Hooks блокируют агента без предыдущего handoff.
**Отклонено:** Convention-based (правила без enforcement).

## D-007: Git model — ветка + коммиты (18.03.2026)
**Контекст:** Нужна изоляция работы от main, но без overhead веток на каждую задачу.
**Решение:** Ветка v2-graphrag. 1 задача = 1 коммит. Human коммитит после H9. Merge в main по phase gate.
**Отклонено:** Feature branches per task, trunk-based.

## D-008: PyMuPDF исключён (18.03.2026)
**Контекст:** AGPL лицензия несовместима с потенциальным коммерческим использованием.
**Решение:** Docling + docling-parse (MIT).
**Отклонено:** PyMuPDF (AGPL).

## D-009: Unified pipeline — не два контура (18.03.2026)
**Контекст:** Два контура (A: Knowledge Base, B: Process Model) усложняют архитектуру, дублируют extraction.
**Решение:** Один pipeline: ingestion → extraction → graph population + text indexing. Views (BPMN, RACI, KPI) из графа.
**Отклонено:** Контуры A и B как отдельные pipelines.

## D-010: ProcessSpec убран как промежуточный формат (18.03.2026)
**Контекст:** ProcessSpec.yaml был intermediate format между extraction и BPMN compiler.
**Решение:** Граф = source of truth. BPMN compiler читает graph query напрямую.
**Отклонено:** ProcessSpec.yaml как обязательный промежуточный файл.
