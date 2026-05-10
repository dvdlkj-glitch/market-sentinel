"""
ai_analysis_dashboard.py
========================

AI Analysis Share Dashboard — extracted from the main dashboard file in
v1.10.0 (2026-05-09) so the main file stops growing past 45K lines.

This module owns the entire "🤖 AI 分析分享" experience-level page:

  1. 📋 AI 論點卡片 (cards grid)        — analyst's claims
  2. 🧭 整體判斷 (synthesis)             — three-paragraph summary
  3. 📊 每日驗證表 (validation tracker)  — live %-conformance per thesis

The validation tracker computes each thesis's "符合論點程度" 0-100% from
real market data every page load, persists daily snapshots in
`st.session_state`, and renders a 7-day trend arrow showing whether the
market is converging toward (↑ green) or diverging from (↓ red) the
analyst's call.

How to maintain
---------------
After each video, edit:
  * AI_ANALYSIS_THESES — list of thesis dicts (schema documented above
    the constant below)
  * AI_ANALYSIS_SYNTHESIS — three-paragraph summary
That's it. No DB, no scraping, no API.

Public surface (imported by the main file)
------------------------------------------
  - render_ai_analysis_share_dashboard()  : top-level entry
  - AI_ANALYSIS_THESES                    : edit this to add theses
  - AI_ANALYSIS_SYNTHESIS                 : edit this to update summary
  - compute_thesis_validation_score()     : exposed for testing / reuse

Internal symbols (prefixed with `_`) shouldn't be imported elsewhere.

Imports from main file (deferred)
---------------------------------
This module needs five helpers from the main dashboard file. To dodge
circular imports at module-load time, those imports are done inside each
function via `_main_module()`. The main file is large and runs Streamlit
side-effects at import, so keeping the import deferred is the safe choice.
"""

from __future__ import annotations

import math
import textwrap
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import streamlit as st


TW_TZ = ZoneInfo("Asia/Taipei")


# ---------------------------------------------------------------------------
# Deferred-import bridge to the main dashboard file.
# We need: fetch_daily_data, render_html_block, _momentum_extract_close_volume,
#          _momentum_pct, _news_briefing_is_zh
# Importing them at module-load time would create a circular import (main
# file imports us; we'd import it back). The bridge lazily resolves them
# the first time they're needed and caches the results.
# ---------------------------------------------------------------------------

_MAIN_MODULE = None
_MAIN_MODULE_NAMES = (
    "stock_dashboard_web_enhanced_v5_live_news",
    "__main__",
)


def _resolve_main_module():
    """Find the main dashboard module by trying known import names, then
    fall back to scanning sys.modules for any module that has the helpers
    we need. Caches the result."""
    global _MAIN_MODULE
    if _MAIN_MODULE is not None:
        return _MAIN_MODULE

    import importlib
    import sys

    for name in _MAIN_MODULE_NAMES:
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "fetch_daily_data"):
            _MAIN_MODULE = mod
            return mod
        try:
            mod = importlib.import_module(name)
            if hasattr(mod, "fetch_daily_data"):
                _MAIN_MODULE = mod
                return mod
        except Exception:
            continue

    # Final fallback: scan all loaded modules for the marker function
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        if (
            hasattr(mod, "fetch_daily_data")
            and hasattr(mod, "render_html_block")
            and hasattr(mod, "_momentum_extract_close_volume")
        ):
            _MAIN_MODULE = mod
            return mod

    raise ImportError(
        "ai_analysis_dashboard: could not locate the main dashboard module. "
        "Expected one of: " + ", ".join(_MAIN_MODULE_NAMES)
    )


def _fetch_daily_data(*args, **kwargs):
    return _resolve_main_module().fetch_daily_data(*args, **kwargs)


def _render_html_block(*args, **kwargs):
    return _resolve_main_module().render_html_block(*args, **kwargs)


def _momentum_extract_close_volume(*args, **kwargs):
    return _resolve_main_module()._momentum_extract_close_volume(*args, **kwargs)


def _momentum_pct(*args, **kwargs):
    return _resolve_main_module()._momentum_pct(*args, **kwargs)


def _news_briefing_is_zh() -> bool:
    return _resolve_main_module()._news_briefing_is_zh()


# ----------------------------------------------------------------------------
# Validation point types — the calculator dispatches on these
# ----------------------------------------------------------------------------
# Each validation_point dict has these fields:
#   "type":      "index_level" | "stock_trend" | "support_zone" | "rally_pace"
#   "label":     short display string (Chinese)
#   "weight":    1.0 by default (relative weight inside the thesis)
#   ...plus type-specific fields documented in each calculator below.

def _ai_calc_index_level(point: dict, daily_data) -> dict:
    """Score: did TAIEX hold above (or below, if direction='below') the
    threshold? Returns {score, value_text, interpretation}.

    Required fields:
      threshold:   float          — the level we're watching
      direction:   "above"|"below" — claim is the index stays above/below
      ticker:      "^TWII"        — defaults to TAIEX
      consec_days: int            — how many consecutive days to inspect (default 5)
    """
    threshold = float(point.get("threshold", 0))
    direction = point.get("direction", "above")
    ticker = point.get("ticker", "^TWII")
    consec_days = int(point.get("consec_days", 5))

    close, _ = _momentum_extract_close_volume(daily_data, ticker)
    if close is None or close.empty:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    latest = float(close.iloc[-1])
    last_n = close.tail(consec_days)
    if direction == "above":
        # Score: % of last N days that closed above threshold + distance bonus
        pct_above = float((last_n > threshold).sum()) / len(last_n) * 100
        distance_pct = (latest - threshold) / threshold * 100
        # Smooth: even if not all N days held, distance compensates
        score = min(100.0, pct_above * 0.7 + max(0, min(30, distance_pct * 10)))
        if pct_above >= 100 and distance_pct >= 1:
            interp = f"持續守住,高出 {distance_pct:+.1f}%"
        elif pct_above >= 80:
            interp = f"大致守住,{int(pct_above)}% 天數在線上"
        elif pct_above >= 40:
            interp = f"觸點頻繁,{int(pct_above)}% 天數在線上"
        else:
            interp = f"已跌破,{int(pct_above)}% 天數在線上"
    else:  # below
        pct_below = float((last_n < threshold).sum()) / len(last_n) * 100
        distance_pct = (threshold - latest) / threshold * 100
        score = min(100.0, pct_below * 0.7 + max(0, min(30, distance_pct * 10)))
        if pct_below >= 100 and distance_pct >= 1:
            interp = f"持續低於,低 {distance_pct:.1f}%"
        elif pct_below >= 80:
            interp = f"大致低於,{int(pct_below)}% 天數低於"
        else:
            interp = f"未守在線下,{int(pct_below)}% 天數低於"

    return {
        "score": round(score, 1),
        "value_text": f"{latest:,.2f} ({direction[:1]} {threshold:,.0f})",
        "interpretation": interp,
    }


def _ai_calc_stock_trend(point: dict, daily_data) -> dict:
    """Score: does the stock's recent return match the claimed pattern?

    Required fields:
      ticker:       e.g. "0056.TW"
      pattern:      "rally" | "consolidate" | "weak"
      lookback:     days (default 5)
      rally_min_pct: for "rally", how much gain expected (default 5)
    """
    ticker = point.get("ticker", "")
    pattern = point.get("pattern", "rally")
    lookback = int(point.get("lookback", 5))
    rally_min_pct = float(point.get("rally_min_pct", 5))

    close, _ = _momentum_extract_close_volume(daily_data, ticker)
    if close is None or len(close) < lookback + 1:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    period_return = _momentum_pct(close.iloc[-1], close.iloc[-(lookback + 1)])
    if period_return is None:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    if pattern == "rally":
        # Want strong upside. Score: scale [0, rally_min_pct*1.5] → [0, 100]
        score = max(0.0, min(100.0, period_return / (rally_min_pct * 1.5) * 100))
        if period_return >= rally_min_pct:
            interp = f"飆股特徵明顯 ({period_return:+.1f}%/{lookback}日)"
        elif period_return >= rally_min_pct * 0.5:
            interp = f"中等漲幅 ({period_return:+.1f}%/{lookback}日)"
        elif period_return >= 0:
            interp = f"漲幅有限 ({period_return:+.1f}%/{lookback}日)"
        else:
            interp = f"反向回測 ({period_return:+.1f}%/{lookback}日)"
    elif pattern == "consolidate":
        # Want |return| <= 3%. Score peaks at 0%, falls to 0 at ±6%
        abs_ret = abs(period_return)
        score = max(0.0, 100 - abs_ret / 6 * 100)
        if abs_ret <= 1.5:
            interp = f"震盪整理 ({period_return:+.1f}%/{lookback}日)"
        elif abs_ret <= 3:
            interp = f"小幅波動 ({period_return:+.1f}%/{lookback}日)"
        else:
            interp = f"已脫離整理 ({period_return:+.1f}%/{lookback}日)"
    else:  # weak
        # Want negative return. Score: -8% = 100, 0% = 0
        score = max(0.0, min(100.0, -period_return / 8 * 100))
        if period_return <= -3:
            interp = f"明顯弱勢 ({period_return:+.1f}%/{lookback}日)"
        elif period_return <= 0:
            interp = f"小幅走弱 ({period_return:+.1f}%/{lookback}日)"
        else:
            interp = f"未走弱 ({period_return:+.1f}%/{lookback}日)"

    return {
        "score": round(score, 1),
        "value_text": f"{period_return:+.1f}% / {lookback}日",
        "interpretation": interp,
    }


