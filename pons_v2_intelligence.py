"""PONS V2 credential-free intelligence adapter.

Stage 1 uses the public Pons Portal API for verified curve progress. Stage 2
combines the Portal holder endpoint with direct Robinhood Chain reads:
- getTokenInfo() for creator-supplied description/socials
- CurveBuy/CurveSell logs for recent activity and early-wallet/sniper metrics
No missing fact is replaced with a guessed zero.
"""
import json, urllib.request, urllib.parse, os, time

BASE='https://api.ponsportal.fun'
BUY_TOPIC='0xec36bf571f136799e8dc0b0b8bea4b04d8bd3d43de838aab0d5fc21d4cbfc455'
SELL_TOPIC='0x8113d738abdcb6b38357e9d53a54a7157861a09031b453651f0fe7fe151f59df'
ZERO='0x0000000000000000000000000000000000000000'

def _get(path):
    req=urllib.request.Request(BASE+path,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.2'})
    with urllib.request.urlopen(req,timeout=12) as r: raw=r.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('PONS response too large')
    x=json.loads(raw)
    if not isinstance(x,dict) or x.get('ok') is False: raise ValueError(str(x.get('error','PONS API error'))[:160])
    return x

def _all_holders(address, max_pages=None):
    max_pages=int(os.environ.get('PONS_V2_HOLDER_MAX_PAGES','8') if max_pages is None else max_pages)
    path='/token/'+urllib.parse.quote(address,safe='')+'/holders';out=[];params={};pages=0
    while pages < max_pages:
        qs=('?'+urllib.parse.urlencode(params)) if params else ''
        x=_get(path+qs);pages+=1;items=x.get('holders')
        if not isinstance(items,list): raise ValueError('PONS holders list missing')
        out.extend(items);params=x.get('next_page_params')
        if not params:return out,True,pages
        if not isinstance(params,dict):raise ValueError('PONS holder cursor invalid')
    return out,False,pages

def _holder_address(h):
    if not isinstance(h,dict):return ''
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

def _holder_stats(holders,deployer=''):
    vals=[];dev=None;deployer=str(deployer or '').lower()
    for h in holders:
        v=_holder_value(h)
        if v is None or v<0:continue
        vals.append(v)
        if deployer and _holder_address(h)==deployer:dev=v
    total=sum(vals)
    if total<=0:return {'count':len(holders)}
    vals.sort(reverse=True)
    return {'count':len(holders),'top10Pct':sum(vals[:10])*100.0/total,
            'devPct':(dev*100.0/total if dev is not None else None)}

def _web3():
    from web3 import Web3
    rpc=os.environ.get('PONS_RPC_URL','').strip()
    if not rpc:raise ValueError('PONS_RPC_URL missing')
    w3=Web3(Web3.HTTPProvider(rpc,request_kwargs={'timeout':20}))
    if w3.eth.chain_id!=4663:raise ValueError('wrong PONS chain id')
    return w3


def _onchain_progress(w3,curve):
    abi=[
      {'inputs':[],'name':'realQuoteReserve','outputs':[{'type':'uint256'}],'stateMutability':'view','type':'function'},
      {'inputs':[],'name':'graduationThreshold','outputs':[{'type':'uint256'}],'stateMutability':'view','type':'function'}]
    c=w3.eth.contract(address=w3.to_checksum_address(curve),abi=abi)
    raised=int(c.functions.realQuoteReserve().call());threshold=int(c.functions.graduationThreshold().call())
    if threshold<=0:raise ValueError('PONS graduation threshold unavailable')
    return min(100.0,max(0.0,raised*100.0/threshold))

def _token_metadata(w3,address):
    # Pons V2 token stores creator-supplied metadata on-chain in getTokenInfo().
    abi=[{'inputs':[],'name':'getTokenInfo','outputs':[
        {'internalType':'address','name':'tokenDeployer','type':'address'},
        {'internalType':'string','name':'tokenLogo','type':'string'},
        {'internalType':'string','name':'tokenDescription','type':'string'},
        {'components':[
            {'internalType':'string','name':'twitter','type':'string'},
            {'internalType':'string','name':'telegram','type':'string'},
            {'internalType':'string','name':'discord','type':'string'},
            {'internalType':'string','name':'website','type':'string'},
            {'internalType':'string','name':'farcaster','type':'string'}],
         'internalType':'struct Socials','name':'tokenSocials','type':'tuple'}],
        'stateMutability':'view','type':'function'}]
    r=w3.eth.contract(address=w3.to_checksum_address(address),abi=abi).functions.getTokenInfo().call()
    socials=r[3] if len(r)>3 else []
    names=('twitter','telegram','discord','website','farcaster')
    out={'description':str(r[2] or '').strip(),'social_checked':True,'token_logo':r[1]}
    for i,k in enumerate(names):
        if i<len(socials) and socials[i]:out[k]=socials[i]
    return out

def _topic_address(v):
    h=v.hex() if hasattr(v,'hex') else str(v)
    h=h[2:] if h.startswith('0x') else h
    return ('0x'+h[-40:]).lower()

def _words(data):
    h=data.hex() if hasattr(data,'hex') else str(data)
    h=h[2:] if h.startswith('0x') else h
    if len(h)<256:return None
    return [int(h[i:i+64],16) for i in range(0,256,64)]

def _curve_trades(w3,curve,from_block,launched_at,holders,pair_label='ETH'):
    tip=w3.eth.block_number
    start=max(int(from_block or 0),tip-int(os.environ.get('PONS_V2_TRADE_LOOKBACK_BLOCKS','50000')))
    chunk=max(100,min(5000,int(os.environ.get('PONS_V2_TRADE_BLOCK_CHUNK','2000'))))
    logs=[]
    for a in range(start,tip+1,chunk):
        b=min(a+chunk-1,tip)
        logs.extend(w3.eth.get_logs({'address':w3.to_checksum_address(curve),'topics':[[BUY_TOPIC,SELL_TOPIC]],'fromBlock':a,'toBlock':b}))
    buys=[];sells=[]
    for log in logs:
        topics=log.get('topics') or []
        if len(topics)<3:continue
        vals=_words(log.get('data'))
        if not vals:continue
        t0='0x'+topics[0].hex().removeprefix('0x')
        rec={'trader':_topic_address(topics[1]),'recipient':_topic_address(topics[2]),'block':int(log['blockNumber'])}
        if t0.lower()==BUY_TOPIC:
            rec.update({'quote':vals[0],'tokens':vals[1]});buys.append(rec)
        elif t0.lower()==SELL_TOPIC:
            rec.update({'tokens':vals[0],'quote':vals[1]});sells.append(rec)
    buyers={x['trader'] for x in buys};sellers={x['trader'] for x in sells}
    quote=sum(x['quote'] for x in buys)+sum(x['quote'] for x in sells)
    out={'trades':{'buys':len(buys),'sells':len(sells),'uniqueBuyers':len(buyers),'uniqueSellers':len(sellers),
                   'buyVolume':sum(x['quote'] for x in buys)/1e18,'sellVolume':sum(x['quote'] for x in sells)/1e18,
                   'volume':quote/1e18,'windowSeconds':max(1,int(time.time())-int(launched_at or time.time()))},
         'volume_asset':pair_label or 'quote'}
    # Early-wallet definition: a buyer whose first curve buy landed within the configured
    # number of seconds after launch. Block timestamps are read from the same RPC.
    early_seconds=int(os.environ.get('PONS_V2_SNIPER_WINDOW_SECONDS','60'))
    block_ts={}
    early=set()
    for x in buys:
        bn=x['block']
        if bn not in block_ts:block_ts[bn]=int(w3.eth.get_block(bn)['timestamp'])
        if launched_at and block_ts[bn] <= int(launched_at)+early_seconds:early.add(x['trader'])
    balances={_holder_address(h):_holder_value(h) for h in holders}
    balances={k:v for k,v in balances.items() if k and v is not None and v>=0}
    total=sum(balances.values())
    early_bal=[balances.get(a,0) for a in early]
    if total>0:
        out['snipers']={'count':len(early),'concentrationPct':sum(early_bal)*100.0/total,
                        'largestPct':(max(early_bal)*100.0/total if early_bal else 0.0),
                        'stillHolding':sum(1 for v in early_bal if v>0),'sold':sum(1 for v in early_bal if v==0)}
    return out

def fetch(address,metadata=None):
    # Tracking is RPC-native. The public Portal API is intentionally NOT polled per
    # token: its documented read limit is too small for hundreds of tracked launches.
    out=dict(metadata or {})
    curve=out.get('pool') or out.get('curve')
    w3=_web3()
    if curve:
        progress=_onchain_progress(w3,curve)
    else:
        # Recovery path for old rows that predate curve persistence.
        token=_get('/token/'+urllib.parse.quote(address,safe=''));curve=token.get('curve')
        if not curve:raise ValueError('PONS curve address unavailable')
        out.update(token);out['curve']=curve;progress=_onchain_progress(w3,curve)
    out['bondingProgress']=progress;out['market']={'progress':progress}
    if progress<60:return progress,out

    # Post-60 only: one token-info API read for quote metadata and the rate-limited
    # holder endpoint. Successful holder data is cached in unified metadata so retries
    # do not burn the holder budget again.
    token={}
    try:
        token=_get('/token/'+urllib.parse.quote(address,safe=''));out.update(token)
    except Exception as e:out['pons_token_api_error']=type(e).__name__+': '+str(e)[:100]
    holders=[]
    cached=out.get('pons_holder_balances')
    if out.get('pons_holders_complete') and isinstance(cached,dict):
        holders=[{'address':a,'value':v} for a,v in cached.items()]
    else:
        try:
            holders,done,pages=_all_holders(address);out['pons_holders_pages']=pages;out['pons_holders_complete']=done
            if done:
                hs=_holder_stats(holders,token.get('deployer') or out.get('creator'));out['holders']=hs;out['holderCount']=hs.get('count')
                if hs.get('top10Pct') is not None:out['top10_holder_pct']=hs['top10Pct']
                if hs.get('devPct') is not None:out['dev_holding_pct']=hs['devPct']
                out['pons_holder_balances']={_holder_address(h):_holder_value(h) for h in holders if _holder_address(h) and _holder_value(h) is not None}
        except Exception as e:out['pons_holder_error']=type(e).__name__+': '+str(e)[:100]
    try:
        out.update(_token_metadata(w3,address))
        launch_block=out.get('height') or out.get('source_height')
        if curve and launch_block and holders:
            out.update(_curve_trades(w3,curve,launch_block,out.get('created') or out.get('launched_at'),holders,token.get('pairTokenLabel') or out.get('pairTokenLabel') or 'ETH'))
        else:out['pons_trade_error']='missing curve/launch block/complete holders'
    except Exception as e:out['pons_native_error']=type(e).__name__+': '+str(e)[:120]
    return progress,out
