"""docker-compose.yml — Faza 1 paper servisinin qaydaları."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "docker-compose.yml").exists():
    # Freqtrade konteynerində yalnız tests/ mount olunur — bu host səviyyəli testdir
    pytest.skip("docker-compose.yml yoxdur (konteyner)", allow_module_level=True)
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
PAPER = COMPOSE["services"]["paper"]


def test_same_pinned_image_as_backtest():
    assert PAPER["image"] == COMPOSE["services"]["freqtrade"]["image"] == "freqtradeorg/freqtrade:2026.9"


def test_runs_paper_config_with_logfile():
    cmd = PAPER["command"]
    assert cmd[0] == "trade"
    assert cmd[cmd.index("--config") + 1] == "user_data/config.paper.json"
    assert cmd[cmd.index("--logfile") + 1] == "user_data/logs/paper.log"  # uptime.py bunu oxuyur


def test_restarts_and_exposes_no_ports():
    assert PAPER["restart"] == "unless-stopped"
    assert "ports" not in PAPER  # api_server yoxdur, xaricə heç nə açılmır


def test_secrets_only_from_env_file():
    env = PAPER["env_file"]
    assert env == [{"path": ".env", "required": True}]
    assert "environment" not in PAPER  # token/chat_id compose faylına yazılmır


def test_code_mounted_read_only():
    vols = PAPER["volumes"]
    for d in ("tools", "risk", "signals"):
        assert any(v.startswith(f"./{d}:") and v.endswith(":ro") for v in vols), d


def test_env_example_has_names_but_no_values():
    lines = [l for l in (ROOT / ".env.example").read_text().splitlines() if l and not l.startswith("#")]
    keys = {l.split("=", 1)[0]: l.split("=", 1)[1] for l in lines}
    assert set(keys) == {"FREQTRADE__TELEGRAM__TOKEN", "FREQTRADE__TELEGRAM__CHAT_ID"}
    assert all(v == "" for v in keys.values())
