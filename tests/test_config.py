"""config.json-un pozulmaz qaydaları (CLAUDE.md) — reqressiyaya qarşı."""

import json
from pathlib import Path

from risk import RiskConfig

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "user_data" / "config.json").read_text())


def test_spot_only_no_leverage():
    assert CONFIG["trading_mode"] == "spot"
    assert CONFIG.get("margin_mode", "") == ""


def test_dry_run():
    assert CONFIG["dry_run"] is True


def test_no_keys_in_config():
    assert CONFIG["exchange"]["key"] == ""
    assert CONFIG["exchange"]["secret"] == ""


def test_no_global_timeframe():
    # config-dəki timeframe hər strategiyanın öz timeframe-ini səssizcə əzir
    # (2026-10-09 smoke backtest: 1h strategiya 4h-da işlədi)
    assert "timeframe" not in CONFIG


def test_risk_block_valid_and_consistent():
    risk = RiskConfig.from_dict(CONFIG["ai_risk"])
    assert risk.max_open_trades == CONFIG["max_open_trades"]
