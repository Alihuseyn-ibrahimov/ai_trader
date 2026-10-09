"""config.paper.json — Faza 1 paper trading konfiqurasiyasının pozulmaz qaydaları.

Təsdiqlənmiş plan: .planning/2026-10-09-ai-trader-faza1-paper/task_plan.md §2, §10.
Backtest konfiqurasiyasından (config.json) yalnız icazə verilmiş açarlar fərqlənə bilər.
"""

import json
from pathlib import Path

import pytest

from risk import RiskConfig

USER_DATA = Path(__file__).resolve().parent.parent / "user_data"
PAPER = json.loads((USER_DATA / "config.paper.json").read_text())
BACKTEST = json.loads((USER_DATA / "config.json").read_text())

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"]

# config.json-dan fərqlənməsinə icazə verilən üst səviyyə açarlar
ALLOWED_TOP_DIFF = {
    "bot_name", "dry_run_wallet", "available_capital", "telegram", "initial_state", "db_url", "strategy",
    "ai_risk", "exchange",
}
# exchange daxilində icazə verilən fərqlər
ALLOWED_EXCHANGE_DIFF = {"pair_whitelist", "enable_ws"}


def test_dry_run_spot_no_leverage():
    assert PAPER["dry_run"] is True
    assert PAPER["trading_mode"] == "spot"
    assert PAPER.get("margin_mode", "") == ""


def test_no_keys_or_secrets_in_file():
    assert PAPER["exchange"]["key"] == ""
    assert PAPER["exchange"]["secret"] == ""
    # Telegram token və chat_id yalnız serverdəki .env-dən gəlir
    # (FREQTRADE__TELEGRAM__TOKEN, FREQTRADE__TELEGRAM__CHAT_ID)
    assert PAPER["telegram"]["token"] == ""
    assert PAPER["telegram"]["chat_id"] == ""
    assert PAPER["telegram"]["enabled"] is True


def test_no_api_server():
    assert "api_server" not in PAPER


def test_no_global_timeframe():
    assert "timeframe" not in PAPER


def test_strategy_fixed():
    assert PAPER["strategy"] == "TrendEmaAtr"


def test_virtual_capital_10000():
    assert PAPER["dry_run_wallet"] == 10000
    # Olmasa Freqtrade başlanğıc kapitalı dry_run_wallet × tradable_balance_ratio (0.99)
    # = 9900 götürür → alt xətt 6930 olur, təsdiqlənmiş 7000 yox (2026-10-09, /balance)
    assert PAPER["available_capital"] == PAPER["dry_run_wallet"]
    assert PAPER["stake_currency"] == "USDT"


def test_pairs_fixed_by_plan():
    assert PAPER["exchange"]["pair_whitelist"] == PAIRS
    assert PAPER["pairlists"] == [{"method": "StaticPairList"}]


def test_risk_block():
    risk = RiskConfig.from_dict(PAPER["ai_risk"])
    assert risk.risk_per_trade == pytest.approx(0.005)
    assert risk.daily_loss_limit == pytest.approx(0.03)
    assert risk.floor_ratio == pytest.approx(0.7)
    assert risk.max_open_trades == 2
    assert PAPER["max_open_trades"] == 2


def test_websocket_disabled():
    # Binance websocket (stream.binance.com) istifadəçinin şəbəkəsində bağlı ola bilər;
    # şamlar data-api.binance.vision REST ilə alınır
    assert PAPER["exchange"]["enable_ws"] is False


def test_separate_database():
    assert PAPER["db_url"] == "sqlite:////freqtrade/user_data/tradesv3.paper.sqlite"


def test_starts_running():
    assert PAPER["initial_state"] == "running"


def test_only_allowed_differences_from_backtest_config():
    diff = {k for k in PAPER.keys() | BACKTEST.keys() if PAPER.get(k) != BACKTEST.get(k)}
    assert diff <= ALLOWED_TOP_DIFF, diff - ALLOWED_TOP_DIFF
    ex_p, ex_b = PAPER["exchange"], BACKTEST["exchange"]
    ex_diff = {k for k in ex_p.keys() | ex_b.keys() if ex_p.get(k) != ex_b.get(k)}
    assert ex_diff <= ALLOWED_EXCHANGE_DIFF, ex_diff - ALLOWED_EXCHANGE_DIFF
    # ai_risk-də yalnız risk_per_trade fərqlənir
    risk_diff = {
        k for k in PAPER["ai_risk"].keys() | BACKTEST["ai_risk"].keys()
        if PAPER["ai_risk"].get(k) != BACKTEST["ai_risk"].get(k)
    }
    assert risk_diff == {"risk_per_trade"}
