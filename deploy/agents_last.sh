#!/usr/bin/env bash
# Son agent qaçışının hesabatları (mənbə: user_data/shadow/runs.jsonl) — yalnız oxuyur.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - user_data/shadow/runs.jsonl <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.loads(f.read().splitlines()[-1])
print("vaxt:", d["time"], "| prompt:", d["prompt_version"])
print("risk faktları:", json.dumps(d["risk_facts"], ensure_ascii=False))
for name, r in d["reports"].items():
    print(f"\n[{name}] ok={r['ok']} xəta={r['error']}")
    if r["data"]:
        print(json.dumps(r["data"], ensure_ascii=False, indent=1))
print("\nxəbər başlıqları:", len(d["news"]))
PY
