# Handoff Protocol — PDFtoBPMN v2.1

> Каждый переход между агентами — формализованный handoff.  
> Каждый handoff записывается в LangGraph `dev_state.sqlite`.  
> Human получает отчёт от orchestrator в фиксированном формате.

---

## 1. Цепочка handoff'ов (полный цикл задачи)

```
Human → H1 → Orchestrator → H2 → Validator(pre) → H3 → Orchestrator
                                                         │
                                               [PASS]    │ [FAIL: fix plan]
                                                         ▼
                                                   Orchestrator → H4 → Coder
                                                                        │
                                                                        ▼
                                                   Coder → H5 → Validator(post)
                                                                        │
                                                              [PASS]    │ [FAIL: retry]
                                                                        ▼
                                              Validator → H6 → Orchestrator
                                                                        │
                                                                        ▼
                                              Orchestrator → H7 → Scribe
                                                                        │
                                                                        ▼
                                              Scribe → H8 → Orchestrator → H9 → Human
```

---

## 2. Формат каждого handoff

### H1: Human → Orchestrator (задание)
```
Формат: свободный текст от human
Пример: "Реализуй page_classifier для ingestion"
Запись в LangGraph: log_action("H1: task received", agent="orchestrator")
```

### H2: Orchestrator → Validator (pre-gate)
```yaml
handoff: H2_plan_to_pregate
from: orchestrator
to: validator
payload:
  plan_file: .cursor/plans/TASK-NNN.md
  checks_requested:
    - plan_vs_decisions    # план не противоречит DECISIONS.md
    - scope_valid          # scope содержит НОВЫЙ/ИЗМЕНИТЬ/ТЕСТЫ
    - ownership_ok         # файлы в scope принадлежат coder zone
    - dependencies_ok      # нет новых pip зависимостей без human ok
Запись в LangGraph: log_action("H2: plan sent to pre-gate", agent="orchestrator")
```

### H3: Validator → Orchestrator (pre-gate result)
```yaml
handoff: H3_pregate_result
from: validator
to: orchestrator
payload:
  gate: pre
  result: PASS | FAIL
  checks:
    plan_vs_decisions: {pass: true}
    scope_valid: {pass: true}
    ownership_ok: {pass: true}
    dependencies_ok: {pass: true, note: "no new deps"}
  # Если FAIL:
  failures:
    - check: plan_vs_decisions
      reason: "D-007 says no NetworkX, plan includes graph_builder.py"
      suggestion: "Remove graph components from scope"
Запись в LangGraph: log_validation(scope="pre-gate TASK-NNN", result="pass|fail")
```

### H4: Orchestrator → Coder (задание на код)
```yaml
handoff: H4_plan_to_coder
from: orchestrator
to: coder
payload:
  plan_file: .cursor/plans/TASK-NNN.md
  pre_gate: PASS
  instructions: |
    Реализуй строго по плану.
    Scope: [список файлов НОВЫЙ/ИЗМЕНИТЬ/ТЕСТЫ]
    Non-goals: [что НЕ трогать]
    При сдаче: формат H5.
Запись в LangGraph: log_action("H4: plan dispatched to coder", agent="orchestrator")
```

### H5: Coder → Validator (сдача работы)
```yaml
handoff: H5_code_to_postgate
from: coder
to: validator
payload:
  task: TASK-NNN
  files_changed:
    - path: scripts/ingestion/page_classifier.py
      action: NEW
      lines: 87
    - path: scripts/ingestion/docling_adapter.py
      action: MODIFIED
      lines_changed: 12
    - path: tests/test_ingestion.py
      action: MODIFIED
      lines_changed: 34
  files_not_touched:
    - scripts/ingestion/chunker.py
    - scripts/ingestion/authority_resolver.py
  risks:
    - "page_classifier heuristic may need tuning on real scans"
  checks_requested:
    - pytest_pass
    - schema_valid
    - diff_in_scope
    - ownership_ok
    - docs_consistent
    - decisions_no_conflict
Запись в LangGraph: log_action("H5: code submitted to post-gate", agent="coder")
```

