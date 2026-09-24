
from pathlib import Path
ROOT=Path(__file__).parent
def test_no_binance_intelligence_files():
    assert not (ROOT/'binance_web3_v2.py').exists()
    assert not (ROOT/'binance_v2_intelligence.py').exists()
def test_no_active_v1_global_filter_names():
    active=['run.py','v2_tracker.py','v2_qualification.py','alert_router.py','stage2_collectors.py']
    text='\n'.join((ROOT/x).read_text() for x in active)
    assert 'global_filter_decisions' not in text
    assert 'global_filter_health' not in text
    assert 'GLOBAL_FILTER_ENABLED' not in text
    assert 'BETA_TESTING_ENABLED' not in text
    assert 'binance_' not in text.lower()
def test_router_uses_v2_delivery_transport():
    s=(ROOT/'alert_router.py').read_text()
    assert 'from telegram_delivery import deliver' in s
    assert 'from scanner import deliver' not in s
