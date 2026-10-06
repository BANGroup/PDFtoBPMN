import sys,re,collections
sys.path.insert(0,'/home/budnik_an/Obligations/poc/canon_assembly/docling_eval'); sys.path.insert(0,'/home/budnik_an/Obligations/poc/canon_assembly')
import run_eval as R
PAT=re.compile(r'(Стр\.?|Page)\s*\d+\s*(из|of)',re.I)
for tag in ('2.80.0','2.131.0'):
  for name in ('KD-RG-174-05','RD-M1.029-07'):
    d=R.load(f'{R.SCR}/json_{tag}/{name}.pdf.json')
    body=[i for i,_ in d.iterate_items(with_groups=False)]
    fur=[i for i,_ in d.iterate_items(with_groups=False,included_content_layers=R.all_layers()) if str(i.label.value) in('page_header','page_footer')]
    bp=collections.defaultdict(int)
    for i in body:
        if hasattr(i,'text') and PAT.search(i.text or ''): bp[i.prov[0].page_no]+=1
    fp={i.prov[0].page_no for i in fur if PAT.search(getattr(i,'text','') or '')}
    hdrlabel_pages={i.prov[0].page_no for i in fur}
    print(tag,name,'pages',len(d.pages),'"Стр N из M" in body on pages',len(bp),'| in furniture on pages',len(fp),'| any furniture on pages',len(hdrlabel_pages))
    # body items that in top 12% of page
    top=0
    for i in body:
        if i.prov:
            pg=d.pages[i.prov[0].page_no]; 
            if i.prov[0].bbox.t>pg.size.height*0.93 and str(i.label.value) in ('text','section_header'): top+=1
    print('    body text items in top 7% of page:',top)