def _ai_calc_support_zone(point: dict, daily_data) -> dict:
    """Score: is the price still respecting the support level?

    Required fields:
      level:    float — the support price
      ticker:   default "^TWII"
      tolerance_pct: how close to support is "still respected" (default 0.5%)
    """
    level = float(point.get("level", 0))
    ticker = point.get("ticker", "^TWII")
    tolerance_pct = float(point.get("tolerance_pct", 0.5))

    close, _ = _momentum_extract_close_volume(daily_data, ticker)
    if close is None or close.empty:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    latest = float(close.iloc[-1])
    distance_pct = (latest - level) / level * 100

    if distance_pct >= 0:
        # Still above support. Score: 100 if comfortably above (>2%),
        # tapers to 60 if right on it
        if distance_pct >= 3:
            score = 100.0
            interp = f"支撐穩固 (高出 {distance_pct:.1f}%)"
        elif distance_pct >= 1:
            score = 80.0
            interp = f"支撐有效 (高出 {distance_pct:.1f}%)"
        elif distance_pct >= 0:
            score = 60.0
            interp = f"逼近支撐 (高出 {distance_pct:.2f}%)"
    else:
        # Below support — broken. Score 0-40 depending on how deep
        breach_pct = -distance_pct
        if breach_pct <= tolerance_pct:
            score = 50.0
            interp = f"輕微跌破 ({distance_pct:.2f}%)"
        elif breach_pct <= 1.5:
            score = 25.0
            interp = f"跌破支撐 ({distance_pct:.1f}%)"
        else:
            score = 10.0
            interp = f"明顯跌破 ({distance_pct:.1f}%)"

    return {
        "score": round(score, 1),
        "value_text": f"{latest:,.2f} vs {level:,.0f}",
        "interpretation": interp,
    }


def _ai_calc_rally_pace(point: dict, daily_data) -> dict:
    """Score: is the rally pace within the analyst's "healthy" range?
    Used for theses like "強勢但偏熱" — too slow = thesis fails (no rally),
    too fast = thesis fails (overheating breakdown imminent).

    Required fields:
      ticker:        default "^TWII"
      lookback:      days (default 10)
      ideal_min_pct: lower bound of healthy rally (default 2)
      ideal_max_pct: upper bound (default 8)
    """
    ticker = point.get("ticker", "^TWII")
    lookback = int(point.get("lookback", 10))
    ideal_min_pct = float(point.get("ideal_min_pct", 2))
    ideal_max_pct = float(point.get("ideal_max_pct", 8))

    close, _ = _momentum_extract_close_volume(daily_data, ticker)
    if close is None or len(close) < lookback + 1:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    period_return = _momentum_pct(close.iloc[-1], close.iloc[-(lookback + 1)])
    if period_return is None:
        return {"score": 50.0, "value_text": "—", "interpretation": "資料準備中"}

    if ideal_min_pct <= period_return <= ideal_max_pct:
        score = 100.0
        interp = f"漲速健康 ({period_return:+.1f}%/{lookback}日)"
    elif period_return < ideal_min_pct:
        gap = ideal_min_pct - period_return
        score = max(20.0, 100 - gap * 15)
        interp = f"動能不足 ({period_return:+.1f}%/{lookback}日)"
    else:  # too hot
        excess = period_return - ideal_max_pct
        score = max(20.0, 100 - excess * 12)
        interp = f"漲速偏熱 ({period_return:+.1f}%/{lookback}日)"

    return {
        "score": round(score, 1),
        "value_text": f"{period_return:+.1f}% / {lookback}日",
        "interpretation": interp,
    }


_AI_VALIDATION_CALCULATORS = {
    "index_level":  _ai_calc_index_level,
    "stock_trend":  _ai_calc_stock_trend,
    "support_zone": _ai_calc_support_zone,
    "rally_pace":   _ai_calc_rally_pace,
}


def compute_thesis_validation_score(thesis: dict, daily_data) -> dict:
    """Compute the aggregated validation score + per-point breakdown.
    Returns:
        {
            "thesis_score":   float,    # 0-100, higher = market validating
            "verdict":        "validating" | "neutral" | "diverging",
            "points":         [{label, score, value_text, interpretation, weight}, ...],
            "ready":          bool,
        }
    """
    points_out: list[dict] = []
    weighted_sum = 0.0
    weight_total = 0.0
    components_ready = 0

    for point in thesis.get("validation_points", []) or []:
        calc_fn = _AI_VALIDATION_CALCULATORS.get(point.get("type"))
        if not calc_fn:
            continue
        result = calc_fn(point, daily_data)
        weight = float(point.get("weight", 1.0))
        points_out.append({
            "label": point.get("label", ""),
            "score": result["score"],
            "value_text": result["value_text"],
            "interpretation": result["interpretation"],
            "weight": weight,
            "type": point.get("type"),
        })
        if result["value_text"] != "—":
            weighted_sum += result["score"] * weight
            weight_total += weight
            components_ready += 1

    if weight_total > 0:
        thesis_score = weighted_sum / weight_total
    else:
        thesis_score = 50.0

    if thesis_score >= 65:
        verdict = "validating"
    elif thesis_score >= 40:
        verdict = "neutral"
    else:
        verdict = "diverging"

    return {
        "thesis_score": round(thesis_score, 1),
        "verdict": verdict,
        "points": points_out,
        "ready": components_ready > 0,
    }


# ----------------------------------------------------------------------------
# 7-day trend persistence — store today's score per thesis in session_state.
# Real persistence would use Supabase; for now a per-session dict keyed by
# (thesis_id, date) suffices to give the user a moving picture within a
# single session, and on cold-start we just say "資料累積中".
# ----------------------------------------------------------------------------

def _ai_thesis_history_key() -> str:
    return "_ai_thesis_history"


def _record_thesis_score_today(thesis_id: str, score: float) -> None:
    """Append today's score to the per-thesis history. De-dupes by date so
    multiple page reloads in one day don't inflate the list."""
    today = datetime.now(TW_TZ).strftime("%Y-%m-%d")
    history = st.session_state.setdefault(_ai_thesis_history_key(), {})
    series = history.setdefault(thesis_id, [])
    if series and series[-1].get("date") == today:
        series[-1]["score"] = score
    else:
        series.append({"date": today, "score": score})
    # Keep only last 14 days
    if len(series) > 14:
        del series[:-14]


def _thesis_trend_arrow(thesis_id: str, current_score: float) -> tuple[str, str, str]:
    """Returns (arrow, css_class, label) reflecting 7-day trend direction."""
    history = st.session_state.get(_ai_thesis_history_key(), {}).get(thesis_id, [])
    if len(history) < 2:
        return ("·", "ai-trend-pending", "資料累積中")
    # Compare current vs ~7 days ago (or oldest available)
    earliest = history[max(0, len(history) - 7)]
    delta = current_score - earliest.get("score", current_score)
    if delta >= 5:
        return ("↑", "ai-trend-up", f"7日 +{delta:.0f}")
    if delta <= -5:
        return ("↓", "ai-trend-down", f"7日 {delta:.0f}")
    return ("→", "ai-trend-flat", f"7日 {delta:+.0f}")


# ----------------------------------------------------------------------------
# AI_TOPIC_REGISTRY — main organizing dimension for the cards / tracker
# ----------------------------------------------------------------------------
# v1.10.5: Theses are grouped by "topic" so the page scales to 20+ entries.
# To add a new topic, append an entry here AND set thesis["topic"] = <key>
# in the relevant theses below. Theses with an unknown topic key fall into
# the "uncategorized" bucket (rendered last).
#
# display_order controls the section sequence (lower = appears earlier).
# ----------------------------------------------------------------------------

AI_TOPIC_REGISTRY: dict[str, dict] = {
    "market-direction": {
        "emoji": "📈",
        "label_zh": "大盤判別",
        "label_en": "Index Direction",
        "tagline_zh": "加權指數整體走勢、支撐壓力、漲速判別",
        "tagline_en": "TAIEX trajectory, supports / resistance, rally pace",
        "display_order": 10,
    },
    "stock-trend": {
        "emoji": "📊",
        "label_zh": "個股走勢",
        "label_en": "Stock Moves",
        "tagline_zh": "單一個股的多空判別、技術面驗證",
        "tagline_en": "Per-stock direction calls, technical validation",
        "display_order": 20,
    },
    "etf-flow": {
        "emoji": "💰",
        "label_zh": "ETF",
        "label_en": "ETFs",
        "tagline_zh": "ETF 類別、資金流向、追價熱度",
        "tagline_en": "ETF categories, fund flow, retail momentum",
        "display_order": 30,
    },
    "macro-narrative": {
        "emoji": "🌐",
        "label_zh": "宏觀主軸",
        "label_en": "Macro Narrative",
        "tagline_zh": "產業主軸、AI / 半導體 / 政策題材",
        "tagline_en": "Sector themes, AI / semis / policy narratives",
        "display_order": 40,
    },
    "volume-positioning": {
        "emoji": "📦",
        "label_zh": "量能籌碼",
        "label_en": "Volume & Positioning",
        "tagline_zh": "成交量結構、外資籌碼、融資餘額",
        "tagline_en": "Volume structure, foreign positioning, margin balance",
        "display_order": 50,
    },
    "uncategorized": {
        "emoji": "🗂",
        "label_zh": "其他論點",
        "label_en": "Other Theses",
        "tagline_zh": "未指定主題的論點",
        "tagline_en": "Theses without an assigned topic",
        "display_order": 999,
    },
}


