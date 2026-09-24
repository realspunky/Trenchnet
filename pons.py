"""PONS launch listener for Robinhood Chain. Read-only private pilot."""
import json
import os
import time
from web3 import Web3
from scanner import clean, deliver
from launch_model import setup as unified_setup, record as record_launch
from rpc_check import call

CHAIN_ID=4663
RPC_DEFAULT='https://rpc.mainnet.chain.robinhood.com'
ACTIVE_FACTORY=Web3.to_checksum_address('0xA5aAb3F0c6EeadF30Ef1D3Eb997108E976351feB')
ACTIVE_START=8991118
LEGACY_FACTORY=Web3.to_checksum_address('0x0c37a24F5D23A486FA692d1500881d698B1F77a4')
LEGACY_START=8600612
V2_FACTORY=Web3.to_checksum_address('0x7eD598BcEf8bd9Edd8C97A195C6d13f40801EC7e')
V2_START=int(os.environ.get('PONS_V2_START_BLOCK','0'))
V2_TOKEN_LAUNCHED_TOPIC='0x8d4aad4953d0ca700d468f3753aa14432d1b35b43ec6409f051fb6aa43a89607'
TOKEN_LAUNCHED_TOPIC='0xdb51ea9ad51ab453a65a4cb7e60c3cb378c9501bb002609f8f97778fb6c4235a'
EVENT_ABI={"anonymous":False,"inputs":[
 {"indexed":True,"name":"token","type":"address"},{"indexed":True,"name":"deployer","type":"address"},
 {"indexed":True,"name":"dexFactory","type":"address"},{"indexed":False,"name":"pairToken","type":"address"},
 {"indexed":False,"name":"pool","type":"address"},{"indexed":False,"name":"dexId","type":"uint256"},
 {"indexed":False,"name":"launchConfigId","type":"uint256"},{"indexed":False,"name":"positionId","type":"uint256"},
 {"indexed":False,"name":"restrictionsEndBlock","type":"uint256"},{"indexed":False,"name":"initialBuyAmount","type":"uint256"}],
 "name":"TokenLaunched","type":"event"}
