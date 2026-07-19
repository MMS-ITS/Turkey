#!/usr/bin/env python3
import re, html, json

raw = open('raw_extract.txt', encoding='utf-8').read()

# --- Normalize noise ---
t = raw
t = re.sub(r'E-\s*\n\s*mail', 'E-mail', t)
t = re.sub(r'E-\s+mail', 'E-mail', t)
t = re.sub(r'[A-Za-z]?HYPERLINK\s+"mailto:([^"]+)"\s*\\h\s*\S*', r'\1', t)
t = re.sub(r'HYPERLINK\s+"[^"]*"\s*\\h', ' ', t)
t = re.sub(r'Salon / Hall\s*:\s*\S+\s*Stant / Stand\s*:\s*\S+', '', t)
t = re.sub(r'(?m)^\s*\d{4,}-?\d*(?=[A-ZÇĞİÖŞÜ])', '', t)
t = re.sub(r'(?m)^\s*0(?=[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ])', '', t)

norm = t
chunks = re.split(r'Tel / Phone\s*:?', norm)

COUNTRIES = ['TÜRKİYE','TURKIYE','TURKEY','INDIA','CHINA','PAKISTAN','EGYPT','GERMANY',
 'UZBEKISTAN','TAIWAN','UNITED STATES','UNITED KINGDOM','ITALY','VIETNAM','VİETNAM','THAILAND',
 'SOUTH KOREA','KOREA','JAPAN','INDONESIA','BANGLADESH','SPAIN','FRANCE','PORTUGAL',
 'GREECE','TAJIKISTAN','TURKMENISTAN','KAZAKHSTAN','IRAN','SWITZERLAND','AUSTRIA',
 'BELGIUM','NETHERLANDS','POLAND','SYRIA','UNITED ARAB EMIRATES','UAE','HONG KONG',
 'SINGAPORE','MALAYSIA','SRI LANKA']
COUNTRY_DISPLAY = {'TÜRKİYE':'Türkiye','TURKIYE':'Türkiye','TURKEY':'Türkiye','VİETNAM':'Vietnam',
 'UAE':'United Arab Emirates'}

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

def extract_country(block):
    up = block.upper()
    found=None; pos=-1
    for c in COUNTRIES:
        i=up.rfind(c)
        if i>pos:
            pos=i; found=c
    return found

COMPKW = re.compile(r'(TEKST[İI]L|TEXTILE|SPINN|İPL[İI]K|IPLIK|COTTON|\bYARN\b|CO\.,?\s?LTD|CO\.\s?LIMITED|\bPVT\b|GMBH|\bLLC\b|A\.\s?Ş|LTD\.?\s?ŞT|L[İI]M[İI]TED|LIMITED|SAN\.|T[İI]C\.|MENSUCAT|\bGROUP\b|IMPEX|INDUSTR|FIBER|FIBRE|TRADING|IMPORT|EXPORT|ENTERPRISE|MILLS|CHEMICAL|CASHMERE|DENIM|POLYESTER|NYLON|WOOL|SYNTEX|SPINTEX)', re.I)
def is_company_header(l):
    if len(l) >= 22: return True
    if COMPKW.search(l): return True
    return False

def parse_chunk(chunk):
    lines = chunk.split('\n')
    email=[]; web=[]; products=[]; nextname=[]
    mode='pre'; seen_web=False
    for raw_l in lines:
        l = raw_l.strip()
        if mode=='name':
            if l: nextname.append(l)
            continue
        if 'Product Groups' in raw_l:
            mode='prod'
            after = raw_l.split('Product Groups',1)[1].strip()
            if after: products.append(after)
            continue
        if l.startswith('Web'):
            w = re.sub(r'^Web\s*:?','',l).strip()
            if w: web.append(w)
            seen_web=True
            continue
        if ('mail' in l.lower() and '@' in raw_l) or (mode=='pre' and '@' in raw_l):
            # repair split first-letter artifacts: "y arn@x" -> "yarn@x"
            fixed = re.sub(r'(?<=\s)([A-Za-z])\s+([A-Za-z0-9._%+\-]*@)', r'\1\2', raw_l)
            for mm in EMAIL_RE.findall(fixed):
                if mm not in email: email.append(mm)
            continue
        if 'Marka / Brand' in raw_l or 'Temsilcilikler' in raw_l or 'Representative' in raw_l or 'Katılımcı' in raw_l:
            mode='brand'; continue
        if mode=='prod':
            if l=='' : continue
            if '/' in raw_l or l in ('Yarns','Fibers'):
                products.append(l); continue
            mode='name'; nextname.append(l); continue
        if mode=='brand':
            # brand values are short tokens; a real company header ends the brand block
            if l and is_company_header(l):
                mode='name'; nextname.append(l)
            continue
        # mode 'pre'
        if seen_web and l:
            mode='name'; nextname.append(l); continue
        # else phone continuation / noise -> ignore
    return email, web, products, nextname

def extract_products(prodlines):
    # take English side of "Turkish / English" pairs
    joined = ' '.join(prodlines)
    parts = re.findall(r'/\s*([A-Za-z][A-Za-z \-]+?(?:Yarns|Fibers|Fiber|Other))', joined)
    seen=[]; 
    for p in parts:
        p=p.strip()
        if p and p not in seen: seen.append(p)
    return seen

records=[]
# chunk[0] is first company's name/address (before its Tel)
pending_name = chunks[0]
for i in range(1, len(chunks)):
    email, web, products, nextname = parse_chunk(chunks[i])
    name_block = pending_name
    country = extract_country(name_block)
    records.append({
        'name_raw': ' '.join(x.strip() for x in name_block.split('\n') if x.strip()),
        'country': COUNTRY_DISPLAY.get(country, (country.title() if country else '')),
        'emails': email,
        'websites': web,
        'products': extract_products(products),
    })
    pending_name = '\n'.join(nextname)

print('total records parsed:', len(records))
# sample
for r in records[:6]:
    print(json.dumps(r, ensure_ascii=False))
print('...')
# stats
with_email=sum(1 for r in records if r['emails'])
with_web=sum(1 for r in records if r['websites'])
print('records with >=1 email:', with_email)
print('records with >=1 website:', with_web)
print('records with no email:', sum(1 for r in records if not r['emails']))
print('records with neither:', sum(1 for r in records if not r['emails'] and not r['websites']))

json.dump(records, open('records_raw.json','w'), ensure_ascii=False, indent=1)