# ----------------------------------------------------------------------------
# AI_ANALYSIS_THESES — manually edited dataset
# ----------------------------------------------------------------------------
# Edit this list after each video. Schema:
#   id:                  unique slug (used for trend history persistence)
#   topic:               slug pointing into AI_TOPIC_REGISTRY (e.g.
#                        "market-direction"). v1.10.5 — required for grouping.
#                        Unknown / missing topic → "uncategorized".
#   title:               short headline (matches video segment title)
#   summary:             "解說重點" — what the analyst is saying
#   cross_validation:    "目前局勢交叉驗證" — supporting market evidence
#   risk:                "風險 / 反證" — what would invalidate this
#   claimed_probability: int 0-100, the analyst's stated confidence
#   issued_date:         "YYYY-MM-DD" when the thesis was posted
#   horizon_date:        "YYYY-MM-DD" when this should be re-evaluated
#   validation_points:   list of dicts (see calculators above for fields)
# ----------------------------------------------------------------------------

AI_ANALYSIS_THESES: list[dict] = [
    {
        "id": "thesis-520-pull-back",
        "topic": "market-direction",
        "title": "杜金龍:520 後以盤代跌",
        "summary": "意思應是:到 2026/05/20 後,台股即使漲多,也比較可能用高檔震盪、類股輪動、時間整理來消化漲幅,而不是立刻大崩。",
        "cross_validation": "台股在 5 月初動能非常強:加權指數5/4收40,705.14、5/7盤中到42,156.06、收41,933.78、5/8仍收41,603.94;這代表多頭主架構還在,但5/8已出現高檔震盪。本週指數漲幅約6.88%、上市總市值達135.70兆元,屬於強勢但偏熱的盤。",
        "risk": "指數短線漲幅過大,若外資轉賣、AI 權值股熄火,或520前後有政策 / 地緣政治雜音,會把「以盤代跌」變成較劇烈修正。",
        "claimed_probability": 62,
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-20",
        "validation_points": [
            {
                "type": "index_level",
                "label": "加權指數守在 41,000 以上",
                "threshold": 41000,
                "direction": "above",
                "consec_days": 5,
                "weight": 1.5,
            },
            {
                "type": "rally_pace",
                "label": "10 日漲速健康(2-8%)",
                "ticker": "^TWII",
                "lookback": 10,
                "ideal_min_pct": 2,
                "ideal_max_pct": 8,
                "weight": 1.0,
            },
            {
                "type": "support_zone",
                "label": "40,700 短線支撐有效",
                "level": 40700,
                "ticker": "^TWII",
                "weight": 1.0,
            },
        ],
    },
    {
        "id": "thesis-0056-rally",
        "topic": "etf-flow",
        "title": "0056 變飆股",
        "summary": "0056本質是高股息ETF,不是小型飆股;但近期因配息、填息、外資買超與高股息資金回流,短線價格表現確實有「熱門股化」現象。",
        "cross_validation": "0056於5/8收44.85元,當日小漲0.29%;Yahoo資料同時顯示其資產規模約5,210億元,為台股ETF規模第2大、高股息ETF龍頭。0056在2026/04/23除息1元,現金股利發放日為2026/05/14。外資5/8買超0056達46,498張,列外資買超第2名,也支持「短線資金追捧」。",
        "risk": "0056是50檔高殖利率股票的ETF,追蹤台灣高股息指數,採現金股利殖利率加權,長期特性偏收益,不宜完全用飆股邏輯追價。若買盤只是配息與填息行情,發息後可能進入震盪。",
        "claimed_probability": 60,
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-31",
        "validation_points": [
            {
                "type": "stock_trend",
                "label": "0056 5 日漲幅符合飆股特徵(>3%)",
                "ticker": "0056.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 3,
                "weight": 1.5,
            },
            {
                "type": "stock_trend",
                "label": "0056 10 日累積漲幅(>5%)",
                "ticker": "0056.TW",
                "pattern": "rally",
                "lookback": 10,
                "rally_min_pct": 5,
                "weight": 1.0,
            },
        ],
    },
    {
        "id": "thesis-0056-hold-or-sell",
        "topic": "etf-flow",
        "title": "0056:上車還是下車",
        "summary": "若是原本為了現金流、長期領息而持有,沒有明顯需要因短線漲幅就急著下車;若是短線想追高,風險報酬已變差,較適合分批而非一次重壓。",
        "cross_validation": "0056本季配息1元、4/23除息、5/14發放,且資金仍在流入;這對存股族與收益型資金有吸引力。",
        "risk": "0056從38元附近快速到44元以上後,殖利率吸引力會被價格上漲稀釋;短線追高若遇大盤修正,可能賺了配息、賠了價差。",
        "claimed_probability": 55,
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-31",
        "validation_points": [
            {
                "type": "stock_trend",
                "label": "0056 短線追高合理(漲速不過熱)",
                "ticker": "0056.TW",
                "pattern": "consolidate",
                "lookback": 5,
                "weight": 1.0,
            },
            {
                "type": "support_zone",
                "label": "0056 仍站穩 42 元支撐",
                "level": 42,
                "ticker": "0056.TW",
                "tolerance_pct": 0.5,
                "weight": 1.5,
            },
        ],
    },
    {
        "id": "thesis-0050-leadership",
        "topic": "etf-flow",
        "title": "0050 / 大型權值 ETF",
        "summary": "影片標籤有0050與ETF,重點應是:大盤若續強,0050仍是最直接參與台股權值股行情的工具。",
        "cross_validation": "0050追蹤台灣50指數,涵蓋台灣證交所市值前50大公司。0050在5/8收97.00元、上漲0.72%,顯示權值ETF仍跟著大盤高檔運行。台股5月初創高主要由AI與大型半導體股帶動,5/4台股大漲逾1,700點並收上40,000點,主因包括AI熱潮與台積電、聯發科等大型半導體股。",
        "risk": "0050高度仰賴大型電子權值股;若台積電、聯發科或AI伺服器供應鏈回檔,0050會比高股息ETF更受衝擊。",
        "claimed_probability": 62,
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-31",
        "validation_points": [
            {
                "type": "stock_trend",
                "label": "0050 5 日續強",
                "ticker": "0050.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 2,
                "weight": 1.5,
            },
            {
                "type": "stock_trend",
                "label": "台積電 5 日領漲",
                "ticker": "2330.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 2,
                "weight": 1.0,
            },
        ],
    },
    {
        "id": "thesis-tw-ai-semi-leadership",
        "topic": "macro-narrative",
        "title": "台股主軸仍在 AI / 半導體",
        "summary": "目前台股不是全面平均上漲,而是 AI、半導體、權值股帶動指數創高,再擴散到 ETF 與部分落後補漲股。",
        "cross_validation": "5月初台股創高被明確歸因於AI樂觀情緒與大型半導體股領漲。外資5/8買超名單中也可見鴻海、光寶科、聯鈞、華通、景碩等電子與AI供應鏈相關標的。",
        "risk": "若AI資本支出預期降溫,或美股科技股回檔,台股權值股與AI族群會同步承壓。",
        "claimed_probability": 67,
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-31",
        "validation_points": [
            {
                "type": "stock_trend",
                "label": "台積電 5 日強勢",
                "ticker": "2330.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 2,
                "weight": 1.5,
            },
            {
                "type": "stock_trend",
                "label": "聯發科 5 日跟漲",
                "ticker": "2454.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 1,
                "weight": 1.0,
            },
            {
                "type": "stock_trend",
                "label": "鴻海 5 日續強",
                "ticker": "2317.TW",
                "pattern": "rally",
                "lookback": 5,
                "rally_min_pct": 1,
                "weight": 0.7,
            },
        ],
    },
    {
        "id": "thesis-no-broad-crash",
        "topic": "market-direction",
        "title": "520 後是否容易「全面大跌」",
        "summary": "以目前資料看,除非外資突然大幅反手或國際利空擴大,單純因 520 時間點而全面大跌的證據不足。比較合理的情境是高檔震盪、強弱股分化。",
        "cross_validation": "指數已創高但仍維持在41,000點以上,成交量也大,顯示資金仍在市場內輪動。",
        "risk": "高檔最大風險不是520本身,而是「漲太快 + 籌碼過熱 + 外資轉向」。如果外資由買超變連續賣超,盤代跌機率會下降。",
        "claimed_probability": 35,  # NOTE: low because thesis is "NOT broad crash"
        "issued_date": "2026-05-08",
        "horizon_date": "2026-05-25",
        "validation_points": [
            {
                "type": "index_level",
                "label": "加權維持 41,000 以上",
                "threshold": 41000,
                "direction": "above",
                "consec_days": 5,
                "weight": 1.5,
            },
            {
                "type": "rally_pace",
                "label": "5 日跌幅未超過 -3%",
                "ticker": "^TWII",
                "lookback": 5,
                "ideal_min_pct": -3,
                "ideal_max_pct": 5,
                "weight": 1.0,
            },
        ],
    },
]


# ----------------------------------------------------------------------------
# AI Synthesis paragraphs — the analyst's three-point summary
# Edit alongside AI_ANALYSIS_THESES.
# ----------------------------------------------------------------------------

