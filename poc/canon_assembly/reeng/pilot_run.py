"""Пилот stepP: py-движок по списку документов, по одному процессу последовательно (RLIMIT_AS 5 ГБ внутри pyengine); таблица сравнения с Word (stepA2)."""
import sys, os, json, subprocess, shutil, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cmpdump
R = os.path.abspath(os.path.join(HERE, '..', '..', '..', 'data', 'canon_reeng')); P = R + '/stepP'
docs = open(P + '/docs.txt').read().split('\n')
rows = []
for d in docs:
    if not os.path.isdir(f'{P}/src/{d}'): shutil.copytree(f'{R}/stepA2/src/{d}', f'{P}/src/{d}')
    subprocess.run([sys.executable, HERE + '/pyengine.py', '--src', f'{P}/src/{d}', '--out', f'{P}/out/{d}', '--work', f'{P}/work/{d}'], capture_output=True)
    sp = f'{P}/out/{d}/status.json'
    st = json.load(open(sp)) if os.path.exists(sp) else {'error': 'нет status.json', 'ready': False}
    row = {'doc': d, 'ready': st.get('ready'), 'sec': st.get('seconds'), 'rss': st.get('ru_maxrss_mb'), 'err': (st.get('error') or '')[-120:].replace('\n', ' ')}
    v = st.get('verify') or {}
    row.update({k: v.get(k) for k in ('missing', 'numbered_bad', 'duplicates', 'frozen_numbers')})
    wv = f'{R}/stepA2/out/{d}/verify.json'
    row['word_ready'] = None
    if os.path.exists(wv):
        w = json.load(open(wv)); row['word_ready'] = w['lines'] > 0 and w['missing'] == 0 and w['numbered_bad'] == 0 and w['duplicates'] == 0 and w['frozen_numbers'] == 0
    ct = f'{P}/out/{d}/canon_text.txt'
    if os.path.exists(ct) and os.path.exists(f'{R}/stepA2/out/{d}/canon_text.txt'):
        c = cmpdump.compare(f'{R}/stepA2/out/{d}/canon_text.txt', ct)
        row.update(text_a=c['text_a'], text_b=c['text_b'], only_a=c['text_only_a'], only_b=c['text_only_b'], num_ok=c['num_ok'], num_cmp=c['num_cmp'], shp=c['shapes_notes'], bad=c['num_bad'][:3])
    rows.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
json.dump(rows, open(P + '/pilot_table.json', 'w'), ensure_ascii=False, indent=1)
