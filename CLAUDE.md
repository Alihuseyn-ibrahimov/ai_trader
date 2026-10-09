# AI Trader — operativ təlimat

Kripto üçün avtomatik ticarət sistemi: qayda əsaslı strategiyalar + sərt risk
modulu (alt xətt / kill switch). LLM qatı (bazar tədqiqatı, AZ dilində gündəlik
hesabat) sonrakı fazalarda əlavə olunacaq. Əsas: **Freqtrade**.

**Plan:** `.planning/2026-10-08-ai-trader-faza0/task_plan.md`
**Araşdırma və qərarlar:** `.planning/2026-10-08-ai-trader-faza0/findings.md`

## Vəziyyət

- **Faza 0 — Backtest.** Real pul YOXDUR, API açarı YOXDUR, bot daimi işləmir.
- Phase 0.1 (mühit) tamamdır: Freqtrade `2026.9` Docker-də işləyir, `config.json`
  validasiyadan keçir.
- Phase 0.2 ✅: data yükləndi (istifadəçinin kompüterində) və yoxlandı — yalnız
  1 boşluq (2023-03-24 13:00, 1h). Data `user_data/data/` qovluğundadır, git-ə girmir.
- Phase 0.3 ✅: BASELINE `findings.md`-də (OOS 50/50: −15.4% xalis, DD 60%).
- Phase 0.4 ✅: risk modulu + `RiskManagedStrategy` + audit. Smoke backtest
  (91 əməliyyat) auditdən keçdi: maks. planlaşdırılan risk 0.990%, alt xətt pozulmayıb.
- Phase 0.5 ✅: B (`MeanRevRsiBb`) IS-də uğursuz oldu və çıxarıldı (PF 0.46).
  A (`TrendEmaAtr`) bir IS düzəlişindən sonra (trailing söndürüldü): 25 əməliyyat,
  PF 3.17, +39.15%. A **dondurulub** — `user_data/strategies/`, `signals/`, `risk/`
  OOS bitənə qədər dəyişdirilmir.
- Phase 0.6: `tools/oos_eval.py` hazırdır. OOS backtest **bir dəfə** işlədilir.

## Pozulmaz qaydalar

1. **Bazar: Binance spot. Leverage YOXDUR, futures/margin YOXDUR.**
   `trading_mode` həmişə `"spot"` qalır. Bunu dəyişmək yalnız istifadəçinin açıq
   qərarı ilə və ayrıca planla olur.
2. **Risk limitlərini nə LLM, nə strategiya kodu dəyişə bilməz.** Limitlər
   (risk/əməliyyat, gündəlik itki, alt xətt) yalnız konfiqurasiyada və yalnız
   insan tərəfindən dəyişdirilir. Risk modulu strategiyaya veto qoyur, əksinə yox.
3. **Out-of-sample dövrünə (2025-01-01 → 2026-09-30) toxunma.** Strategiya yalnız
   in-sample-da (2023-01-01 → 2024-12-31) qurulur. OOS sona qədər **bir dəfə**
   işlədilir. OOS nəticəsinə baxıb parametr dəyişmək qadağandır, çünki bu
   overfitting-dir və nəticəni dəyərsiz edir.
4. **BASELINE (buy & hold) rəqəmləri `findings.md`-də dəyişdirilmir.**
5. **Faza 0-da LLM ilə backtest edilmir.** Model tarixi bazarı təlim datasından
   "bilir", bu da look-ahead bias yaradır.
6. **Açarlar:** birja açarı yalnız Faza 1+ üçün, yalnız `.env`-də saxlanılır və
   heç vaxt commit olunmur. Açarda **withdrawal bağlı**, IP whitelist, yalnız spot.
   `config.json`-da `key`/`secret` **həmişə boş** qalır. Açarlar mühit dəyişəni
   ilə ötürülür (`FREQTRADE__EXCHANGE__KEY`, `FREQTRADE__EXCHANGE__SECRET`).
7. Nəticəni **mənbədən** təsdiqlə: backtest JSON nəticəsi
   (`user_data/backtest_results/`), pytest çıxışı. Log mətninə görə yox.

## Struktur

