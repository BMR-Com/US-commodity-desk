import requests, gzip
H={'User-Agent':'Mozilla/5.0'}
log=open('probe/out_basis4.txt','w')
for vid in ['v85y-3hep','g92w-8cn7']:
    r=requests.get(f'https://agtransport.usda.gov/resource/{vid}.csv',params={'$limit':2000000},headers=H,timeout=300)
    log.write(f'{vid} {r.status_code} {len(r.content)}\n'); log.write(r.text[:1500]+'\n')
    if r.ok: gzip.open(f'probe/agt_{vid}.csv.gz','wt').write(r.text)
log.close()