TOKEN_ABI=[
 {"inputs":[],"name":"name","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"logo","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"description","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
]

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS pons_cursor(factory TEXT PRIMARY KEY,height INTEGER NOT NULL,hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pons_tokens(address TEXT PRIMARY KEY,creator TEXT,name TEXT,symbol TEXT,pool TEXT,
      factory TEXT,tx TEXT,height INTEGER,created INTEGER,status TEXT DEFAULT 'new',snapshot TEXT);
    CREATE TABLE IF NOT EXISTS pons_outbox(id INTEGER PRIMARY KEY,recipient INTEGER,event_key TEXT,body TEXT,
      state TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,next_attempt INTEGER DEFAULT 0,
      message_id INTEGER,expires INTEGER NOT NULL DEFAULT 0,UNIQUE(recipient,event_key));
    CREATE TABLE IF NOT EXISTS pons_health(id INTEGER PRIMARY KEY CHECK(id=1),updated INTEGER,status TEXT);
    ''')
    unified_setup(c)
    with c:c.execute("UPDATE pons_outbox SET state='uncertain' WHERE state='sending'")

def metadata(w3,address):
    """Best-effort display metadata; broken token metadata never hides a launch."""
    token=w3.eth.contract(address=Web3.to_checksum_address(address),abi=TOKEN_ABI)
    name='Unknown token'; symbol=''
    try: name=clean(token.functions.name().call()) or 'Unknown token'
    except Exception: pass
    try: symbol=clean(token.functions.symbol().call(),30)
    except Exception: pass
    return name,symbol

def alert_body(t,decision):
    extra=''
    if decision.get('creator_launches',1)>1:
        extra=f'\n⚠️ Creator launches in window: {decision["creator_launches"]}'
    return (f'📣 PRIVATE PILOT — New launch\n🪙 {t["name"]} ({t["symbol"]})\n'
        f'🌐 Network: Robinhood Chain | 🚀 Launchpad: PONS\n📋 Contract: {t["address"]}\n'
        f'👤 Creator: {t["creator"]}\n🏊 Pool: {t["pool"]}{extra}\n'
        f'🔗 https://robinhoodchain.blockscout.com/token/{t["address"]}\n'
        'Launch detected directly from the PONS factory. Names/symbols are not unique; always verify the contract address.')

class Scanner:
    def __init__(self,c,url,recipient):
        self.c=c;self.url=url;self.recipient=recipient;self.w3=Web3(Web3.HTTPProvider(url,request_kwargs={'timeout':20}))
        self.factories=[(V2_FACTORY,V2_START,'v2'),(ACTIVE_FACTORY,ACTIVE_START,'v1'),(LEGACY_FACTORY,LEGACY_START,'v1')]
    def health(self,msg):
        with self.c:self.c.execute('INSERT OR REPLACE INTO pons_health VALUES(1,?,?)',(int(time.time()),msg))
    def scan_factory(self,factory,start,tip,generation='v1'):
        row=self.c.execute('SELECT height,hash FROM pons_cursor WHERE factory=?',(factory.lower(),)).fetchone()
        if row is None:
            # Snapshot current head on first boot. This prevents a history flood but captures every future launch.
            block=self.w3.eth.get_block(tip)
            with self.c:self.c.execute('INSERT INTO pons_cursor VALUES(?,?,?)',(factory.lower(),tip,block['hash'].hex()))
            return 0
        height,old_hash=row
        # If this deployment inherited a very old cursor, do not spend hours replaying
        # historical PONS logs. Keep only a small recent lookback and then follow live blocks.
        max_lag=max(50,int(os.environ.get('PONS_MAX_CURSOR_LAG_BLOCKS','200')))
        if tip-height > max_lag:
            height=max(0,tip-max_lag)
            base=self.w3.eth.get_block(height)
            old_hash=base['hash'].hex()
            with self.c:self.c.execute('UPDATE pons_cursor SET height=?,hash=? WHERE factory=?',(height,old_hash,factory.lower()))
        check=self.w3.eth.get_block(height)
        if check['hash'].hex()!=old_hash:raise ValueError('PONS checkpoint mismatch')
        found=0
        for _ in range(8):
            if height>=tip:break
            end=min(height+int(os.environ.get('PONS_LOG_BLOCK_CHUNK','10')),tip)
            topic = V2_TOKEN_LAUNCHED_TOPIC if generation=='v2' else TOKEN_LAUNCHED_TOPIC
            logs=self.w3.eth.get_logs({'address':factory,'topics':[topic],
                                      'fromBlock':height+1,'toBlock':end})
            contract=self.w3.eth.contract(address=factory,abi=[EVENT_ABI]) if generation=='v1' else None
            for log in logs:
                if generation=='v2':
                    # V2: token, curve and deployer are indexed topics 1..3.
                    if len(log.get('topics',[])) < 4: continue
                    address=('0x'+log['topics'][1].hex()[-40:]).lower()
                    pool=('0x'+log['topics'][2].hex()[-40:]).lower()  # bonding curve address
                    creator=('0x'+log['topics'][3].hex()[-40:]).lower()
                else:
                    ev=contract.events.TokenLaunched().process_log(log)['args']
                    address=ev['token'].lower();creator=ev['deployer'].lower();pool=ev['pool'].lower()
                name,symbol=metadata(self.w3,address)
                block=self.w3.eth.get_block(log['blockNumber'])
                t=dict(address=address,creator=creator,pool=pool,name=name,symbol=symbol,
                       factory=factory.lower(),tx=log['transactionHash'].hex(),height=log['blockNumber'],created=block['timestamp'])
                event_key=record_launch(self.c,chain='robinhood',launchpad='pons',address=address,creator=creator,
                    name=name,symbol=symbol,source_tx=t['tx'],source_height=t['height'],launched_at=t['created'],
                    source_table='pons_tokens',metadata=t,now=block['timestamp'])
                if os.environ.get('TRENCHNET_V2_ENABLED','false').lower()=='true':
                    with self.c:self.c.execute("UPDATE unified_launches SET pipeline_state='v2_tracking' WHERE event_key=?",(event_key,))
                decision={'creator_launches':1}
                with self.c:
                    self.c.execute('''INSERT OR IGNORE INTO pons_tokens(address,creator,name,symbol,pool,factory,tx,height,created,status,snapshot)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(address,creator,name,symbol,pool,factory.lower(),t['tx'],t['height'],t['created'],
                        'intake',json.dumps(t)))
                    if os.environ.get('TRENCHNET_V2_ENABLED','true').lower()!='true':
                        self.c.execute('INSERT OR IGNORE INTO pons_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',
                        (self.recipient,'robinhood:'+address+':launch',alert_body(t,decision),int(time.time())+600))
                found+=1
            end_block=self.w3.eth.get_block(end)
            with self.c:self.c.execute('UPDATE pons_cursor SET height=?,hash=? WHERE factory=?',(end,end_block['hash'].hex(),factory.lower()))
            height=end
        return found
    def scan(self):
        if self.w3.eth.chain_id!=CHAIN_ID:raise ValueError('Wrong network; expected Robinhood Chain')
        tip=self.w3.eth.block_number;found=0
        for factory,start,generation in self.factories:found+=self.scan_factory(factory,start,tip,generation)
        total=self.c.execute("SELECT COUNT(*) FROM unified_launches WHERE launchpad='pons'").fetchone()[0]
        pending=self.c.execute("SELECT COUNT(*) FROM unified_launches WHERE launchpad='pons' AND pipeline_state='intake'").fetchone()[0]
        approved=self.c.execute("SELECT COUNT(*) FROM unified_launches WHERE launchpad='pons' AND pipeline_state='approved'").fetchone()[0]
        self.health(f'PONS: block {tip}; {found} new launch logs; unified total {total}; intake {pending}; approved {approved}')

def run():
    if os.environ.get('PONS_ENABLED')!='true':return
    from bot import database,api
    recipient=int(os.environ['ADMIN_CHAT_ID']);token=os.environ['TELEGRAM_BOT_TOKEN']
    if recipient<=0:raise ValueError('Private ADMIN_CHAT_ID required')
    c=database();setup(c);scanner=Scanner(c,os.environ.get('PONS_RPC_URL',RPC_DEFAULT),recipient)
    print('PONS private scanner started.',flush=True)
    while True:
        try:
            scanner.scan()
            if os.environ.get('TRENCHNET_V2_ENABLED','true').lower()!='true':
                for _ in range(10):deliver(c,token,api,table='pons_outbox');time.sleep(.5)
        except Exception as e:
            scanner.health('PONS retrying: '+type(e).__name__+'; reduce/check RPC log requests if persistent')
            print('PONS retrying: '+type(e).__name__+'; RPC request failed',flush=True)
        time.sleep(15)

if __name__=='__main__':run()
