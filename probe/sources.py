import requests, re, json
H={'User-Agent':'Mozilla/5.0'}
out=open('probe/out_basis2.txt','w')
def log(*a):
    s=' '.join(str(x) for x in a); print(s); out.write(s+'\n'); out.flush()
def get(u,**k):
    try:
        r=requests.get(u,headers=H,timeout=25,**k); log('URL',u[:160],r.status_code,len(r.content)); return r
    except Exception as e: log('URL',u[:160],'ERR',str(e)[:80])
for q in ['basis','grain price','bids']:
    r=get('https://api.us.socrata.com/api/catalog/v1',params=dict(domains='agtransport.usda.gov',q=q,limit=30))
    if r is not None and r.ok:
        for x in r.json().get('results',[]):
            rs=x['resource']; log('  DS',rs['id'],'|',rs['name'],'|',rs.get('data_updated_at'),'|',', '.join(rs.get('columns_name',[]))[:300])
r=get('https://agtransport.usda.gov/api/catalog/v1',params=dict(q='basis',limit=30))
if r is not None and r.ok:
    for x in r.json().get('results',[]):
        rs=x['resource']; log('  DS2',rs['id'],'|',rs['name'],'|',', '.join(rs.get('columns_name',[]))[:300])
for u in ['https://www.ers.usda.gov/data-products/feed-grains-database','https://www.ers.usda.gov/data-products/wheat-data','https://www.ers.usda.gov/data-products/oil-crops-yearbook']:
    r=get(u)
    if r is not None and r.ok:
        for m in sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip)[^"]*)"',r.text)))[:40]: log('  link',m)
out.close()
