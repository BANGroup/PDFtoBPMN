import json,sys
d=json.load(open(sys.argv[1]+'/check.json'))
m=d['metrics']; print({k:v for k,v in m.items() if k!='regions_tables_images'})
skip=sys.argv[2:] 
for x in d['defects']:
    print(x['severity'][:3],x['type'][:28],'|',x['where'][:45],'|',x['what'][:int(200)])
