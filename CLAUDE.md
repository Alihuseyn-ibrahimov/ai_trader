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
- Növbəti: Phase 0.2 — BTC/USDT, ETH/USDT tarixi datasının yüklənməsi.

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
└── user_data/
    ├── config.json           # spot, dry_run, BTC/USDT + ETH/USDT, açarsız
    ├── strategies/           # strategiyalar (Phase 0.5)
    ├── data/                 # tarixi data — git-ə girmir
    ├── backtest_results/     # git-ə girmir
    └── logs/                 # git-ə girmir
```

`risk/` (saf Python risk modulu + pytest) Phase 0.4-də əlavə olunacaq.

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

## Bilinən problemlər

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
