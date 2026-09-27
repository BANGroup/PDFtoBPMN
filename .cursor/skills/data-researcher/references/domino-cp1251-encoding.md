# Domino KEEP — CP1251 Encoding in Cyrillic Fields

## Проблема

Domino KEEP API (MCP-серверы `user-domino-keep`, `user-domino-keep-bnd`) возвращает кириллические
строки в кодировке **CP1251** (Windows-1251). MCP-прокси/Hermes отображает
их как **Latin-1 (ISO 8859-1)**, что даёт «кракозябры»:

| Оригинал (CP1251) | Отображается (Latin-1) |
|---|---|
| начальник отдела | `íà÷àëüíèê îòäåëà` |
| АО "ЮТэйр-Инжиниринг" | `àî "þòýéð-èíaeèíèðèíã"` |
| служба-качества | `ñëóaeáà-êà÷åñòâà` |

## Решение

Декодирование в два шага:

```python
# шаг 1: взять кракозябру как Latin-1 → получить исходные CP1251 байты
# шаг 2: декодировать CP1251 байты → читаемая кириллица
clean = mojibake_string.encode('latin-1').decode('cp1251')
```

### Пример

```python
>>> raw = "íà÷àëüíèê îòäåëà êà÷åñòâà - íà÷àëüíèê ñìåíû"
>>> raw.encode('latin-1').decode('cp1251')
'начальник отдела качества - начальник смены'
```

## Верификация через hex

Если сомневаешься в результате — верифицируй через hex-представление:

```python
# Получить hex из ответа MCP (если доступен в логе/файле)
# Пример: hex строки "начальник отдела"
expected_hex = "ed e0 f7 e0 eb fc ed e8 ea 20 ee f2 e4 e5 eb e0"
bytes.fromhex(expected_hex.replace(' ', '')).decode('cp1251')
# → 'начальник отдела'
```

## Какие поля затрагивает

Все строковые поля с кириллицей из Domino KEEP:
- `JobTitle` — должность
- `Department` — подразделение (иерархия)
- `CompanyName` — юридическое лицо
- `CN` (Common Name) — логин/имя в Domino
- `FullName` — полный DN (Distinguished Name)
- Любые пользовательские поля names.nsf

## Поля, НЕ требующие декодирования

- `MailAddress` — email (латиница)
- `TelephoneNumber` / `MobileNumber` — номера телефонов (цифры)
- `sAMAccountName` / `uid` — логины (латиница)
- Поля на английском языке

## Поиск в names.nsf

Для поиска сотрудников по Domino используй `mcp_domino_keep_domino_contacts`:

```python
# По sAMAccountName (Windows-логин) — самый надёжный
mcp_domino_keep_domino_contacts("Kozlenkov_VA")

# По фамилии (будет кракозябра в выводе, но найдёт)
mcp_domino_keep_domino_contacts("Козленков")

# По email
mcp_domino_keep_domino_contacts("Victor.Kozlenkov@utair.ru")
```

После получения результата, декодируй каждое кириллическое поле.

## Альтернативные источники данных о сотрудниках

| Источник | Метод | Надёжность |
|---|---|---|
| Domino names.nsf | `domino_contacts("логин")` | Высокая (всегда есть) |
| mcp_employees | `get_employee("логин")` | Средняя (не все есть) |
| mcp_employees | `search_employees("ФИО")` | Низкая (часто пусто) |
| mcp_credinform | `search_company("ФИО")` | Для ИП (по фамилии) |

Если в задаче требуется найти данные о сотруднике — всегда начинай с
`domino_contacts`, затем сверяй с `mcp_employees`.