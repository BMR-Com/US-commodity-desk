import requests, itertools, io, zipfile
H={'User-Agent':'Mozilla/5.0'}
out=open('probe/out_basis.txt','w')
def log(*a):
    s=' '.join(str(x) for x in a); print(s); out.write(s+'\n'); out.flush()
def get(u,n=600):
    try:
        r=requests.get(u,headers=H,timeout=40)
        log('URL',u,r.status_code,len(r.content)); 
        if r.ok: log(r.text[:n].replace('\r',''))
        return r
    except Exception as e: log('URL',u,'ERR',str(e)[:100])
# old AMS market news archive
for u in ['https://search.ams.usda.gov/mndms/2015/06/','https://search.ams.usda.gov/mnsearch/','https://www.ams.usda.gov/mnreports/gx_gr110.txt',
          'https://www.ams.usda.gov/mnreports/sj_gr110.txt','https://www.ams.usda.gov/mnreports/gl_gr110.txt','https://www.ams.usda.gov/mnreports/nw_gr110.txt',
          'https://www.ams.usda.gov/mnreports/ams_3192.pdf','https://www.ams.usda.gov/mnreports/ams_2850.pdf']:
    get(u,300)
for pre,num in itertools.product(['GX','SJ','GL','NW','KC','MS','AM','WA','TS'],['GR110','GR111','GR112','GR113','GR115','GR116','GR117','GR210']):
    u=f'https://search.ams.usda.gov/mndms/2015/06/{pre}_{num}20150602.TXT'
    try:
        r=requests.get(u,headers=H,timeout=30)
        if r.ok and len(r.content)>200: log('HIT',u,len(r.content)); log(r.text[:900].replace('\r',''))
        else: log('miss',u,r.status_code)
    except Exception as e: log('miss',u,'ERR',str(e)[:60])
# ERS monthly price datasets
for u in ['https://www.ers.usda.gov/data-products/feed-grains-database','https://www.ers.usda.gov/data-products/wheat-data','https://www.ers.usda.gov/data-products/oil-crops-yearbook']:
    r=get(u,0)
    if r is not None and r.ok:
        import re
        for m in sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip)[^"]*)"',r.text)))[:40]: log('  link',m)
out.close()
