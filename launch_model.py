"""Canonical launch model shared by every TrenchNet launchpad.

Scanners own discovery. This module only normalizes/persists launch facts so the
next-stage global filter and per-user routing can operate without launchpad-specific
schemas.
"""
import json, time
from urllib.parse import urlparse

CHAINS={'bnb','solana','robinhood'}
LAUNCHPADS={'flap','stonk','pons','embercurve','pumpfun'}

def setup(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS unified_launches(
      id INTEGER PRIMARY KEY,
      event_key TEXT NOT NULL UNIQUE,
      chain TEXT NOT NULL,
      launchpad TEXT NOT NULL,
      address TEXT NOT NULL,
      creator TEXT NOT NULL DEFAULT '',
      name TEXT NOT NULL DEFAULT '',
      symbol TEXT NOT NULL DEFAULT '',
      pair_symbol TEXT NOT NULL DEFAULT '',
      source_tx TEXT NOT NULL DEFAULT '',
      source_height INTEGER,
      launched_at INTEGER NOT NULL,
      first_seen INTEGER NOT NULL,
      last_seen INTEGER NOT NULL,
      bonding_progress REAL,
      migrated INTEGER NOT NULL DEFAULT 0,
      source_table TEXT NOT NULL DEFAULT '',
      metadata TEXT NOT NULL DEFAULT '{}',
      social_x_url TEXT NOT NULL DEFAULT '',
      website_url TEXT NOT NULL DEFAULT '',
      pipeline_state TEXT NOT NULL DEFAULT 'intake'
    );
    CREATE INDEX IF NOT EXISTS unified_launchpad_time ON unified_launches(launchpad,launched_at);
    CREATE INDEX IF NOT EXISTS unified_chain_address ON unified_launches(chain,address);
    CREATE INDEX IF NOT EXISTS unified_creator_time ON unified_launches(chain,creator,launched_at);
    CREATE INDEX IF NOT EXISTS unified_pipeline ON unified_launches(pipeline_state,launched_at);
    ''')
    cols={r[1] for r in c.execute('PRAGMA table_info(unified_launches)')}
    if 'social_x_url' not in cols: c.execute("ALTER TABLE unified_launches ADD COLUMN social_x_url TEXT NOT NULL DEFAULT ''")
    if 'website_url' not in cols: c.execute("ALTER TABLE unified_launches ADD COLUMN website_url TEXT NOT NULL DEFAULT ''")
    c.commit()

def _valid_url(value, x=False):
    try:
        value=str(value or '').strip()
        u=urlparse(value)
        if u.scheme not in {'http','https'} or not u.netloc: return ''
        host=(u.hostname or '').lower()
        if x and host not in {'x.com','www.x.com','twitter.com','www.twitter.com','mobile.twitter.com'}: return ''
        return value[:1000]
    except Exception:return ''

def social_links(metadata):
    """Best-effort normalization of token-supplied social metadata. Never invent links."""
    xurl=web=''
    xkeys={'twitter','twitter_url','twitterurl','x','x_url','xurl'}
    wkeys={'website','website_url','websiteurl','external_url','externalurl','homepage','site'}
    def walk(v,depth=0):
        nonlocal xurl,web
        if depth>4:return
        if isinstance(v,dict):
            for k,val in v.items():
                key=str(k).lower().replace('-','_')
                if not xurl and key in xkeys:xurl=_valid_url(val,True)
                if not web and key in wkeys:web=_valid_url(val,False)
                if isinstance(val,(dict,list)):walk(val,depth+1)
        elif isinstance(v,list):
            for z in v[:30]:walk(z,depth+1)
    walk(metadata or {})
    return xurl,web

def record(c, *, chain, launchpad, address, name='', symbol='', creator='', pair_symbol='',
           source_tx='', source_height=None, launched_at=None, bonding_progress=None,
           migrated=False, source_table='', metadata=None, now=None):
    if chain not in CHAINS: raise ValueError('unsupported unified chain')
    if launchpad not in LAUNCHPADS: raise ValueError('unsupported unified launchpad')
    address=str(address or '').strip()
    if not address: raise ValueError('missing unified contract address')
    now=int(time.time() if now is None else now)
    launched_at=int(now if launched_at is None else launched_at)
    event_key=f'{chain}:{launchpad}:{address.lower()}:launch'
    payload=json.dumps(metadata or {},separators=(',',':'),sort_keys=True,default=str)
    social_x_url,website_url=social_links(metadata)
    setup(c)
    with c:
        c.execute('''INSERT INTO unified_launches(event_key,chain,launchpad,address,creator,name,symbol,pair_symbol,
          source_tx,source_height,launched_at,first_seen,last_seen,bonding_progress,migrated,source_table,metadata,social_x_url,website_url)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(event_key) DO UPDATE SET
            creator=CASE WHEN excluded.creator<>'' THEN excluded.creator ELSE unified_launches.creator END,
            name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE unified_launches.name END,
            symbol=CASE WHEN excluded.symbol<>'' THEN excluded.symbol ELSE unified_launches.symbol END,
            pair_symbol=CASE WHEN excluded.pair_symbol<>'' THEN excluded.pair_symbol ELSE unified_launches.pair_symbol END,
            source_tx=CASE WHEN excluded.source_tx<>'' THEN excluded.source_tx ELSE unified_launches.source_tx END,
            source_height=COALESCE(excluded.source_height,unified_launches.source_height),
            last_seen=excluded.last_seen,
            bonding_progress=COALESCE(excluded.bonding_progress,unified_launches.bonding_progress),
            migrated=MAX(unified_launches.migrated,excluded.migrated), metadata=excluded.metadata,
            social_x_url=CASE WHEN excluded.social_x_url<>'' THEN excluded.social_x_url ELSE unified_launches.social_x_url END,
            website_url=CASE WHEN excluded.website_url<>'' THEN excluded.website_url ELSE unified_launches.website_url END''',
          (event_key,chain,launchpad,address,str(creator or ''),str(name or ''),str(symbol or ''),str(pair_symbol or ''),
           str(source_tx or ''),source_height,launched_at,now,now,bonding_progress,int(bool(migrated)),source_table,payload,social_x_url,website_url))
    try:
        from v2_intelligence import enabled as v2_enabled, mark_progress, upsert_intelligence
        if v2_enabled():
            mark_progress(c,event_key,address,launchpad,bonding_progress,launched_at,migrated,now)
            # Source metadata may already contain Stage-2 facts. Extract them immediately;
            # missing facts remain incomplete and therefore cannot alert.
            upsert_intelligence(c,event_key,address,launchpad,metadata or {},source=source_table,now=now)
    except Exception:
        # Intake must remain durable even if enrichment is temporarily unavailable.
        pass
    return event_key
