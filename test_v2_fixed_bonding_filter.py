import os, sqlite3
from v2_intelligence import bonding_gate, V2_MIN_BONDING
from bot import reply, _public_commands

def test_fixed_60_gate():
    assert V2_MIN_BONDING == 60.0
    assert bonding_gate(59.999, False) is None
    assert bonding_gate(60, False) == 60.0
    assert bonding_gate(.60, False) is None

def test_threshold_command_removed(monkeypatch):
    c=sqlite3.connect(':memory:')
    c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 80)')
    monkeypatch.setenv('BETA_TESTING_ENABLED','true')
    out=reply(c,1,'/threshold 95')
    assert 'threshold saved' not in out.lower()
    assert '/threshold' not in reply(c,1,'/help')
    assert 'threshold' not in {x['command'] for x in _public_commands()}