### H6: Validator → Orchestrator (post-gate result)
```yaml
handoff: H6_postgate_result
from: validator
to: orchestrator
payload:
  gate: post
  result: PASS | FAIL
  checks:
    pytest_pass: {pass: true, details: "15/15 tests, 0.4s"}
    schema_valid: {pass: true}
    diff_in_scope: {pass: true, files_in_scope: 3, files_out_scope: 0}
    ownership_ok: {pass: true}
    docs_consistent: {pass: true}
    decisions_no_conflict: {pass: true}
  retry_count: 0  # 0/1/2, на 3 → BLOCK → human
  # Если FAIL:
  failures:
    - check: pytest_pass
      reason: "test_page_classifier_approval FAILED — AssertionError"
      suggestion: "Fix classification logic for approval sheets"
Запись в LangGraph: log_validation(scope="post-gate TASK-NNN", result="pass|fail")
```

### H7: Orchestrator → Scribe (запись результата)
Только после ALL PASS на post-gate.
```yaml
handoff: H7_accept_to_scribe
from: orchestrator
to: scribe
payload:
  task: TASK-NNN
  status: done
  record_instructions:
    - update_component: {name: "ingestion", status: "in_progress", tests_pass: true}
    - log_decision: {title: "...", decision: "..."} # если были решения по ходу
    - update_current_state: true
    - update_changelog: true
Запись в LangGraph: log_action("H7: accepted, dispatched to scribe", agent="orchestrator")
```

### H8: Scribe → Orchestrator (запись завершена)
```yaml
handoff: H8_scribe_done
from: scribe
to: orchestrator
payload:
  recorded:
    - dev_state.sqlite: updated
    - CURRENT_STATE.md: updated
    - changelog.md: entry added
    - DECISIONS.md: [appended | no changes]
Запись в LangGraph: log_action("H8: state recorded", agent="scribe")
```

### H9: Orchestrator → Human (доклад)
```markdown
## Доклад по TASK-NNN: [название]

**Статус:** DONE ✅
**Фаза:** [текущая]

### Что сделано
- [файл]: [описание изменения]
- [файл]: [описание изменения]

### Gates
- Pre-gate: PASS (plan validated)
- Post-gate: PASS (15/15 tests, schema ok, scope ok)
- Retries: 0

### Решения (если были)
- D-NNN: [описание]

### Следующий шаг
- [предложение orchestrator'а]

### Готово к коммиту
```bash
git add -A && git commit -m "TASK-NNN: [описание]"
```
```
Запись в LangGraph: log_action("H9: report to human", agent="orchestrator")

---

## 3. LangGraph: что записывается

Каждый handoff → `log_action()` в dev_state.sqlite:

```python
# Пример action_log после полного цикла задачи:
[
  {"date": "...", "action": "H1: task received — page_classifier", "agent": "orchestrator"},
  {"date": "...", "action": "H2: plan sent to pre-gate", "agent": "orchestrator"},
  {"date": "...", "action": "H3: pre-gate PASS", "agent": "validator"},
  {"date": "...", "action": "H4: plan dispatched to coder", "agent": "orchestrator"},
  {"date": "...", "action": "H5: code submitted to post-gate", "agent": "coder"},
  {"date": "...", "action": "H6: post-gate PASS (15/15 tests)", "agent": "validator"},
  {"date": "...", "action": "H7: accepted, dispatched to scribe", "agent": "orchestrator"},
  {"date": "...", "action": "H8: state recorded", "agent": "scribe"},
  {"date": "...", "action": "H9: report to human — ready to commit", "agent": "orchestrator"},
]
```

Плюс отдельно:
- `log_validation()` — на каждый gate (pre и post)
- `update_component()` — на успешное завершение
- `log_decision()` — если по ходу задачи принималось решение

