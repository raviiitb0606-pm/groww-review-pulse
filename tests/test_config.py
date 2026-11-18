from pulse.config import load_config


def test_default_config_loads():
    cfg = load_config()
    assert cfg.app.play_package == "com.nextbillion.groww"
    assert cfg.themes.max == 5
    assert cfg.note.max_words == 250


def test_mcp_command_env_overrides_config(monkeypatch):
    monkeypatch.setenv("PULSE_MCP_COMMAND", "")
    cfg = load_config()
    assert cfg.mcp.command == ""
    assert cfg.mcp.url  # the hosted server is used instead


def test_mcp_command_from_config_without_env(monkeypatch):
    monkeypatch.delenv("PULSE_MCP_COMMAND", raising=False)
    assert load_config().mcp.command
