#!/usr/bin/env python3
import re, json
from collections import defaultdict

records = json.load(open('records_raw.json', encoding='utf-8'))

def clean_ws_url(u):
    u = u.strip().strip('.,;')
    u = re.sub(r'\s+', '', u)
    u = u.replace('\\', '')
    if u and not re.match(r'^https?://', u, re.I):
        if u.startswith('www.') or '.' in u:
            u = 'http://' + u
    # strip trailing uppercase/Turkish junk appended to the path (OCR/layout artifacts)
    m = re.match(r'(https?://[^/]+)(/.*)?$', u)
    if m and m.group(2):
        path = m.group(2)
        cut = re.search(r'[A-ZÇĞİÖŞÜ]', path)
        if cut:
            path = path[:cut.start()]
        u = m.group(1) + path
    return u

def clean_email(e):
    e = re.sub(r'\s+', '', e.strip().strip('.,;')).lower()
    return e

ADDR_KW = re.compile(r'(MAH\.|MAHALLES|CAD\.|CADDE|CADDES|SOK\.|SOKAK|SOKAĞI|BULVAR|NO:|NO :|BÖLGES|\bOSB\b|SANAY|STREET|\bROAD\b|FLOOR|\bPLOT\b|\bZONE\b|DISTRICT|BUILDING|AVENUE|\bBLOCK\b|\bTOWN\b|VILLAGE|\bHOUSE\b|\bMARG\b|COLONY|\bAREA\b|HIGHWAY|INDUSTR|ORGANIZE|ORGANİZE|NEAR |PLAZA|CENTER|CENTRE|\bUNIT\b|\bROOM\b|\bFLR\b|\bNO\.|\bST\.)', re.I)

SUFFIX_RE = re.compile(
    r'(.*?\b('
    r'A\.\s?Ş\.?|A\.S\.?|SANAY[İI] A\.?Ş\.?|'
    r'LTD\.?\s?ŞT[İI]\.?|L[İI]M[İI]TED Ş[İI]RKET[İI]|ANON[İI]M Ş[İI]RKET[İI]|'
    r'PVT\.?\s?LTD\.?|PRIVATE LIMITED|LLP|'
    r'CO\.,?\s?LTD\.?|CO\.\s?LIMITED|'
    r'GMBH|LLC|INC\.?|S\.P\.A\.?|S\.R\.L\.?|CORP\.?|'
    r'LTD\.?|L[İI]M[İI]TED|LIMITED'
    r'))', re.I)

NOISE_WORDS = re.compile(r'(Yarns|Fibers|Fibres|İplik(ler|leri)|Elyaf|Product Groups|Representati|Brand|/ )', re.I)

PRODSEG = re.compile(r'(Pamuk|Viskon|Polyester|Akrilik|Yün|Elastan|Naylon|Tekstüre|Rejenere|Organik|Fantezi|Teknik|Metalik|Metalize|Polipropilen|İpek|Elyaflar|Elyaf|El Örgü|Diğer|Bobin|Masura|Makaralar|RawYarns|Sektörel|Publication|Bobbin)[^\n]*?(Yarns|Fibers|Fibres|Fiber|Other|Reels|Organization|Yayın|Spool)', re.I)

def clean_name(raw, country):
    s = raw
    s = re.split(r'Kat[ıi]l[ıi]mc[ıi]\s*:', s)[0]
    s = re.split(r'Marka\s*/', s)[0]
    s = re.split(r'Temsilci', s)[0]
    s = re.split(r'Ürün Grupları', s)[0]
    s = re.split(r'Product Groups', s)[0]
    s = re.split(r'https?', s)[0]
    s = re.split(r'\bWeb\b', s)[0]
    s = re.sub(r'\d{4,}-?\d+', ' ', s)      # coordinate artifacts
    # strip product-category segments that got merged into the name (prefix pollution)
    prev=None
    while prev!=s:
        prev=s
        s=PRODSEG.sub(' ', s)
    s = s.replace('"',' ').replace('00',' ')
    s = re.sub(r'\s+', ' ', s).strip()
    # try legal suffix cut
    m = SUFFIX_RE.match(s)
    if m and len(m.group(1).strip()) >= 4:
        name = m.group(1).strip()
    else:
        am = ADDR_KW.search(s)
        if am and am.start() > 3:
            name = s[:am.start()].strip()
        elif country:
            ci = s.upper().find(country.upper())
            name = s[:ci].strip() if ci > 3 else s
        else:
            name = s
    name = re.sub(r'\s+', ' ', name).strip(' ,.-')
    return name

