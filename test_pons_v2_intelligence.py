from pons_v2_intelligence import _holder_stats

def test_holder_concentration_and_dev():
    hs=_holder_stats([
      {'address':{'hash':'0x'+'1'*40},'value':'50'},
      {'address':{'hash':'0x'+'2'*40},'value':'30'},
      {'address':{'hash':'0x'+'3'*40},'value':'20'},
    ],'0x'+'2'*40)
    assert hs['count']==3
    assert hs['top10Pct']==100
    assert hs['devPct']==30
