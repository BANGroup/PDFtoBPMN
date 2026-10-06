"""verify_canon без Word: python simverify.py <plan-only dir> <src dir документа> -> missing/duplicates сборки (plan-only).
Сборка = base_marked.docx с вставленными фрагментами (dupsim.assemble); нумерация автоспискаов не имитируется (numbered_bad не показателен)."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dupsim
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_canon.py'), encoding='utf-8').read().replace('miss_real[:10]', 'miss_real').replace('num_bad[:10]', 'num_bad')
_ns = {'__file__': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_canon.py'), '__name__': 'verify_all'}
exec(compile(_src, 'verify_canon(all)', 'exec'), _ns)
class V: verify = staticmethod(_ns['verify'])
def run(pod, src):
    a = dupsim.assemble(pod)
    tmp = tempfile.mkdtemp(); p = os.path.join(tmp, 'canon_text.txt')
    with open(p, 'w', encoding='utf-8') as f:
        for i, (t, o) in enumerate(a): f.write(f'{i}\t-\t\t{t.replace(chr(9), " ").replace(chr(10), " ")}\t0\n')
    return V.verify(src, p, os.path.join(pod, 'base_marked.docx'), [os.path.join(pod, 'base_orig.docx')])
if __name__ == '__main__':
    r = run(sys.argv[1], sys.argv[2]); print({k: r[k] for k in ('lines', 'missing', 'missing_in_objects', 'duplicates', 'duplicates_explained')})
    for e in r['examples_missing'][:int(os.environ.get('N', '6'))]: print('  ', e)
