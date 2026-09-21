"""EmberCurve launch intake. Public read-only API; filtration intentionally happens later."""
import json, os, time, urllib.request
from scanner import clean, deliver
from launch_model import setup as unified_setup, record as record_launch

API=os.environ.get('EMBER_MARKETS_URL','https://embercurve.fun/api/solana/markets')

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS ember_tokens(mint TEXT PRIMARY KEY,name TEXT,symbol TEXT,creator TEXT,pair_symbol TEXT,
      progress REAL,graduated INTEGER,first_seen INTEGER,last_seen INTEGER,snapshot TEXT);
    CREATE TABLE IF NOT EXISTS ember_outbox(id INTEGER PRIMARY KEY,recipient INTEGER,event_key TEXT,body TEXT,
      state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,message_id INTEGER,
      expires INTEGER NOT NULL DEFAULT 0,UNIQUE(recipient,event_key));
    CREATE TABLE IF NOT EXISTS ember_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,status TEXT);
    CREATE TABLE IF NOT EXISTS ember_state(key TEXT PRIMARY KEY,value TEXT);
    ''')
    with c:c.execute("UPDATE ember_outbox SET state='uncertain' WHERE state='sending'")
    unified_setup(c)

def fetch(url=API):
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'TrenchNet-private-pilot/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read(5_000_001)
        if len(raw)>5_000_000:raise ValueError('Ember response too large')
        return json.loads(raw)

def rows(payload):
    if isinstance(payload,list):return payload
    if not isinstance(payload,dict):raise ValueError('Invalid Ember response')
    for k in ('markets','data','items','results'):
        v=payload.get(k)
        if isinstance(v,list):return v
        if isinstance(v,dict):
            for kk in ('markets','items','results'):
                if isinstance(v.get(kk),list):return v[kk]
    raise ValueError('Ember markets list not found')

def pick(d,*keys,default=None):
    for k in keys:
        if isinstance(d,dict) and d.get(k) is not None:return d[k]
    return default

def normalize(x):
    if not isinstance(x,dict):raise ValueError('Invalid Ember market')
    token=x.get('token') if isinstance(x.get('token'),dict) else {}
    mint=str(pick(x,'mint','tokenMint','baseMint','address',default=pick(token,'mint','address',default='')))
    if not 32<=len(mint)<=50:raise ValueError('Invalid Ember mint')
    name=clean(pick(x,'name',default=pick(token,'name',default='Unknown')))
    symbol=clean(pick(x,'symbol','ticker',default=pick(token,'symbol','ticker',default='')),30)
    creator=str(pick(x,'creator','creatorWallet','deployer',default=''))
    pair=x.get('pair') if isinstance(x.get('pair'),dict) else {}
    pair_symbol=clean(pick(x,'pairSymbol','quoteSymbol',default=pick(pair,'symbol',default='')),30)
    progress=pick(x,'bondingProgress','bonding_progress','progress','curveProgress')
    try: progress=float(progress) if progress is not None else None
    except (TypeError,ValueError): progress=None
    if progress is not None and 0<=progress<=1:progress*=100
    graduated=bool(pick(x,'graduated','isGraduated',default=False) or str(pick(x,'status',default='')).lower() in {'graduated','migrated'})
    return dict(mint=mint,name=name,symbol=symbol,creator=creator,pair_symbol=pair_symbol,progress=progress,graduated=graduated)

def body(t):
    prog='unknown' if t['progress'] is None else f'{t["progress"]:.1f}%'
    pair=t['pair_symbol'] or 'unknown'
    return (f'📣 PRIVATE PILOT — New launch\n🪙 {t["name"]} ({t["symbol"]})\n'
      f'🌐 Network: Solana | 🔥 Launchpad: EmberCurve\n📋 Contract: {t["mint"]}\n'
      f'💱 Pair: {pair}\n📈 Bonding progress: {prog}\n'
      f'🔗 https://embercurve.fun/t/{t["mint"]}\n'
      'Source: Ember public market data. Contract address is the unique token identity.')

class Scanner:
    def __init__(self,c,recipient,get=fetch):self.c=c;self.recipient=recipient;self.get=get
    def health(self,msg):
        with self.c:self.c.execute('INSERT OR REPLACE INTO ember_health VALUES(1,?,?)',(int(time.time()),msg))
    def scan(self):
        now=int(time.time()); payload=self.get(); markets=[normalize(x) for x in rows(payload)]
        initialized=self.c.execute("SELECT value FROM ember_state WHERE key='initialized'").fetchone()
        new=0
        with self.c:
            for t in markets:
                old=self.c.execute('SELECT graduated FROM ember_tokens WHERE mint=?',(t['mint'],)).fetchone()
                record_launch(self.c,chain='solana',launchpad='embercurve',address=t['mint'],creator=t['creator'],
                  name=t['name'],symbol=t['symbol'],pair_symbol=t['pair_symbol'],launched_at=now,bonding_progress=t['progress'],
                  migrated=t['graduated'],source_table='ember_tokens',metadata=t,now=now)
                self.c.execute('''INSERT INTO ember_tokens(mint,name,symbol,creator,pair_symbol,progress,graduated,first_seen,last_seen,snapshot)
                  VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mint) DO UPDATE SET name=excluded.name,symbol=excluded.symbol,
                  creator=excluded.creator,pair_symbol=excluded.pair_symbol,progress=excluded.progress,graduated=excluded.graduated,
                  last_seen=excluded.last_seen,snapshot=excluded.snapshot''',(t['mint'],t['name'],t['symbol'],t['creator'],t['pair_symbol'],t['progress'],int(t['graduated']),now,now,json.dumps(t)))
                if initialized and old is None:
                    self.c.execute('INSERT OR IGNORE INTO ember_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',
                      (self.recipient,'solana:'+t['mint']+':ember:launch',body(t),now+600));new+=1
            self.c.execute("INSERT OR REPLACE INTO ember_state VALUES('initialized','1')")
        self.health(f'EmberCurve: {len(markets)} markets indexed; {new} new launches queued; filtration not yet applied')

def run():
    if os.environ.get('EMBER_ENABLED')!='true':return
    from bot import database,api
    recipient=int(os.environ['ADMIN_CHAT_ID']);token=os.environ['TELEGRAM_BOT_TOKEN']
    c=database();setup(c);s=Scanner(c,recipient)
    print('EmberCurve private scanner started.',flush=True)
    while True:
        try:
            s.scan()
            if os.environ.get('GLOBAL_FILTER_ENABLED','true')!='true':
                for _ in range(10):deliver(c,token,api,table='ember_outbox');time.sleep(.5)
        except Exception as e:
            s.health('EmberCurve retrying: '+type(e).__name__);print('EmberCurve retrying: '+type(e).__name__,flush=True)
        time.sleep(int(os.environ.get('EMBER_POLL_SECONDS','15')))
if __name__=='__main__':run()
