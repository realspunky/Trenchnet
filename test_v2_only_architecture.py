import json,os,sqlite3,time,unittest
from unittest.mock import patch
from launch_model import record,setup as launch_setup
from v2_intelligence import setup as v2_setup
from v2_qualification import setup as qualify_setup,process,holder_reward_policy

class V2Only(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');launch_setup(self.c);v2_setup(self.c);qualify_setup(self.c)
  self.env=patch.dict(os.environ,{'TRENCHNET_V2_ENABLED':'true','STAGE2_REQUIRED':'false'})
  self.env.start()
 def tearDown(self):self.env.stop();self.c.close()
 def add(self,pad,pct,meta=None):
  return record(self.c,chain='bnb' if pad=='flap' else 'solana',launchpad=pad,address='test'+str(time.time_ns()),name='Test',symbol='T',bonding_progress=pct,metadata=meta or {},now=int(time.time()))
 def test_all_five_enter_tracking_below60(self):
  for pad in ('flap','stonk','pons','embercurve','pumpfun'):
   k=self.add(pad,0.98)
   self.assertEqual(self.c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(k,)).fetchone()[0],'v2_tracking')
   self.assertIsNone(self.c.execute('SELECT crossed_90_at FROM v2_intelligence WHERE event_key=?',(k,)).fetchone()[0])
 def test_qualify_never_uses_v1_assess(self):
  k=self.add('pons',60)
  self.c.execute("UPDATE unified_launches SET pipeline_state='intake' WHERE event_key=?",(k,))
  self.assertEqual(process(self.c,now=int(time.time()))['allowed'],1)
 def test_sub60_cannot_qualify_even_in_bypass(self):
  k=self.add('pons',0.98)
  self.c.execute("UPDATE unified_launches SET pipeline_state='intake' WHERE event_key=?",(k,))
  self.assertEqual(process(self.c,now=int(time.time()))['allowed'],0)
  self.assertEqual(self.c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(k,)).fetchone()[0],'v2_tracking')
 def test_flap_tax_rewards_are_v2_rule(self):
  self.assertTrue(holder_reward_policy('flap',json.dumps({'verified':True,'holder_rewards':True,'buy_tax_bps':200,'sell_tax_bps':200})))
  self.assertFalse(holder_reward_policy('flap',json.dumps({'verified':True,'holder_rewards':True,'buy_tax_bps':200,'sell_tax_bps':100})))
 def test_stonk_nonreward_still_enters_tracker(self):
  k=self.add('stonk',12,{'eligible':False})
  self.assertEqual(self.c.execute('SELECT pipeline_state FROM unified_launches WHERE event_key=?',(k,)).fetchone()[0],'v2_tracking')
if __name__=='__main__':unittest.main()
