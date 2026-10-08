import sys
from pathlib import Path

# tools/ qovluğu paket deyil — konteynerdə skript kimi işlədilir. Testlər üçün
# yola əlavə edirik.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