```
ai_trader/
├── CLAUDE.md
├── docker-compose.yml        # Freqtrade 2026.9 (versiya sabitdir)
├── tools/                    # analiz skriptləri, konteynerdə /freqtrade/tools (ro)
│   ├── data_quality.py       # boşluq, dublikat, OHLC, sıfır həcm yoxlaması
│   └── baseline.py           # buy & hold: gəlir, xalis gəlir, DD, volatillik
│   ├── risk_audit.py         # backtest nəticəsində risk qaydalarının yoxlanması
│   └── oos_eval.py           # OOS: vergi, MTM drawdown, 6 meyar → GO / NO-GO
├── signals/                  # SAF pandas siqnal məntiqi, konteynerdə /freqtrade/signals (ro)
│   ├── indicators.py         # ema, atr (Wilder), rsi (Wilder), bollinger (ddof=0)
│   ├── tags.py               # enter_tag-da stop məsafəsi: "ad|sd=<məsafə>"
│   └── trend.py              # Strategiya A qaydaları
├── risk/                     # SAF Python risk modulu, konteynerdə /freqtrade/risk (ro)
│   └── limits.py             # RiskConfig, position_size, check_entry, floor/daily
├── tests/                    # pytest, konteynerdə /freqtrade/ai_tests (ro)
└── user_data/
    ├── config.json           # spot, dry_run, BTC/USDT + ETH/USDT, açarsız
    ├── strategies/
    │   ├── risk_managed.py   # BAZA SİNİF — bütün strategiyalar bundan törəməlidir
    │   ├── risk_smoke_test.py# yalnız risk mexanikasının sınağı, strategiya DEYİL
    │   └── trend_ema_atr.py  # A: TrendEmaAtr (4h) — DONDURULUB
    ├── data/                 # tarixi data — git-ə girmir
    ├── backtest_results/     # git-ə girmir
    └── logs/                 # git-ə girmir
```

### Risk arxitekturası

- `config.json` → `ai_risk`: `risk_per_trade` 1%, `daily_loss_limit` 3%,
  `floor_ratio` 0.7 (alt xətt = başlanğıc kapitalın 70%-i), `max_open_trades` 2.
  Naməlum açar (yazı səhvi) → bot başlamır. Sərt tavanlar kodda: risk ≤ 5%, gündəlik ≤ 10%.
- `RiskManagedStrategy`: `custom_stake_amount` (mövqe ölçüsü), `confirm_trade_entry`
  (veto: alt xətt → gündəlik itki → mövqe sayı), `custom_exit` (kill switch),
  `protections` (CooldownPeriod, StoplossGuard, MaxDrawdown).
- **Fail closed:** Freqtrade callback xətasında default-a qayıdır (stake = bütün
  balans, confirm = True). Ona görə hər callback xətanı özü tutur və girişi bloklayır.
  Bu qaydanı pozma.
- **ATR stopu üçün tək mənbə — `enter_tag`:** siqnal `"ad|sd=<məsafə>"` yazır;
  `custom_stake_amount` (mövqe ölçüsü), `custom_stoploss` (stop) və
  `risk_audit.py` (yoxlama) eyni dəyəri oxuyur. Səbəb: Freqtrade-in
  `initial_stop_loss_abs`-u yalnız sabit `stoploss`-dan (backstop) yazılır.
- Strategiya faylı yalnız siqnal modulunu çağırır; qaydalar `signals/`-dadır və
  lokal test olunur. Parametrlər `params` atributundadır və testlə sabitlənib.
- Məhdudiyyətlər (Faza 0 üçün qəbul olunub): kapital reallaşmış PnL ilə ölçülür
  (açıq mövqelərin cari zərəri yalnız kill switch-də nəzərə alınır); gündəlik
  limit də reallaşmış PnL-ə əsaslanır; qiymət stopdan boşluqla keçərsə faktiki
  itki 1%-dən çox ola bilər — `risk_audit.py` bunu "ən pis faktiki itki" kimi göstərir.

## Əmrlər

Bütün Freqtrade əmrləri Docker ilə işləyir (Windows-da Docker Desktop lazımdır;
sistem Python-u işlədilmir). Bash tool-un cari qovluğu qorunmadığı üçün hər
çağırışda `cd` et:

```bash
cd "C:/Users/Alihuseyn Ibrahimov/PycharmProjects/Quantum/ai_trader"

# Versiya
docker compose run --rm freqtrade --version

# Konfiqurasiya validasiyası (exit 0 = keçdi)
docker compose run --rm freqtrade show-config --config user_data/config.json

# Tarixi data (Phase 0.2) — Binance-ə şəbəkə çıxışı lazımdır
docker compose run --rm freqtrade download-data --config user_data/config.json \
  --timerange 20230101-20260930 --timeframes 1h 4h 1d

# Backtest (Phase 0.5+) — komissiya ehtiyatlı: 0.1% + 0.05% slippage
docker compose run --rm freqtrade backtesting --config user_data/config.json \
  --strategy <Ad> --timerange 20230101-20241231 --fee 0.0015
```

### PowerShell (istifadəçinin terminalı)

