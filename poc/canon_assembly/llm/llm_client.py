"""Клиент корпоративного шлюза LLM (ai.utair.ru, OpenAI-совместимый /api/chat/completions) — под контролем orchestrator (TASK-021).
Каждый вызов пишется в data/canon_reeng/llm/calls.jsonl: время, модель, запрос, ответ, токены, длительность.
Окружение: LLM_API_URL, LLM_API_KEY. Модель по решению human 05.10.2026: ag.yc/deepseek-v4-flash/latest."""
import os, json, time, urllib.request
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..'))
LOG = os.path.join(REPO, 'data/canon_reeng/llm/calls.jsonl')
MODEL = os.environ.get('CANON_LLM_MODEL', 'ag.yc/deepseek-v4-flash/latest')


def chat(messages, model=MODEL, max_tokens=2000, temperature=0, tag='', timeout=120):
    body = json.dumps({'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}).encode()
    req = urllib.request.Request(os.environ['LLM_API_URL'], body, {'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'], 'Content-Type': 'application/json'})
    t0 = time.time(); err = None; d = {}
    for attempt in range(3):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=timeout)); err = None; break
        except Exception as e:
            err = f'{type(e).__name__}: {e}'; time.sleep(2 * (attempt + 1))
    ans = (d.get('choices') or [{}])[0].get('message', {}).get('content') if d else None
    rec = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'tag': tag, 'model': model, 'served_model': d.get('model'), 'messages': messages,
           'answer': ans, 'usage': d.get('usage'), 'sec': round(time.time() - t0, 2), 'error': err}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return ans, rec
