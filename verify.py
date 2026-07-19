#!/usr/bin/env python3
import json, re, sys, concurrent.futures as cf
import dns.resolver
import requests

records = json.load(open('records_merged.json', encoding='utf-8'))

def dom_of(email): return email.split('@')[-1].lower().strip().strip('.')

# ---- 1. DNS check unique domains (MX or A) ----
domains = set()
for r in records:
    for e in r['emails']:
        domains.add(dom_of(e))

resolver = dns.resolver.Resolver()
resolver.lifetime = 6; resolver.timeout = 6

def dns_ok(d):
    for rt in ('MX','A'):
        try:
            ans = resolver.resolve(d, rt)
            if ans: return True
        except Exception:
            pass
    # try AAAA as last resort
    try:
        if resolver.resolve(d,'AAAA'): return True
    except Exception:
        pass
    return False

dom_status = {}
with cf.ThreadPoolExecutor(max_workers=30) as ex:
    fut = {ex.submit(dns_ok, d): d for d in domains}
    for f in cf.as_completed(fut):
        d = fut[f]
        try: dom_status[d] = f.result()
        except Exception: dom_status[d] = False

bad_domains = sorted(d for d,ok in dom_status.items() if not ok)
print('unique email domains:', len(domains))
print('domains with NO DNS presence (to discard):', len(bad_domains))
for d in bad_domains: print('   x', d)

# ---- 2. Fetch websites for rows that have website but no email ----
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
BAD_EMAIL_SUFFIX = ('.png','.jpg','.jpeg','.gif','.webp','.svg','.css','.js','.wixpress.com','sentry.io','example.com','domain.com','yourdomain.com','email.com')
HDRS = {'User-Agent':'Mozilla/5.0 (compatible; contact-finder/1.0)'}

def norm_site(u):
    if not re.match(r'^https?://', u): u='http://'+u
    return u

def find_email_on_site(base):
    base = norm_site(base)
    root = re.match(r'^(https?://[^/]+)', base)
    root = root.group(1) if root else base
    tried = []
    cands = [base, root, root+'/contact', root+'/contact-us', root+'/contactus',
             root+'/iletisim', root+'/en/contact', root+'/about', root+'/tr/iletisim']
    seen=set(); out=[]
    for url in cands:
        if url in seen: continue
        seen.add(url)
        try:
            resp = requests.get(url, headers=HDRS, timeout=12, verify=False, allow_redirects=True)
            html = resp.text
        except Exception:
            continue
        # mailto first
        found = re.findall(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', html)
        found += EMAIL_RE.findall(html)
        for e in found:
            el=e.lower().strip('.')
            if any(el.endswith(s) or s in el for s in BAD_EMAIL_SUFFIX): continue
            if len(el)>60: continue
            if el not in out: out.append(el)
        if out: break
    return out

import urllib3
urllib3.disable_warnings()

web_only = [r for r in records if r['websites'] and not r['emails']]
print('\nwebsite-only rows to probe:', len(web_only))

def probe(r):
    for w in r['websites']:
        try:
            found = find_email_on_site(w)
        except Exception:
            found=[]
        if found:
            return r, found
    return r, []

fetch_results=[]
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    futs=[ex.submit(probe, r) for r in web_only]
    for f in cf.as_completed(futs):
        r, found = f.result()
        fetch_results.append((r, found))

# validate fetched emails via DNS and attach
added=0
for r, found in fetch_results:
    good=[]
    for e in found:
        d=dom_of(e)
        if d not in dom_status:
            dom_status[d]=dns_ok(d)
        if dom_status[d] and e not in good:
            good.append(e)
    # prefer info@/contact@/sales@ style, limit to 2
    good.sort(key=lambda e: (0 if re.match(r'(info|contact|sales|export|mail|office)',e) else 1, len(e)))
    if good:
        r['emails'].extend(good[:2])
        r['emails']=list(dict.fromkeys(r['emails']))
        r['fetched_email']=True
        added+=1
print('website-only rows where a valid email was found online:', added)

# ---- 3. Discard emails whose domain has zero DNS presence ----
discarded=[]
for r in records:
    keep=[]
    for e in r['emails']:
        d=dom_of(e)
        if dom_status.get(d, True):
            keep.append(e)
        else:
            discarded.append(e)
    r['emails']=keep
print('\nindividual emails discarded (dead domains):', len(discarded))

json.dump(records, open('records_final.json','w'), ensure_ascii=False, indent=1)

# ---- Final counts ----
only_web=sum(1 for r in records if r['websites'] and not r['emails'])
only_mail=sum(1 for r in records if r['emails'] and not r['websites'])
both=sum(1 for r in records if r['emails'] and r['websites'])
neither=sum(1 for r in records if not r['emails'] and not r['websites'])
print('\n=== FINAL COUNTS ===')
print('total rows :', len(records))
print('only website, no email :', only_web)
print('only email, no website :', only_mail)
print('both website and email :', both)
print('neither website nor email :', neither)
