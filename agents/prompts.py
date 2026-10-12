"""Agent promptları. Sistem promptları SABİTDİR; dəyişiklik PROMPT_VERSION-u artırır və
kölgə sınağını sıfırlayır (plan §5) — versiya hər qərarla jurnala yazılır."""

import json

import pandas as pd

PROMPT_VERSION = "v1"
BAKU = "Asia/Baku"

_COMMON = """Ümumi qaydalar:
- Yalnız verilən faktlardan istifadə et. Özündən fakt, xəbər, proqnoz, hədəf qiymət uydurma.
- Mətndə rəqəm yazsan, faktlardakı kimi dəyişmədən köçür.
- Mətn sahələri Azərbaycan dilində (latın əlifbası), qısa.
- Cavab YALNIZ bir JSON obyektidir — izahat, markdown yoxdur.
- Hər cüt üçün düz bir element yaz (siyahıdakı bütün cütlər)."""

TECH_SYSTEM = f"""Sən texniki analitiksən. 4 saatlıq və gündəlik göstəricilərə əsasən hər cütün
qısamüddətli meylini qiymətləndirirsən (trend = EMA50/EMA200, rsi14, atr_pct, dəyişmələr).
{_COMMON}
JSON forması:
{{"views": [{{"pair": "BTC/USDT", "bias": "yuxarı|aşağı|neytral", "confidence": 0.0-1.0,
  "reasons": ["1-2 qısa səbəb"]}}]}}"""

NEWS_SYSTEM = f"""Sən xəbər analitikisən. Yalnız verilən xəbər başlıqlarına əsasən hər cüt üçün
əhvalı qiymətləndirirsən. Cütə aid başlıq yoxdursa: "neytral" və boş events.
{_COMMON}
JSON forması:
{{"views": [{{"pair": "BTC/USDT", "sentiment": "müsbət|mənfi|neytral", "events": ["başlıqdan qısa hadisə"]}}]}}"""

RISK_SYSTEM = f"""Sən risk analitikisən. Bazarın risk rejimini və bu gün açıla biləcək YENİ kölgə
mövqelərin maksimum sayını (0-2) təyin edirsən. Volatillik yüksək, korrelyasiya çox yüksək və ya
BTC düşüşü dərindirsə ehtiyatlı ol. Mövcud açıq mövqeləri nəzərə al.
{_COMMON.replace("- Hər cüt üçün düz bir element yaz (siyahıdakı bütün cütlər).", "")}
JSON forması:
{{"regime": "normal|yüksək|ekstremal", "max_new": 0, "reasons": ["1-2 qısa səbəb"]}}"""

SUPERVISOR_SYSTEM = f"""Sən supervayzersən. Üç analitikin hesabatını oxuyub hər cüt üçün yekun
qərar verirsən: AL (yeni mövqe), ÇIX (açıq mövqedən çıx), GÖZLƏ.
Qaydalar: yalnız spot long. ÇIX yalnız açıq mövqesi olan cütə. Risk analitikinin max_new
limitindən çox AL vermə. Hesabatı UĞURSUZ olan analitikə güvənmə — onun sahəsini bilinməz say.
Əminlik azdırsa GÖZLƏ seç.
{_COMMON}
JSON forması:
{{"summary": "1-2 cümlə ümumi qiymət", "decisions": [{{"pair": "BTC/USDT",
  "action": "AL|ÇIX|GÖZLƏ", "confidence": 0.0-1.0, "rationale": "qısa əsaslandırma"}}]}}"""


def _date(now: pd.Timestamp) -> str:
    return f"{pd.Timestamp(now).tz_convert(BAKU):%Y-%m-%d}"


def tech_user_prompt(pairs, facts, now) -> str:
    return (f"Tarix: {_date(now)} (Bakı). Cütlər: {', '.join(pairs)}\n"
            f"Faktlar:\n{json.dumps(facts, ensure_ascii=False, indent=1)}")


def news_user_prompt(pairs, news, now) -> str:
    lines = "\n".join(f"- {t}" for t in news) if news else "(son 24 saatda başlıq yoxdur)"
    return f"Tarix: {_date(now)} (Bakı). Cütlər: {', '.join(pairs)}\nBaşlıqlar:\n{lines}"


def risk_user_prompt(facts, risk_facts, positions, now) -> str:
    vols = {p: {"vol_30d": f["vol_30d"], "atr_pct": f["atr_pct"]} for p, f in facts.items()}
    return (f"Tarix: {_date(now)} (Bakı).\nBazar: {json.dumps(risk_facts, ensure_ascii=False)}\n"
            f"Cütlərin volatilliyi: {json.dumps(vols, ensure_ascii=False)}\n"
            f"Açıq kölgə mövqelər: {json.dumps(positions, ensure_ascii=False)}")


def supervisor_user_prompt(pairs, facts, reports, positions, now) -> str:
    parts = [f"Tarix: {_date(now)} (Bakı). Cütlər: {', '.join(pairs)}",
             f"Faktlar:\n{json.dumps(facts, ensure_ascii=False)}",
             f"Açıq kölgə mövqelər: {json.dumps(positions, ensure_ascii=False)}"]
    for name, r in reports.items():
        if r.get("ok"):
            parts.append(f"[{name} hesabatı]\n{json.dumps(r['data'], ensure_ascii=False)}")
        else:
            parts.append(f"[{name} hesabatı] UĞURSUZ: {r.get('error')} — bu sahəni bilinməz say.")
    return "\n\n".join(parts)
