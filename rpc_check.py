"""Read-only RPC preflight. URLs may contain secrets and are never printed."""
import json
import os
import time
import urllib.request
from flap import PORTAL,HELPER
DEFAULT_RPC='https://bsc-dataseed.bnbchain.org'

def call(url,method,params):
    request=urllib.request.Request(url,data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        result=json.load(response)
    if result.get('error') or 'result' not in result:
        raise ValueError('RPC call rejected')
    return result['result']

def check(url, rpc=call):
    if int(rpc(url,'eth_chainId',[]),16)!=56:
        raise ValueError('Wrong network; expected BNB mainnet')
    block=rpc(url,'eth_getBlockByNumber',['finalized',False])
    if not isinstance(block,dict) or not block.get('number'):
        raise ValueError('Finalized block unavailable')
    age=time.time()-int(block.get('timestamp','0x0'),16)
    if not -60 <= age <= 300:
        raise ValueError('Finalized block is stale or clock is incorrect')
    height=block['number']
    for address in [PORTAL,HELPER]:
        if rpc(url,'eth_getCode',[address,height]) in ('0x','0x0',None):
            raise ValueError('Required contract missing')
    logs=False
    try:
        result=rpc(url,'eth_getLogs',[{'address':PORTAL,'fromBlock':height,'toBlock':height}])
        logs=isinstance(result,list)
    except Exception:
        pass
    return {'chain_id':56,'finalized_block':int(height,16),'contracts_present':True,
            'log_query_supported':logs,'note':'Contract presence is not ABI/token validation.'}

if __name__=='__main__':
    try:
        print(json.dumps(check(os.environ.get('BNB_RPC_URL',DEFAULT_RPC)),indent=2))
    except Exception:
        raise SystemExit('RPC preflight failed; verify connectivity, BNB mainnet and finalized-block support. Endpoint hidden.')
