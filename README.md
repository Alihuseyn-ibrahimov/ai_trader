# AI Trader — Automated Crypto Trading System

Rule-based trading strategies for the Binance spot market, protected by a strict risk-management module. The project follows a research-driven process: in-sample / out-of-sample split, comparison against a buy-and-hold baseline, and an explicit GO / NO-GO decision at every phase.

## Key features
- **Freqtrade-based strategies** (`user_data/strategies/`)
- **Risk module** — maximum risk per trade, daily loss limit and kill switch; it can veto the strategy, never the other way round
- **Backtesting and out-of-sample evaluation** tools (`tools/`)
- **Paper trading** mode with a virtual balance — no real money
- **Tests** that catch unauthorised configuration changes

## Safety principles
Spot market only — no leverage, futures or margin. Risk limits can only be changed by a human.

## Tech stack
Python · Freqtrade · Docker Compose · pytest

## Getting started
```bash
docker compose up -d
```
Details: [DEPLOY.md](DEPLOY.md)

---

## Azərbaycan dilində

# AI Trader — kripto üçün avtomatik ticarət sistemi

Binance spot bazarı üçün qayda əsaslı ticarət strategiyaları və sərt risk idarəetmə
modulu. Layihə elmi metodla qurulur: in-sample / out-of-sample bölgüsü, baseline
(buy & hold) ilə müqayisə və hər mərhələdə GO / NO-GO qərarı.

## Əsas imkanlar
- **Freqtrade** əsaslı strategiyalar (`user_data/strategies/`)
- **Risk modulu:** hər əməliyyata maksimum risk, gündəlik itki limiti, kill switch —
  strategiyaya veto hüququ var, əksinə yox
- **Backtest və OOS qiymətləndirmə** alətləri (`tools/`)
- **Paper trading** rejimi (virtual balans, real pul yoxdur)
- Testlər: konfiqurasiyanın icazəsiz dəyişikliklərini tutan testlər daxil

## Təhlükəsizlik prinsipləri
Yalnız spot bazar — leverage, futures, margin yoxdur. Risk limitlərini yalnız insan dəyişir.

## Texnologiyalar
Python · Freqtrade · Docker Compose · pytest

## İşə salma
```bash
docker compose up -d
```
Ətraflı: [DEPLOY.md](DEPLOY.md)
