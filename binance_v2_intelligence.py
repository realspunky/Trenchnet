"""Binance Web3 read-only enrichment for TrenchNet V2.

Official Binance Wallet public token-info/audit endpoints are used only after the
launchpad-native bonding gate reaches >=90%. Binance never determines bonding.
Supported here: BSC (Flap) and Solana (STOnK/EmberCurve/Pump.fun).
PONS/Robinhood Chain remains native because Binance token-info does not list it.
"""
import json, os, urllib.parse, urllib.request, uuid

BASE='https://web3.binance.com'
UA='binance-web3/1.4 (Skill)'
CHAIN={'flap':'56','stonk':'CT_501','embercurve':'CT_501','pumpfun':'CT_501'}
META='/bapi/defi/v1/public/wallet-direct/buw/wallet/dex/market/token/meta/info/ai'
DYNAMIC='/bapi/defi/v4/public/wallet-direct/buw/wallet/market/token/dynamic/info/ai'
AUDIT='/bapi/defi/v1/public/wallet-direct/security/token/audit'


def _get(path, params):
    url=BASE+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Accept':'application/json','Accept-Encoding':'identity','User-Agent':UA,'source':'agent'})
    with urllib.request.urlopen(req,timeout=float(os.environ.get('BINANCE_V2_TIMEOUT','12'))) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('Binance response too large')
    x=json.loads(raw)
    if not isinstance(x,dict) or str(x.get('code','000000')) not in {'0','000000'}: raise ValueError('Binance API error')
    d=x.get('data')
    return d if isinstance(d,dict) else {}


def _post(path, body):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Accept-Encoding':'identity','User-Agent':UA,'source':'agent'},method='POST')
    with urllib.request.urlopen(req,timeout=float(os.environ.get('BINANCE_V2_TIMEOUT','12'))) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('Binance response too large')
    x=json.loads(raw)
    if not isinstance(x,dict) or str(x.get('code','000000')) not in {'0','000000'}: raise ValueError('Binance API error')
    d=x.get('data')
    return d if isinstance(d,dict) else {}


def _first(d,*keys):
    for k in keys:
        if isinstance(d,dict) and d.get(k) not in (None,''): return d[k]
    return None


def _num(v, integer=False):
    if v is None:return None
    try:return int(float(v)) if integer else float(v)
    except (TypeError,ValueError):return None


def _url(v):
    if isinstance(v,str) and v.startswith(('https://','http://')):return v
    return ''


def _socials(meta):
    out={}
    # Binance has changed field naming across versions; accept only explicit URLs.
    for key,val in meta.items() if isinstance(meta,dict) else []:
        lk=str(key).lower()
        if not isinstance(val,str):continue
        u=_url(val)
        if not u:continue
        if ('twitter' in lk or lk in {'x','xurl','x_url'}) and ('x.com/' in u or 'twitter.com/' in u):out['twitter']=u
        elif any(x in lk for x in ('website','officialwebsite','homepage')):out['website']=u
        elif 'telegram' in lk or 'tme' in lk:out['telegram']=u
    # Some responses place social links in an array/object.
    social=meta.get('social') or meta.get('socials') or meta.get('socialLinks') if isinstance(meta,dict) else None
    if isinstance(social,dict):
        for k,v in social.items():
            u=_url(v)
            lk=str(k).lower()
            if u and ('twitter' in lk or lk=='x'):out['twitter']=u
            elif u and 'telegram' in lk:out['telegram']=u
            elif u and 'website' in lk:out['website']=u
    elif isinstance(social,list):
        for item in social:
            if not isinstance(item,dict):continue
            u=_url(_first(item,'url','link','value'))
            typ=str(_first(item,'type','name','platform') or '').lower()
            if u and ('twitter' in typ or typ=='x'):out['twitter']=u
            elif u and 'telegram' in typ:out['telegram']=u
            elif u and 'website' in typ:out['website']=u
    return out


