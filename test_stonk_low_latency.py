from pathlib import Path
TEXT=(Path(__file__).parent/"stonk.py").read_text()
def test_low_latency_defaults():
    assert "STONK_POLL_SECONDS','8'" in TEXT
    assert "STONK_FRESH_BATCH','40'" in TEXT
    assert "STONK_MAINTENANCE_BATCH','4'" in TEXT
    assert "created>=?" in TEXT
def test_metadata_gate_preserved():
    assert "Token metadata name unavailable" in TEXT
    assert "if s['eligible']:" in TEXT
