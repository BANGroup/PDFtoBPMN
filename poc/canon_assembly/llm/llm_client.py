"""Клиент корпоративного шлюза LLM (ai.utair.ru, OpenAI-совместимый /api/chat/completions) — под контролем orchestrator (TASK-021).
Каждый вызов пишется в data/canon_reeng/llm/calls.jsonl: время, модель, запрос, ответ, токены, длительность.
Окружение: LLM_API_URL, LLM_API_KEY. Модель по решению human 06.10.2026: deepseek-v4.1-flash
(с 07.10 шлюз знает её как «deepseek-v4.1-flash», старое имя ag.yc/…/latest даёт «Model not found»).

Темп: у шлюза предел порядка 10 запросов за период (human 07.10), заголовков о лимите нет. Общий для всех процессов счётчик
(файл rate.json под fcntl-замком): не больше LLM_RATE запросов за LLM_RATE_WINDOW секунд (по умолчанию 8 за 60).
HTTP 429 — ожидание (Retry-After или окно) и повтор, не ошибка.
"""
import os, json, time, fcntl, urllib.request
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
LOG = os.path.join(REPO, 'data/canon_reeng/llm/calls.jsonl')
RATE_FILE = os.path.join(REPO, 'data/canon_reeng/llm/rate.json')
MODEL = os.environ.get('CANON_LLM_MODEL', 'deepseek-v4.1-flash')
RATE = int(os.environ.get('LLM_RATE', '8'))
WINDOW = float(os.environ.get('LLM_RATE_WINDOW', '60'))


def _wait_slot():
    """Ждать, пока в окне WINDOW секунд меньше RATE запросов (по всем процессам); занять слот."""
    os.makedirs(os.path.dirname(RATE_FILE), exist_ok=True)
    while True:
        with open(RATE_FILE, 'a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            try: ts = json.loads(f.read() or '[]')
            except ValueError: ts = []
            now = time.time(); ts = [t for t in ts if now - t < WINDOW]
            if len(ts) < RATE:
                ts.append(now); f.seek(0); f.truncate(); f.write(json.dumps(ts)); return
            wait = WINDOW - (now - min(ts)) + 0.5
        time.sleep(max(wait, 1))


def chat(messages, model=MODEL, max_tokens=4000, temperature=0, tag='', timeout=180):
    body = json.dumps({'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}).encode()
    req = urllib.request.Request(os.environ['LLM_API_URL'], body, {'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'], 'Content-Type': 'application/json'})
    t0 = time.time(); err = None; d = {}; waited429 = 0
    attempt = 0
    while attempt < 3:
        _wait_slot()
        try:
            d = json.load(urllib.request.urlopen(req, timeout=timeout)); err = None; break
        except Exception as e:
            err = f'{type(e).__name__}: {e}'
            code = getattr(e, 'code', None)
            if code == 429 and waited429 < 5:   # предел шлюза: ждать и повторить (не считается попыткой)
                ra = getattr(e, 'headers', {}) and e.headers.get('Retry-After')
                time.sleep(float(ra) if ra and str(ra).isdigit() else WINDOW); waited429 += 1; continue
            if code == 400: break   # запрос отвергнут — повтор бессмыслен
            attempt += 1; time.sleep(2 * attempt)
    ans = (d.get('choices') or [{}])[0].get('message', {}).get('content') if d else None
    rec = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'tag': tag, 'model': model, 'served_model': d.get('model'), 'messages': messages,
           'answer': ans, 'usage': d.get('usage'), 'sec': round(time.time() - t0, 2), 'error': err, 'waited_429': waited429}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return ans, rec
