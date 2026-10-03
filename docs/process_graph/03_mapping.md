# 03. Соответствие моделей

Наша модель (`schema/process_graph.schema.yaml`) сопоставлена с:
- **BS** — Business Studio (имена по справке BS 5; BS 6/7 — сверить по выгрузке);
- **BPMN** — BPMN 2.0;
- **v4.0** — онтология «PDFtoBPMN v2 — GraphRAG Ontology v4.0 FINAL» (портал todo, `webBI/bpmn-graph-ontology.html`, 23.03.2026);
- **core** — `core/knowledge_types.py` (13 типов) и `core/edge_types.py` (19 рёбер);
- **161** — КД-СТ-161-01.

## Узлы

| Наш id | Обяз. | BS | BPMN | v4.0 | core | 161 |
|---|---|---|---|---|---|---|
| PROCESS | да | Процесс / единица деятельности | process, pool | PROCESS | — (неявно) | процесс, подпроцесс |
| TASK | да | Задача | task | ACTIVITY | PROCESS_STEP | задача |
| EVENT (start / end) | да | Стартовое / Конечное событие | startEvent / endEvent | EVENT | — | событие |
| EVENT (intermediate) | нет | Промежуточное событие | intermediateEvent | EVENT | — | событие |
| GATEWAY | если есть ветвление | Шлюз | gateway | GATEWAY | DECISION_RULE (частично) | шлюз |
| LINK | да (или конец) | Ссылка / свёрнутый пул / процесс-ссылка | linkEvent, messageFlow → pool, callActivity | — (только через общие узлы, #3) | — | свёрнутый пул, процесс-ссылка, МДС |
| ORG_UNIT (подразделение) | да | Оргединица: Подразделение | lane | ORG_UNIT | ORG_UNIT | Оргединицы |
| ORG_UNIT (должность, роль, группа, человек) | нет | Должность, Роль, Группа оргединиц, физлицо | вложенная lane | ORG_UNIT / атрибут ребра (#12) | ROLE | Оргединицы: должность, роль, группа |
| DOCUMENT | нет (источник — всегда) | Документы / НСД | — | NSD | DOCUMENT_REF | Документы |
| OBJECT | нет | Функциональные объекты: документ, информация, материальный объект | dataObject | FUNC_OBJECT | INPUT_OUTPUT, FORM_TEMPLATE | Документы, Информация, Материальные объекты |
| DATA_STORE | нет | Базы данных | dataStore | = SOFTWARE (#39) | — | Базы данных |
| SOFTWARE | нет | Программные продукты | — | SOFTWARE | SYSTEM | Программные продукты |
| EXTERNAL | нет | Внешние ссылки / внешняя оргединица | collapsed pool | — | — | Внешние ссылки |
| BUSINESS_RULE | нет | — | textAnnotation | — | DECISION_RULE | — |
| RISK | нет | — | — | RISK | — | нет |
| KPI | нет (только измеримый) | Показатели | — | KPI | KPI, FORMULA | Показатели |
| — (признак TASK.control) | — | — | — | — | CONTROL | — |
| — (словарь, не граф) | — | Термины | — | TERM | DEFINITION, ABBREVIATION | Термины |
| — (не входит) | — | Цели | — | GOAL исключён (#26) | — | Цели BSC |

## Рёбра

| Наш id | Обяз. | BS | BPMN | v4.0 | core |
|---|---|---|---|---|---|
| FLOW | да | Поток управления | sequenceFlow | sequence_flow | SEQUENCE, DECISION, PARALLEL |
| PERFORMS | да | «выполняет» | lane membership | has_role (executor) | RESPONSIBLE_FOR |
| CONTAINS | да (structural) | декомпозиция | subProcess | contains | — |
| OWNS | нет ⚑ | субъект «владелец» | — | owner_id (атрибут) | ACCOUNTABLE_FOR |
| PARTICIPATES | нет | субъект «участник» | — | has_role (approver, consulted, informed…) | CONSULTED_IN, INFORMED_OF |
| INPUT | нет | «предоставляет входные данные для», «является входом для», «используется» | dataInputAssociation | uses_object (input) | INPUTS |
| OUTPUT | нет | «имеет на выходе», «создает на выходе», «изменяет» | dataOutputAssociation | uses_object (output) | OUTPUTS |
| STORED_IN | нет | ассоциация с базой данных | association → dataStore | — | — |
| SUPPORTED_BY | нет | «поддерживает» / «выполняет» | — | uses_software | USES_SYSTEM |
| MESSAGE | нет ⚑ | Поток сообщений | messageFlow | — | — |
| REGULATED_BY | нет (на источник — авто) | Нормативно-справочные документы | — | regulated_by | REFERENCES, DEFINED_IN |
| IN_UNIT | нет | иерархия оргструктуры | — | subordinate_to (частично) | PART_OF |
| MEMBER_OF | нет | «Назначение на роль», агрегация группы | — | — | — |
| SUBORDINATE_TO | нет (из справочника) | «Административное» / «Функциональное подчинение» | — | subordinate_to, functional_subordinate_to | REPORTS_TO |
| RULE_FOR | нет | — | association к аннотации | — | DECISION |
| HAS_RISK | нет | — | — | has_risk | — |
| MITIGATES | нет | — | — | — | MITIGATES |
| MEASURED_BY | нет | — | — | — | CONTROLS (частично) |
| MEASURES | нет | Показатели процесса | — | has_kpi | MEASURES |
| RESPONSIBLE_FOR_KPI | нет | «ответственный за выполнение» | — | responsible_for | — |
| SW_PART_OF | нет | ИС → модуль → функция | — | part_of | — |
| — | — | — | — | — | TARGET (→ атрибут KPI), SUPERSEDES (версии документов — вне графа процессов) |

## Расхождения с онтологией v4.0, которые эта модель меняет

| v4.0 | Здесь | Почему |
|---|---|---|
| #39 dataStore = SOFTWARE | DATA_STORE отдельно + STORED_IN | BS, Репин, КД-СТ-161 держат базы данных отдельно |
| #3 межпроцессные связи только через общие узлы | + LINK и MESSAGE явно | Практика Исаева и КД-СТ-161 |
| #12 роль — атрибут ребра | роль — ORG_UNIT ниже подразделения | В BS роль — класс оргединиц; дорожка-подразделение обязательна |
| activity_type userTask / manual / service | тип «не определён» / ручная / сервисная | Rule 0: по умолчанию «не определён»; userTask в КД-СТ-161 нет |
| TERM — узел графа | словарь вне графа | Схеме не нужен |
| NSD отдельно от источника | DOCUMENT, источник регулирует свой процесс автоматически | Убран дубль |
| CONTROL не было / в core — узел | признак TASK.control | Контроль — шаг процесса |
| KPI: 4 атрибута | KPI только при наличии меры | Rule 0, без меры — не показатель |

## Что не меняется в `core/*` сейчас

`core/knowledge_types.py` и `core/edge_types.py` не правились. Приведение — отдельная задача уровня `high` (схема графа — публичный контракт): план → согласование human → реализация → validator.