---

## 4. Retry и escalation

```
Post-gate FAIL, retry 1/3:
  H6 result = FAIL → orchestrator → H4' → coder fixes → H5' → validator
  Каждый retry записывается: log_action("H5': retry 1 submitted")

Post-gate FAIL, retry 3/3:
  H6 result = FAIL, retry_count=3 → BLOCK
  Orchestrator: H9(BLOCKED) → Human decides

Pre-gate FAIL:
  H3 result = FAIL → orchestrator rewrites plan → H2' → validator
  Max 2 rewrites. На 3-й → BLOCK → Human.
```

---

## 5. Git commit — только после H9

```
H9 доклад содержит готовую команду:
  git add -A && git commit -m "TASK-NNN: [описание]"

Human выполняет ВРУЧНУЮ после проверки доклада.
Ни один агент не делает git commit.

Ветка: v2-graphrag
1 task = 1 commit
Merge в main: по phase governance gate (human решение)
```

---

## 6. Enforcement: Cursor Hooks

Hooks — не рекомендация, а блокировка. Без записанного handoff'а агент
не получит промпт. `.cursor/hooks.json` + `.cursor/hooks/*.py`.

### check_handoff.py (beforeSubmitPrompt)
Перед каждым промптом к модели:
- Определить текущего агента (env: `CURSOR_AGENT_NAME`)
- Прочитать `dev_state.sqlite`: есть ли handoff TO этого агента?
- Нет handoff → **exit 2** → Cursor **блокирует** промпт
- Orchestrator — исключение (первый в цепочке, получает от human)

```
Coder пытается начать без H4 → BLOCKED
"No handoff recorded to 'coder'. Orchestrator must dispatch first."

Scribe пытается записать без H7 → BLOCKED
"No handoff recorded to 'scribe'. Orchestrator must accept first."
```

### block_orchestrator_code.py (beforeShellExecution)
Orchestrator пытается запустить shell команду:
- `python`, `pytest`, `pip` → **exit 2** → BLOCKED
- `git add/commit/push` → **exit 2** → BLOCKED (только human коммитит)
- `cat/sed` на `scripts/`, `core/` → **exit 2** → BLOCKED
- `ls`, `grep`, `find` → разрешено (навигация)
- Разрешено: чтение `docs/`, `.cursor/plans/`, `.cursor/state/`

```
Orchestrator: "python3 scripts/ingestion/page_classifier.py" → BLOCKED
"Orchestrator must not run code. Dispatch to coder via H4."

Orchestrator: "pytest tests/" → BLOCKED
"Orchestrator must not run tests. Dispatch to validator via H2."
```

### check_ownership.py (afterFileEdit)
После каждого редактирования файла:
- Агент отредактировал файл вне своей зоны → **exit 2** → BLOCK
- Coder трогает docs/ → BLOCKED
- Scribe трогает scripts/ → BLOCKED
- Кто-то трогает .cursor/rules/ → BLOCKED (human only)

### record_stop.py (stop)
При завершении сессии агента:
- Записать в session_log (SQLite)
- Если coder завершил без H5 (code → validator) → WARNING в лог
- Не блокирует (сессия уже завершена), но фиксирует нарушение

### Что это даёт
```
БЕЗ HOOKS:
  Orchestrator может случайно написать код в чате → coder копирует.
  Coder начинает без handoff → state рассинхронизирован.
  Scribe записывает до прохождения gates → ложный "done".

С HOOKS:
  Orchestrator пытается запустить python → BLOCKED.
  Coder без H4 в LangGraph → BLOCKED (не получит промпт).
  Scribe без H7 → BLOCKED.
  Кто-то трогает .cursor/rules/ → BLOCKED (human only).
  
  Handoff protocol = enforcement, не convention.
  Ownership = физическая блокировка, не правило в .md файле.
```
