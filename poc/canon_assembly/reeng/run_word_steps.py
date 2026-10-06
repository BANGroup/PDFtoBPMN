"""Word-этапы. python run_word_steps.py <slug> --assemble | --final [--nocompare]"""
import sys, json, os
import wordrun as W
slug = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
pl = json.load(open(os.path.join(here, [d for d in os.listdir(here) if os.path.exists(f'{d}/plan.json') and json.load(open(f'{d}/plan.json'))['slug'] == slug][0], 'plan.json')))
p = lambda n: W.winpath(f'{slug}/{n}')
if '--assemble' in sys.argv:
    r = W.run([{'op': 'assemble', 'base': p('base_marked.docx'), 'out': p('canon_raw.docx'), 'inserts': pl['inserts']}], slug + '_asm', 1500)
    print(r['log'][-400:], r['out'], r['sec'])
if '--final' in sys.argv:
    steps = [{'op': 'dump', 'src': p('canon.docx'), 'out': p('canon_dump.txt')}, {'op': 'pdf', 'src': p('canon.docx'), 'out': p('canon.pdf')}]
    r = W.run(steps, slug + '_fin', 1500)
    print(r['log'][-300:], r['out'], r['sec'])
    if '--nocompare' not in sys.argv:
        for att in (1, 2):
            r = W.run([{'op': 'compare', 'orig': p('base_orig.docx'), 'revised': p('canon.docx'), 'out': p('markup.docx')}], slug + '_cmp', 1500)
            print(r['log'][-200:])
            if 'ERROR' not in r['log']: break