PowerShell-də sətir davamı `\` **deyil**, backtick-dir (`` ` ``). Ən təhlükəsizi
əmri **bir sətirdə** yazmaqdır. Əmrlər mütləq `ai_trader` qovluğundan işlədilir,
əks halda `no configuration file provided: not found` xətası çıxır.

```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\ai_trader"
docker compose run --rm freqtrade download-data --config user_data/config.json --timerange 20230101-20260930 --timeframes 1h 4h 1d
```

### Risk smoke backtest (yalnız IS dövrü)

```powershell
docker compose run --rm freqtrade backtesting --config user_data/config.json --strategy RiskSmokeTest --timerange 20230101-20230701 --fee 0.0015 --enable-protections --export trades
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/risk_audit.py RiskSmokeTest
```

`--enable-protections` olmadan backtest protections-ı nəzərə almır.

### Strategiya IS backtest-i (Phase 0.5) — OOS-a TOXUNMA

```powershell
docker compose run --rm freqtrade backtesting --config user_data/config.json --strategy TrendEmaAtr --timerange 20230101-20250101 --fee 0.0015 --enable-protections --export trades
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/risk_audit.py TrendEmaAtr
docker compose run --rm freqtrade lookahead-analysis --config user_data/config.json --strategy TrendEmaAtr --timerange 20230101-20250101
```

`startup_candle_count=400` olduğu üçün backtest
datanın əvvəlindən 400 şam sonra başlayır (4h: ~2023-03-08, 1h: ~2023-01-17).

### OOS sınağı (Phase 0.6) — YALNIZ BİR DƏFƏ

```powershell
docker compose run --rm freqtrade backtesting --config user_data/config.json --strategy TrendEmaAtr --timerange 20250101-20260930 --fee 0.0015 --enable-protections --export trades
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/risk_audit.py TrendEmaAtr
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/oos_eval.py TrendEmaAtr --is-profit-factor 3.17
```

Nəticədən sonra strategiyanı dəyişib OOS-u təkrar işlətmək **qadağandır** — bu,
OOS-u IS-ə çevirir və nəticəni dəyərsiz edir.

### Analiz skriptləri və testlər (PowerShell, bir sətir)

```powershell
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/data_quality.py
docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/baseline.py
docker compose run --rm --entrypoint sh freqtrade -c "pip install -q --user pytest && python -m pytest -q -p no:cacheprovider -c /dev/null --rootdir /freqtrade/ai_tests /freqtrade/ai_tests"
```

Testlərdə `-c /dev/null` vacibdir: Freqtrade image-inin öz `pyproject.toml`-u
pytest-ə `--dist` parametri ötürür və testlər işə düşmür.

## Bilinən problemlər

- **`config.json`-a `timeframe` YAZMA.** Freqtrade onu strategiyanın öz
  timeframe-inin üstünə yazır (2026-10-09: 1h smoke strategiya 4h-da işlədi).
  Hər strategiya öz `timeframe`-ini təyin edir. `tests/test_config.py` bunu yoxlayır.

- **Azərbaycandan (istifadəçinin şəbəkəsi) `api.binance.com` bloklanıb**: TLS
  handshake zamanı `ConnectionResetError`. Açıq olanlar: `data-api.binance.vision`
  (Binance-in rəsmi publik market-data endpoint-i) və `data.binance.vision`
  (tarixi arxiv). Ona görə `config.json`-da `exchange.ccxt_config`:
  - `urls.api.public` → `https://data-api.binance.vision/api/v3`
  - `options.fetchMarkets.types` → `["spot"]` (futures endpoint-ləri bağlıdır və
    lazım deyil)
  Bu yalnız **publik data** üçündür. Faza 2-də real ticarət üçün (açarlı, private
  API) bu yol işləməyəcək. Onda bot Binance-ə çıxışı olan serverdə (VPS) işləməlidir.

- `no configuration file provided: not found` → əmr `ai_trader/` qovluğundan
  kənarda işlədilib (`docker-compose.yml` cari qovluqda olmalıdır).
- PowerShell: `Missing expression after unary operator '--'` → `\` ilə sətir
  bölünüb. Əmri bir sətirdə yaz.

- `config.json`-da `api_server` bloku yarımçıq yazılsa validasiya düşür
  (`'listen_ip_address' is a required property`). Faza 0-da `api_server`
  ümumiyyətlə yoxdur, Faza 1-də tam blok ilə əlavə olunacaq.
- Claude Code bulud mühitində (claude.ai/code) `api.binance.com` şəbəkə
  siyasətinə görə bloklana bilər (proxy 403). Data yükləmək üçün ya mühitin
  Allowed domains siyahısına `api.binance.com` və `data.binance.vision`
  (Binance-in tarixi data arxivi) əlavə et, ya da əmri lokal
  kompüterdə və ya VPS-də işlət.
