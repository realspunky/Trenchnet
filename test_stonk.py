import io
import json
import sqlite3
import unittest
from unittest.mock import patch,Mock
from datetime import datetime,timezone
from stonk import setup,normalize,fetch,Scanner,FeedError,RateLimited,body
from scanner import deliver
from urllib.error import HTTPError

NOW=2000000000
M='GCTEMRaPyys7km2kqbgEhdo14DQSQDumVbciyrpBV3zG'
Q='CARDSccUMFKoPRZxt5vt3ksUbxEFEcnZ3H2pd3dKxYjp'
def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def token(rate=100,progress=.85,mode='reward',status='aboutToGraduate'):
 return {'network':'mainnet-beta','token':dict(mint=M,name='Example',symbol='EX',launchpad='launchlab',mode=mode,
  transferFee={'bps':rate},graduationProgress=progress,status=status,quote={'mint':Q,'symbol':'CARDS'})}
class StonkTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');setup(self.c)
  self.c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,threshold INTEGER)')
  self.c.execute('INSERT INTO users VALUES(42,85)');self.c.commit()
 def tearDown(self):self.c.close()
 def test_tax_and_reward_gates(self):
  for rate in [100,200,300]:self.assertTrue(normalize(token(rate),M)['eligible'])
  for rate in [0,150,400,True,'100']:self.assertFalse(normalize(token(rate),M)['eligible'])
  self.assertFalse(normalize(token(mode='standard'),M)['eligible'])
  data=token();data['token'].pop('transferFee');self.assertFalse(normalize(data,M)['eligible'])
 def test_wrong_network_token_and_scale(self):
  for data in [dict(token(),network='devnet'),token(progress=85),token(progress=float('nan')),token(status='unknown')]:
   with self.assertRaises(FeedError):normalize(data,M)
  with self.assertRaises(FeedError):normalize(token(),'1'*32)
 def test_api_freshness_and_rate_limit(self):
  for age,valid in [(10,True),(301,False),(-61,False)]:
   payload={'meta':{'generatedAt':iso(NOW-age)},'data':{}}
   response=Mock();response.read.return_value=json.dumps(payload).encode()
   response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
   with patch('stonk.urllib.request.urlopen',return_value=response):
    if valid:self.assertEqual(fetch('/tokens',now=NOW)[0],{})
    else:
     with self.assertRaises(FeedError):fetch('/tokens',now=NOW)
  error=HTTPError('redacted',429,'limit',{'Retry-After':'120'},io.BytesIO())
  with patch('stonk.urllib.request.urlopen',side_effect=error):
   with self.assertRaises(RateLimited) as raised:fetch('/tokens',now=NOW)
   self.assertEqual(raised.exception.delay,120)
 def get(self,path):
  if path.startswith('/launches?'):
   return {'launches':[dict(mint=M,createdAt=iso(NOW+1))],'pagination':{'page':1,'totalPages':1}},NOW+2
  return token(),NOW+2
 def test_restart_dedup_and_bonding(self):
  scanner=Scanner(self.c,42,self.get,bonding_enabled=True)
  with patch('stonk.time.time',return_value=NOW):scanner.scan()
  with patch('stonk.time.time',return_value=NOW+2):scanner.scan()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM stonk_outbox').fetchone()[0],2)
  setup(self.c)
  with patch('stonk.time.time',return_value=NOW+70):scanner.scan()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM stonk_outbox').fetchone()[0],2)
  self.assertEqual(self.c.execute('SELECT DISTINCT recipient FROM stonk_outbox').fetchall(),[(42,)])
 def test_production_default_launch_only(self):
  scanner=Scanner(self.c,42,self.get)
  with patch('stonk.time.time',return_value=NOW):scanner.scan()
  with patch('stonk.time.time',return_value=NOW+2):scanner.scan()
  keys=self.c.execute('SELECT event_key FROM stonk_outbox').fetchall()
  self.assertEqual(keys,[('solana:'+M+':launch',)])
 def test_no_historical_launch_flood(self):
  scanner=Scanner(self.c,42,self.get)
  with patch('stonk.time.time',return_value=NOW+5):scanner.scan();scanner.scan()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM stonk_tokens').fetchone()[0],0)
 def test_backlog_and_malformed_do_not_advance_cursor(self):
  scanner=Scanner(self.c,42,self.get)
  with patch('stonk.time.time',return_value=NOW):scanner.scan()
  scanner.get=lambda path:({'launches':[],'pagination':{'page':1,'totalPages':6}},NOW+10)
  with self.assertRaises(FeedError):scanner.scan()
  self.assertEqual(self.c.execute('SELECT since FROM stonk_cursor').fetchone()[0],NOW)
 def test_graduated_does_not_trigger_threshold(self):
  def get(path):return self.get(path) if path.startswith('/launches?') else (token(progress=1,status='graduated'),NOW+2)
  scanner=Scanner(self.c,42,get)
  with patch('stonk.time.time',return_value=NOW):scanner.scan()
  with patch('stonk.time.time',return_value=NOW+2):scanner.scan()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM stonk_outbox').fetchone()[0],0)
  self.assertEqual(self.c.execute('SELECT status FROM stonk_tokens').fetchone()[0],'migrated')
 def test_delivery_isolation_and_layout(self):
  text=body(normalize(token(),M),'New launch',NOW)
  self.assertEqual(text.count('https://'),1)
  self.assertIn('awaiting scale verification',text);self.assertNotIn('Minimum holder',text)
  self.c.execute('INSERT INTO stonk_outbox(recipient,event_key,body,expires) VALUES(?,?,?,?)',(42,'solana:test',text,NOW+100))
  self.c.commit();send=Mock(return_value={'message_id':99})
  with patch('scanner.time.time',return_value=NOW):deliver(self.c,'unused',send,table='stonk_outbox')
  self.assertEqual(self.c.execute('SELECT state FROM stonk_outbox').fetchone()[0],'sent')
  with self.assertRaises(ValueError):deliver(self.c,'unused',send,table='users')
if __name__=='__main__':unittest.main()
