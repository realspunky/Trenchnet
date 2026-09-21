import sqlite3
from launch_filter import assess

def db(): return sqlite3.connect(':memory:')

def test_duplicate_name_different_contract_is_suppressed():
    c=db()
    a=assess(c,chain='robinhood',launchpad='pons',address='0x1',creator='0xa',name='DOG Coin',symbol='DOG',now=1000)
    b=assess(c,chain='robinhood',launchpad='pons',address='0x2',creator='0xb',name='dog-coin',symbol='dog',now=1010)
    assert a['allow'] is True
    assert b['allow'] is False and b['reason']=='duplicate_name_cluster'

def test_same_name_outside_window_is_allowed():
    c=db()
    assess(c,chain='robinhood',launchpad='pons',address='0x1',creator='0xa',name='DOG',symbol='DOG',now=1000,duplicate_window=60)
    b=assess(c,chain='robinhood',launchpad='pons',address='0x2',creator='0xb',name='DOG',symbol='DOG',now=1100,duplicate_window=60)
    assert b['allow'] is True

def test_creator_multi_launch_suppresses_after_limit():
    c=db()
    for i in range(3):
        assert assess(c,chain='robinhood',launchpad='pons',address=f'0x{i}',creator='0xa',name=f'T{i}',symbol=f'T{i}',now=1000+i,creator_limit=3)['allow']
    d=assess(c,chain='robinhood',launchpad='pons',address='0x4',creator='0xa',name='T4',symbol='T4',now=1004,creator_limit=3)
    assert not d['allow'] and d['reason']=='creator_multi_launch'
