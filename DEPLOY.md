# AI Trader — VPS-ə yerləşdirmə (Faza 1 paper bot-u)

**Server:** Hetzner VPS `$S` (SSH açarı ilə). Server
**tv-monitor və n8n ilə paylaşılır**. Bot onlara toxunmur: ayrıca `/opt/ai_trader` qovluğu,
ayrıca konteyner, yaddaş həddi 1 GB, port açılmır.
**Vəziyyət (2026-10-10):** Ubuntu 26.04, Docker 29.6, Compose v5.3, RAM 3.7 GB (1.9 GB boş),
disk 18 GB boş, 2 nüvə, saat qurşağı **Asia/Baku** (binance 200, telegram 302).

Faza 1-də birja açarı **yoxdur** (dry_run). `.env`-də yalnız Telegram token və chat_id var.
Faza 2-dən (real pul) əvvəl bot ayrıca VPS-ə köçürülür (plan §9).

Bütün əmrlər Windows PowerShell-dən, **bir sətirdə** işlədilir. `$K` və `$S` qısaltmalarını
hər yeni PowerShell pəncərəsində bir dəfə təyin et:

```powershell
$K = "$HOME\.ssh\<your_key>"
$S = "root@<server_ip>"
```

## 1. İlk yerləşdirmə

### 1.1 Serverin şəbəkəsini yoxla (Binance data + Telegram)
```powershell
ssh -i $K $S "curl -s -o /dev/null -w 'binance %{http_code}\n' https://data-api.binance.vision/api/v3/ping; curl -s -o /dev/null -w 'telegram %{http_code}\n' https://api.telegram.org; ls /opt; timedatectl | grep 'Time zone'"
```
Gözlənilən: `binance 200`, `telegram 302` (və ya 200), `/opt`-da `ai_trader` yoxdur.
Saat qurşağı fərq etmir: `install_cron.sh` vaxtları UTC-dən yerli saata özü çevirir.

### 1.2 Kodu paketlə və göndər (lokal, `Quantum` qovluğundan)
```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum"
git pull
git archive -o "$env:TEMP\ai_trader.tar" HEAD ai_trader
scp -i $K "$env:TEMP\ai_trader.tar" $S:/opt/
```
`git archive` yalnız commit olunmuş faylları götürür: `.env`, DB, data, loglar paketə **girmir**.

### 1.3 Serverdə aç
```powershell
ssh -i $K $S "tar -xf /opt/ai_trader.tar -C /opt && rm /opt/ai_trader.tar && mkdir -p /opt/ai_trader/user_data/logs && chown -R 1000:1000 /opt/ai_trader/user_data && ls /opt/ai_trader"
```
`chown 1000:1000` vacibdir: konteyner `ftuser` (uid 1000) ilə işləyir. Bu olmasa, bot
DB-ni və logu yarada bilmir.

### 1.4 `.env`-i göndər (yalnız serverdə, icazə 600)
```powershell
scp -i $K "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\ai_trader\.env" $S:/opt/ai_trader/.env
ssh -i $K $S "chmod 600 /opt/ai_trader/.env && ls -l /opt/ai_trader/.env"
```

### 1.5 Ev kompüterindəki botu DAYANDIR, sonra serverdə başlat
Eyni Telegram token ilə iki bot eyni anda işləyə bilməz (Telegram `Conflict` xətası verir).
```powershell
cd "C:\Users\Alihuseyn Ibrahimov\PycharmProjects\Quantum\ai_trader"; docker compose stop paper
ssh -i $K $S "cd /opt/ai_trader && docker compose up -d paper && sleep 90 && docker compose ps paper && docker compose logs --tail 15 paper"
```
Gözlənilən: `Up`, `state='RUNNING'`, Telegram-a "Status: running" gəlir.

