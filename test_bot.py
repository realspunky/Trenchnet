import sqlite3
import unittest
from bot import qualifies, advance_due, reply
from access import setup

class Rules(unittest.TestCase):
    def setUp(self):
        self.token = dict(verified=True, launchpad='flap', chain='bnb', total_tax_bps=300,
                          holder_rewards=True, migrated=False, bonding_percent=85)
    def test_filters_fail_closed(self):
        self.assertTrue(qualifies(self.token))
        for key, value in [('verified', False), ('total_tax_bps', 500), ('holder_rewards', False), ('chain', 'unknown')]:
            self.assertFalse(qualifies(dict(self.token, **{key: value})))
        self.assertFalse(qualifies({}))
    def test_progress(self):
        self.assertTrue(advance_due(self.token, 80))
        self.assertFalse(advance_due(self.token, 90))
        self.assertFalse(advance_due(dict(self.token, migrated=True), 80))
        self.assertFalse(advance_due(dict(self.token, bonding_percent=100), 80))
    def test_settings_isolation(self):
        c = sqlite3.connect(':memory:')
        setup(c)
        c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, threshold INTEGER DEFAULT 80)')
        self.assertNotIn('threshold saved', reply(c, 1, '/threshold 95').lower())
        self.assertNotIn('/threshold', reply(c, 1, '/help'))
        reply(c, 1, '/threshold 96')
        self.assertIn('fixed at 60%', reply(c, 1, '/status'))
        reply(c, 1, '/delete_me')
        self.assertIsNone(c.execute('SELECT * FROM users WHERE id=1').fetchone())

if __name__ == '__main__':
    unittest.main()
