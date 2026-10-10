# AI Trader — VPS-ə yerləşdirmə (Faza 1 paper bot-u)

**Server:** Hetzner VPS `root@91.99.149.63` (açar `~/.ssh/hetzner_tvmonitor`). Server
**tv-monitor və n8n ilə paylaşılır**. Bot onlara toxunmur: ayrıca `/opt/ai_trader` qovluğu,
ayrıca konteyner, yaddaş həddi 1 GB, port açılmır.
**Vəziyyət (2026-10-10):** Ubuntu 26.04, Docker 29.6, Compose v5.3, RAM 3.7 GB (1.9 GB boş),
disk 18 GB boş, 2 nüvə.

Faza 1-də birja açarı **yoxdur** (dry_run). `.env`-də yalnız Telegram token və chat_id var.
Faza 2-dən (real pul) əvvəl bot ayrıca VPS-ə köçürülür (plan §9).

Bütün əmrlər Windows PowerShell-dən, **bir sətirdə** işlədilir. `$K` qısaltmasını
hər yeni PowerShell pəncərəsində bir dəfə təyin et:

```powershell
$K = "$HOME\.ssh\hetzner_tvmonitor"
```

## 1. İlk yerləşdirmə

### 1.1 Serverin şəbəkəsini yoxla (Binance data + Telegram)
```powershell
ssh -i $K root@91.99.149.63 "curl -s -o /dev/null -w 'binance %{http_code}\n' https://data-api.binance.vision/api/v3/ping; curl -s -o /dev/null -w 'telegram %{http_code}\n' https://api.telegram.org; ls /opt; timedatectl | grep 'Time zone'"
```
Gözlənilən: `binance 200`, `telegram 302` (və ya 200), `/opt`-da `ai_trader` yoxdur,
saat qurşağı `Etc/UTC`. UTC deyilsə, cron vaxtını (bölmə 1.6) uyğunlaşdır.

### 1.2 Kodu paketlə və göndər (lokal, `Quantum` qovluğundan)
```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum"
git pull
git archive -o "$env:TEMP\ai_trader.tar" HEAD ai_trader
scp -i $K "$env:TEMP\ai_trader.tar" root@91.99.149.63:/opt/
```
`git archive` yalnız commit olunmuş faylları götürür: `.env`, DB, data, loglar paketə **girmir**.

### 1.3 Serverdə aç
```powershell
ssh -i $K root@91.99.149.63 "tar -xf /opt/ai_trader.tar -C /opt && rm /opt/ai_trader.tar && mkdir -p /opt/ai_trader/user_data/logs && chown -R 1000:1000 /opt/ai_trader/user_data && ls /opt/ai_trader"
```
`chown 1000:1000` vacibdir: konteyner `ftuser` (uid 1000) ilə işləyir. Bu olmasa, bot
DB-ni və logu yarada bilmir.

### 1.4 `.env`-i göndər (yalnız serverdə, icazə 600)
```powershell
scp -i $K "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\ai_trader\.env" root@91.99.149.63:/opt/ai_trader/.env
ssh -i $K root@91.99.149.63 "chmod 600 /opt/ai_trader/.env && ls -l /opt/ai_trader/.env"
```

### 1.5 Ev kompüterindəki botu DAYANDIR, sonra serverdə başlat
Eyni Telegram token ilə iki bot eyni anda işləyə bilməz (Telegram `Conflict` xətası verir).
```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\ai_trader"; docker compose stop paper
ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose up -d paper && sleep 90 && docker compose ps paper && docker compose logs --tail 15 paper"
```
Gözlənilən: `Up`, `state='RUNNING'`, Telegram-a "Status: running" gəlir.

### 1.6 Gündəlik hesabat və aylıq uptime (cron)
```powershell
ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && ./deploy/daily_report.sh && ./deploy/install_cron.sh"
```
- Birinci skript hesabatı dərhal göndərir (yoxlama).
- İkincisi cron-a 2 sətir əlavə edir: hər gün 05:00 UTC (09:00 Bakı) hesabat, ayın 1-i uptime.
- Mövcud cron işlərinə (tv-monitor) toxunmur. Təkrar işlədilsə dublikat yaratmır.
  Çıxışda tam crontab görünür; köhnə sətirlərin yerində olduğunu yoxla.

## 2. Sabitlik həftəsi və T0 (plan Phase 1.4)

1. Deploy-dan sonra **7 gün** gözlə. Gündəlik Telegram hesabatı gəlməlidir.
2. 7 gündən sonra yoxla:
   ```powershell
   ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose logs paper 2>&1 | grep -cE 'ERROR|Traceback'; docker compose exec -T paper python /freqtrade/tools/uptime.py --start <deploy günü>T00:00"
   ```
   Uptime ≥ 98% və izah olunmamış xəta yoxdursa → T0.
3. **T0: təmiz başlanğıc.** Sabitlik həftəsinin əməliyyatları sınağa sayılmır:
   ```powershell
   ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose stop paper && rm -f user_data/tradesv3.paper.sqlite* user_data/paper_equity.csv user_data/uptime_candles.csv && docker compose up -d paper && date -u"
   ```
   Çıxan tarix/saat = **T0**. Claude onu `progress.md`-yə yazır. Sonrakı bütün
   qiymətləndirmələr `--start <T0>` ilə aparılır.

## 3. Yeniləmə (kod dəyişəndə)

Bölmə 1.2 və 1.3-ü təkrarla, sonra:
```powershell
ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose up -d paper && docker compose ps paper"
```
- Paket DB-yə, `.env`-ə və csv fayllarına toxunmur (onlar git-də yoxdur).
- **Diqqət (plan §6):** `user_data/strategies/`, `signals/`, `risk/` və ya
  `config.paper.json`-da ticarətə təsir edən dəyişiklik sınağı **sıfırdan** başladır.
  `tools/` dəyişiklikləri (hesabat, alətlər) sınağa təsir etmir.

## 4. Gündəlik istifadə

| Nə | Əmr |
|---|---|
| Vəziyyət | `ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose ps paper"` |
| Son log | `ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose logs --tail 30 paper"` |
| Risk auditi | `ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose exec -T paper python /freqtrade/tools/risk_audit.py TrendEmaAtr --config /freqtrade/user_data/config.paper.json --db"` |
| Dayandır (plan §5) | `ssh -i $K root@91.99.149.63 "cd /opt/ai_trader && docker compose stop paper"` |

Telegram əmrləri: `/status`, `/balance`, `/profit`, `/daily`, `/whitelist`.

## 5. Bilinən tələlər

- `chown 1000:1000` unudularsa → `unable to open database file`.
- Ev kompüterində və serverdə bot eyni anda işləsə → Telegram `Conflict: terminated by
  other getUpdates request`.
- `.sh` faylları LF olmalıdır. `ai_trader/.gitattributes` bunu təmin edir. CRLF olsa
  `bad interpreter` xətası çıxır.
- `api.coingecko.com` xətaları yalnız USD göstəricisinə aiddir, ticarətə təsir etmir.
