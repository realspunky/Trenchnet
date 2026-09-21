import hashlib,struct
from pumpfun import ALPH,CREATE_V2,parse_create_data,creations

def b58(b):
 n=int.from_bytes(b,'big');s=''
 while n:n,r=divmod(n,58);s=ALPH[r]+s
 return '1'*(len(b)-len(b.lstrip(b'\0')))+(s or '')
def st(x):
 b=x.encode();return struct.pack('<I',len(b))+b
def test_create_v2_decode():
 creator=bytes(range(32));raw=CREATE_V2+st('Alpha')+st('ALP')+st('https://x')+creator+b'\0'
 x=parse_create_data(b58(raw));assert x['name']=='Alpha' and x['symbol']=='ALP' and len(x['creator'])>=32
def test_creation_mint_from_accounts():
 raw=CREATE_V2+st('Coin')+st('C')+st('u')+bytes(range(32))+b'\0'
 tx={'transaction':{'message':{'accountKeys':[], 'instructions':[{'programId':'6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P','accounts':['11111111111111111111111111111111'],'data':b58(raw)}]}},'meta':{}}
 x=creations(tx);assert x[0]['mint']=='11111111111111111111111111111111'
