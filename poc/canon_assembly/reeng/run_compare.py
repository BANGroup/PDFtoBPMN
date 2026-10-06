import sys, wordrun as W
slug=sys.argv[1]; p=lambda n: W.winpath(f'{slug}/{n}')
r=W.run([{'op':'compare','orig':p('base_orig.docx'),'revised':p('canon.docx'),'out':p('markup.docx')}], slug+'_cmp', 1200)
print(r['log'], r['out'], r['sec'])
