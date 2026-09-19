import sqlite3
import unittest
from access import setup,start_trial,state,reserve_alert,grant_verified_payment,DAY

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:'); setup(self.c)
    def test_expiry_and_no_repeat(self):
        self.assertTrue(start_trial(self.c,1,100))
        self.assertFalse(start_trial(self.c,1,200))
        self.assertEqual(state(self.c,1,100+5*DAY)[0],'expired')
        self.assertFalse(reserve_alert(self.c,1,'launch',100+5*DAY))
    def test_daily_cap_dedup_and_independent_users(self):
        start_trial(self.c,1,100); start_trial(self.c,2,100)
        self.assertTrue(reserve_alert(self.c,1,'a:launch',100))
        self.assertFalse(reserve_alert(self.c,1,'a:bonding',101))
        self.assertTrue(reserve_alert(self.c,2,'a:launch',101))
        self.assertFalse(reserve_alert(self.c,1,'a:launch',100+DAY))
        self.assertTrue(reserve_alert(self.c,1,'a:bonding',100+DAY))
    def test_empty_days_do_not_extend_trial(self):
        start_trial(self.c,1,100)
        self.assertEqual(state(self.c,1,100+5*DAY)[0],'expired')
    def test_paid_unlimited_replay_and_renewal(self):
        self.assertTrue(grant_verified_payment(self.c,1,'monthly','charge1',100))
        end=state(self.c,1,100)[1]
        self.assertFalse(grant_verified_payment(self.c,2,'lifetime','charge1',100))
        self.assertTrue(reserve_alert(self.c,1,'a',101))
        self.assertTrue(reserve_alert(self.c,1,'b',101))
        self.assertEqual(state(self.c,1,end)[0],'expired')
        grant_verified_payment(self.c,1,'yearly','charge2',102)
        self.assertGreater(state(self.c,1,102)[1],end)
    def test_lifetime(self):
        grant_verified_payment(self.c,1,'lifetime','charge',100)
        self.assertEqual(state(self.c,1,10**10)[0],'lifetime')
    def test_commands_and_delete_preserve_trial_history(self):
        import os
        from bot import reply
        from unittest.mock import patch
        self.c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,threshold INTEGER DEFAULT 80)')
        with patch.dict(os.environ, {'TRIALS_ENABLED':'false'}):
            self.assertIn('not started',reply(self.c,1,'/trial'))
            self.assertEqual(state(self.c,1)[0],'inactive')
        with patch.dict(os.environ, {'TRIALS_ENABLED':'true'}):
            reply(self.c,1,'/trial'); reply(self.c,1,'/delete_me')
            self.assertIn('already',reply(self.c,1,'/trial'))
