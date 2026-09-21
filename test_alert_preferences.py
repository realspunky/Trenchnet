import sqlite3
from alert_preferences import setup,get,toggle,set_all

def test_defaults_all_enabled_and_toggle():
 c=sqlite3.connect(':memory:'); setup(c)
 p=get(c,7); assert all(p.values())
 assert toggle(c,7,'pumpfun') is False
 assert get(c,7)['pumpfun'] is False

def test_all_switch():
 c=sqlite3.connect(':memory:'); setup(c); set_all(c,1,False); assert not any(get(c,1).values()); set_all(c,1,True); assert all(get(c,1).values())
