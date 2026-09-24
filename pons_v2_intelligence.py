"""PONS V2 read-only intelligence adapter.

Uses the public Pons Portal read API for verified curve progress and holders.
Trade/sniper metrics are deliberately not fabricated; they can be merged by a
configured Stage-2 provider until direct event indexing is enabled.
"""
import json, urllib.request, urllib.parse, os
BASE='https://api.ponsportal.fun'

def _get(path):
    req=urllib.request.Request(BASE+path,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.0'})
    with urllib.request.urlopen(req,timeout=12) as r:
        raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('PONS response too large')
    x=json.loads(raw)
    if not isinstance(x,dict) or x.get('ok') is False: raise ValueError(str(x.get('error','PONS API error'))[:160])
    return x

def _all_holders(address, max_pages=None):
    """Fetch the complete holder set only after Stage 1 has crossed 90%.

    Pons documents cursor pagination and a strict holder endpoint rate limit, so
    this is deliberately Stage-2-only and capped. If pagination cannot complete,
    concentration remains unavailable and the alert stays fail-closed.
    """
    max_pages=int(os.environ.get('PONS_V2_HOLDER_MAX_PAGES','8') if max_pages is None else max_pages)
    path='/token/'+urllib.parse.quote(address,safe='')+'/holders'
    out=[]; params={}; pages=0
    while pages < max_pages:
        qs=('?'+urllib.parse.urlencode(params)) if params else ''
        x=_get(path+qs); pages+=1
        items=x.get('holders')
        if not isinstance(items,list): raise ValueError('PONS holders list missing')
        out.extend(items)
        params=x.get('next_page_params')
        if not params: return out,True,pages
        if not isinstance(params,dict): raise ValueError('PONS holder cursor invalid')
    return out,False,pages

def _holder_address(h):
    if not isinstance(h,dict): return ''
    for k in ('address','address_hash','holder','wallet','hash'):
        v=h.get(k)
        if isinstance(v,str) and v.startswith('0x') and len(v)==42:return v.lower()
    a=h.get('address')
    if isinstance(a,dict):
        for k in ('hash','address_hash'):
            v=a.get(k)
            if isinstance(v,str) and v.startswith('0x') and len(v)==42:return v.lower()
    return ''

def _holder_value(h):
    if not isinstance(h,dict):return None
    for k in ('value','balance','token_balance','amount'):
        v=h.get(k)
        if isinstance(v,dict):v=v.get('value') or v.get('raw')
        if v is not None:
            try:return int(v)
            except (TypeError,ValueError):pass
    return None

def _holder_stats(holders, deployer=''):
    vals=[]; dev=None; deployer=str(deployer or '').lower()
    for h in holders:
        v=_holder_value(h)
        if v is None or v < 0: continue
        vals.append(v)
        if deployer and _holder_address(h)==deployer:dev=v
    total=sum(vals)
    if total <= 0:return {'count':len(holders)}
    vals.sort(reverse=True)
    return {'count':len(holders),'top10Pct':sum(vals[:10])*100.0/total,
            'devPct':(dev*100.0/total if dev is not None else None)}

def fetch(address):
    token=_get('/token/'+urllib.parse.quote(address,safe=''))
    price=_get('/token/'+urllib.parse.quote(address,safe='')+'/price')
    progress=100.0 if int(token.get('phase') or 0)>=2 else float(price['progressPercent'])
    out=dict(token)
    out.update({'bondingProgress':progress,'market':{'progress':progress},'pons_price':price})
    # Do not burn the holder API's 8 req/min budget while silently tracking <90%.
    if progress >= 90:
        try:
            holders,complete,pages=_all_holders(address)
            out['pons_holders_pages']=pages
            out['pons_holders_complete']=complete
            if complete:
                hs=_holder_stats(holders,token.get('deployer'))
                out['holders']=hs
                out['holderCount']=hs.get('count')
                if hs.get('top10Pct') is not None:out['top10_holder_pct']=hs['top10Pct']
                if hs.get('devPct') is not None:out['dev_holding_pct']=hs['devPct']
        except Exception as e:
            out['pons_holder_error']=type(e).__name__
    return progress,out
