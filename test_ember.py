import sqlite3
from ember import Scanner,setup,normalize

def test_normalize():
    x=normalize({'mint':'A'*32,'name':'Cat','symbol':'CAT','pairSymbol':'SOL','bondingProgress':.25})
    assert x['progress']==25

def test_first_snapshot_no_flood_then_new_alert():
    c=sqlite3.connect(':memory:');setup(c)
    payloads=[{'markets':[{'mint':'A'*32,'name':'A','symbol':'A'}]}, {'markets':[{'mint':'A'*32,'name':'A','symbol':'A'},{'mint':'B'*32,'name':'B','symbol':'B'}]}]
    s=Scanner(c,1,get=lambda:payloads.pop(0));s.scan()
    assert c.execute('select count(*) from ember_outbox').fetchone()[0]==0
    s.scan();assert c.execute('select count(*) from ember_outbox').fetchone()[0]==1