def name_score(name):
    """higher = cleaner/better company name"""
    if not name: return -100
    s = 0
    low = name.lower()
    # penalize pollution
    if NOISE_WORDS.search(name): s -= 40
    if 'marka' in low or 'brand' in low: s -= 20
    if re.search(r'\d{3,}', name): s -= 10
    if len(name) > 70: s -= 15
    if len(name) < 4: s -= 30
    # reward legal suffix presence
    if SUFFIX_RE.match(name): s += 10
    # reward mostly uppercase (company header style)
    letters = [c for c in name if c.isalpha()]
    if letters:
        up = sum(1 for c in letters if c.upper()==c)/len(letters)
        s += up*10
    # prefer shorter reasonable names
    s -= len(name)*0.05
    return s

EMAIL_BLACKLIST = {'0@0.com'}
EMAIL_FIX = {
 'info@turktex.netrenat':'info@turktex.net',
 'info@pyramidsfair.comfashio':'info@pyramidsfair.com',
}
for r in records:
    r['websites'] = list(dict.fromkeys(x for x in (clean_ws_url(u) for u in r['websites']) if x))
    ems=[]; seen=set()
    for e in r['emails']:
        ce=clean_email(e)
        ce=EMAIL_FIX.get(ce, ce)
        if ce in EMAIL_BLACKLIST: continue
        if ce and re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', ce) and ce not in seen:
            seen.add(ce); ems.append(ce)
    r['emails']=ems
    r['company']=clean_name(r['name_raw'], r['country'])

# ---- Union-find grouping by shared email ----
parent={}
def find(x):
    parent.setdefault(x,x)
    while parent[x]!=x:
        parent[x]=parent[parent[x]]; x=parent[x]
    return x
