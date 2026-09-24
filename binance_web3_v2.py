"""Authenticated Binance Web3 API Stage-2 intelligence.

Uses only documented read-only Market API endpoints. Requires BINANCE_WEB3_API_KEY
and BINANCE_WEB3_SECRET_KEY. It never determines launchpad bonding progress.
"""
import base64, hashlib, hmac, json, os, urllib.parse, urllib.request
from datetime import datetime, timezone

HOST='https://web3.binance.com'
BASE='/build'
CHAIN={'flap':'56','stonk':'CT_501','embercurve':'CT_501','pumpfun':'CT_501'}

def configured():
    return bool(os.environ.get('BINANCE_WEB3_API_KEY','').strip() and os.environ.get('BINANCE_WEB3_SECRET_KEY','').strip())

def _enc(v): return urllib.parse.quote(str(v),safe='')

def _request(path,params=None,method='GET',body=None):
    key=os.environ.get('BINANCE_WEB3_API_KEY','').strip(); secret=os.environ.get('BINANCE_WEB3_SECRET_KEY','').strip()
    if not key or not secret: raise RuntimeError('Binance Web3 API credentials not configured')
    params=params or {}
    query='&'.join(f'{_enc(k)}={_enc(v)}' for k,v in params.items() if v is not None)
    wire_path=BASE+path+('?' + query if query else '')
    raw_body='' if body is None else json.dumps(body,separators=(',',':'))
    now=datetime.now(timezone.utc)
    ts=now.strftime('%Y-%m-%dT%H:%M:%S.')+f'{now.microsecond//1000:03d}Z'
    pre=ts+method.upper()+wire_path+raw_body
    sig=base64.b64encode(hmac.new(secret.encode(),pre.encode(),hashlib.sha256).digest()).decode()
    headers={'Accept':'application/json','Accept-Encoding':'identity','User-Agent':'TrenchNet-V2/2.3','X-OC-APIKEY':key,'X-OC-TIMESTAMP':ts,'X-OC-SIGN':sig,'X-OC-RECV-WINDOW':'10000'}
    data=None
    if body is not None:
        data=raw_body.encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(HOST+wire_path,data=data,headers=headers,method=method.upper())
    with urllib.request.urlopen(req,timeout=float(os.environ.get('BINANCE_WEB3_TIMEOUT','15'))) as r: raw=r.read(4_000_001)
    if len(raw)>4_000_000: raise ValueError('Binance Web3 response too large')
    x=json.loads(raw)
    if not isinstance(x,dict) or str(x.get('code','0'))!='0' or x.get('success') is False:
        raise ValueError('Binance Web3 API error: '+str(x.get('msg','unknown'))[:120])
    return x.get('data')

def _f(v):
    try:return float(v)
    except (TypeError,ValueError):return None

def _i(v):
    try:return int(float(v))
    except (TypeError,ValueError):return None

def _rows(tag,chain,address):
    d=_request('/api/v1/dex/market/token/holder',{'binanceChainId':chain,'tokenContractAddress':address,'tagFilter':tag})
    return d if isinstance(d,list) else []

def _trade_window(chain,address,window_seconds=3600):
    import time
    cutoff=int((time.time()-window_seconds)*1000); cursor=None; rows=[]
    pages=max(1,min(6,int(os.environ.get('BINANCE_WEB3_TRADE_PAGES','3'))))
    for _ in range(pages):
        p={'binanceChainId':chain,'tokenContractAddress':address,'limit':500}
        if cursor:p['cursor']=cursor
        d=_request('/api/v1/dex/market/trades',p) or {}
        batch=d.get('trades') if isinstance(d,dict) else []
        if not isinstance(batch,list) or not batch:break
        stop=False
        for t in batch:
            tm=_i(t.get('time'))
            if tm is not None and tm<cutoff: stop=True; continue
            rows.append(t)
        cursor=d.get('cursor') if isinstance(d,dict) else None
        if stop or not cursor:break
    buys=[t for t in rows if str(t.get('type','')).lower()=='buy']; sells=[t for t in rows if str(t.get('type','')).lower()=='sell']
    def wallets(xs):return {str(t.get('userAddress')) for t in xs if t.get('userAddress')}
    def vol(xs):return sum((_f(t.get('volume')) or 0.0) for t in xs)
    return {'buys':len(buys),'sells':len(sells),'uniqueBuyers':len(wallets(buys)),'uniqueSellers':len(wallets(sells)),'buyVolume':vol(buys),'sellVolume':vol(sells),'volume':vol(rows),'windowSeconds':window_seconds}

def fetch(launchpad,address):
    """Return documented advanced intelligence for BSC/Solana launchpads."""
    chain=CHAIN.get(launchpad)
    if not chain or not configured():return {}
    out={'binance_web3_authenticated':True}
    # Holder ranking: top-10 concentration. Binance returns descending ranking, max 100.
    all_holders=_request('/api/v1/dex/market/token/holder',{'binanceChainId':chain,'tokenContractAddress':address})
    if isinstance(all_holders,list):
        pct=[_f(x.get('holdingPercent')) for x in all_holders[:10]]
        pct=[x for x in pct if x is not None]
        if pct: out.setdefault('holders',{})['top10Pct']=sum(pct)
    # Explicit Binance labels: 5=Sniper, 6=Bundler. Empty list is a verified zero result.
    sniper=_rows(5,chain,address); bundle=_rows(6,chain,address)
    sp=[_f(x.get('holdingPercent')) or 0.0 for x in sniper]
    out['snipers']={'count':len(sniper),'concentrationPct':sum(sp),'largestPct':max(sp) if sp else 0.0,
                    'stillHolding':sum(1 for x in sniper if (_f(x.get('holdAmount')) or 0)>0),
                    'sold':sum(1 for x in sniper if (_f(x.get('soldAmount')) or 0)>0 and (_f(x.get('holdAmount')) or 0)<=0)}
    out['bundled_wallet_count']=len(bundle)
    # Developer profile and historical launch summary.
    dev=_request('/api/v1/dex/market/memepump/tokenDevInfo',{'binanceChainId':chain,'tokenContractAddress':address}) or {}
    dh=dev.get('devHoldingInfo') if isinstance(dev,dict) else {}; dl=dev.get('devLaunchedInfo') if isinstance(dev,dict) else {}
    if isinstance(dh,dict):
        dp=_f(dh.get('devHoldingPercent'))
        if dp is None and dh.get('devHoldingPercent')=='': dp=0.0
        if dp is not None:out.setdefault('holders',{})['devPct']=dp
        if dh.get('devAddress'):out['creator']=dh['devAddress']
        out['developer']={k:v for k,v in {'address':dh.get('devAddress'),'fundingSource':dh.get('fundingSource'),'fundingSourceLabel':dh.get('fundingSourceLabel'),'nativeBalance':_f(dh.get('devBalance')),'totalLaunched':_i(dl.get('totalToken')) if isinstance(dl,dict) else None,'migratedCount':_i(dl.get('migratedCount')) if isinstance(dl,dict) else None}.items() if v not in (None,'')}
    # Exact recent unique traders and buy/sell activity from documented trade history.
    out['trades']=_trade_window(chain,address,int(os.environ.get('V2_TRADE_WINDOW_SECONDS','3600')))
    return out