AI_ANALYSIS_SYNTHESIS: dict = {
    "headline": "AI 整體判斷",
    "headline_en": "AI Overall Take",
    "intro": "這集標題中的核心論點,我會拆成三句看:",
    "intro_en": "Core claims from this video, broken into three points:",
    "issued_date": "2026-05-08",
    # v1.10.9: Each paragraph now carries its own validation_points list
    # (same schema as thesis-level validation_points). The renderer scores
    # each paragraph 0-100% from live market data and shows a small chip
    # on the paragraph's lead line. The whole synthesis block also gets
    # a header-level avg score that aggregates the three paragraphs.
    #
    # When you write a new synthesis after a video, fill in 1-2
    # validation_points per paragraph — these should be the most direct
    # quantifiable claim from that paragraph (a specific level / trend /
    # support that the market can confirm or deny).
    "paragraphs": [
        {
            "lead": "第一,台股「520 後以盤代跌」的可信度偏中高。",
            "body": "大盤剛經歷 5 月初急漲,5/7 創高後 5/8 拉回但仍守在 41,000 點以上,這比較像多頭高檔整理,而不是趨勢立刻反轉。短線支撐可看 40,700 附近,也就是 5/4 收盤突破 40,000 後的區域;壓力則看 5/7 盤中高點 42,156 附近。",
            "validation_points": [
                {
                    "type": "index_level",
                    "label": "加權守 41,000",
                    "threshold": 41000,
                    "direction": "above",
                    "consec_days": 5,
                    "weight": 1.5,
                },
                {
                    "type": "support_zone",
                    "label": "40,700 短線支撐",
                    "level": 40700,
                    "ticker": "^TWII",
                    "weight": 1.0,
                },
            ],
        },
        {
            "lead": "第二,0056「已經變熱門」是高機率,但「繼續像飆股一樣噴」只能算中等機率。",
            "body": "0056 有配息 1 元、快速填息、外資買超與高股息 ETF 龍頭光環,這些都是真實利多;但它畢竟是收益型 ETF,不是高 β 個股,追高時要小心把高股息 ETF 買成短線價差股。",
            "validation_points": [
                {
                    "type": "stock_trend",
                    "label": "0056 5 日漲幅(熱門股化)",
                    "ticker": "0056.TW",
                    "pattern": "rally",
                    "lookback": 5,
                    "rally_min_pct": 2,
                    "weight": 1.0,
                },
                {
                    "type": "rally_pace",
                    "label": "0056 漲速不過熱(0-6%)",
                    "ticker": "0056.TW",
                    "lookback": 10,
                    "ideal_min_pct": 0,
                    "ideal_max_pct": 6,
                    "weight": 1.0,
                },
            ],
        },
        {
            "lead": "第三,0050 與 AI 權值股仍是台股主幹,但短線不宜忽略漲多風險。",
            "body": "若台股繼續往上,0050 受惠會直接;若進入盤整,0056 這種高股息 ETF 可能會因防禦與現金流需求而相對抗震。簡單說:看成長與指數彈性偏 0050;看現金流與震盪抗性偏 0056。",
            "validation_points": [
                {
                    "type": "stock_trend",
                    "label": "0050 5 日續強",
                    "ticker": "0050.TW",
                    "pattern": "rally",
                    "lookback": 5,
                    "rally_min_pct": 1,
                    "weight": 1.5,
                },
                {
                    "type": "stock_trend",
                    "label": "台積電 5 日領漲",
                    "ticker": "2330.TW",
                    "pattern": "rally",
                    "lookback": 5,
                    "rally_min_pct": 2,
                    "weight": 1.0,
                },
            ],
        },
    ],
}


# ----------------------------------------------------------------------------
# Renderer
# ----------------------------------------------------------------------------

