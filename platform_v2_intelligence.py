"""Native Stage-2 adapters for Flap, STOnK, EmberCurve and Pump.fun."""
import json, os, sqlite3, time
from stage2_collectors import enrich

def _db():
 return sqlite3.connect(os.environ.get('DATABASE_PATH','/data/trenchnet.sqlite3'))

def _source_snapshot(launchpad,address):
 c=_db()
 try:
  if launchpad=='stonk':r=c.execute('SELECT snapshot FROM stonk_tokens WHERE mint=?',(address,)).fetchone()
  elif launchpad=='embercurve':r=c.execute('SELECT snapshot FROM ember_tokens WHERE mint=?',(address,)).fetchone()
  elif launchpad=='flap':r=c.execute('SELECT snapshot FROM scan_tokens WHERE address=?',(address,)).fetchone()
  else:r=None
  if not r or not r[0]:return {}
  x=json.loads(r[0]);return x if isinstance(x,dict) else {}
 finally:c.close()

def fetch(launchpad,address,metadata=None):
 meta=dict(metadata or {})
 src=_source_snapshot(launchpad,address)
 meta.update(src)
 if launchpad=='flap':p=src.get('bonding_percent')
 elif launchpad=='stonk':p=src.get('progress')
 elif launchpad=='embercurve':p=src.get('progress')
 else:p=meta.get('bondingProgress')
 if p is None:return None
 p=float(p)
 if p < 60:return p,meta
 return p,enrich(launchpad,address,meta)
