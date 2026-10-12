"""LangGraph qrafı: 3 analitik paralel → supervayzer. Deterministik axın (plan §3).

LangSmith izləmə LangChain/LangGraph tərəfindən avtomatik olur (LANGSMITH_TRACING=true).
"""

import json
import re
import sys
from pathlib import Path
from typing import Annotated, TypedDict

import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))

from market_brief import allowed_numbers, unverified_numbers  # noqa: E402

from agents import prompts  # noqa: E402
from agents.schemas import NewsReport, RiskReport, SupervisorReport, TechReport  # noqa: E402

MAX_ATTEMPTS = 2  # 1 cəhd + 1 düzəliş


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class State(TypedDict, total=False):
    pairs: list[str]
    facts: dict
    risk_facts: dict
    news: list[str]
    positions: list[dict]
    now: str
    reports: Annotated[dict, _merge]
    decision: dict


def _extract_json(text: str) -> str:
    """İlk TAM JSON obyekti (kod çəpəri, öndəki/arxadakı mətn və ikinci obyekt atılır)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    i = text.find("{")
    if i == -1:
        return text
    try:
        _, end = json.JSONDecoder().raw_decode(text, i)
    except json.JSONDecodeError:
        return text[i:]  # pydantic dəqiq JSON xətasını göstərəcək
    return text[i:end]


def run_agent(llm, system: str, user: str, schema, allowed: set[float], check=None, name: str = ""):
    """(obyekt, None) uğurda; (None, səbəb) uğursuzluqda. Xəta olsa 1 düzəliş cəhdi.
    Rədd edilən xam cavab stderr-ə (cron logu) yazılır — Telegram-a getmir."""
    messages = [SystemMessage(system), HumanMessage(user)]
    err = None
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = llm.invoke(messages).content
        except Exception as e:  # noqa: BLE001 — API/şəbəkə xətası açıq qaytarılır
            return None, f"{type(e).__name__}: {e}"
        text = reply if isinstance(reply, str) else str(reply)
        try:
            obj = schema.model_validate_json(_extract_json(text))
        except ValidationError as e:
            kind = "JSON xətası" if "json" in str(e).lower() else "sxem xətası"
            err = f"{kind}: {e.errors()[0].get('msg', '')[:150]}"
        else:
            bad = unverified_numbers(" ".join(obj.texts()), allowed)
            err = ("faktlarda olmayan rəqəmlər: " + ", ".join(bad)) if bad else (check(obj) if check else None)
            if err is None:
                return obj, None
        print(f"[{name}] RƏDD ({err}):\n{text[:3000]}\n", file=sys.stderr)
        messages += [AIMessage(text), HumanMessage(f"Cavab qəbul edilmədi ({err}). Qaydalara uyğun yenidən yaz.")]
    return None, err


def _pairs_check(pairs):
    def check(obj):
        got = [v.pair for v in getattr(obj, "views", getattr(obj, "decisions", []))]
        if sorted(got) != sorted(pairs):
            return f"cütlər uyğun deyil: gözlənilən {sorted(pairs)}, alınan {sorted(got)}"
        return None
    return check


def _allowed(state: State) -> set[float]:
    facts = {**state["facts"], "_risk": state.get("risk_facts", {})}
    return allowed_numbers(facts, state.get("news", []), pd.Timestamp(state["now"]))


def build_graph(llms: dict):
    """llms: {"texniki", "xəbər", "risk", "supervayzer"} → LangChain chat modeli."""

    def report(name, schema, system, make_user, needs_pairs=True):
        def node(state: State):
            obj, err = run_agent(llms[name], system, make_user(state), schema, _allowed(state),
                                 _pairs_check(state["pairs"]) if needs_pairs else None, name)
            return {"reports": {name: {"ok": obj is not None,
                                       "data": obj.model_dump() if obj else None, "error": err}}}
        return node

    tech = report("texniki", TechReport, prompts.TECH_SYSTEM,
                  lambda s: prompts.tech_user_prompt(s["pairs"], s["facts"], s["now"]))
    news = report("xəbər", NewsReport, prompts.NEWS_SYSTEM,
                  lambda s: prompts.news_user_prompt(s["pairs"], s.get("news", []), s["now"]))
    risk = report("risk", RiskReport, prompts.RISK_SYSTEM,
                  lambda s: prompts.risk_user_prompt(s["facts"], s.get("risk_facts", {}),
                                                     s.get("positions", []), s["now"]),
                  needs_pairs=False)

    def supervisor(state: State):
        reports = state["reports"]
        r = reports.get("risk", {})
        max_new = r["data"]["max_new"] if r.get("ok") else 0  # risk bilinmirsə yeni mövqe yox
        user = prompts.supervisor_user_prompt(state["pairs"], state["facts"], reports,
                                              state.get("positions", []), state["now"])
        obj, err = run_agent(llms["supervayzer"], prompts.SUPERVISOR_SYSTEM, user, SupervisorReport,
                             _allowed(state), _pairs_check(state["pairs"]), "supervayzer")
        if obj is None:  # fail-safe
            return {"decision": {"ok": False, "error": err, "max_new": max_new, "summary": None,
                                 "actions": {p: "GÖZLƏ" for p in state["pairs"]}, "details": []}}
        return {"decision": {"ok": True, "error": None, "max_new": max_new, "summary": obj.summary,
                             "actions": {d.pair: d.action for d in obj.decisions},
                             "details": [d.model_dump() for d in obj.decisions]}}

    g = StateGraph(State)
    for name, fn in (("tech", tech), ("news", news), ("risk", risk)):
        g.add_node(name, fn)
        g.add_edge(START, name)
        g.add_edge(name, "supervisor")
    g.add_node("supervisor", supervisor)
    g.add_edge("supervisor", END)
    return g.compile()
