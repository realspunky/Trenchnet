
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_legacy_total_tax_not_primary_in_bot():
    p = ROOT / "bot.py"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        # Any legacy fallback must prefer token_tax_bps.
        for line in text.splitlines():
            if 'total_tax_bps' in line and '.get(' in line:
                assert 'token_tax_bps' in line

def test_flap_policy_contains_supported_tax_rates_and_dividend():
    p = ROOT / "flap.py"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        assert "dividend" in text.lower()
        assert any(x in text for x in ("100", "200", "300"))
