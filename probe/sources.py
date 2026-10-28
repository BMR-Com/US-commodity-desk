import requests
H={'User-Agent':'Mozilla/5.0'}
out=open('probe/out_basis3.txt','w')
def log(*a):
    s=' '.join(str(x) for x in a); print(s); out.write(s+'\n'); out.flush()
try:
    r=requests.get('https://agtransport.usda.gov/api/views.json',params={'limit':300},headers=H,timeout=40); log('views',r.status_code,len(r.content))
    for v in r.json():
        nm=v.get('name',''); 
        if any(k in nm.lower() for k in ('basis','price','bid','spread')):
            log('  V',v['id'],'|',nm,'|',v.get('rowsUpdatedAt'),'|',', '.join(c['fieldName'] for c in v.get('columns',[]))[:250])
except Exception as e: log('ERR',e)
for vid in []: pass
out.close()