_AI_ANALYSIS_CSS = """
<style>
.ai-share-shell {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC",
                 "Microsoft JhengHei", sans-serif;
    color: #e9ecf3;
    margin-bottom: 16px;
}
.ai-share-section-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin: 18px 0 10px 0;
}
.ai-share-section-title {
    font-size: 19px;
    font-weight: 700;
    color: #f4f6fb;
    letter-spacing: 0.3px;
}
.ai-share-section-meta {
    font-size: 13px;
    color: #98a2b8;
    font-style: italic;
}
.ai-cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 12px;
}
.ai-card {
    background: linear-gradient(180deg, rgba(20,26,45,.92), rgba(14,18,32,.92));
    border: 1px solid rgba(96,110,145,.35);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.ai-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 10px;
}
.ai-card-title {
    font-size: 16px;
    font-weight: 700;
    color: #f4f6fb;
    line-height: 1.35;
    flex: 1;
}
.ai-card-prob-pill {
    font-size: 12.5px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(96,110,145,.25);
    color: #c2c8d8;
    white-space: nowrap;
    flex-shrink: 0;
}
.ai-card-prob-validating { background: rgba(76,208,168,.25); color: #8be8b1; }
.ai-card-prob-neutral { background: rgba(230,195,95,.22); color: #f4d68a; }
.ai-card-prob-diverging { background: rgba(217,102,112,.22); color: #f4a3aa; }
.ai-card-section {
    font-size: 13.5px;
    line-height: 1.55;
    color: #c2c8d8;
}
.ai-card-section-label {
    font-size: 11px;
    font-weight: 700;
    color: #98a2b8;
    text-transform: uppercase;
    letter-spacing: .5px;
    margin-bottom: 3px;
}
.ai-card-section-risk { color: #f4a3aa; }
.ai-card-section-cross { color: #c2c8d8; }
.ai-card-validation-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(8,11,22,.5);
    border-radius: 8px;
    padding: 8px 10px;
    margin-top: 4px;
    border: 1px solid rgba(96,110,145,.18);
}
.ai-card-validation-num {
    font-size: 20px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.ai-card-validation-num-validating { color: #8be8b1; }
.ai-card-validation-num-neutral { color: #f4d68a; }
.ai-card-validation-num-diverging { color: #f4a3aa; }
.ai-card-validation-trend {
    font-size: 12.5px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 5px;
    margin-left: auto;
    font-variant-numeric: tabular-nums;
}
.ai-trend-up { background: rgba(76,208,168,.22); color: #8be8b1; }
.ai-trend-down { background: rgba(217,102,112,.22); color: #f4a3aa; }
.ai-trend-flat { background: rgba(96,110,145,.25); color: #c2c8d8; }
.ai-trend-pending { background: rgba(96,110,145,.18); color: #98a2b8; }
.ai-card-validation-label {
    font-size: 12px;
    color: #98a2b8;
    line-height: 1.3;
}

.ai-synthesis-shell {
    background: linear-gradient(180deg, rgba(35,44,70,.55), rgba(20,26,45,.85));
    border: 1px solid rgba(96,110,145,.35);
    border-radius: 12px;
    padding: 16px 20px;
    margin: 12px 0;
}
.ai-synthesis-headline {
    font-size: 18px;
    font-weight: 700;
    color: #f4f6fb;
    margin-bottom: 4px;
}
.ai-synthesis-head-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 6px;
}
.ai-synthesis-headline-score {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 6px;
    background: rgba(96,110,145,.18);
}
.ai-synthesis-headline-score-num {
    font-size: 22px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.ai-synthesis-headline-score-num-validating { color: #8be8b1; }
.ai-synthesis-headline-score-num-neutral { color: #f4d68a; }
.ai-synthesis-headline-score-num-diverging { color: #f4a3aa; }
.ai-synthesis-issued {
    font-size: 12px;
    color: #98a2b8;
    font-style: italic;
    margin-left: auto;
}
.ai-synthesis-intro {
    font-size: 14px;
    color: #98a2b8;
    margin-bottom: 14px;
}

/* v1.10.10 — synthesis paragraphs as cards */
.ai-synthesis-cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 12px;
}
.ai-synthesis-card {
    background: linear-gradient(180deg, rgba(20,26,45,.92), rgba(14,18,32,.92));
    border: 1px solid rgba(96,110,145,.35);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    position: relative;
}
.ai-synthesis-card-validating { border-left: 3px solid #5ec689; }
.ai-synthesis-card-neutral { border-left: 3px solid #e6c35f; }
.ai-synthesis-card-diverging { border-left: 3px solid #d96670; }
.ai-synthesis-card-no-validation { border-left: 3px solid rgba(96,110,145,.30); }
.ai-synthesis-card-tag {
    font-size: 11px;
    font-weight: 700;
    color: #98a2b8;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.ai-synthesis-card-lead {
    font-size: 14.5px;
    font-weight: 700;
    color: #f4d68a;
    line-height: 1.45;
}
.ai-synthesis-card-body {
    font-size: 13.5px;
    line-height: 1.65;
    color: #d8dde9;
    flex: 1;
}
.ai-synthesis-card-validation-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(8,11,22,.5);
    border-radius: 8px;
    padding: 8px 10px;
    margin-top: auto;
    border: 1px solid rgba(96,110,145,.18);
}
.ai-synthesis-card-validation-num {
    font-size: 20px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.ai-synthesis-card-validation-num-validating { color: #8be8b1; }
.ai-synthesis-card-validation-num-neutral { color: #f4d68a; }
.ai-synthesis-card-validation-num-diverging { color: #f4a3aa; }
.ai-synthesis-card-validation-label {
    font-size: 11px;
    color: #98a2b8;
    line-height: 1.3;
    flex: 1;
}
.ai-synthesis-card-validation-trend {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 5px;
    margin-left: auto;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
}
.ai-synthesis-card-no-data-hint {
    font-size: 11.5px;
    color: #7a8499;
    font-style: italic;
    padding: 4px 0;
}

.ai-validation-tracker {
    background: linear-gradient(180deg, rgba(20,26,45,.92), rgba(14,18,32,.92));
    border: 1px solid rgba(96,110,145,.35);
    border-radius: 12px;
    padding: 14px 16px;
    margin: 12px 0;
}
.ai-tracker-table {
    background: rgba(8,11,22,.5);
    border-radius: 8px;
    border: 1px solid rgba(96,110,145,.18);
    overflow: hidden;
}
.ai-tracker-row {
    display: grid;
    grid-template-columns: minmax(180px, 1.3fr) minmax(220px, 1.6fr) minmax(140px, 0.8fr) minmax(180px, 1.5fr);
    gap: 10px;
    padding: 10px 12px;
    align-items: center;
    border-bottom: 1px solid rgba(96,110,145,.12);
    font-size: 13.5px;
}
.ai-tracker-row:last-child { border-bottom: none; }
.ai-tracker-row-header {
    background: rgba(35,44,70,.55);
    font-weight: 600;
    color: #b8c0d4;
    font-size: 12px;
    letter-spacing: .4px;
    text-transform: uppercase;
}
.ai-tracker-row-thesis {
    background: rgba(96,110,145,.10);
    grid-template-columns: 1fr;
    padding: 8px 14px;
    border-left: 3px solid #5b8def;
}
.ai-tracker-row-thesis.ai-thesis-validating { border-left-color: #5ec689; }
.ai-tracker-row-thesis.ai-thesis-neutral { border-left-color: #e6c35f; }
.ai-tracker-row-thesis.ai-thesis-diverging { border-left-color: #d96670; }
.ai-tracker-thesis-line {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.ai-tracker-thesis-title {
    font-size: 14px;
    font-weight: 700;
    color: #f4f6fb;
    flex: 1;
    min-width: 200px;
}
.ai-tracker-thesis-score {
    font-size: 18px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
}
.ai-tracker-cell-label { color: #d8dde9; font-weight: 500; padding-left: 14px; position: relative; }
.ai-tracker-cell-label::before {
    content: "›";
    position: absolute;
    left: 4px;
    color: #98a2b8;
    font-weight: 600;
}
.ai-tracker-cell-value { color: #f4f6fb; font-variant-numeric: tabular-nums; font-weight: 600; }
.ai-tracker-cell-score {
    display: flex;
    align-items: center;
    gap: 6px;
}
.ai-tracker-score-num { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 32px; }
.ai-tracker-score-bar {
    flex: 1;
    height: 5px;
    background: rgba(96,110,145,.25);
    border-radius: 3px;
    overflow: hidden;
}
.ai-tracker-score-fill { height: 100%; border-radius: 3px; }
.ai-tracker-score-fill-validating { background: linear-gradient(90deg, #4cd0a8, #6fd99a); }
.ai-tracker-score-fill-neutral { background: linear-gradient(90deg, #e6c35f, #f4d68a); }
.ai-tracker-score-fill-diverging { background: linear-gradient(90deg, #d96670, #f08894); }
.ai-tracker-cell-interp { color: #c2c8d8; font-size: 12.5px; }

.ai-share-foot {
    margin-top: 8px;
    font-size: 12px;
    color: #7a8499;
    font-style: italic;
}

/* v1.10.5 — topic accordions */
.ai-topic-section {
    background: linear-gradient(180deg, rgba(20,26,45,.85), rgba(14,18,32,.85));
    border: 1px solid rgba(96,110,145,.30);
    border-radius: 12px;
    margin-bottom: 12px;
    overflow: hidden;
}
.ai-topic-section[open] {
    border-color: rgba(96,110,145,.45);
}
.ai-topic-summary {
    padding: 14px 18px;
    cursor: pointer;
    list-style: none;
    user-select: none;
    transition: background 0.15s;
}
.ai-topic-summary::-webkit-details-marker { display: none; }
.ai-topic-summary:hover {
    background: rgba(96,110,145,.10);
}
.ai-topic-section[open] > .ai-topic-summary {
    border-bottom: 1px solid rgba(96,110,145,.25);
    background: rgba(96,110,145,.08);
}
.ai-topic-head-line {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.ai-topic-emoji {
    font-size: 24px;
    line-height: 1;
}
.ai-topic-label {
    font-size: 18px;
    font-weight: 700;
    color: #f4f6fb;
    letter-spacing: 0.3px;
}
.ai-topic-tagline {
    font-size: 13px;
    color: #98a2b8;
    margin-left: auto;
    margin-right: 4px;
    font-style: italic;
}
.ai-topic-toggle {
    font-size: 12.5px;
    color: #98a2b8;
    padding: 3px 9px;
    border-radius: 5px;
    background: rgba(96,110,145,.18);
    font-weight: 600;
    flex-shrink: 0;
}
.ai-topic-section[open] > .ai-topic-summary .ai-topic-toggle::before {
    content: "▼ 收起";
}
.ai-topic-section:not([open]) > .ai-topic-summary .ai-topic-toggle::before {
    content: "▶ 展開";
}
.ai-topic-avg-score {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.ai-topic-avg-num {
    font-size: 24px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1;
}
.ai-topic-avg-validating { color: #8be8b1; }
.ai-topic-avg-neutral { color: #f4d68a; }
.ai-topic-avg-diverging { color: #f4a3aa; }
.ai-topic-trend-pill {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 4px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* v1.10.7 — second line of the header: distribution + extreme-thesis hint */
.ai-topic-meta-line {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px dashed rgba(96,110,145,.18);
    font-size: 13px;
}
.ai-topic-distribution {
    display: inline-flex;
    gap: 10px;
    align-items: center;
    flex-shrink: 0;
}
.ai-topic-dist-item {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: #c2c8d8;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
}
.ai-topic-dist-item-validating { color: #8be8b1; }
.ai-topic-dist-item-neutral { color: #f4d68a; }
.ai-topic-dist-item-diverging { color: #f4a3aa; }
.ai-topic-meta-divider {
    color: #565d72;
    user-select: none;
}
.ai-topic-extreme-hint {
    color: #c2c8d8;
    font-size: 12.5px;
    line-height: 1.4;
}
.ai-topic-extreme-hint-strong {
    color: #8be8b1;
}
.ai-topic-extreme-hint-weak {
    color: #f4a3aa;
}
.ai-topic-extreme-hint strong {
    font-variant-numeric: tabular-nums;
}

/* v1.10.7 — tracker accordion: same topic structure as cards */
.ai-tracker-shell-grouped {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.ai-tracker-table-segment {
    background: rgba(8,11,22,.5);
    border-radius: 8px;
    border: 1px solid rgba(96,110,145,.18);
    overflow: hidden;
    margin-top: 10px;
}
.ai-topic-body {
    padding: 14px 16px;
}
.ai-master-toggle-row {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}
.ai-master-hint {
    font-size: 12px;
    color: #98a2b8;
    font-style: italic;
}
.ai-master-toggle-btn {
    font-size: 12.5px;
    color: #c2c8d8;
    padding: 4px 12px;
    border-radius: 6px;
    background: rgba(96,110,145,.18);
    border: 1px solid rgba(96,110,145,.30);
    font-weight: 600;
    text-decoration: none;
}
.ai-master-toggle-btn:hover {
    background: rgba(96,110,145,.28);
    color: #f4f6fb;
}
.ai-tracker-topic-divider {
    background: rgba(96,110,145,.10);
    grid-template-columns: 1fr;
    padding: 6px 14px;
    font-size: 12.5px;
    color: #98a2b8;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    border-top: 2px solid rgba(96,110,145,.20);
}

@media (max-width: 900px) {
    .ai-cards-grid { grid-template-columns: 1fr; }
    .ai-synthesis-cards-grid { grid-template-columns: 1fr; }
    .ai-tracker-row {
        grid-template-columns: 1fr 1fr;
        grid-template-rows: auto auto;
    }
    .ai-tracker-cell-score, .ai-tracker-cell-interp {
        grid-column: 1 / -1;
    }
    .ai-topic-tagline { display: none; }
}
</style>
"""


def _ensure_ai_analysis_css():
    """Inject every render. v1.10.1: Removed the session_state guard
    that caused styles to vanish on rerun. CSS in <style> tags is
    idempotent."""
    _render_html_block(_AI_ANALYSIS_CSS)


def _verdict_to_score_class(verdict: str, prefix: str) -> str:
    """e.g. _verdict_to_score_class("validating", "ai-card-validation-num")
    → "ai-card-validation-num-validating"."""
    return f"{prefix}-{verdict}"


# ----------------------------------------------------------------------------
# v1.10.5 — topic grouping helpers
# ----------------------------------------------------------------------------

def _resolve_topic_key(thesis: dict) -> str:
    """Return the topic slug for a thesis, defaulting to 'uncategorized'
    if missing or unknown."""
    key = thesis.get("topic") or "uncategorized"
    if key not in AI_TOPIC_REGISTRY:
        return "uncategorized"
    return key


