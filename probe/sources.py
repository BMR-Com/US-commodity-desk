import re, requests, time
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
B = "https://esmis.nal.usda.gov"
out = []
for page in (0, 20, 36, 37):
    r = requests.get(f"{B}/publication/cme-group-weekly-recaptrading?page={page}", headers=H, timeout=60)
    files = re.findall(r'href="([^"]+\.(?:txt|TXT|pdf|PDF))"', r.text)
    dates = re.findall(r'(\w{3} \d{1,2} \d{4})', r.text)
    out.append(f"PAGE {page} status {r.status_code} files {len(files)} first {files[:4]} dates {dates[:6]} last {dates[-3:]}")
txt = [f for f in re.findall(r'href="([^"]+\.TXT)"', requests.get(f"{B}/publication/cme-group-weekly-recaptrading?page=36", headers=H, timeout=60).text, re.I)]
if txt:
    u = txt[-1] if txt[-1].startswith("http") else B + txt[-1]
    out.append("OLD FILE " + u + "\n" + requests.get(u, headers=H, timeout=60).text[:3500])
# Cornell library archive
r = requests.get("https://usda.library.cornell.edu/concern/publications/0v838058r?locale=en", headers=H, timeout=60)
out.append(f"CORNELL status {r.status_code} " + str(re.findall(r'(\d{4})', r.text)[:0]) + " years " + str(sorted(set(re.findall(r'release_datepublished[^"]*?(\d{4})', r.text)))[:30]) + " " + str(re.findall(r'href="([^"]+\.(?:txt|TXT))"', r.text)[:3]))
m = re.findall(r'<option[^>]*value="(\d{4})"', r.text)
out.append("cornell year options " + str(m[:40]))
open("probe/out_cme.txt", "w").write("\n\n".join(out))
print("\n\n".join(out))
