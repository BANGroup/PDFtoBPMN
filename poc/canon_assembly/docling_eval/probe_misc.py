import sys,json,collections,re
sys.path.insert(0,'/home/budnik_an/Obligations/poc/canon_assembly/docling_eval'); sys.path.insert(0,'/home/budnik_an/Obligations/poc/canon_assembly')
import run_eval as R, assemble as A
from lxml import etree
import zipfile
tag=sys.argv[1]
out=R.SCR
for name in ('KD-RG-174-05','RD-M1.029-07','x_visio_RG-201-03','x_visio_B1.034-01','x_excel_M1.027-06','x_txbx_B1.004-06'):
    dx=R.INPUTS[name][0]
    d=R.load(f'{out}/json_{tag}/{name}.docx.json')
    flat=R.flat_texts(d,True)
    c=collections.Counter(A.norm(t) for t in flat)
    dup=sum(v-1 for v in c.values() if v>1)
    ours=[A.norm(t) for pg in A.docx_pages(dx) for t in pg]; ours=[x for x in ours if x]
    dset=set(c); hay=' '+' '.join(c)+' '
    miss=[x for x in ours if x not in dset and (' '+x+' ') not in hay]
    au=R.xml_audit(dx)
    z=zipfile.ZipFile(dx); root=etree.fromstring(z.read('word/document.xml'))
    W='{%s}'%R.NS['w']
    body_txt=' '+A.norm(' '.join(''.join(x.text or '' for x in p.iter(W+'t')) for p in root.iter(W+'p')))+' '
    emb=[t for v in list(au['vsdx'].values())+list(au['xlsx'].values()) for t in v]
    seen=set(); uniq=[]
    for t in emb:
        n=A.norm(t)
        if len(n)>=3 and n not in seen and (' '+n+' ') not in body_txt: seen.add(n); uniq.append(t)
    fnd=[t for t in uniq if (' '+A.norm(t)+' ') in hay]
    pics=[p for p in d.pictures]
    print(name,tag,'dup_norm_texts',dup,'ours_not_in_docling',len(miss),'of',len(ours),'| embedded texts absent from doc body:',len(uniq),'found in docling',len(fnd))
    print('   miss sample',[m[:70] for m in miss[:4]], '  emb-not-found sample',[t[:30] for t in uniq if t not in fnd][:6])
    print('   pics w/o image',sum(1 for p in pics if p.image is None),'of',len(pics), 'image uri type',[ (str(p.image.uri)[:20], p.image.mimetype) for p in pics if p.image][:2])
    # numbered heading check
    nl=[i for i in R.items(d) if str(i.label.value)=='list_item']
    print('   list marker sample',[(getattr(i,'marker',''),i.text[:30]) for i in nl if getattr(i,'marker','')][:3])
