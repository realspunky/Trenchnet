"""Credential-free Flap Stage-2 event intelligence from BNB RPC.

Uses documented Portal TokenBought/TokenSold events for recent trade counts, unique
traders, early-wallet/sniper heuristics and quote volume. ERC-20 Transfer logs are
used to reconstruct current holder concentration when the launch block is available.
"""
import json, os, time, urllib.request
PORTAL='0xe2cE6ab80874Fa9Fa2aAE65D277Dd6B8e65C9De0'
ZERO='0x'+'0'*40

def _rpc(method,params):
    url=os.environ.get('BNB_RPC_URL','').strip()
    if not url:raise ValueError('BNB_RPC_URL missing')
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','User-Agent':'TrenchNet-V2/2.6'})
    with urllib.request.urlopen(req,timeout=20) as r:raw=r.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('BNB RPC response too large')
    x=json.loads(raw)
    if x.get('error'):raise ValueError('BNB RPC error: '+str(x['error'])[:140])
    return x.get('result')

def _keccak(text):
    try:
        from eth_utils import keccak
        return '0x'+keccak(text=text).hex()
    except Exception:
        from web3 import Web3
        return '0x'+Web3.keccak(text=text).hex().removeprefix('0x')

def _logs(address,topics,start,end):
    chunk=max(1,int(os.environ.get('V2_BNB_LOG_CHUNK','10'))); out=[]
    max_blocks=max(100,int(os.environ.get('V2_BNB_MAX_STAGE2_BLOCKS','12000')))
    if end-start+1>max_blocks:raise ValueError('BNB Stage2 history exceeds configured verified window')
    a=start
    while a<=end:
        b=min(end,a+chunk-1)
        got=_rpc('eth_getLogs',[{'address':address,'topics':topics,'fromBlock':hex(a),'toBlock':hex(b)}]) or []
        out.extend(got);a=b+1
    return out

def _addr(topic):return '0x'+str(topic)[-40:].lower()
def _uint(data):return int(data,16) if data and data!='0x' else 0

def holders(token,start,end,creator=''):
    topic=_keccak('Transfer(address,address,uint256)')
    logs=_logs(token,[topic],start,end); bal={}
    for l in logs:
        ts=l.get('topics') or []
        if len(ts)<3:continue
        f,t=_addr(ts[1]),_addr(ts[2]);v=_uint(l.get('data'))
        if f!=ZERO:bal[f]=bal.get(f,0)-v
        if t!=ZERO:bal[t]=bal.get(t,0)+v
    bal={k:v for k,v in bal.items() if v>0}; total=sum(bal.values())
    if total<=0:raise ValueError('Flap holder reconstruction empty')
    vals=sorted(bal.values(),reverse=True)
    out={'count':len(bal),'top10Pct':sum(vals[:10])*100.0/total}
    if creator:out['devPct']=bal.get(str(creator).lower(),0)*100.0/total
    return out,bal,total

def _decode_trade(log,side):
    # All seven documented event fields are non-indexed.
    from eth_abi import decode
    vals=decode(['uint256','address','address','uint256','uint256','uint256','uint256'],bytes.fromhex(log['data'][2:]))
    return {'ts':int(vals[0]),'token':str(vals[1]).lower(),'wallet':str(vals[2]).lower(),'amount':int(vals[3]),'quote':int(vals[4]),'side':side,'block':int(log['blockNumber'],16)}

def trades(token,start,end,launched_at=None):
    now=int(time.time()); cutoff=now-int(os.environ.get('V2_TRADE_WINDOW_SECONDS','3600'))
    buy=_keccak('TokenBought(uint256,address,address,uint256,uint256,uint256,uint256)')
    sell=_keccak('TokenSold(uint256,address,address,uint256,uint256,uint256,uint256)')
    rows=[]
    for topic,side in ((buy,'buy'),(sell,'sell')):
        for l in _logs(PORTAL,[topic],start,end):
            try:
                r=_decode_trade(l,side)
                if r['token']==token.lower():rows.append(r)
            except Exception:continue
    recent=[r for r in rows if r['ts']>=cutoff]
    buys=[r for r in recent if r['side']=='buy'];sells=[r for r in recent if r['side']=='sell']
    out={'trades':{'buys':len(buys),'sells':len(sells),'uniqueBuyers':len({r['wallet'] for r in buys}),'uniqueSellers':len({r['wallet'] for r in sells}),'windowSeconds':int(os.environ.get('V2_TRADE_WINDOW_SECONDS','3600'))},'native_flap_trades':True}
    # quote values use 18 decimals for native BNB in the documented Portal API.
    out['native_quote_volume']=(sum(r['quote'] for r in recent)/1e18)
    if launched_at:
        w=max(15,int(os.environ.get('V2_NATIVE_SNIPER_WINDOW_SECONDS','120')))
        early={r['wallet'] for r in rows if r['side']=='buy' and int(launched_at)<=r['ts']<=int(launched_at)+w}
        out['_early_wallets']=sorted(early)
    return out

def enrich(token,metadata):
    out=dict(metadata or {}); start=out.get('height') or out.get('source_height') or out.get('launch_block')
    if start is None:raise ValueError('Flap launch block unavailable')
    start=int(start); tip=int(_rpc('eth_blockNumber',[]),16); creator=out.get('creator') or ''
    hs,balances,total=holders(token,start,tip,creator);out['holders']=hs
    ti=trades(token,start,tip,out.get('created') or out.get('launched_at')); early=set(ti.pop('_early_wallets',[]));out.update(ti)
    pcts=[balances.get(w,0)*100.0/total for w in early]
    out['snipers']={'count':len(early),'concentrationPct':sum(balances.get(w,0) for w in early)*100.0/total,'largestPct':max(pcts) if pcts else 0.0,'stillHolding':sum(1 for w in early if balances.get(w,0)>0),'sold':sum(1 for w in early if balances.get(w,0)==0),'method':'flap_documented_early_buy_event'}
    return out
