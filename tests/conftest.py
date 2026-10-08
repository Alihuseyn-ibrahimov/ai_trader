import sys
from pathlib import Path

# tools/ qovluğu paket deyil — konteynerdə skript kimi işlədilir. Testlər üçün
# yola əlavə edirik.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
# `risk` paketi ai_trader/ altındadır (konteynerdə /freqtrade/risk)
sys.path.insert(0, str(ROOT))