### 1.6 Gündəlik hesabat və aylıq uptime (cron)
```powershell
ssh -i $K $S "cd /opt/ai_trader && ./deploy/daily_report.sh && ./deploy/install_cron.sh"
```
- Birinci skript hesabatı dərhal göndərir (yoxlama).
- İkincisi cron-a 2 sətir əlavə edir: hər gün 05:00 UTC (= 09:00 Bakı) hesabat, ayın 1-i uptime.
  Cron serverin yerli saatı ilə işləyir; Asia/Baku-da sətir `0 9 * * *` olacaq.
- Mövcud cron işlərinə (tv-monitor) toxunmur. Təkrar işlədilsə dublikat yaratmır.
  Çıxışda tam crontab görünür; köhnə sətirlərin yerində olduğunu yoxla.

### 1.7 AI bazar icmalı (Groq, 09:05 Bakı)
1. Lokal `ai_trader\.env`-ə `GROQ_API_KEY=...` sətrini əlavə et (`notepad .env`), sonra
   bölmə 1.4 ilə `.env`-i yenidən göndər (icazə 600).
2. Paketi yenilə (bölmə 1.2–1.3), sonra əl ilə sına və cron-u yenilə:
   ```powershell
   ssh -i $K $S "cd /opt/ai_trader && ./deploy/market_brief.sh && ./deploy/install_cron.sh"
   ```
- Açar bot konteynerinin mühitinə düşmür: `market_brief.sh` onu `.env`-dən oxuyub yalnız
  icmal prosesinə ötürür, ona görə bot-u restart etmək lazım deyil.
- LLM alınmasa (açar yoxdur, Groq xətası, uydurma rəqəm), faktlar cədvəli yenə gəlir və
  "⚠️ AI icmalı bu gün alınmadı (səbəb)" yazılır.

### 1.8 Agentlər — analiz + KÖLGƏ qərar (LangGraph + LangSmith, 09:10 Bakı)
Plan: `.planning/2026-10-12-ai-trader-agents/task_plan.md`. Qərarlar **icra olunmur**.
Ayrıca konteyner (`agents` servisi, profile — `up -d` onu başlatmır); paper bot restart olunmur.
1. smith.langchain.com → Settings → API Keys → açar yarat. Lokal `ai_trader\.env`-ə
   `LANGSMITH_API_KEY=...` əlavə et və bölmə 1.4 ilə göndər. **Açarı heç kimə (çata da) göndərmə.**
2. Paketi yenilə (bölmə 1.2–1.3). `paper` konteynerinə toxunma (sabitlik həftəsi).
3. Imici qur, `shadow` qovluğunu hazırla, əl ilə bir dəfə sına, cron-u yenilə:
   ```powershell
   ssh -i $K $S "cd /opt/ai_trader && docker compose build agents && mkdir -p user_data/shadow && chown 1000:1000 user_data/shadow && ./deploy/agents_shadow.sh && ./deploy/install_cron.sh"
   ```
4. Yoxla (mənbədən): Telegram-da "🕶 KÖLGƏ — icra olunmur" mesajı; serverdə
   `tail -3 user_data/shadow/decisions.csv`; LangSmith-də `ai-trader-agents` layihəsində 4 LLM çağırışı.
- Eyni Bakı günündə ikinci işləmə bloklanır (kölgə iki dəfə alış etməsin). Təkrar sınaq:
  `./deploy/agents_shadow.sh --force` (DİQQƏT: kölgə portfelə təsir edir — yalnız sınaq günü).
- Agent uğursuz olsa mesajda "UĞURSUZ" görünür; supervayzer uğursuz olsa hamısı GÖZLƏ.
- Prompt dəyişsə (`agents/prompts.py`, `PROMPT_VERSION`) kölgə sınağı sıfırdan başlayır.
- Aylıq müqayisə (A.7, ayın 1-i 09:35): `./deploy/monthly_compare.sh` — kölgə ↔ TrendEmaAtr,
  eyni dövr, eyni düsturlar. Əl ilə baxış (göndərmədən): `./deploy/monthly_compare.sh --start 2026-10-19`.
  Mənbələr: `user_data/shadow/equity.csv`, `shadow/book.json`, `paper_equity.csv`, paper DB.
  **T0 sıfırlamasında** `paper_equity.csv` silinir — müqayisə avtomatik T0-dan başlayır.

