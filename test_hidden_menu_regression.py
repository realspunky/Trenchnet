from pathlib import Path
TEXT=(Path(__file__).parent/"bot.py").read_text()
def test_no_admin_status_menu_scope():
    assert "commands + [{'command':'status'" not in TEXT
    assert "deleteMyCommands" in TEXT
def test_status_command_still_exists_for_admin():
    assert "if cmd == '/status':" in TEXT
