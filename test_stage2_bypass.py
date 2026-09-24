import os, sqlite3
from v2_intelligence import setup, gate, stage2_required, render, mark_progress

def conn():
    c=sqlite3.connect(':memory:')
    setup(c)
    return c

def test_bypass_keeps_bonding_gate(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
    monkeypatch.setenv('STAGE2_REQUIRED','false')
    c=conn()
    assert stage2_required() is False
    assert gate(c,'x',59.99,False)==(False,'bonding_below_60')
    assert gate(c,'x',60.0,False)==(True,'stage2_bypassed')

def test_bypass_render_is_explicit(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
    monkeypatch.setenv('STAGE2_REQUIRED','false')
    c=conn()
    lines=render(c,'x')
    assert any('BYPASSED' in x for x in lines)
    assert any('60%' in x for x in lines)

def test_stage2_true_still_blocks_without_intel(monkeypatch):
    monkeypatch.setenv('TRENCHNET_V2_ENABLED','true')
    monkeypatch.setenv('STAGE2_REQUIRED','true')
    c=conn()
    assert gate(c,'x',60.0,False)==(False,'intelligence_incomplete')
