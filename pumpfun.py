"""Pump.fun launch intake via Solana JSON-RPC. Filtration intentionally happens later."""
import hashlib,json,os,struct,time,urllib.request,ipaddress,socket
from urllib.parse import urlparse
from scanner import clean,deliver
from launch_model import setup as unified_setup, record as record_launch

PROGRAM=os.environ.get('PUMPFUN_PROGRAM','6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P')
RPC=os.environ.get('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')
CREATE_V2=hashlib.sha256(b'global:create_v2').digest()[:8]
ALPH='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def setup(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS pumpfun_tokens(mint TEXT PRIMARY KEY,name TEXT,symbol TEXT,creator TEXT,uri TEXT,
   signature TEXT,slot INTEGER,first_seen INTEGER,snapshot TEXT);
 CREATE TABLE IF NOT EXISTS pumpfun_outbox(id INTEGER PRIMARY KEY,recipient INTEGER,event_key TEXT,body TEXT,
   state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,message_id INTEGER,
   expires INTEGER NOT NULL DEFAULT 0,UNIQUE(recipient,event_key));
 CREATE TABLE IF NOT EXISTS pumpfun_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,status TEXT);
 CREATE TABLE IF NOT EXISTS pumpfun_state(key TEXT PRIMARY KEY,value TEXT);
 ''')
 with c:c.execute("UPDATE pumpfun_outbox SET state='uncertain' WHERE state='sending'")
 unified_setup(c)

def rpc(method,params,url=RPC):
 data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
 req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','User-Agent':'TrenchNet-private-pilot/1.0'})
 with urllib.request.urlopen(req,timeout=25) as r:
  x=json.loads(r.read(5_000_001))
 if x.get('error'):raise RuntimeError('Solana RPC: '+str(x['error']))
 return x.get('result')

def b58decode(s):
 n=0
 for ch in s:n=n*58+ALPH.index(ch)
 raw=n.to_bytes((n.bit_length()+7)//8,'big') if n else b''
 return b'\0'*(len(s)-len(s.lstrip('1')))+raw

def _string(b,p):
 if p+4>len(b):raise ValueError('short Pump create data')
 n=struct.unpack_from('<I',b,p)[0];p+=4
 if n>1000 or p+n>len(b):raise ValueError('bad Pump string')
 return b[p:p+n].decode('utf-8','replace'),p+n

def parse_create_data(data):
 b=b58decode(data)
 if not b.startswith(CREATE_V2):return None
 p=8;name,p=_string(b,p);symbol,p=_string(b,p);uri,p=_string(b,p)
 if p+32>len(b):raise ValueError('short Pump creator')
 creator=base58encode(b[p:p+32])
 return {'name':clean(name),'symbol':clean(symbol,30),'uri':uri[:500],'creator':creator}

def base58encode(b):
 n=int.from_bytes(b,'big');s=''
 while n:n,r=divmod(n,58);s=ALPH[r]+s
 z=len(b)-len(b.lstrip(b'\0'))
 return '1'*z+(s or ('' if z else '1'))

def account_keys(tx):
 msg=tx['transaction']['message'];out=[]
 for x in msg.get('accountKeys',[]):out.append(x.get('pubkey') if isinstance(x,dict) else x)
 loaded=(tx.get('meta') or {}).get('loadedAddresses') or {}
 out += loaded.get('writable',[])+loaded.get('readonly',[])
 return out

def creations(tx):
 keys=account_keys(tx);out=[]
 for ix in tx['transaction']['message'].get('instructions',[]):
  pid=ix.get('programId')
  if not pid and ix.get('programIdIndex') is not None:pid=keys[ix['programIdIndex']]
  if pid!=PROGRAM or not ix.get('data'):continue
  try:meta=parse_create_data(ix['data'])
  except (ValueError,UnicodeError):continue
  if not meta:continue
  accts=ix.get('accounts',[])
  mint=(accts[0] if accts and isinstance(accts[0],str) else keys[accts[0]]) if accts else ''
  if 32<=len(str(mint))<=50:out.append(dict(meta,mint=str(mint)))
 return out

def fetch_metadata(uri):
 # Pump create_v2 stores a metadata URI; fetch only public HTTP(S) JSON and cap response size.
 uri=str(uri or '').strip()
 if uri.startswith('ipfs://'): uri='https://ipfs.io/ipfs/'+uri[7:].lstrip('/')
 u=urlparse(uri)
 if u.scheme not in {'http','https'} or not u.hostname:return {}
 try:
  for info in socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM):
   ip=ipaddress.ip_address(info[4][0])
   if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:return {}
 except Exception:return {}
 req=urllib.request.Request(uri,headers={'Accept':'application/json','User-Agent':'TrenchNet-private-pilot/1.0'})
 try:
  with urllib.request.urlopen(req,timeout=8) as r:
   raw=r.read(256001)
   if len(raw)>256000:return {}
   data=json.loads(raw)
   return data if isinstance(data,dict) else {}
 except Exception:return {}

def body(t):
 return (f'📣 PRIVATE PILOT — New launch\n🪙 {t["name"]} ({t["symbol"]})\n'
   f'🌐 Network: Solana | 🟢 Launchpad: Pump.fun\n📋 Contract: {t["mint"]}\n'
   f'👤 Creator: {t["creator"]}\n🔗 https://pump.fun/coin/{t["mint"]}\n'
   'Source: Pump.fun on-chain create_v2 instruction. Filtration not yet applied.')

class Scanner:
 def __init__(self,c,recipient,call=rpc,metadata_get=fetch_metadata):self.c=c;self.recipient=recipient;self.call=call;self.metadata_get=metadata_get
 def health(self,msg):
  with self.c:self.c.execute('INSERT OR REPLACE INTO pumpfun_health VALUES(1,?,?)',(int(time.time()),msg))
 def scan(self):
  now=int(time.time());limit=int(os.environ.get('PUMPFUN_SIGNATURE_LIMIT','100'))
  sigs=self.call('getSignaturesForAddress',[PROGRAM,{'limit':limit,'commitment':'confirmed'}]) or []
  initialized=self.c.execute("SELECT value FROM pumpfun_state WHERE key='initialized'").fetchone()
  known=self.c.execute("SELECT value FROM pumpfun_state WHERE key='last_signature'").fetchone()
  last=known[0] if known else None;fresh=[]
  for s in sigs:
   if s['signature']==last:break
   if s.get('err') is None:fresh.append(s)
  queued=0
  # First run snapshots the current head; later runs process oldest -> newest.
  if initialized:
   for s in reversed(fresh):
    tx=self.call('getTransaction',[s['signature'],{'encoding':'jsonParsed','commitment':'confirmed','maxSupportedTransactionVersion':0}])
    if not tx:continue
    for t in creations(tx):
     meta=self.metadata_get(t.get('uri')) if t.get('uri') else {}
     if meta: t=dict(t,metadata=meta,**{k:meta.get(k) for k in ('twitter','website') if meta.get(k)})
     old=self.c.execute('SELECT 1 FROM pumpfun_tokens WHERE mint=?',(t['mint'],)).fetchone()
     record_launch(self.c,chain='solana',launchpad='pumpfun',address=t['mint'],creator=t['creator'],
      name=t['name'],symbol=t['symbol'],source_tx=s['signature'],source_height=s.get('slot',0),launched_at=now,
      source_table='pumpfun_tokens',metadata=t,now=now)
     with self.c:
      self.c.execute('INSERT OR IGNORE INTO pumpfun_tokens VALUES(?,?,?,?,?,?,?,?,?)',(t['mint'],t['name'],t['symbol'],t['creator'],t['uri'],s['signature'],s.get('slot',0),now,json.dumps(t)))
      if old is None:
       self.c.execute('INSERT OR IGNORE INTO pumpfun_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',(self.recipient,'solana:'+t['mint']+':pumpfun:launch',body(t),now+600));queued+=1
  if sigs:
   with self.c:
    self.c.execute("INSERT OR REPLACE INTO pumpfun_state VALUES('last_signature',?)",(sigs[0]['signature'],))
    self.c.execute("INSERT OR REPLACE INTO pumpfun_state VALUES('initialized','1')")
  self.health(f'Pump.fun: {len(fresh)} new program txs scanned; {queued} launches queued; filtration not yet applied')

def run():
 if os.environ.get('PUMPFUN_ENABLED')!='true':return
 from bot import database,api
 recipient=int(os.environ['ADMIN_CHAT_ID']);token=os.environ['TELEGRAM_BOT_TOKEN']
 c=database();setup(c);s=Scanner(c,recipient)
 print('Pump.fun private scanner started.',flush=True)
 while True:
  try:
   s.scan()
   if os.environ.get('GLOBAL_FILTER_ENABLED','true')!='true':
    for _ in range(10):deliver(c,token,api,table='pumpfun_outbox');time.sleep(.5)
  except Exception as e:
   s.health('Pump.fun retrying: '+type(e).__name__);print('Pump.fun retrying: '+type(e).__name__,flush=True)
  time.sleep(int(os.environ.get('PUMPFUN_POLL_SECONDS','8')))
if __name__=='__main__':run()