## 2. Sabitlik həftəsi və T0 (plan Phase 1.4)

1. Deploy-dan sonra **7 gün** gözlə. Gündəlik Telegram hesabatı gəlməlidir.
2. 7 gündən sonra yoxla:
   ```powershell
   ssh -i $K $S "cd /opt/ai_trader && docker compose logs paper 2>&1 | grep -cE 'ERROR|Traceback'; docker compose exec -T paper python /freqtrade/tools/uptime.py --start <deploy günü>T00:00"
   ```
   Uptime ≥ 98% və izah olunmamış xəta yoxdursa → T0.
3. **T0: təmiz başlanğıc.** Sabitlik həftəsinin əməliyyatları sınağa sayılmır:
   ```powershell
   ssh -i $K $S "cd /opt/ai_trader && docker compose stop paper && rm -f user_data/tradesv3.paper.sqlite* user_data/paper_equity.csv user_data/uptime_candles.csv && docker compose up -d paper && date -u"
   ```
   Çıxan tarix/saat = **T0**. Claude onu `progress.md`-yə yazır. Sonrakı bütün
   qiymətləndirmələr `--start <T0>` ilə aparılır.

## 3. Yeniləmə (kod dəyişəndə)

Bölmə 1.2 və 1.3-ü təkrarla, sonra:
```powershell
ssh -i $K $S "cd /opt/ai_trader && docker compose up -d paper && docker compose ps paper"
```
- Paket DB-yə, `.env`-ə və csv fayllarına toxunmur (onlar git-də yoxdur).
- **Diqqət (plan §6):** `user_data/strategies/`, `signals/`, `risk/` və ya
  `config.paper.json`-da ticarətə təsir edən dəyişiklik sınağı **sıfırdan** başladır.
  `tools/` dəyişiklikləri (hesabat, alətlər) sınağa təsir etmir.

## 4. Gündəlik istifadə

| Nə | Əmr |
|---|---|
| Vəziyyət | `ssh -i $K $S "cd /opt/ai_trader && docker compose ps paper"` |
| Son log | `ssh -i $K $S "cd /opt/ai_trader && docker compose logs --tail 30 paper"` |
| Risk auditi | `ssh -i $K $S "cd /opt/ai_trader && docker compose exec -T paper python /freqtrade/tools/risk_audit.py TrendEmaAtr --config /freqtrade/user_data/config.paper.json --db"` |
| Panel (HTML, Telegram faylı) | hər gün 09:15 avtomatik; əl ilə: `ssh -i $K $S "cd /opt/ai_trader && ./deploy/daily_panel.sh"` |
| Kölgə qərarları | `ssh -i $K $S "cd /opt/ai_trader && tail -14 user_data/shadow/decisions.csv && tail -5 user_data/logs/cron_agents.log"` |
| Dayandır (plan §5) | `ssh -i $K $S "cd /opt/ai_trader && docker compose stop paper"` |

Telegram əmrləri: `/status`, `/balance`, `/profit`, `/daily`, `/whitelist`.

## 5. Bilinən tələlər

- `chown 1000:1000` unudularsa → `unable to open database file`.
- Ev kompüterində və serverdə bot eyni anda işləsə → Telegram `Conflict: terminated by
  other getUpdates request`.
- `.sh` faylları LF olmalıdır. `ai_trader/.gitattributes` bunu təmin edir. CRLF olsa
  `bad interpreter` xətası çıxır.
- `api.coingecko.com` xətaları yalnız USD göstəricisinə aiddir, ticarətə təsir etmir.
- Ubuntu 26.04-də `date` = uutils (0.8.0): `date -d '05:00 UTC'` saat qurşağını nəzərə almır
  (05:00 qaytarır). Skriptlərdə vaxt çevirmək üçün yalnız `date +%z` istifadə et.