def union(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[rb]=ra

# node id per record
for idx,r in enumerate(records):
    parent[('r',idx)]=('r',idx)
# link records that share an email
email_first={}
for idx,r in enumerate(records):
    for e in r['emails']:
        if e in email_first:
            union(('r',email_first[e]), ('r',idx))
        else:
            email_first[e]=idx

groups=defaultdict(list)
for idx,r in enumerate(records):
    groups[find(('r',idx))].append(idx)

# Also merge no-email records that are exact duplicates by website+company
merged=[]
for root, idxs in groups.items():
    grp=[records[i] for i in idxs]
    emails=[]; 
    for r in grp:
        for e in r['emails']:
            if e not in emails: emails.append(e)
    websites=[]
    for r in grp:
        for w in r['websites']:
            if w not in websites: websites.append(w)
    products=[]
    for r in grp:
        for p in r['products']:
            if p not in products: products.append(p)
    # keep ALL distinct candidate names (deduped by core); final pick done later
    def core(x): return re.sub(r'[^a-z0-9]','', x.lower())
    cand=[]
    for r in grp:
        nm=r['company']
        if nm: cand.append((nm, r['country']))
    dedup=[]; seen_c=set()
    for nm,ctry in cand:
        c=core(nm)
        if not c: continue
        skip=False
        for j,(dn,dc) in enumerate(dedup):
            dcore=core(dn)
            if c==dcore or c in dcore or dcore in c:
                # keep the higher-scoring of the two
                if name_score(nm) > name_score(dn):
                    dedup[j]=(nm,ctry)
                skip=True; break
        if not skip:
            dedup.append((nm,ctry))
    merged.append({'name_candidates':dedup, 'companies':dedup, 'emails':emails, 'websites':websites, 'products':products})

# ---- Manual name overrides for residual mis-parsed entries (recovered from source) ----
OVERRIDES = [
 ('bansalspinning.com','BANSAL SPINNING MILLS PRIVATE LIMITED','India'),
 ('daromensucat','DARO MENSUCAT SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('polyarniplik.com','ERİŞİM TRİKO TEKNİK SERVİS VE İNŞAAT SANAYİ TİCARET LİMİTED ŞİRKETİ','Türkiye'),
 ('ertuiplik','ERTU İPLİK SANAYİ TİC. LTD. ŞTİ.','Türkiye'),
 ('happyyarn.com','İBERYARNS TEKSTİL İPLİK İTH. İHR. SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('knitmeyarns.com','İBERYARNS TEKSTİL İPLİK İTH. İHR. SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('img.com.tr','İSTMAG MAGAZİN GAZETECİLİK YAYINCILIK İÇ VE DIŞ TİC. LTD. ŞTİ.','Türkiye'),
 ('sinrylion.com','JINJIANG XINGLILAI YARNS CO., LTD.','China'),
 ('xll-group.com','JINJIANG XINGLILAI YARNS CO., LTD.','China'),
 ('kaleiplik','KALE İPLİK SAN. VE DIŞ TİC. A.Ş.','Türkiye'),
 ('kaynakgroup.com','KAYNAK İPLİK SANAYİ VE TİCARET ANONİM ŞİRKETİ','Türkiye'),
 ('msgiplik','MSG İPLİK SANAYİ VE TİCARET ANONİM ŞİRKETİ','Türkiye'),
 ('muradimtex.com','MURADIM TEKSTİL SANAYİ VE TİC. A.Ş.','Türkiye'),
 ('jsxszx.com','NANTONG POLYGOLD THREAD CO.,LTD','China'),
 ('color-search.com','DONGYANG TAILIAN ARTS & CRAFTS MANUFACTURER CO.,LTD','China'),
 ('ozvaycan.com','ÖZ VAYCAN TEKSTİL SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('seceniplik.com','SEÇEN İPLİK VE BÜKÜM TEKSTİL SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('usaktso.org','UŞAK TİCARET VE SANAYİ ODASI','Türkiye'),
 ('yangincitekstil.com','YANGINCI TEKSTİL SAN. VE TİC. A.Ş.','Türkiye'),
 ('yanteks.com','YANTEKS İNŞAAT TAAHHÜT TEKSTİL İTH. İHR. SAN. TİC. LTD. ŞTİ.','Türkiye'),
 ('gc-nylon.com','ZHEJIANG GUCHUANG CHEMICAL FIBER CO., LTD.','China'),
 ('zjoceanstar.com','ZHUJI BAIFUQIN TRADE CO., LTD','China'),
 ('jingyigroup.net','WUJIANG JINGYI SPECIAL FIBER CO.,LTD','China'),
 ('indospun.com','INDO SPUN LLP','India'),
 ('indorama.com','INDORAMA İPLİK SAN. VE TİC. A.Ş.','Türkiye'),
 ('isiksoytekstil.com.tr','IŞIKSOY TEKSTİL İNŞ. TAAH. SAN. TİC. A.Ş.','Türkiye'),
 ('rbkaresi.com.tr','KARESİ POLYESTER VE PETROKİMYA SANAYİ ANONİM ŞİRKETİ','Türkiye'),
 ('kenanozsoytekstil.com','KENAN ÖZSOY TEKSTİL KON. İNŞ. PAZ. SAN. TİC. LTD. ŞTİ.','Türkiye'),
 ('sebatextile.com.tr','SEBA PAMUK TEKSTİL SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
 ('sayindokuma.com','SAYIN TEKSTİL SAN. VE TİC. A.Ş.','Türkiye'),
]
OVERRIDES += [
 ('pyramidsfair','PYRAMIDS GRUP FUARCILIK A.Ş.','Türkiye'),
 ('safteks.com','SAF MENSUCAT SAN. VE TİC. A.Ş.','Türkiye'),
 ('tepar.com','TEPAR TEKSTİL SANAYİ VE TİC. A.Ş.','Türkiye'),
 ('iranyarn.ir','IRAN YARN (Abtin Tejarat Ayrik)','Iran'),
 ('nhrtrading.com','NHR İPLİK TEKSTİL İTHALAT İHRACAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ','Türkiye'),
 ('hoyiatex.com','SHANGHAI HOYIA TEXTILE CO., LTD','China'),
 ('mangoiplik.com','MANGO İPLİK SAN. TİC. VE LTD. ŞTİ.','Türkiye'),
 ('uzairecg@gmail.com','U.S. PUBLISHERS (PVT.) LTD','Pakistan'),
 ('melihturky@gmail.com','TÜRKAYLAR TEKSTİL SANAYİ VE TİCARET A.Ş.','Türkiye'),
 ('303745021@qq.com','JIN LI CHENG COMPANY','Vietnam'),
 ('berrakdurmaz@tantas.com.tr','E. MIROGLIO EAD','Bulgaria'),
]

GENERIC=set('san tic ltd sti ve ic dis ith ihr ins taah paz and the co pvt inc textile tekstil iplik iplikleri sanayi ticaret anonim sirketi group yarns yarn private limited company corp new material fiber fibre import export trade trading'.split())
def name_tokens(nm):
    return [w for w in re.findall(r'[a-zçğıöşü]{4,}', nm.lower()) if w not in GENERIC]
def domain_str(row):
    s=''
    for x in row['emails']+row['websites']:
        s+=re.sub(r'[^a-z]','', x.lower())
    return s
def select_best(row):
    ds=domain_str(row)
    best=None; bestsc=-1e9
    for nm,ctry in row['name_candidates']:
        sc=name_score(nm)
        for tk in name_tokens(nm):
            if tk in ds:
                sc+=100; break
        if sc>bestsc:
            bestsc=sc; best=(nm,ctry)
    if best: row['companies']=[best]

# ---- Curated genuinely-grouped companies (real shared-email cases) ----
CURATED_MULTI = {
 'urmpl.com':[('KAYAVLON IMPEX PVT. LTD','India'),('UNITED RAW MATERIAL PTE. LTD','Singapore')],
 'madhusudangroup.com':[('SHRI MADHUSUDAN RAYONS PVT. LTD','India'),('MADHUSUDAN THREADS','India')],
 'pankajenka.com':[('PANKAJ ENKA PRIVATE LIMITED','India'),('HARMONY YARNS PVT LTD','India')],
}
def apply_override(row):
    hay = ' '.join(row['emails']+row['websites']).lower().replace(' ','')
    for key,vals in CURATED_MULTI.items():
        if key in hay:
            row['companies']=list(vals); return
    for key,name,ctry in OVERRIDES:
        if key.replace(' ','') in hay:
            row['companies']=[(name,ctry)]
            return

for row in merged:
    select_best(row)
    apply_override(row)

# ---- Clean residual junk in company name strings ----
def scrub_name(nm):
    s = nm
    s = re.split(r'\bmail\s*:', s)[0]           # drop trailing "mail: ..." artifacts
    s = re.sub(r'@\S+', ' ', s)
    s = re.sub(r'^[\\"0\s]+', '', s)            # leading junk: backslash, quote, 0
    s = re.sub(r'\b(ves|BRAND|Brand)\b', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip(' ,.-')
    return s
for row in merged:
    row['companies'] = [(scrub_name(n), c) for (n,c) in row['companies'] if scrub_name(n)]

# ---- Reassign cross-contaminated emails to their true owners ----
REASSIGN = [
 ('karaholding.com','KARAFİBER TEKSTİL SAN. VE TİC. A.Ş.','Türkiye'),
 ('kempasiplik.com','KEMPAŞ İPLİK TEKSTİL SAN. VE TİC. LTD. ŞTİ.','Türkiye'),
]
def norm_txt(x): return re.sub(r'[^a-z0-9]','', x.lower())
for dom, owner, ctry in REASSIGN:
    moved=[]
    for row in merged:
        keep=[]
        for e in row['emails']:
            if dom in e: moved.append(e)
            else: keep.append(e)
        row['emails']=keep
    # find/create owner row
    target=None
    for row in merged:
        if any(norm_txt(owner)==norm_txt(n) for n,_ in row['companies']):
            target=row; break
    if target is None:
        target={'companies':[(owner,ctry)],'emails':[],'websites':[],'products':[]}
        merged.append(target)
    for e in moved:
        if e not in target['emails']: target['emails'].append(e)

# ---- Final dedup: collapse rows with identical company set + website (no-email dupes) ----
seen={}; final=[]
for row in merged:
    compkey = tuple(sorted(norm_txt(c[0]) for c in row['companies']))
    webkey = tuple(sorted(row['websites']))
    k = (compkey, webkey)
    if compkey and k in seen:
        ex=seen[k]
        for e in row['emails']:
            if e not in ex['emails']: ex['emails'].append(e)
        for p in row['products']:
            if p not in ex['products']: ex['products'].append(p)
        continue
    seen[k]=row; final.append(row)
merged=final

# ---- Fuzzy dedup of no-contact junk duplicates against other rows ----
def sig_tokens(row):
    toks=set()
    for n,_ in row['companies']:
        for w in re.findall(r'[A-Za-zÇĞİÖŞÜçğıöşü]{3,}', n.lower()):
            if w not in ('san','tic','ltd','sti','ltd.','ve','ic','dis','ith','ihr','ins',
                         'taah','paz','and','the','co','pvt','inc','sti̇','a.ş','textile',
                         'tekstil','iplik','sanayi','ticaret','anonim','sirketi','group',
                         'yarns','yarn','private','limited','company'):
                toks.add(w)
    return toks
def has_contact(row): return bool(row['emails'] or row['websites'])

keep=[True]*len(merged)
for i,row in enumerate(merged):
    if has_contact(row): continue
    ti=sig_tokens(row)
    if not ti: continue
    for j,other in enumerate(merged):
        if i==j or not keep[j]: continue
        tj=sig_tokens(other)
        if not tj: continue
        inter=ti & tj
        # drop row i if it's essentially covered by another (prefer keeping contact rows / cleaner)
        if ti <= tj and (has_contact(other) or len(other['companies'][0][0])>=len(row['companies'][0][0])):
            keep[i]=False; break
        if len(inter)>=2 and len(inter)>=0.7*len(ti) and has_contact(other):
            keep[i]=False; break
merged=[r for k,r in zip(keep,merged) if k]

# ---- Drop explicit junk duplicate rows (fragments of clean rows that exist) ----
DROP_SUBSTR = ['indoflame','isiksoysem','karafitekstisel','irketmsg',
               'tailianyarns','rameszenith','sayintekstisayin']
def is_junk(row):
    if not row['companies']: return True   # empty name
    if row['emails'] or row['websites']: return False
    core=norm_txt(row['companies'][0][0])
    if core=='kempaiplik': return True
    return any(s in core for s in DROP_SUBSTR)
merged=[r for r in merged if not is_junk(r)]

# ---- Targeted name fixes for garbled/mis-ordered rows ----
def fix_row(row):
    comps=row['companies']
    if not comps: return
    c0=norm_txt(comps[0][0])
    if 'simfleks' in c0 or 'recron' in c0 or 'tangsha' in c0:
        row['companies']=[('SİMFLEKS TEKSTİL VE AMBALAJ SAN. TİC. A.Ş.','Türkiye')]
    # UĞURLULAR row wrongly led by U.S. PUBLİS fragment
    doms=' '.join(row['emails']+row['websites']).lower()
    if 'ugurlular' in doms:
        row['companies']=[('UĞURLULAR TEKSTİL SAN. VE TİC. A.Ş.','Türkiye')]
for row in merged:
    fix_row(row)

print('groups (email-merged) count:', len(merged))
multi=[m for m in merged if len(m['companies'])>1]
print('rows with >1 company name:', len(multi))
for m in multi[:25]:
    print('  ', [c[0] for c in m['companies']], '<=', m['emails'])

json.dump(merged, open('records_merged.json','w'), ensure_ascii=False, indent=1)
