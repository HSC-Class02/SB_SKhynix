import io, json, os, re, time, zipfile
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests, yaml
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
CFG=yaml.safe_load((ROOT/'config/config.yml').read_text(encoding='utf-8'))
METRICS=yaml.safe_load((ROOT/'config/metrics.yml').read_text(encoding='utf-8'))['metrics']
KEY=os.environ.get('OPENDART_API_KEY','').strip()
if not KEY: raise SystemExit('OPENDART_API_KEY secret is required.')
API='https://opendart.fss.or.kr/api'; CORP=CFG['company']['corp_code']; START=int(CFG['company']['start_year']); END=int(CFG['company']['end_year'] or datetime.now().year)
DATA=ROOT/'data'; RAW=DATA/'raw'; DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
s=requests.Session(); s.headers['User-Agent']='SB_SKhynix-DART-Agent/1.0'
def get(path,params,binary=False):
    p=dict(params); p['crtfc_key']=KEY; r=s.get(f'{API}/{path}',params=p,timeout=90); r.raise_for_status()
    if binary:return r.content
    o=r.json()
    if o.get('status') not in (None,'000'): raise RuntimeError(f"{o.get('status')}: {o.get('message')}")
    return o
def norm(x): return re.sub(r'[\s\(\)\[\]·•,.:;／/\\_-]','',str(x)).lower()
def num(v):
    if v is None:return None
    x=str(v).strip().replace(',','').replace('(','-').replace(')','')
    if x in ('','-','—','nan','None'):return None
    try:return float(x)
    except:return None
def find(rows,m):
    aliases=[norm(a) for a in METRICS[m]['aliases']]; best=None
    for row in rows:
        lab=norm(row.get('account_nm',''))
        for a in aliases:
            if lab==a:return row
            if a and (a in lab or lab in a):best=row
    return best
def val(rows,m):
    r=find(rows,m)
    if not r:return None
    for k in ('thstrm_amount','thstrm_add_amount'):
        if k in r and num(r[k]) is not None:return num(r[k])
    return None
def filings(year):
    return get('list.json',{'corp_code':CORP,'bgn_de':f'{year}0101','end_de':f'{year}1231','pblntf_ty':'A','sort':'date','sort_mth':'asc','page_no':1,'page_count':100}).get('list',[])
def target(name):return any(x in str(name) for x in ('사업보고서','반기보고서','분기보고서'))
def legacy(f):
    out={m:None for m in METRICS}
    try:
        content=get('document.xml',{'rcept_no':f['rcept_no']},True)
        if CFG['storage']['save_raw_filings']:(RAW/f"{f['rcept_no']}.zip").write_bytes(content)
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            text=' '.join(BeautifulSoup(z.read(n),'lxml-xml').get_text(' ',strip=True) for n in z.namelist() if n.lower().endswith(('.xml','.html','.htm')))
        for m,spec in METRICS.items():
            for a in spec['aliases']:
                p=text.lower().find(str(a).lower())
                if p>=0:
                    nums=re.findall(r'-?\d[\d,]*',text[p:p+500]); out[m]=num(nums[0]) if nums else None; break
    except Exception as e: print('[WARN] legacy parser:',e)
    return out
records=[]; meta=[]
for y in range(START,END+1):
    try: fs=[f for f in filings(y) if target(f.get('report_nm',''))]
    except Exception as e: print('[WARN] filing search',y,e); continue
    for f in fs:
        name=f.get('report_nm',''); kind='annual' if '사업보고서' in name else ('half-year' if '반기보고서' in name else 'quarterly'); code='11011' if kind=='annual' else ('11012' if kind=='half-year' else ('11014' if '3분기' in name else '11013'))
        base={'year':y,'report_type':kind,'report_nm':name,'rcept_no':f.get('rcept_no'),'rcept_dt':f.get('rcept_dt'),'dart_url':f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f.get('rcept_no')}"}
        meta.append(base)
        row=dict(base); structured=[]; fsdiv=None
        if y>=2015:
            for div in (CFG['financial_statement']['fs_div'],CFG['financial_statement']['fallback_fs_div']):
                try: structured=get('fnlttSinglAcntAll.json',{'corp_code':CORP,'bsns_year':str(y),'reprt_code':code,'fs_div':div}).get('list',[]); fsdiv=div; break
                except Exception: pass
        if structured:
            row.update({m:val(structured,m) for m in METRICS}); row['fs_div']=fsdiv; row['source']='OpenDART fnlttSinglAcntAll'
        else:
            row.update(legacy(f)); row['fs_div']=None; row['source']='OpenDART document.xml legacy parser'
        records.append(row); time.sleep(.12)
df=pd.DataFrame(records)
if not df.empty:
    df=df.sort_values(['year','report_type','rcept_dt']).drop_duplicates(['year','report_type'],keep='last')
    div=lambda a,b: a/b if pd.notna(a) and pd.notna(b) and b!=0 else None
    df['operating_margin']=[div(a,b) for a,b in zip(df.operating_income,df.revenue)]
    df['net_margin']=[div(a,b) for a,b in zip(df.net_income,df.revenue)]
    df['roe']=[div(a,b) for a,b in zip(df.net_income,df.total_equity)]
    df['roa']=[div(a,b) for a,b in zip(df.net_income,df.total_assets)]
    df['debt_ratio']=[div(a,b) for a,b in zip(df.total_liabilities,df.total_equity)]
    df['current_ratio']=[div(a,b) for a,b in zip(df.current_assets,df.current_liabilities)]
    df['asset_turnover']=[div(a,b) for a,b in zip(df.revenue,df.total_assets)]
else: df=pd.DataFrame(columns=['year','report_type'])
df.to_csv(DATA/'financials.csv',index=False,encoding='utf-8-sig'); df.to_json(DATA/'financials.json',orient='records',force_ascii=False,indent=2); (DATA/'filings.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print('records:',len(df))