def _group_thesis_results_by_topic(thesis_results: list[dict]) -> list[dict]:
    """Group the [{thesis, validation}] list into topic buckets, sorted
    by AI_TOPIC_REGISTRY[topic]['display_order'].

    Returns:
        [
            {
                "key":      "market-direction",
                "config":   <registry entry>,
                "items":    [{thesis, validation}, ...],
                "stats":    <output of _compute_topic_stats>,
            },
            ...
        ]

    Empty topics are skipped (only topics with at least one thesis appear).
    """
    buckets: dict[str, list[dict]] = {}
    for tr in thesis_results:
        key = _resolve_topic_key(tr["thesis"])
        buckets.setdefault(key, []).append(tr)

    groups: list[dict] = []
    for key, items in buckets.items():
        cfg = AI_TOPIC_REGISTRY.get(key, AI_TOPIC_REGISTRY["uncategorized"])
        stats = _compute_topic_stats(key, items)
        groups.append({"key": key, "config": cfg, "items": items, "stats": stats})

    groups.sort(key=lambda g: g["config"].get("display_order", 999))
    return groups


def _compute_topic_stats(topic_key: str, items: list[dict]) -> dict:
    """Compute aggregate metrics for a topic group:
        avg_score, avg_verdict, distribution, strongest, weakest,
        avg_trend_arrow, ready_count.
    """
    scores: list[float] = []
    distribution = {"validating": 0, "neutral": 0, "diverging": 0}
    strongest_pair: tuple[float, dict] | None = None
    weakest_pair: tuple[float, dict] | None = None
    ready_count = 0

    for tr in items:
        v = tr["validation"]
        if not v.get("ready"):
            continue
        ready_count += 1
        s = float(v.get("thesis_score", 50))
        scores.append(s)
        verdict = v.get("verdict", "neutral")
        distribution[verdict] = distribution.get(verdict, 0) + 1
        if strongest_pair is None or s > strongest_pair[0]:
            strongest_pair = (s, tr["thesis"])
        if weakest_pair is None or s < weakest_pair[0]:
            weakest_pair = (s, tr["thesis"])

    avg_score = sum(scores) / len(scores) if scores else 50.0

    if avg_score >= 65:
        avg_verdict = "validating"
    elif avg_score >= 40:
        avg_verdict = "neutral"
    else:
        avg_verdict = "diverging"

    # Aggregate 7-day trend = avg of per-thesis trend deltas
    history = st.session_state.get(_ai_thesis_history_key(), {})
    deltas: list[float] = []
    for tr in items:
        thesis_id = tr["thesis"].get("id", "")
        h = history.get(thesis_id, [])
        if len(h) >= 2:
            earliest = h[max(0, len(h) - 7)]
            current = h[-1]
            deltas.append(current.get("score", 50) - earliest.get("score", 50))
    if deltas:
        avg_delta = sum(deltas) / len(deltas)
        if avg_delta >= 5:
            avg_trend_arrow = ("↑", "ai-trend-up", f"7日 +{avg_delta:.0f}")
        elif avg_delta <= -5:
            avg_trend_arrow = ("↓", "ai-trend-down", f"7日 {avg_delta:.0f}")
        else:
            avg_trend_arrow = ("→", "ai-trend-flat", f"7日 {avg_delta:+.0f}")
    else:
        avg_trend_arrow = ("·", "ai-trend-pending", "資料累積中")

    return {
        "avg_score": round(avg_score, 1),
        "avg_verdict": avg_verdict,
        "distribution": distribution,
        "strongest": strongest_pair[1] if strongest_pair else None,
        "strongest_score": strongest_pair[0] if strongest_pair else None,
        "weakest": weakest_pair[1] if weakest_pair else None,
        "weakest_score": weakest_pair[0] if weakest_pair else None,
        "avg_trend_arrow": avg_trend_arrow,
        "ready_count": ready_count,
    }


def _resolve_master_toggle() -> str | None:
    """Read the optional ?ai_topics=expand-all|collapse-all URL param."""
    try:
        params = st.query_params
        val = params.get("ai_topics")
    except Exception:
        return None
    if not val:
        return None
    if isinstance(val, list):
        val = val[0] if val else None
    if val in ("expand-all", "collapse-all"):
        st.session_state["_ai_topics_master"] = val
        try:
            params.pop("ai_topics", None)
        except Exception:
            pass
        return val
    return None


def _topic_should_default_open(stats: dict) -> bool:
    """Auto-expand: low avg_score (diverging) opens, high collapses.
    The whole point is to surface what needs attention."""
    return stats["avg_score"] < 50


def _topic_open_state(topic_key: str, stats: dict) -> bool:
    """Order of precedence:
        1. Master toggle (URL param or session override)
        2. Auto rule (low score = open)
    """
    master = _resolve_master_toggle() or st.session_state.get("_ai_topics_master")
    if master == "expand-all":
        return True
    if master == "collapse-all":
        return False
    return _topic_should_default_open(stats)


def _render_topic_summary_html(group: dict, lang_zh: bool, block_kind: str = "cards") -> str:
    """Render the always-visible topic header (the <summary>).

    v1.10.7: Two-line layout that gives readers enough info to prioritize
    attention without expanding:
        line 1: emoji · topic name · big avg score · trend arrow · tagline · toggle
        line 2: ✅ X 驗證 · 🟡 X 中性 · ❌ X 脫離  ·  💪 / ⚠️ extreme thesis hint

    block_kind controls which extreme thesis is highlighted:
        "cards"   → 💪 strongest (browse the most-validating one first)
        "tracker" → ⚠️ weakest   (drill into the most-diverging one first)
    """
    cfg = group["config"]
    stats = group["stats"]
    emoji = cfg.get("emoji", "🗂")
    label = cfg.get("label_zh") if lang_zh else cfg.get("label_en")
    tagline = cfg.get("tagline_zh") if lang_zh else cfg.get("tagline_en")

    avg_num = stats["avg_score"]
    avg_verdict = stats["avg_verdict"]
    arrow, trend_class, trend_label = stats["avg_trend_arrow"]
    dist = stats["distribution"]
    n_theses = len(group["items"])

    if lang_zh:
        n_label = f"{n_theses} 篇"
        v_label = "驗證"
        n_label_neutral = "中性"
        d_label = "脫離"
        strong_label = "💪 強"
        weak_label = "⚠️ 弱"
    else:
        n_label = f"{n_theses}"
        v_label = "validating"
        n_label_neutral = "neutral"
        d_label = "diverging"
        strong_label = "💪 Strongest"
        weak_label = "⚠️ Weakest"

    # Distribution chips
    dist_html = (
        f'<span class="ai-topic-distribution">'
        f'  <span class="ai-topic-dist-item ai-topic-dist-item-validating">✅ {dist["validating"]} {escape(v_label)}</span>'
        f'  <span class="ai-topic-meta-divider">·</span>'
        f'  <span class="ai-topic-dist-item ai-topic-dist-item-neutral">🟡 {dist["neutral"]} {escape(n_label_neutral)}</span>'
        f'  <span class="ai-topic-meta-divider">·</span>'
        f'  <span class="ai-topic-dist-item ai-topic-dist-item-diverging">❌ {dist["diverging"]} {escape(d_label)}</span>'
        f'</span>'
    )

    # Pick the right extreme thesis to highlight based on block_kind
    extreme_html = ""
    strongest = stats.get("strongest")
    weakest = stats.get("weakest")

    if block_kind == "cards":
        # Show strongest first (the "best news" of the topic)
        if strongest:
            s_score = stats.get("strongest_score") or 0
            extreme_html = (
                f'<span class="ai-topic-extreme-hint ai-topic-extreme-hint-strong">'
                f'{escape(strong_label)}:{escape(str(strongest.get("title", "")))} '
                f'<strong>({s_score:.0f})</strong>'
                f'</span>'
            )
    else:
        # tracker — show weakest (where to drill in for problems)
        if weakest:
            w_score = stats.get("weakest_score") or 0
            extreme_html = (
                f'<span class="ai-topic-extreme-hint ai-topic-extreme-hint-weak">'
                f'{escape(weak_label)}:{escape(str(weakest.get("title", "")))} '
                f'<strong>({w_score:.0f})</strong>'
                f'</span>'
            )

    # Edge case: only 1 thesis means strongest == weakest, just show it once
    if n_theses == 1 and extreme_html:
        the_one = strongest if block_kind == "cards" else weakest
        the_score = stats.get("strongest_score" if block_kind == "cards" else "weakest_score") or 0
        extreme_html = (
            f'<span class="ai-topic-extreme-hint">'
            f'{escape(str(the_one.get("title", "")))} '
            f'<strong>({the_score:.0f})</strong>'
            f'</span>'
        )

    # Compose the meta-line: distribution + middle dot + extreme hint
    if extreme_html:
        meta_line_html = (
            f'<div class="ai-topic-meta-line">'
            f'  {dist_html}'
            f'  <span class="ai-topic-meta-divider">·</span>'
            f'  {extreme_html}'
            f'</div>'
        )
    else:
        meta_line_html = (
            f'<div class="ai-topic-meta-line">{dist_html}</div>'
        )

    return textwrap.dedent(f"""
        <summary class="ai-topic-summary">
            <div class="ai-topic-head-line">
                <span class="ai-topic-emoji">{emoji}</span>
                <span class="ai-topic-label">{escape(label or "")}</span>
                <span class="ai-topic-avg-score">
                    <span class="ai-topic-avg-num ai-topic-avg-{escape(avg_verdict)}">{avg_num:.0f}</span>
                    <span class="ai-topic-trend-pill {escape(trend_class)}">{arrow} {escape(trend_label)}</span>
                </span>
                <span class="ai-topic-tagline">{escape(tagline or "")} · {n_label}</span>
                <span class="ai-topic-toggle"></span>
            </div>
            {meta_line_html}
        </summary>
    """).strip()


