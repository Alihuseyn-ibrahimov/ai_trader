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
