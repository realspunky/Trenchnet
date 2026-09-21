"""Flap BNB private pilot. No public subscriber delivery or trading."""
import json
import re
import os
import sqlite3
import time
import unicodedata
from flap import Reader, PORTAL
from rpc_check import call
from launch_model import setup as unified_setup, record as record_launch

SIGNATURE = 'TokenCreated(uint256,address,uint256,address,string,string,string)'
TYPES = ['uint256','address','uint256','address','string','string','string']

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS scan_cursor (id INTEGER PRIMARY KEY CHECK(id=1), height INTEGER, hash TEXT);
    CREATE TABLE IF NOT EXISTS scan_tokens (
      address TEXT PRIMARY KEY, name TEXT, symbol TEXT, tx TEXT, created INTEGER,
      height INTEGER, next_check INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0,
      status TEXT DEFAULT 'pending', snapshot TEXT);
    CREATE TABLE IF NOT EXISTS pilot_outbox (
      id INTEGER PRIMARY KEY, recipient INTEGER, event_key TEXT, body TEXT,
      state TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, next_attempt INTEGER DEFAULT 0,
      message_id INTEGER, expires INTEGER NOT NULL DEFAULT 0, UNIQUE(recipient,event_key));
    CREATE TABLE IF NOT EXISTS scanner_health (id INTEGER PRIMARY KEY CHECK(id=1), updated INTEGER, status TEXT);
    ''')
    if 'expires' not in [r[1] for r in c.execute('PRAGMA table_info(pilot_outbox)')]:
        c.execute('ALTER TABLE pilot_outbox ADD COLUMN expires INTEGER NOT NULL DEFAULT 0')
    # A send interrupted by a restart might have reached Telegram. Do not blindly resend.
    c.execute("UPDATE pilot_outbox SET state='uncertain' WHERE state='sending'")
    c.commit()
    unified_setup(c)

def clean(value, limit=100):
    return ''.join(ch for ch in str(value) if not unicodedata.category(ch).startswith('C'))[:limit]

def decode_launch(log):
    from eth_abi import decode
    from web3 import Web3
    topics=log.get('topics',[])
    topic='0x'+Web3.keccak(text=SIGNATURE).hex().removeprefix('0x')
    if log.get('removed') or log.get('address','').lower()!=PORTAL.lower():
        raise ValueError('Unexpected emitter or removed log')
    if len(topics)!=1 or topics[0].lower()!=topic.lower():
        raise ValueError('Unexpected event signature/indexing')
    ts,creator,nonce,address,name,symbol,meta=decode(TYPES,bytes.fromhex(log['data'][2:]))
    return dict(address=address.lower(),creator=str(creator).lower(),name=clean(name),symbol=clean(symbol,30),
                tx=log['transactionHash'],created=ts,height=int(log['blockNumber'],16))

def persist_batch(c, tokens, height, block_hash):
    with c:
        for t in tokens:
            c.execute('INSERT OR IGNORE INTO scan_tokens(address,name,symbol,tx,created,height) VALUES (?,?,?,?,?,?)',
                      tuple(t[k] for k in ['address','name','symbol','tx','created','height']))
            record_launch(c,chain='bnb',launchpad='flap',address=t['address'],creator=t.get('creator',''),
                name=t['name'],symbol=t['symbol'],source_tx=t['tx'],source_height=t['height'],
                launched_at=t['created'],source_table='scan_tokens',metadata=t)
        c.execute('INSERT OR REPLACE INTO scan_cursor VALUES (1,?,?)',(height,block_hash))

def minimum_balance(s):
    raw = str(s.get('minimum_share_balance', ''))
    decimals = s.get('token_decimals')
    if not raw.isdigit() or type(decimals) is not int or not 0 <= decimals <= 255:
        return 'unavailable'
    # Integer arithmetic preserves every digit, even for uint256 balances.
    whole, fraction = divmod(int(raw), 10**decimals)
    tail = str(fraction).zfill(decimals).rstrip('0') if decimals else ''
    return f'{whole:,}' + ('.' + tail if tail else '') + ' units'

def body(t,s,kind):
    allocation=s['dividend_allocation_bps']/100
    return (f'📣 PRIVATE PILOT — {kind}\n🪙 {t["name"]} ({t["symbol"]})\n'
        f'🌐 Network: BNB Chain | 🚀 Launchpad: Flap\n📋 Contract: {t["address"]}\n'
        f'💸 Token tax: buy {s["buy_tax_bps"]/100:g}% / sell {s["sell_tax_bps"]/100:g}%\n'
        f'📊 Holder allocation: {allocation:g}% of tax allocation\n'
        f'💰 Reward asset: {s.get("reward_token")} (zero address means native BNB)\n'
        f'🏦 Minimum holder balance: {minimum_balance(s)}\n'
        f'📈 Bonding progress: {s["bonding_percent"]:.2f}% at block {s.get("block_number", "unknown")}\n'
        f'🔗 https://bscscan.com/token/{t["address"]}\n'
        'Separate protocol fees may apply. This is a test candidate, total trading fees are not yet verified. '
        'A bonding alert does not confirm migration.')

def queue_candidate(c,t,s,recipient,threshold,now):
    # Only verified basic contract readings; public total-fee matching remains disabled.
    if not s.get('verified') or s.get('status')!=1:
        return
    items=[]
    if 0 <= now-t['created'] <= 600:
        items.append(('launch','New launch'))
    if threshold <= s['bonding_percent'] < 100:
        items.append(('bonding','Pre-migration threshold reached'))
    for kind,title in items:
        c.execute('INSERT OR IGNORE INTO pilot_outbox(recipient,event_key,body,expires) VALUES (?,?,?,?)',
                  (recipient,'bnb:'+t['address']+':'+kind,body(t,s,title),now+300))

class Scanner:
    def __init__(self,c,url,recipient):
        self.c=c; self.url=url; self.recipient=recipient
        self.reader=Reader(url)
        from web3 import Web3
        self.topic='0x'+Web3.keccak(text=SIGNATURE).hex().removeprefix('0x')
    def scan(self):
        block=call(self.url,'eth_getBlockByNumber',['finalized',False])
        tip=int(block['number'],16); now=int(time.time())
        if not -60 <= now-int(block['timestamp'],16) <= 300:
            raise ValueError('Stale finalized head')
        row=self.c.execute('SELECT height,hash FROM scan_cursor WHERE id=1').fetchone()
        if row is None:
            # Start now, never dump old launches on the first deployment.
            persist_batch(self.c,[],tip,block['hash']);return
        height,old_hash=row
        check=call(self.url,'eth_getBlockByNumber',[hex(height),False])
        if not check or check['hash']!=old_hash:
            raise ValueError('Finalized checkpoint mismatch; operator review required')
        # Bounded work and <=10 blocks per Alchemy Free log request.
        for _ in range(10):
            if height>=tip:break
            end=min(height+10,tip)
            logs=call(self.url,'eth_getLogs',[{'address':PORTAL,'topics':[self.topic],
                          'fromBlock':hex(height+1),'toBlock':hex(end)}])
            if not isinstance(logs,list):raise ValueError('Invalid log response')
            tokens=[]
            for log in logs:
                if not height < int(log['blockNumber'],16) <= end:
                    raise ValueError('Log outside requested range')
                tokens.append(decode_launch(log))
            end_block=call(self.url,'eth_getBlockByNumber',[hex(end),False])
            persist_batch(self.c,tokens,end,end_block['hash']);height=end
        threshold_row=self.c.execute('SELECT threshold FROM users WHERE id=?',(self.recipient,)).fetchone()
        threshold=threshold_row[0] if threshold_row else 80
        self.c.row_factory=sqlite3.Row
        rows=self.c.execute("SELECT * FROM scan_tokens WHERE status IN ('pending','tracking','retry') AND next_check<=? ORDER BY next_check LIMIT 5",(now,)).fetchall()
        self.c.row_factory=None
        for row in rows:
            t=dict(row)
            try:
                s=self.reader.inspect(t['address'])
                if s['migrated']:status='migrated'
                elif s['verified']:status='tracking'
                else:status='excluded'
                with self.c:
                    queue_candidate(self.c,t,s,self.recipient,threshold,now)
                    self.c.execute('UPDATE scan_tokens SET status=?,snapshot=?,next_check=?,attempts=0 WHERE address=?',
                          (status,json.dumps(s),now+30,t['address']))
            except Exception:
                attempts=t['attempts']+1
                with self.c:
                    self.c.execute('UPDATE scan_tokens SET status=?,attempts=?,next_check=? WHERE address=?',
                        ('review' if attempts>=5 else 'retry',attempts,now+min(600,30*2**attempts),t['address']))
                print('Token read failed; address='+t['address']+'; queued for retry/review.',flush=True)
        with self.c:
            self.c.execute('INSERT OR REPLACE INTO scanner_health VALUES(1,?,?)',(now,f'Private pilot: scanned block {height}, lag {tip-height} blocks; public alerts disabled'))

def alert_payload(recipient, text):
    payload = {'chat_id': recipient, 'text': text, 'disable_web_page_preview': True}
    match = re.search(r'^(?:📋 )?Contract: (0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})$', text, re.MULTILINE)
    if match:
        address = match.group(1)
        # Telegram entity offsets count UTF-16 units, including preceding emojis.
        offset = len(text[:match.start(1)].encode('utf-16-le')) // 2
        payload['entities'] = [{'type': 'code', 'offset': offset, 'length': len(address)}]
        buttons=[{'text': '📋 Copy contract', 'copy_text': {'text': address}}]
        xm=re.search(r'^𝕏 X: (https?://\S+)$', text, re.MULTILINE)
        wm=re.search(r'^🌐 Website: (https?://\S+)$', text, re.MULTILINE)
        if xm: buttons.append({'text':'𝕏 X','url':xm.group(1)})
        if wm: buttons.append({'text':'🌐 Website','url':wm.group(1)})
        payload['reply_markup'] = {'inline_keyboard': [buttons]}
    return payload

def deliver(c,token,send,table="pilot_outbox"):
    if table not in {"pilot_outbox", "stonk_outbox", "pons_outbox", "ember_outbox", "pumpfun_outbox", "global_outbox"}:raise ValueError("Invalid delivery table")
    from urllib.error import HTTPError
    with c:
        c.execute(f"UPDATE {table} SET state='expired' WHERE state='pending' AND expires<=?",(int(time.time()),))
    row=c.execute(f"SELECT id,recipient,body,attempts FROM {table} WHERE state='pending' AND next_attempt<=? ORDER BY id LIMIT 1",(int(time.time()),)).fetchone()
    if not row:return
    ident,recipient,text,attempts=row
    with c:c.execute(f"UPDATE {table} SET state='sending' WHERE id=?",(ident,))
    try:
        result=send(token,'sendMessage',alert_payload(recipient,text))
        with c:c.execute(f"UPDATE {table} SET state='sent',message_id=? WHERE id=?",(result['message_id'],ident))
    except HTTPError as e:
        # Telegram's explicit rate rejection can be retried. Others require review.
        retry=60
        if e.code==429:
            try:retry=max(1,int(json.load(e).get('parameters',{}).get('retry_after',60)))
            except Exception:pass
        state='pending' if e.code==429 and attempts<5 else 'review'
        with c:c.execute(f'UPDATE {table} SET state=?,attempts=?,next_attempt=? WHERE id=?',
                         (state,attempts+1,int(time.time())+retry,ident))
    except Exception:
        with c:c.execute(f"UPDATE {table} SET state='uncertain' WHERE id=?",(ident,))
        print('Private alert delivery uncertain; retained for review, not resent.',flush=True)

def run():
    if os.environ.get('SCANNER_ENABLED')!='true':
        print('Scanner disabled.',flush=True);return
    recipient=int(os.environ['ADMIN_CHAT_ID'])
    if recipient<=0:raise ValueError('Private positive ADMIN_CHAT_ID required')
    url=os.environ['BNB_RPC_URL'];token=os.environ['TELEGRAM_BOT_TOKEN']
    from bot import database,api
    c=database();setup(c)
    scanner=None
    while True:
        try:
            if scanner is None:scanner=Scanner(c,url,recipient)
            scanner.scan()
            if os.environ.get('GLOBAL_FILTER_ENABLED','true')!='true':
                deliver(c,token,api)
        except Exception as e:
            # Type is useful without risking API key disclosure in exception text.
            print('Scanner paused/retrying: '+type(e).__name__,flush=True)
            with c:c.execute('INSERT OR REPLACE INTO scanner_health VALUES(1,?,?)',(int(time.time()),'Scanner error; retrying'))
        time.sleep(15)

if __name__=='__main__':run()