def _render_master_toggle_row_html(lang_zh: bool) -> str:
    """The "expand all / collapse all" row above the topic stack."""
    if lang_zh:
        hint = "💡 低驗證分(<50)的主題預設展開,高驗證分預設收起"
        expand_all = "全部展開"
        collapse_all = "全部收起"
    else:
        hint = "💡 Topics with avg score <50 auto-expand; ≥50 auto-collapse"
        expand_all = "Expand all"
        collapse_all = "Collapse all"
    return textwrap.dedent(f"""
        <div class="ai-master-toggle-row">
            <span class="ai-master-hint">{escape(hint)}</span>
            <a class="ai-master-toggle-btn" href="?ai_topics=expand-all" target="_self">▼ {escape(expand_all)}</a>
            <a class="ai-master-toggle-btn" href="?ai_topics=collapse-all" target="_self">▶ {escape(collapse_all)}</a>
        </div>
    """).strip()


def _render_ai_card_html(thesis: dict, validation: dict, lang_zh: bool) -> str:
    """Render one thesis card."""
    title = thesis.get("title", "")
    summary = thesis.get("summary", "")
    cross = thesis.get("cross_validation", "")
    risk = thesis.get("risk", "")
    claimed = thesis.get("claimed_probability", 50)
    score = validation.get("thesis_score", 50)
    verdict = validation.get("verdict", "neutral")

    arrow, trend_class, trend_label = _thesis_trend_arrow(thesis.get("id", ""), score)

    # Truncate cross + risk for the card view (full text shows in tracker if needed)
    def trim(s: str, n: int) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else s[:n - 1] + "…"

    label_summary = "解說重點" if lang_zh else "Summary"
    label_cross = "交叉驗證" if lang_zh else "Cross-validation"
    label_risk = "風險 / 反證" if lang_zh else "Risk"
    label_validation = "目前驗證" if lang_zh else "Validation"
    label_claimed = "推估成立" if lang_zh else "Claimed"

    return textwrap.dedent(f"""
        <div class="ai-card">
            <div class="ai-card-header">
                <div class="ai-card-title">{escape(title)}</div>
                <div class="ai-card-prob-pill ai-card-prob-{escape(verdict)}">
                    {label_claimed} {claimed}%
                </div>
            </div>
            <div class="ai-card-section">
                <div class="ai-card-section-label">{escape(label_summary)}</div>
                {escape(trim(summary, 220))}
            </div>
            <div class="ai-card-section ai-card-section-cross">
                <div class="ai-card-section-label">{escape(label_cross)}</div>
                {escape(trim(cross, 240))}
            </div>
            <div class="ai-card-section ai-card-section-risk">
                <div class="ai-card-section-label">{escape(label_risk)}</div>
                {escape(trim(risk, 200))}
            </div>
            <div class="ai-card-validation-bar">
                <div class="ai-card-validation-num ai-card-validation-num-{escape(verdict)}">{score:.0f}</div>
                <div class="ai-card-validation-label">
                    {escape(label_validation)} %<br/>
                    <span style="opacity:.7">vs {label_claimed} {claimed}%</span>
                </div>
                <div class="ai-card-validation-trend {escape(trend_class)}">
                    {arrow} {escape(trend_label)}
                </div>
            </div>
        </div>
    """).strip()


def _render_ai_synthesis_html(synthesis: dict, lang_zh: bool, daily_data=None) -> str:
    """Render the synthesis (AI 整體判斷) block as a card grid.

    v1.10.10: Each paragraph now renders as its own card (matching the
    AI 論點卡片 visual language) so the layout scales gracefully as the
    user adds more paragraphs over time. Each card has:
        * Lead text as the title
        * Body text as the supporting prose
        * Validation chip at the bottom (score + verdict color + 7-day trend)

    daily_data is the same MultiIndex DataFrame used by thesis validation.
    Pass None to skip validation rendering (graceful degradation).
    """
    headline = (synthesis.get("headline") if lang_zh else synthesis.get("headline_en")) \
               or synthesis.get("headline", "")
    intro = (synthesis.get("intro") if lang_zh else synthesis.get("intro_en")) \
            or synthesis.get("intro", "")
    issued = synthesis.get("issued_date", "")
    paragraphs = synthesis.get("paragraphs") or []

    # ----- Compute per-paragraph validation scores -----
    para_validations: list[dict] = []
    for idx, p in enumerate(paragraphs):
        if p.get("validation_points") and daily_data is not None:
            v = compute_thesis_validation_score(p, daily_data)
            if v.get("ready"):
                _record_thesis_score_today(f"synthesis-{idx}", v["thesis_score"])
            para_validations.append(v)
        else:
            para_validations.append({"thesis_score": 0, "verdict": "neutral",
                                     "ready": False, "points": []})

    # ----- Block-level aggregate -----
    weighted_sum = 0.0
    weight_total = 0.0
    ready_count = 0
    for v in para_validations:
        if v.get("ready"):
            ready_count += 1
            weighted_sum += v["thesis_score"]
            weight_total += 1
    block_avg = weighted_sum / weight_total if weight_total > 0 else 50.0

    if block_avg >= 65:
        block_verdict = "validating"
    elif block_avg >= 40:
        block_verdict = "neutral"
    else:
        block_verdict = "diverging"

    # 7-day trend for the block
    history = st.session_state.get(_ai_thesis_history_key(), {})
    deltas = []
    for idx in range(len(paragraphs)):
        h = history.get(f"synthesis-{idx}", [])
        if len(h) >= 2:
            earliest = h[max(0, len(h) - 7)]
            current = h[-1]
            deltas.append(current.get("score", 50) - earliest.get("score", 50))
    if deltas:
        avg_delta = sum(deltas) / len(deltas)
        if avg_delta >= 5:
            block_arrow = ("↑", "ai-trend-up", f"7日 +{avg_delta:.0f}")
        elif avg_delta <= -5:
            block_arrow = ("↓", "ai-trend-down", f"7日 {avg_delta:.0f}")
        else:
            block_arrow = ("→", "ai-trend-flat", f"7日 {avg_delta:+.0f}")
    else:
        block_arrow = ("·", "ai-trend-pending", "資料累積中" if lang_zh else "Building")

    # ----- Header HTML -----
    block_chip_html = ""
    if ready_count > 0:
        b_arrow, b_class, b_label = block_arrow
        block_chip_html = (
            f'<span class="ai-synthesis-headline-score">'
            f'  <span class="ai-synthesis-headline-score-num ai-synthesis-headline-score-num-{escape(block_verdict)}">{block_avg:.0f}</span>'
            f'  <span class="ai-card-validation-trend {escape(b_class)}">{b_arrow} {escape(b_label)}</span>'
            f'</span>'
        )

    issued_html = (
        f'<span class="ai-synthesis-issued">'
        + (f'發布 {escape(issued)}' if lang_zh else f'Issued {escape(issued)}')
        + '</span>'
        if issued else '<span class="ai-synthesis-issued"></span>'
    )

    # ----- Per-paragraph cards -----
    label_validation = "目前驗證" if lang_zh else "Validation"
    label_no_data = "暫無驗證點(可日後補上)" if lang_zh else "No validation points yet"
    label_pos_tag = "判斷"  # used as the small "uppercase" tag at top

    card_html_parts: list[str] = []
    for idx, p in enumerate(paragraphs):
        v = para_validations[idx]
        lead = p.get("lead", "")
        body = p.get("body", "")

        # Card border color depends on verdict (or neutral if no validation)
        if v.get("ready"):
            verdict = v.get("verdict", "neutral")
            border_class = f"ai-synthesis-card-{verdict}"
        else:
            verdict = None
            border_class = "ai-synthesis-card-no-validation"

        # Validation bar at the bottom
        validation_bar_html = ""
        if v.get("ready"):
            score = v.get("thesis_score", 50)
            arrow, trend_class, trend_label = _thesis_trend_arrow(
                f"synthesis-{idx}", score
            )
            validation_bar_html = (
                f'<div class="ai-synthesis-card-validation-bar">'
                f'  <div class="ai-synthesis-card-validation-num ai-synthesis-card-validation-num-{escape(verdict)}">{score:.0f}</div>'
                f'  <div class="ai-synthesis-card-validation-label">'
                f'    {escape(label_validation)} %'
                f'  </div>'
                f'  <div class="ai-synthesis-card-validation-trend {escape(trend_class)}">'
                f'    {arrow} {escape(trend_label)}'
                f'  </div>'
                f'</div>'
            )
        else:
            # No validation: small italic hint instead of a bar
            validation_bar_html = (
                f'<div class="ai-synthesis-card-no-data-hint">{escape(label_no_data)}</div>'
            )

        # Tag prefix for the card (e.g. 第一 / 第二 / 第三 — auto-generated)
        if lang_zh:
            tag_text = ["第一", "第二", "第三", "第四", "第五", "第六", "第七", "第八"][idx] \
                       if idx < 8 else f"第{idx+1}"
        else:
            tag_text = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"][idx] \
                       if idx < 8 else f"#{idx+1}"

        card_html_parts.append(
            f'<div class="ai-synthesis-card {border_class}">'
            f'  <div class="ai-synthesis-card-tag">{escape(tag_text)}</div>'
            f'  <div class="ai-synthesis-card-lead">{escape(lead)}</div>'
            f'  <div class="ai-synthesis-card-body">{escape(body)}</div>'
            f'  {validation_bar_html}'
            f'</div>'
        )

    cards_html = "".join(card_html_parts)

    return textwrap.dedent(f"""
        <div class="ai-synthesis-shell">
            <div class="ai-synthesis-head-row">
                <div class="ai-synthesis-headline">🧭 {escape(headline)}</div>
                {block_chip_html}
                {issued_html}
            </div>
            <div class="ai-synthesis-intro">{escape(intro)}</div>
            <div class="ai-synthesis-cards-grid">
                {cards_html}
            </div>
        </div>
    """).strip()


