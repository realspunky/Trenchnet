import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import bot

def test_beta_menu_hides_commercial_and_status(monkeypatch):
    monkeypatch.setenv("BETA_TESTING_ENABLED","true")
    names={x["command"] for x in bot._public_commands()}
    assert "status" not in names
    assert "plans" not in names
    assert "price" not in names
    assert "pricing" not in names
    assert {"start","alerts","help"}.issubset(names)
