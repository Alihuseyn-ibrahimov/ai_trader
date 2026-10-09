"""enter_tag-da stop məsafəsi: mövqe ölçüsü, custom_stoploss və audit üçün tək mənbə.

Format: "<ad>|sd=<stop məsafəsi, qiymət vahidində>"
"""

import math

_KEY = "sd="


def make_tag(name: str, stop_dist: float) -> str:
    if not (stop_dist > 0) or math.isnan(stop_dist):
        raise ValueError("stop məsafəsi müsbət olmalıdır")
    return f"{name}|{_KEY}{stop_dist:.10g}"


def parse_stop_dist(tag: str | None) -> float | None:
    if not tag:
        return None
    for part in tag.split("|")[1:]:
        if part.startswith(_KEY):
            try:
                value = float(part[len(_KEY):])
            except ValueError:
                return None
            return value if value > 0 else None
    return None
