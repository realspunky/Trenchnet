"""Pump.fun V2 verified bonding adapter using the bonding-curve PDA account.

The curve account stores virtual/real reserves and a completion flag. Progress is
computed from current real-token reserves relative to the initial real-token reserve
from the Pump global account when available. An explicit override is supported for
RPC providers that expose a decoded Pump account endpoint.
"""
import base64, hashlib, json, os, struct, urllib.request
from v2_intelligence import normalize_progress

PROGRAM='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
RPC=os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')
ALPH='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def b58decode(s):
 n=0
 for ch in s:n=n*58+ALPH.index(ch)
 raw=n.to_bytes((n.bit_length()+7)//8,'big') if n else b''
 return b'\0'*(len(s)-len(s.lstrip('1')))+raw

def b58encode(b):
 n=int.from_bytes(b,'big');s=''
 while n:n,r=divmod(n,58);s=ALPH[r]+s
 z=len(b)-len(b.lstrip(b'\0'));return '1'*z+(s or ('' if z else '1'))

def _rpc(method,params):
 body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
 req=urllib.request.Request(RPC,data=body,headers={'Content-Type':'application/json','User-Agent':'TrenchNet-V2/2.1'})
 with urllib.request.urlopen(req,timeout=20) as r:x=json.loads(r.read(2_000_000))
 if x.get('error'):raise ValueError('Pump RPC '+str(x['error'])[:120])
 return x.get('result')

def _pda(seed,mint):
 # Prefer solders when available through web3 dependencies; fallback provider URL otherwise.
 try:
  from solders.pubkey import Pubkey
  p,_=Pubkey.find_program_address([seed,b58decode(mint)],Pubkey.from_string(PROGRAM))
  return str(p)
 except Exception:
  return None

def _decoded_override(mint):
 tpl=os.environ.get('PUMPFUN_V2_CURVE_URL','').strip()
 if not tpl:return None
 url=tpl.replace('{address}',mint).replace('{mint}',mint)
 req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-V2/2.1'})
 with urllib.request.urlopen(req,timeout=15) as r:x=json.loads(r.read(1_000_000))
 if not isinstance(x,dict):raise ValueError('Pump curve provider invalid')
 p=next((normalize_progress(x.get(k)) for k in ('bondingProgress','progress','progressPercent') if x.get(k) is not None),None)
 if p is None:raise ValueError('Pump curve provider missing progress')
 return p,x

def fetch(mint):
 over=_decoded_override(mint)
 if over:return over
 pda=_pda(b'bonding-curve',mint)
 if not pda:return None
 acc=_rpc('getAccountInfo',[pda,{'encoding':'base64','commitment':'confirmed'}])
 val=(acc or {}).get('value')
 if not val:return None
 raw=base64.b64decode(val['data'][0])
 # Anchor discriminator + 5 u64 reserve/supply fields + bool complete.
 if len(raw)<49:raise ValueError('Pump curve account too short')
 vals=struct.unpack_from('<QQQQQ',raw,8)
 virtual_token,virtual_sol,real_token,real_sol,total_supply=vals
 complete=bool(raw[48])
 initial=int(os.environ.get('PUMPFUN_INITIAL_REAL_TOKEN_RESERVES','793100000000000'))
 if initial<=0:raise ValueError('Pump initial reserve invalid')
 progress=100.0 if complete else max(0.0,min(100.0,(initial-real_token)*100.0/initial))
 return progress,{'bondingProgress':progress,'pump_curve':{'realTokenReserves':real_token,'realSolReserves':real_sol,'complete':complete}}
