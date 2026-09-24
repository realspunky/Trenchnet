"""StonkFun Solana private API pilot. Read-only; no wallet/API key required."""
import json
import math
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.error import HTTPError
from scanner import clean, deliver
from launch_model import setup as unified_setup, record as record_launch

BASE = 'https://www.stonkfun.xyz/api/public/v1'
MINT = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}\Z')

class FeedError(ValueError):pass

class RateLimited(FeedError):
    def __init__(self, delay):self.delay = delay

def timestamp(value):
    if not isinstance(value,str):raise FeedError('Missing timestamp')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise FeedError('Unzoned timestamp')
    return dt.timestamp()

def fetch(path, now=None):
    request=urllib.request.Request(BASE+path,headers={'Accept':'application/json','User-Agent':'TrenchNet-private-pilot/1.0'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise FeedError('Response too large')
            result=json.loads(raw)
    except HTTPError as e:
        if e.code==429:
            try:delay=max(60,int(e.headers.get('Retry-After','60')))
            except (TypeError,ValueError):delay=60
            raise RateLimited(delay) from None
        raise
    clock=time.time() if now is None else now
    generated=timestamp(result.get('meta',{}).get('generatedAt'))
    if not -60<=clock-generated<=300:raise FeedError('Stale API response')
    if not isinstance(result.get('data'),dict):raise FeedError('Missing data')
    return result['data'],generated

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS stonk_cursor(id INTEGER PRIMARY KEY CHECK(id=1), since REAL, started REAL);
    CREATE TABLE IF NOT EXISTS stonk_tokens(mint TEXT PRIMARY KEY,created REAL,status TEXT DEFAULT 'pending',
        next_check REAL DEFAULT 0,attempts INTEGER DEFAULT 0,snapshot TEXT);
    CREATE TABLE IF NOT EXISTS stonk_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,status TEXT);
    CREATE TABLE IF NOT EXISTS stonk_outbox(id INTEGER PRIMARY KEY,recipient INTEGER,event_key TEXT,body TEXT,
        state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,
        message_id INTEGER,expires INTEGER NOT NULL DEFAULT 0,UNIQUE(recipient,event_key));
    ''')
    with c:c.execute("UPDATE stonk_outbox SET state='uncertain' WHERE state='sending'")
    unified_setup(c)

def normalize(data, expected):
    if data.get('network')!='mainnet-beta':raise FeedError('Wrong network')
    t=data.get('token',{})
    if not MINT.fullmatch(expected) or t.get('mint')!=expected:raise FeedError('Wrong token')
    progress=t.get('graduationProgress')
    if type(progress) not in (int,float) or not math.isfinite(progress) or not 0<=progress<=1:
        raise FeedError('Unknown bonding scale')
    status=t.get('status')
    if status not in {'new','aboutToGraduate','graduated'}:raise FeedError('Unknown status')
    fee=t.get('transferFee') or {}
    rate=fee.get('bps')
    eligible=(t.get('launchpad')=='launchlab' and t.get('mode')=='reward'
              and type(rate) is int and rate in {100,200,300})
    quote=t.get('quote') or {}
    if eligible and not MINT.fullmatch(str(quote.get('mint',''))):raise FeedError('Missing reward asset')
    name=clean(t.get('name',''))
    symbol=clean(t.get('symbol',''),30)
    if not name or name.casefold() in {'unknown','unknown token'}:raise FeedError('Token metadata name unavailable')
    if not symbol:raise FeedError('Token metadata symbol unavailable')
    return dict(mint=expected,name=name,symbol=symbol,
        eligible=eligible,rate=rate,progress=progress*100,status=status,
        reward_mint=quote.get('mint'),reward_symbol=clean(quote.get('symbol',''),30))

def body(s, kind, observed):
    return (f'📣 PRIVATE PILOT — {kind}\n🪙 {s["name"]} ({s["symbol"]})\n'
        f'🌐 Network: Solana | 🚀 Launchpad: StonkFun\n📋 Contract: {s["mint"]}\n'
        f'💸 Transfer tax: {s["rate"]/100:g}%\n💰 Holder rewards: {s["reward_symbol"]}\n'
        f'Reward asset: {s["reward_mint"]}\n📈 Bonding progress: awaiting scale verification\n'
        f'Observed (UTC): {datetime.fromtimestamp(observed,timezone.utc):%Y-%m-%d %H:%M:%S}\n'
        f'🔗 https://www.stonkfun.xyz/token/{s["mint"]}\n'
        'Source: StonkFun API. Separate trading fees may apply; total fees are not verified. '
        'A bonding alert does not confirm migration.')

class Scanner:
    def __init__(self,c,recipient,get=fetch,bonding_enabled=False):
        self.c=c;self.recipient=recipient;self.get=get;self.bonding_enabled=bonding_enabled
    def health(self,message):
        with self.c:self.c.execute('INSERT OR REPLACE INTO stonk_health VALUES(1,?,?)',(int(time.time()),message))
    def scan(self):
        now=time.time()
        cursor=self.c.execute('SELECT since,started FROM stonk_cursor WHERE id=1').fetchone()
        if cursor is None:
            # Begin now; do not consume old launches or flood the owner's inbox.
            with self.c:self.c.execute('INSERT INTO stonk_cursor VALUES(1,?,?)',(now,now))
            self.health('Stonk initialized; waiting for new launches');return
        since,started=cursor
        iso=datetime.fromtimestamp(since-600,timezone.utc).isoformat()
        records=[];watermark=None
        for page in range(1,6):
            data,generated=self.get('/launches?'+urlencode(dict(mode='reward',since=iso,page=page,pageSize=100)))
            rows=data.get('launches');pagination=data.get('pagination',{})
            if not isinstance(rows,list) or len(rows)>100:raise FeedError('Invalid launches')
            pages=pagination.get('totalPages')
            if type(pages) is not int or pages<0 or pagination.get('page')!=page:raise FeedError('Invalid pagination')
            if pages>5:raise FeedError('Launch backlog exceeds 500; checkpoint retained')
            watermark=generated if watermark is None else min(watermark,generated)
            for t in rows:
                mint=t.get('mint','')
                if not MINT.fullmatch(mint):raise FeedError('Invalid mint')
                created=timestamp(t.get('createdAt'))
                if created>now+60:raise FeedError('Future launch')
                records.append((mint,created))
            if page>=pages:break
        with self.c:
            for mint,created in records:
                # The overlap protects against delayed indexing and moving page boundaries.
                if created>=max(started,since-600):
                    inserted=self.c.execute('INSERT OR IGNORE INTO stonk_tokens(mint,created) VALUES(?,?)',(mint,created)).rowcount
                    if inserted and os.environ.get('TRENCHNET_V2_ENABLED','true').lower()=='true':
                        record_launch(self.c,chain='solana',launchpad='stonk',address=mint,
                                      launched_at=created,source_table='stonk_tokens',
                                      metadata={'mint':mint},now=now)
            self.c.execute('UPDATE stonk_cursor SET since=? WHERE id=1',(max(since,watermark),))
        threshold_row=self.c.execute('SELECT threshold FROM users WHERE id=?',(self.recipient,)).fetchone()
        threshold=threshold_row[0] if threshold_row else 80
        # Prioritize genuinely new launches so historical tracking/retry rows cannot starve alerts.
        fresh_limit=max(8,int(os.environ.get('STONK_FRESH_BATCH','40')))
        maintenance_limit=max(0,int(os.environ.get('STONK_MAINTENANCE_BATCH','4')))
        fresh_rows=self.c.execute("SELECT mint,created,attempts FROM stonk_tokens WHERE status='pending' AND next_check<=? ORDER BY created DESC LIMIT ?",(now,fresh_limit)).fetchall()
        # Fresh metadata retries get their own priority lane. Old tracking/retry work
        # cannot consume the capacity reserved for newly detected launches.
        fresh_retry=self.c.execute("SELECT mint,created,attempts FROM stonk_tokens WHERE status='retry' AND created>=? AND next_check<=? ORDER BY created DESC LIMIT ?",(now-600,now,fresh_limit)).fetchall()
        selected={r[0] for r in fresh_rows+fresh_retry}
        maintenance=self.c.execute("SELECT mint,created,attempts FROM stonk_tokens WHERE status IN ('tracking','retry') AND next_check<=? ORDER BY next_check LIMIT ?",(now,maintenance_limit)).fetchall() if maintenance_limit else []
        maintenance=[r for r in maintenance if r[0] not in selected]
        rows=fresh_rows+fresh_retry+maintenance
        failures=0
        for mint,created,attempts in rows:
            # Keep the mint locally immediately, but do NOT enter the unified alert
            # pipeline until verified token metadata is available. TrenchNet must never
            # send a STOnK launch alert named "Unknown token".
            try:
                data,generated=self.get('/tokens/'+mint)
                s=normalize(data,mint)
                status='migrated' if s['status']=='graduated' else ('tracking' if s['eligible'] else 'excluded')
                # Only holder-reward launches with an allowed 1%-3% transfer tax may
                # enter the unified alert pipeline. Metadata resolution alone is not
                # enough to qualify a STOnK launch.
                if os.environ.get('TRENCHNET_V2_ENABLED','true').lower()=='true' or s['eligible']:
                    record_launch(self.c,chain='solana',launchpad='stonk',address=mint,name=s['name'],symbol=s['symbol'],
                        launched_at=int(created),bonding_progress=s['progress'],migrated=s['status']=='graduated',
                        source_table='stonk_tokens',metadata=s)
                items=[]
                if os.environ.get('TRENCHNET_V2_ENABLED','true').lower()!='true' and status=='tracking':
                    if 0<=time.time()-created<=600:items.append(('launch','New launch'))
                    if self.bonding_enabled and threshold<=s['progress']<100:items.append(('bonding','Pre-migration threshold reached'))
                with self.c:
                    for kind,title in items:
                                        self.c.execute('INSERT OR IGNORE INTO stonk_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',
                            (self.recipient,'solana:'+mint+':'+kind,body(s,title,generated),int(time.time())+300))
                    self.c.execute('UPDATE stonk_tokens SET status=?,snapshot=?,next_check=?,attempts=0 WHERE mint=?',
                        (status,json.dumps(s),time.time()+60,mint))
            except RateLimited:raise
            except Exception as e:
                failures+=1
                with self.c:self.c.execute('UPDATE stonk_tokens SET status=?,attempts=?,next_check=? WHERE mint=?',
                    ('review' if attempts>=8 else 'retry',attempts+1,
                     time.time()+(min(30,3*(2**min(attempts,3))) if time.time()-created<=600 else min(600,60*2**min(attempts,4))),mint))
                print('Stonk token read failed: '+mint+' ('+type(e).__name__+')',flush=True)
        unresolved=self.c.execute("SELECT COUNT(*) FROM stonk_tokens WHERE status IN ('pending','retry','review')").fetchone()[0]
        self.health(f'Stonk API polling; {len(records)} launch records checked; fresh_pending={len(fresh_rows)}; serviced={len(rows)}; {failures} token read failures this cycle; metadata_waiting={unresolved}')

def run():
    if os.environ.get('STONK_ENABLED')!='true':return
    from bot import database,api
    recipient=int(os.environ['ADMIN_CHAT_ID'])
    if recipient<=0:raise ValueError('Private ADMIN_CHAT_ID required')
    token=os.environ['TELEGRAM_BOT_TOKEN']
    c=database();setup(c);scanner=Scanner(c,recipient)
    print('Stonk private scanner started.',flush=True)
    while True:
        delay=max(3,int(os.environ.get('STONK_POLL_SECONDS','8')))
        try:
            scanner.scan()
            if os.environ.get('TRENCHNET_V2_ENABLED','true').lower()!='true':
                for _ in range(5):
                    deliver(c,token,api,table='stonk_outbox')
                    time.sleep(1)
        except RateLimited as e:
            delay=e.delay;scanner.health('Stonk rate limited; waiting for provider retry window')
        except Exception as e:
            reason=str(e) if isinstance(e,FeedError) else type(e).__name__
            scanner.health('Stonk retrying: '+reason)
            print('Stonk retrying: '+reason,flush=True)
        # Interruptible process shutdown; no busy retrying on a rate limit.
        time.sleep(delay)

if __name__=='__main__':run()