def normalize(meta,dyn,audit=None):
    """Map only fields Binance actually returned; never manufacture missing facts."""
    meta=meta if isinstance(meta,dict) else {}; dyn=dyn if isinstance(dyn,dict) else {}; audit=audit if isinstance(audit,dict) else {}
    out={'binance_web3':{'meta':meta,'dynamic':dyn}}
    desc=_first(meta,'description','desc','tokenDescription','introduction')
    if isinstance(desc,str) and desc.strip():out['description']=desc.strip()[:600]
    out.update(_socials(meta))
    creator=_first(meta,'creator','creatorAddress','deployer','ownerAddress')
    if creator:out['creator']=str(creator)
    holders=_num(_first(dyn,'holders','holderCount','holder_count','holdersCount'),True)
    top10=_num(_first(dyn,'top10HoldersPercentage','top10HolderPercentage','top10_holder_percentage','top10HoldersPercent'))
    dev=_num(_first(dyn,'devHoldingPercentage','dev_holding_percentage','creatorHoldingPercentage'))
    if any(v is not None for v in (holders,top10,dev)):
        out['holders']={k:v for k,v in {'count':holders,'top10Pct':top10,'devPct':dev}.items() if v is not None}
        if holders is not None:out['holderCount']=holders
        if top10 is not None:out['top10_holder_pct']=top10
        if dev is not None:out['dev_holding_pct']=dev
    # Binance dynamic data documents 24h volume and may return buy/sell splits/counts.
    volume=_num(_first(dyn,'volume1h','volume1H','volume24h','volume'))
    buyv=_num(_first(dyn,'volume1hBuy','volume1HBuy','volume24hBuy','buyVolume24h'))
    sellv=_num(_first(dyn,'volume1hSell','volume1HSell','volume24hSell','sellVolume24h'))
    buys=_num(_first(dyn,'buyTxCount1h','buyTxCount1H','buyTxCount','buy_tx_count'),True)
    sells=_num(_first(dyn,'sellTxCount1h','sellTxCount1H','sellTxCount','sell_tx_count'),True)
    ub=_num(_first(dyn,'uniqueBuyers1h','uniqueBuyers','unique_buyers'),True)
    us=_num(_first(dyn,'uniqueSellers1h','uniqueSellers','unique_sellers'),True)
    # Prefer 1h if explicitly returned, otherwise accurately label 24h.
    has1h=any(_first(dyn,k) is not None for k in ('volume1h','volume1H','volume1hBuy','volume1HBuy','buyTxCount1h','buyTxCount1H'))
    trades={k:v for k,v in {'volume':volume,'buyVolume':buyv,'sellVolume':sellv,'buys':buys,'sells':sells,'uniqueBuyers':ub,'uniqueSellers':us}.items() if v is not None}
    if trades:
        trades['windowSeconds']=3600 if has1h else 86400
        out['trades']=trades
    liq=_num(_first(dyn,'liquidity','liquidityUsd','liquidityUSD'))
    mcap=_num(_first(dyn,'marketCap','market_cap'))
    price=_num(_first(dyn,'price','priceUsd','priceUSD'))
    if any(v is not None for v in (liq,mcap,price)):out['binance_market']={'liquidity':liq,'marketCap':mcap,'price':price}
    if audit.get('hasResult') is True and audit.get('isSupported') is True:
        extra=audit.get('extraInfo') if isinstance(audit.get('extraInfo'),dict) else {}
        out['binance_audit']={'riskLevel':audit.get('riskLevel'),'riskLevelEnum':audit.get('riskLevelEnum'),'buyTax':extra.get('buyTax'),'sellTax':extra.get('sellTax'),'isVerified':extra.get('isVerified'),'riskItems':audit.get('riskItems') or []}
    return out


def fetch(launchpad,address):
    chain=CHAIN.get(launchpad)
    if not chain or os.environ.get('BINANCE_V2_ENABLED','true').lower()!='true':return {}
    params={'chainId':chain,'contractAddress':address}
    meta=_get(META,params)
    dyn=_get(DYNAMIC,params)
    audit={}
    if os.environ.get('BINANCE_V2_AUDIT','true').lower()=='true':
        try:audit=_post(AUDIT,{'binanceChainId':chain,'contractAddress':address,'requestId':str(uuid.uuid4())})
        except Exception:pass # audit is enrichment, not a substitute for mandatory intelligence
    return normalize(meta,dyn,audit)