def _render_ai_validation_tracker_html(thesis_results: list[dict], lang_zh: bool) -> str:
    """Render the multi-thesis validation tracker.

    v1.10.7: Now uses the SAME collapsible-by-topic structure as the
    cards block. Each topic is its own <details> element with a
    rich summary header (matching the cards block, but highlighting
    ⚠️ weakest instead of 💪 strongest, since the tracker is where
    you drill in to fix problems).

    Auto-expand state is shared with the cards block: a topic open
    in the cards is also open in the tracker, and vice versa.
    """
    if lang_zh:
        col_label, col_value, col_score, col_interp = "驗證點", "目前數值", "符合 %", "解讀"
        title = "📊 每日驗證表"
        subtitle = "依主題分組;同樣依驗證分自動展開。每個論點分數 = 各驗證點加權平均"
    else:
        col_label, col_value, col_score, col_interp = "Point", "Latest", "Score %", "Read"
        title = "📊 Daily Validation Tracker"
        subtitle = "Grouped by topic; auto-expands by score. Score = weighted avg of validation points"

    header_row = (
        f'<div class="ai-tracker-row ai-tracker-row-header">'
        f'  <div>{escape(col_label)}</div>'
        f'  <div>{escape(col_value)}</div>'
        f'  <div>{escape(col_score)}</div>'
        f'  <div>{escape(col_interp)}</div>'
        f'</div>'
    )

    # Build one <details> accordion per topic
    groups = _group_thesis_results_by_topic(thesis_results)
    accordions_html: list[str] = []
    for group in groups:
        is_open = _topic_open_state(group["key"], group["stats"])
        open_attr = " open" if is_open else ""
        summary_html = _render_topic_summary_html(group, lang_zh, block_kind="tracker")

        # Build the rows for this topic only
        topic_rows: list[str] = [header_row]
        for tr in group["items"]:
            thesis = tr["thesis"]
            v = tr["validation"]
            verdict = v.get("verdict", "neutral")
            score = v.get("thesis_score", 50)
            arrow, trend_class, trend_label = _thesis_trend_arrow(thesis.get("id", ""), score)

            # Thesis-level summary row
            topic_rows.append(
                f'<div class="ai-tracker-row ai-tracker-row-thesis ai-thesis-{escape(verdict)}">'
                f'  <div class="ai-tracker-thesis-line">'
                f'    <span class="ai-tracker-thesis-title">{escape(thesis.get("title", ""))}</span>'
                f'    <span class="ai-tracker-thesis-score ai-card-validation-num-{escape(verdict)}">{score:.0f}</span>'
                f'    <span class="ai-card-validation-trend {escape(trend_class)}">{arrow} {escape(trend_label)}</span>'
                f'  </div>'
                f'</div>'
            )

            # Per-point detail rows
            for p in v.get("points") or []:
                p_score = p.get("score", 50)
                if p_score >= 65:
                    pv = "validating"
                elif p_score >= 40:
                    pv = "neutral"
                else:
                    pv = "diverging"
                fill_pct = max(0.0, min(100.0, p_score))
                topic_rows.append(
                    f'<div class="ai-tracker-row">'
                    f'  <div class="ai-tracker-cell-label">{escape(p.get("label", ""))}</div>'
                    f'  <div class="ai-tracker-cell-value">{escape(p.get("value_text", "—"))}</div>'
                    f'  <div class="ai-tracker-cell-score">'
                    f'    <span class="ai-tracker-score-num">{p_score:.0f}</span>'
                    f'    <div class="ai-tracker-score-bar">'
                    f'      <div class="ai-tracker-score-fill ai-tracker-score-fill-{escape(pv)}" style="width:{fill_pct:.0f}%"></div>'
                    f'    </div>'
                    f'  </div>'
                    f'  <div class="ai-tracker-cell-interp">{escape(p.get("interpretation", ""))}</div>'
                    f'</div>'
                )

        accordions_html.append(textwrap.dedent(f"""
            <details class="ai-topic-section"{open_attr}>
                {summary_html}
                <div class="ai-topic-body">
                    <div class="ai-tracker-table-segment">
                        {''.join(topic_rows)}
                    </div>
                </div>
            </details>
        """).strip())

    return textwrap.dedent(f"""
        <div class="ai-validation-tracker">
            <div class="ai-share-section-head" style="margin-top:0">
                <div class="ai-share-section-title">{escape(title)}</div>
            </div>
            <div class="ai-share-section-meta" style="margin-bottom:8px">{escape(subtitle)}</div>
            <div class="ai-tracker-shell-grouped">
                {''.join(accordions_html)}
            </div>
        </div>
    """).strip()


def render_ai_analysis_share_dashboard() -> None:
    """Top-level entry for the 🤖 AI 分析分享 Dashboard. Called from
    generate_dashboard when:
      dashboard_mode == "General Market"
      AND dashboard_experience_level == "beginner"
    """
    lang_zh = _news_briefing_is_zh()
    _ensure_ai_analysis_css()

    # 1. Fetch the universe of tickers used by the validation calculators
    needed_tickers: set[str] = {"^TWII", "2330.TW"}  # always need these
    for thesis in AI_ANALYSIS_THESES:
        for point in thesis.get("validation_points", []) or []:
            t = point.get("ticker")
            if t:
                needed_tickers.add(t)
    # v1.10.9: Synthesis paragraphs also have validation_points
    for para in (AI_ANALYSIS_SYNTHESIS.get("paragraphs") or []):
        for point in para.get("validation_points", []) or []:
            t = point.get("ticker")
            if t:
                needed_tickers.add(t)

    try:
        daily_data = _fetch_daily_data(sorted(needed_tickers), "3mo", "1d")
    except Exception:
        daily_data = None

    # 2. Compute validation per thesis
    thesis_results: list[dict] = []
    for thesis in AI_ANALYSIS_THESES:
        validation = compute_thesis_validation_score(thesis, daily_data)
        # Persist today's score for the trend arrow
        if validation.get("ready"):
            _record_thesis_score_today(thesis.get("id", ""), validation["thesis_score"])
        thesis_results.append({"thesis": thesis, "validation": validation})

    # ----- Block 1: AI 論點卡片 (v1.10.5: now grouped by topic) -----
    section_title = "📋 AI 論點卡片" if lang_zh else "📋 AI Theses"
    section_meta = (
        "依主題分組;低驗證分主題自動展開,點主題標頭可折疊 / 展開"
        if lang_zh else
        "Grouped by topic; low-score topics auto-expand. Click any header to fold/unfold."
    )
    head_html = textwrap.dedent(f"""
        <div class="ai-share-shell">
            <div class="ai-share-section-head" style="margin-top:0">
                <div class="ai-share-section-title">{escape(section_title)}</div>
                <div class="ai-share-section-meta">{escape(section_meta)}</div>
            </div>
    """).strip()
    _render_html_block(head_html)

    # Master expand-all / collapse-all toggle row
    _render_html_block(_render_master_toggle_row_html(lang_zh))

    # Group + render each topic as a <details> accordion
    groups = _group_thesis_results_by_topic(thesis_results)
    for group in groups:
        is_open = _topic_open_state(group["key"], group["stats"])
        open_attr = " open" if is_open else ""
        summary_html = _render_topic_summary_html(group, lang_zh, block_kind="cards")
        cards_html = "".join(
            _render_ai_card_html(tr["thesis"], tr["validation"], lang_zh)
            for tr in group["items"]
        )
        section_html = textwrap.dedent(f"""
            <details class="ai-topic-section"{open_attr}>
                {summary_html}
                <div class="ai-topic-body">
                    <div class="ai-cards-grid">
                        {cards_html}
                    </div>
                </div>
            </details>
        """).strip()
        _render_html_block(section_html)

    _render_html_block("</div>")  # close ai-share-shell

    # ----- Block 2: 整體判斷 -----
    if AI_ANALYSIS_SYNTHESIS:
        _render_html_block(_render_ai_synthesis_html(AI_ANALYSIS_SYNTHESIS, lang_zh, daily_data=daily_data))

    # ----- Block 3: 每日驗證表 -----
    _render_html_block(_render_ai_validation_tracker_html(thesis_results, lang_zh))

    # Footer
    foot = (
        "💡 編輯 AI_ANALYSIS_THESES 來新增 / 修改論點;每張卡片的「目前驗證」分數每天從真實市場數據動態計算"
        if lang_zh else
        "Edit AI_ANALYSIS_THESES to add / modify theses. Validation scores recompute daily from market data."
    )
    _render_html_block(f'<div class="ai-share-foot">{escape(foot)}</div>')
