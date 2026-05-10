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
# v1.10.11 — Local JSON persistence for user-added theses + synthesis
# ----------------------------------------------------------------------------
# We store user-added items in `ai_analysis_data.json` in the same directory
# as this module. This file is created on first save and read every render.
# We deliberately skip caching so multiple Streamlit instances pointing at
# the same shared filesystem (e.g. Docker volume) stay in sync.
#
# Schema:
#   {
#     "user_theses":    [thesis_dict, ...],
#     "user_synthesis": [paragraph_dict, ...]
#   }
#
# Each user-added item gets an id prefixed "user-<unix-timestamp>" so it
# never clashes with built-in IDs.
# ----------------------------------------------------------------------------

import json
import os
import re
import time as _time

_USER_DATA_FILENAME = "ai_analysis_data.json"


def _user_data_path() -> str:
    """Absolute path to the JSON data file (alongside this module)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _USER_DATA_FILENAME)


def _load_user_data() -> dict:
    """Read user-added data from disk. Returns empty structure if file
    doesn't exist or is unreadable."""
    path = _user_data_path()
    if not os.path.exists(path):
        return {"user_theses": [], "user_synthesis": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Defensive: ensure both keys exist
        if not isinstance(data, dict):
            return {"user_theses": [], "user_synthesis": []}
        data.setdefault("user_theses", [])
        data.setdefault("user_synthesis", [])
        if not isinstance(data["user_theses"], list):
            data["user_theses"] = []
        if not isinstance(data["user_synthesis"], list):
            data["user_synthesis"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"user_theses": [], "user_synthesis": []}


def _save_user_data(data: dict) -> bool:
    """Write user-added data to disk using atomic rename. Returns True on
    success, False on failure."""
    path = _user_data_path()
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)  # atomic on POSIX
        return True
    except OSError:
        # Best-effort cleanup
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


def _make_user_id(prefix: str = "user") -> str:
    """Generate a TRULY unique ID for a new user-added item.

    v1.10.20: Switched from int(time()) (second precision) to
    time.time_ns() (nanosecond) + 4-digit random suffix. Previously,
    a batch-import loop processing 9 theses in a fraction of a second
    produced 9 identical IDs because they all rounded to the same
    second. Nanosecond precision + random suffix makes collision
    practically impossible.
    """
    import random
    return f"{prefix}-{_time.time_ns()}-{random.randint(1000, 9999)}"


# Smart detection — light heuristic, just to give the user clickable
# starting-point chips. Not authoritative.
# v1.10.12: Removed \b (word boundary) for CJK compat — Chinese chars
# don't form word boundaries with ASCII digits properly. Use lookaround
# instead: not preceded by another digit (so we don't break 1,234,567).
_RE_INDEX_THRESHOLD = re.compile(r"(?<!\d)(\d{2},\d{3}|\d{4,5})(?!\d)")
_RE_TICKER_TW_LONG = re.compile(r"(?<!\d)(\d{4})\.TW(?!\d)")
_RE_TICKER_TW_BARE = re.compile(r"(?<!\d)(\d{4})(?!\d|\.\d|\.TW)")
_RE_PERCENT = re.compile(r"([+\-]?\d+(?:\.\d+)?)\s*%")
_RE_HORIZON_KEYWORD = re.compile(r"(本週|本月|下週|下個月|月底|520|6/30|7月底|半年|年底)")


def _smart_detect(text: str) -> dict:
    """Light regex-based hints for filling in form fields.

    Returns {
        "thresholds": [int, ...],     # candidate index levels
        "tickers":    [str, ...],     # candidate stock tickers (with .TW suffix)
        "percents":   [float, ...],   # candidate rally_min_pct values
        "horizons":   [str, ...],     # raw horizon keywords found
    }
    """
    if not text:
        return {"thresholds": [], "tickers": [], "percents": [], "horizons": []}

    thresholds: list[int] = []
    for m in _RE_INDEX_THRESHOLD.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            n = int(raw)
            # filter sensible index thresholds (10,000 - 60,000 cover TWII range)
            if 10000 <= n <= 60000:
                thresholds.append(n)
        except ValueError:
            pass

    tickers: set[str] = set()
    for m in _RE_TICKER_TW_LONG.finditer(text):
        tickers.add(f"{m.group(1)}.TW")
    # Bare 4-digits — only catch ones not already prefixed with .TW
    for m in _RE_TICKER_TW_BARE.finditer(text):
        n = m.group(1)
        # Avoid pulling out things that were really thresholds (already in thresholds)
        if int(n) in thresholds:
            continue
        # Sensible TW stock code range: 1000-9999, exclude obvious year-like
        if 1000 <= int(n) <= 9999 and n not in {"2024", "2025", "2026", "2027"}:
            tickers.add(f"{n}.TW")

    percents: list[float] = []
    for m in _RE_PERCENT.finditer(text):
        try:
            p = float(m.group(1))
            if -50 <= p <= 50:
                percents.append(p)
        except ValueError:
            pass

    horizons: list[str] = []
    for m in _RE_HORIZON_KEYWORD.finditer(text):
        h = m.group(1)
        if h not in horizons:
            horizons.append(h)

    # Dedupe preserving order
    return {
        "thresholds": list(dict.fromkeys(thresholds)),
        "tickers":    sorted(tickers),
        "percents":   list(dict.fromkeys(percents)),
        "horizons":   horizons,
    }


# ----------------------------------------------------------------------------
# v1.10.12 — Batch import parsers (TSV / CSV → thesis dicts)
# ----------------------------------------------------------------------------
# User's natural workflow: after a video, they fill out a structured table
# (one row per thesis) in Google Docs / Excel. We accept that table directly
# via paste (TSV) or upload (CSV), parse rows into thesis dicts, and
# auto-seed validation_points.
# ----------------------------------------------------------------------------

# Probability parsing — handles user's natural language patterns:
#   "高,約65%以上"      → 75
#   "中高,約60-65%"     → 62
#   "中,約55-60%"       → 57
#   "中偏低,約35-45%"   → 40
#   "低,約30%"          → 30
# Strategy: extract first percent value or range, average a range.
_RE_PROB_NUM = re.compile(r"(\d+)\s*[\-–~到]\s*(\d+)\s*%|(\d+)\s*%")


def _parse_probability(text: str) -> int:
    """Convert a user's probability description to an int 0-100.
    Examples:
        "高,約65%以上"     → 75
        "中高,約60-65%"    → 62
        "中,約55-60%"      → 57
        "中偏低,約35-45%"  → 40
        "低,約30%"         → 30
        "ASIC題材成立:中高,約65-70%;5,000元短中期達標:中,約45-55%"
                              → 67 (first % match)
    Falls back to 50 if no parseable percent found.
    """
    if not text:
        return 50
    m = _RE_PROB_NUM.search(text)
    if not m:
        # Try keyword fallback
        s = text.strip()
        if s.startswith("高"):    return 75
        if s.startswith("中高"):  return 62
        if "中偏低" in s:         return 40
        if s.startswith("中"):    return 55
        if s.startswith("低"):    return 30
        return 50
    if m.group(1) and m.group(2):
        # Range like "65-70%" — take midpoint
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2
    if m.group(3):
        # Single value like "65%". If it's stated as "以上", lift slightly.
        n = int(m.group(3))
        if "以上" in text or "更高" in text:
            return min(100, n + 10)
        return n
    return 50


# Topic auto-detection from title — used when user leaves the topic
# column blank. Order matters: more-specific keywords first.
def _auto_detect_topic(title: str, summary: str = "") -> str:
    """Guess a topic key from the title (and optionally summary).
    Returns an entry in AI_TOPIC_REGISTRY (excluding 'uncategorized')."""
    haystack = f"{title} {summary}".lower()
    # ETF-specific tickers / phrases
    if any(k in haystack for k in ["0050", "0056", "00878", "00919", "00929", "etf"]):
        return "etf-flow"
    # Chinese characters
    haystack_zh = f"{title} {summary}"
    if any(k in haystack_zh for k in ["0050", "0056", "ETF"]):
        return "etf-flow"
    # Macro narrative
    if any(k in haystack_zh for k in ["AI", "半導體", "晶片", "ABF", "光寶", "聯發科",
                                       "ASIC", "台積", "景碩", "權值股"]):
        return "macro-narrative"
    # Volume / positioning
    if any(k in haystack_zh for k in ["外資", "成交量", "量縮", "量增", "籌碼",
                                       "融資", "三大法人"]):
        return "volume-positioning"
    # Market direction (most defaults end here)
    if any(k in haystack_zh for k in ["大盤", "加權", "指數", "4萬", "5萬", "點", "突破",
                                       "拉回", "回測", "支撐", "壓力", "崩"]):
        return "market-direction"
    # Stock-trend (single-stock keywords)
    if any(k in haystack_zh for k in ["個股", "目標價"]):
        return "stock-trend"
    # Default
    return "market-direction"


def _auto_generate_validation_points(title: str, cross_validation: str) -> list[dict]:
    """Auto-generate up to 3 validation_points from the cross_validation text.

    v1.10.13: Smarter generation:
        - Multiple index thresholds (e.g. body mentions 41,000 / 42,000 / 45,000)
          → one index_level point per threshold (up to 3, sorted by relevance)
        - Stock ticker(s) detected → one stock_trend point per ticker (up to 2)
        - Percent value mentioned → optional rally_pace point
        - Fallback only when truly nothing detected

    Cap at 3 points total (avoids over-fitting). User edits in preview.
    """
    detected = _smart_detect(cross_validation or "")
    points: list[dict] = []

    # Index-level points: one per threshold, but cap at 2 (avoid clutter)
    # Sort thresholds by appearance order (most relevant first usually)
    thresholds_in_range = [t for t in detected["thresholds"] if t >= 30000]
    for thresh in thresholds_in_range[:2]:
        points.append({
            "type": "index_level",
            "label": f"加權守 {thresh:,}",
            "threshold": thresh,
            "direction": "above",
            "ticker": "^TWII",
            "consec_days": 5,
            "weight": 1.0,
        })

    # Stock-trend points: one per detected ticker (up to 2)
    for ticker in detected["tickers"][:2]:
        if len(points) >= 3:
            break
        ticker_short = ticker.replace(".TW", "")
        points.append({
            "type": "stock_trend",
            "label": f"{ticker_short} 5 日續強",
            "ticker": ticker,
            "pattern": "rally",
            "lookback": 5,
            "rally_min_pct": 2.0,
            "weight": 1.0,
        })

    # Fallback: if nothing detected, use TAIEX rally_pace
    if not points:
        points.append({
            "type": "rally_pace",
            "label": "加權近 10 日漲速合理",
            "ticker": "^TWII",
            "lookback": 10,
            "ideal_min_pct": -2.0,
            "ideal_max_pct": 8.0,
            "weight": 1.0,
        })

    return points


def _parse_table_text(text: str, separator: str = "\t") -> list[dict]:
    """Parse a TSV/CSV blob (with optional header row) into thesis dicts.

    Expected columns (in this order):
        1. 影片可確認主題 / title          [REQUIRED]
        2. 解說重點 / summary              [REQUIRED]
        3. 目前局勢交叉驗證 / cross_validation
        4. 風險 / 反證 / risk
        5. 推估成立機率 / probability
        6. 主題分類 / topic [OPTIONAL]

    Header row (with 影片可確認主題 / title) is auto-detected and skipped.

    Returns a list of dicts with keys: title, summary, cross_validation,
    risk, claimed_probability, topic, validation_points (auto-seeded).
    """
    if not text or not text.strip():
        return []

    rows: list[dict] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]

    for line_idx, line in enumerate(lines):
        cols = [c.strip() for c in line.split(separator)]

        # Skip a header row if the first cell looks like a header
        first = cols[0] if cols else ""
        if line_idx == 0 and any(h in first for h in
                                 ["影片可確認主題", "Title", "title", "主題"]):
            continue

        # Need at least title + summary
        if len(cols) < 2 or not cols[0] or not cols[1]:
            continue

        title = cols[0]
        summary = cols[1]
        cv = cols[2] if len(cols) > 2 else ""
        risk = cols[3] if len(cols) > 3 else ""
        prob_text = cols[4] if len(cols) > 4 else ""
        topic_override = cols[5] if len(cols) > 5 else ""

        prob = _parse_probability(prob_text)

        # Resolve topic
        if topic_override and topic_override in AI_TOPIC_REGISTRY:
            topic = topic_override
        elif topic_override:
            # Try to match by display label
            topic = None
            for k, v in AI_TOPIC_REGISTRY.items():
                if v.get("label_zh") == topic_override or v.get("label_en") == topic_override:
                    topic = k
                    break
            if not topic:
                topic = _auto_detect_topic(title, summary)
        else:
            topic = _auto_detect_topic(title, summary)

        # Auto-generate validation_points from cross_validation text
        vps = _auto_generate_validation_points(title, cv)

        rows.append({
            "title": title,
            "summary": summary,
            "cross_validation": cv,
            "risk": risk,
            "claimed_probability": prob,
            "probability_text_raw": prob_text,
            "topic": topic,
            "validation_points": vps,
        })

    return rows


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
    position: relative;
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

/* v1.10.15 — card-corner action buttons (delete / lock indicator)
   v1.10.19 — repositioned to TOP of card as a full-width banner-style
   tag, so it doesn't overlap with the prob-pill in the header. */
.ai-card-actions {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 2px;
    /* not absolute — sits at top of flex column */
}
.ai-card-action-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 5px;
    font-size: 11.5px;
    font-weight: 600;
    text-decoration: none;
    border: 1px solid rgba(96,110,145,.30);
    background: rgba(96,110,145,.12);
    color: #c2c8d8;
    line-height: 1.4;
    transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.ai-card-action-btn:hover {
    background: rgba(96,110,145,.28);
    color: #f4f6fb;
    border-color: rgba(96,110,145,.55);
}
.ai-card-action-delete {
    color: #f4a3aa;
    border-color: rgba(217,102,112,.40);
    background: rgba(217,102,112,.10);
}
.ai-card-action-delete:hover {
    background: rgba(217,102,112,.25);
    color: #ffd7da;
}
.ai-card-action-confirm {
    color: #ffd7da;
    background: rgba(217,102,112,.45);
    border-color: rgba(217,102,112,.85);
    animation: ai-confirm-pulse 1.2s ease-in-out infinite;
}
@keyframes ai-confirm-pulse {
    0%, 100% { background: rgba(217,102,112,.45); }
    50%      { background: rgba(217,102,112,.65); }
}
.ai-card-action-locked {
    color: #98a2b8;
    background: rgba(96,110,145,.12);
    border-color: rgba(96,110,145,.18);
    cursor: default;
    font-style: italic;
}
.ai-card-action-locked:hover {
    background: rgba(96,110,145,.12);
    color: #98a2b8;
    border-color: rgba(96,110,145,.18);
}

/* v1.10.19 — User-added badge (display-only; actions moved to manager panel) */
.ai-card-action-user {
    color: #8be8b1;
    background: rgba(76,208,168,.12);
    border-color: rgba(76,208,168,.30);
    cursor: default;
}
.ai-card-action-user:hover {
    background: rgba(76,208,168,.12);
    color: #8be8b1;
    border-color: rgba(76,208,168,.30);
}

/* v1.10.16 — multi-select states */
.ai-card-action-select {
    color: #c2c8d8;
    border-color: rgba(96,110,145,.30);
    background: rgba(96,110,145,.10);
}
.ai-card-action-select:hover {
    background: rgba(96,110,145,.25);
    color: #f4f6fb;
}
.ai-card-action-selected {
    color: #ffd7da;
    background: rgba(217,102,112,.40);
    border-color: rgba(217,102,112,.75);
    font-weight: 700;
}
.ai-card-action-selected:hover {
    background: rgba(217,102,112,.55);
    color: #fff;
}

/* Sticky selection bar (visible when at least one item selected) */
.ai-selection-bar {
    background: linear-gradient(180deg, rgba(35,18,28,.95), rgba(28,12,22,.95));
    border: 1px solid rgba(217,102,112,.55);
    border-radius: 10px;
    padding: 10px 16px;
    margin: 14px 0 18px 0;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    box-shadow: 0 4px 20px rgba(217,102,112,.15);
}
.ai-selection-count {
    font-size: 14px;
    color: #ffd7da;
    font-weight: 700;
}
.ai-selection-count-num {
    font-size: 18px;
    font-variant-numeric: tabular-nums;
}
.ai-selection-actions {
    display: inline-flex;
    gap: 8px;
    margin-left: auto;
}
.ai-selection-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    text-decoration: none;
    border: 1px solid rgba(96,110,145,.40);
    background: rgba(96,110,145,.20);
    color: #c2c8d8;
    transition: background 0.12s;
}
.ai-selection-btn:hover {
    background: rgba(96,110,145,.40);
    color: #f4f6fb;
}
.ai-selection-btn-danger {
    color: #ffd7da;
    background: rgba(217,102,112,.45);
    border-color: rgba(217,102,112,.85);
}
.ai-selection-btn-danger:hover {
    background: rgba(217,102,112,.65);
    color: #fff;
}

/* Confirmation panel (inline modal substitute) */
.ai-delete-confirm-panel {
    background: linear-gradient(180deg, rgba(45,20,30,.98), rgba(35,15,25,.98));
    border: 2px solid rgba(217,102,112,.85);
    border-radius: 12px;
    padding: 18px 22px;
    margin: 18px 0;
    box-shadow: 0 8px 32px rgba(217,102,112,.25);
}
.ai-delete-confirm-title {
    font-size: 16px;
    font-weight: 700;
    color: #ffd7da;
    margin-bottom: 10px;
}
.ai-delete-confirm-list {
    margin: 10px 0 14px 0;
    padding-left: 8px;
    font-size: 13px;
    color: #d8dde9;
    line-height: 1.7;
}
.ai-delete-confirm-list-item {
    padding: 4px 8px;
    background: rgba(8,11,22,.4);
    border-radius: 4px;
    margin-bottom: 4px;
    border-left: 3px solid rgba(217,102,112,.55);
}
.ai-delete-confirm-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
}

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

/* ============================================================
   v1.10.18 — Comprehensive responsive design (3-tier breakpoints)
   ============================================================
   Goals (subscription product readiness):
   - Mobile (< 768px): one-thumb friendly, 44px touch targets
   - Tablet (768-1024px): 2-column layouts, comfortable padding
   - Desktop (> 1024px): existing 3-column layouts unchanged
   ============================================================ */

:root {
    --rd-bp-mobile: 768px;
    --rd-bp-tablet: 1024px;
    --rd-touch-min: 44px;
    --rd-card-pad-mobile: 12px;
    --rd-card-pad-tablet: 14px;
    --rd-card-pad-desktop: 16px;
    --rd-fs-base-mobile: 14px;
    --rd-fs-base-tablet: 14.5px;
    --rd-fs-base-desktop: 15px;
    --rd-card-gap-mobile: 10px;
    --rd-card-gap-tablet: 14px;
    --rd-card-gap-desktop: 16px;
}

/* === TABLET breakpoint (768px - 1024px) === */
@media (min-width: 768px) and (max-width: 1024px) {
    .ai-cards-grid {
        grid-template-columns: repeat(2, 1fr) !important;
        gap: var(--rd-card-gap-tablet) !important;
    }
    .ai-synthesis-cards-grid {
        grid-template-columns: repeat(2, 1fr) !important;
        gap: var(--rd-card-gap-tablet) !important;
    }
    .ai-card,
    .ai-synthesis-card {
        padding: var(--rd-card-pad-tablet) !important;
    }
    .ai-card-title { font-size: 15px !important; }
    .ai-synthesis-card-lead { font-size: 14.5px !important; }
    .ai-synthesis-card-body { font-size: 13.5px !important; }
}

/* === MOBILE breakpoint (< 768px) — one-thumb friendly === */
@media (max-width: 767px) {
    /* === Card grids: collapse to single column with snug spacing === */
    .ai-cards-grid,
    .ai-synthesis-cards-grid {
        grid-template-columns: 1fr !important;
        gap: var(--rd-card-gap-mobile) !important;
    }
    .ai-card,
    .ai-synthesis-card {
        padding: var(--rd-card-pad-mobile) !important;
        gap: 6px !important;
    }
    
    /* === Typography scale-down for narrow viewports === */
    .ai-card-title {
        font-size: 14.5px !important;
        line-height: 1.35 !important;
    }
    .ai-card-section,
    .ai-card-section-cross,
    .ai-card-section-risk {
        font-size: 12.5px !important;
        line-height: 1.5 !important;
    }
    .ai-card-section-label {
        font-size: 10.5px !important;
    }
    .ai-card-prob-pill {
        font-size: 11px !important;
        padding: 3px 8px !important;
    }
    .ai-card-validation-bar {
        padding: 8px 9px !important;
        gap: 7px !important;
    }
    .ai-card-validation-num {
        font-size: 18px !important;
    }
    .ai-card-validation-label {
        font-size: 10.5px !important;
        line-height: 1.3 !important;
    }
    .ai-card-validation-trend {
        font-size: 11px !important;
        padding: 2px 6px !important;
    }
    
    .ai-synthesis-card-lead {
        font-size: 14px !important;
        line-height: 1.4 !important;
    }
    .ai-synthesis-card-body {
        font-size: 13px !important;
        line-height: 1.6 !important;
    }
    .ai-synthesis-card-tag {
        font-size: 10px !important;
        padding: 2px 8px !important;
    }
    
    /* === Touch-friendly action buttons (44px min hit target) === */
    .ai-card-actions {
        top: 8px !important;
        right: 8px !important;
        gap: 5px !important;
    }
    .ai-card-action-btn {
        font-size: 11px !important;
        padding: 5px 10px !important;
        min-height: 28px !important;  /* visible size */
        /* Invisible padding extends hit target to 44px without affecting layout */
        position: relative;
    }
    .ai-card-action-btn::after {
        content: '';
        position: absolute;
        inset: -8px;  /* extends touch area outward */
        z-index: -1;
    }
    
    /* === Topic accordion: tighter spacing on mobile === */
    .ai-topic-summary {
        padding: 9px 11px !important;
        gap: 6px !important;
    }
    .ai-topic-title {
        font-size: 14px !important;
    }
    .ai-topic-meta {
        flex-wrap: wrap !important;
        gap: 6px !important;
        font-size: 11px !important;
    }
    .ai-topic-distribution {
        flex-wrap: wrap !important;
        gap: 4px !important;
    }
    .ai-topic-dist-item {
        font-size: 10.5px !important;
        padding: 1px 5px !important;
    }
    .ai-topic-extreme-hint {
        font-size: 11px !important;
        padding: 2px 6px !important;
    }
    
    /* === Selection bar: stack vertically on mobile === */
    .ai-selection-bar {
        flex-direction: column !important;
        align-items: stretch !important;
        padding: 11px 14px !important;
        gap: 10px !important;
    }
    .ai-selection-count {
        font-size: 13px !important;
        text-align: center;
    }
    .ai-selection-count-num {
        font-size: 16px !important;
    }
    .ai-selection-actions {
        margin-left: 0 !important;
        justify-content: stretch !important;
        gap: 6px !important;
    }
    .ai-selection-btn {
        flex: 1;
        text-align: center;
        justify-content: center;
        font-size: 12.5px !important;
        padding: 9px 12px !important;
        min-height: var(--rd-touch-min) !important;
    }
    
    /* === Confirmation panel: full-width buttons on mobile === */
    .ai-delete-confirm-panel {
        padding: 14px 16px !important;
    }
    .ai-delete-confirm-title {
        font-size: 14.5px !important;
    }
    .ai-delete-confirm-list {
        font-size: 12px !important;
    }
    .ai-delete-confirm-list-item {
        padding: 5px 8px !important;
    }
    .ai-delete-confirm-actions {
        flex-direction: column-reverse !important;  /* "確定刪除" on top for emphasis */
        gap: 8px !important;
    }
    .ai-delete-confirm-actions .ai-selection-btn {
        width: 100%;
        min-height: var(--rd-touch-min) !important;
    }
    
    /* === Validation tracker: wraps verdict + score row better === */
    .ai-tracker-row {
        padding: 9px 11px !important;
        font-size: 12.5px !important;
    }
    .ai-tracker-cell-title {
        font-size: 13px !important;
    }
    .ai-tracker-cell-score {
        font-size: 14px !important;
    }
    .ai-tracker-cell-interp {
        font-size: 11.5px !important;
    }
    
    /* === Master toggle row (expand all / collapse all) === */
    .ai-master-toggle-row {
        flex-wrap: wrap !important;
        gap: 6px !important;
        padding: 8px 10px !important;
    }
    .ai-master-toggle-btn {
        font-size: 11.5px !important;
        padding: 6px 10px !important;
        min-height: var(--rd-touch-min) !important;
    }
    
    /* === Synthesis shell — header / intro / issued tag wrap better === */
    .ai-synthesis-shell {
        padding: 14px 14px !important;
    }
    .ai-synthesis-headline {
        font-size: 16px !important;
    }
    .ai-synthesis-intro {
        font-size: 13px !important;
        line-height: 1.6 !important;
    }
    .ai-synthesis-issued {
        font-size: 11px !important;
    }
    .ai-synthesis-card-validation-num {
        font-size: 17px !important;
    }
    .ai-synthesis-card-no-data-hint {
        font-size: 11.5px !important;
        padding: 6px 8px !important;
    }
}

/* === iOS Safari fix: prevent input zoom on focus === */
/* Inputs with font-size < 16px trigger auto-zoom on iOS. Force 16px
   on the form's text-area / text-input on small viewports. */
@media (max-width: 767px) {
    .stTextArea textarea,
    .stTextInput input,
    [data-testid="stFileUploader"] input {
        font-size: 16px !important;
    }
}

/* === Long text sections: 4-line clamp on mobile to keep cards bounded === */
@media (max-width: 767px) {
    .ai-card-section {
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .ai-synthesis-card-body {
        display: -webkit-box;
        -webkit-line-clamp: 8;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
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


# v1.10.15 — Delete request handling
# Two-click confirmation pattern: first click sets pending flag, second
# click (on the same button) actually deletes. Click any other delete
# button → clears prior pending and sets new one.

def _is_user_added_thesis(thesis: dict) -> bool:
    """User-added items have IDs prefixed 'user-' (set by _make_user_id)."""
    return str(thesis.get("id", "")).startswith("user-")


def _is_user_added_synth(paragraph: dict) -> bool:
    """User-added synthesis paragraphs have IDs prefixed 'user-synth-'."""
    return str(paragraph.get("id", "")).startswith("user-synth-")


def _resolve_delete_request() -> None:
    """Read URL params for delete operations.

    v1.10.16 patterns (multi-select + confirm panel):
        ?toggle_select_thesis=<id>     → toggle thesis in/out of selection set
        ?toggle_select_synth=<idx>     → toggle synth para in/out of selection set
        ?clear_selection=1             → empty the selection sets
        ?show_delete_confirm=1         → open confirmation panel
        ?execute_delete=1              → commit the bulk delete

    v1.10.15 patterns (still supported, single-card flow):
        ?delete_thesis_pending=<id>    → first click; mark for confirmation
        ?delete_thesis_confirm=<id>    → second click; actually delete
        Same for synth: delete_synth_pending / delete_synth_confirm

    All URL params are cleared after handling so a refresh doesn't re-trigger.
    """
    try:
        params = st.query_params
    except Exception:
        return

    def _take(key: str) -> str | None:
        v = params.get(key)
        if not v:
            return None
        if isinstance(v, list):
            v = v[0] if v else None
        try:
            params.pop(key, None)
        except Exception:
            pass
        return v

    # === v1.10.16 multi-select handlers ===

    # Toggle thesis in/out of selection set
    toggle_thesis = _take("toggle_select_thesis")
    if toggle_thesis:
        sel = st.session_state.setdefault("_delete_selection_thesis", set())
        if toggle_thesis in sel:
            sel.discard(toggle_thesis)
        else:
            sel.add(toggle_thesis)
        # Close any open confirmation panel
        st.session_state.pop("_delete_confirm_open", None)

    # Toggle synth para in/out of selection set
    toggle_synth = _take("toggle_select_synth")
    if toggle_synth:
        try:
            idx = int(toggle_synth)
            sel = st.session_state.setdefault("_delete_selection_synth", set())
            if idx in sel:
                sel.discard(idx)
            else:
                sel.add(idx)
            st.session_state.pop("_delete_confirm_open", None)
        except ValueError:
            pass

    # Clear all selections
    if _take("clear_selection"):
        st.session_state.pop("_delete_selection_thesis", None)
        st.session_state.pop("_delete_selection_synth", None)
        st.session_state.pop("_delete_confirm_open", None)

    # Show confirmation panel
    if _take("show_delete_confirm"):
        st.session_state["_delete_confirm_open"] = True

    # Execute the bulk delete (after confirmation)
    if _take("execute_delete"):
        sel_thesis = st.session_state.get("_delete_selection_thesis", set())
        sel_synth = st.session_state.get("_delete_selection_synth", set())
        if sel_thesis or sel_synth:
            data = _load_user_data()

            # Delete selected theses
            if sel_thesis:
                data["user_theses"] = [
                    t for t in data.get("user_theses", [])
                    if str(t.get("id", "")) not in sel_thesis
                ]
                # Clean up trend history
                history = st.session_state.get(_ai_thesis_history_key(), {})
                for tid in sel_thesis:
                    history.pop(tid, None)

            # Delete selected synth paragraphs (by index, descending so indices stay valid)
            if sel_synth:
                user_synth = data.get("user_synthesis", [])
                for idx in sorted(sel_synth, reverse=True):
                    if 0 <= idx < len(user_synth):
                        user_synth.pop(idx)
                # Conservatively clear all synth-* history (indices shifted)
                history = st.session_state.get(_ai_thesis_history_key(), {})
                stale_keys = [k for k in list(history.keys())
                              if k.startswith("synthesis-")]
                for k in stale_keys:
                    history.pop(k, None)

            _save_user_data(data)

        # Clear all delete-related state
        st.session_state.pop("_delete_selection_thesis", None)
        st.session_state.pop("_delete_selection_synth", None)
        st.session_state.pop("_delete_confirm_open", None)

    # === v1.10.15 single-card delete patterns (kept for backward compat) ===

    pending_thesis = _take("delete_thesis_pending")
    if pending_thesis:
        st.session_state["_delete_pending_id"] = pending_thesis
        st.session_state.pop("_delete_pending_synth_idx", None)

    confirm_thesis = _take("delete_thesis_confirm")
    if confirm_thesis:
        data = _load_user_data()
        before = len(data.get("user_theses", []))
        data["user_theses"] = [
            t for t in data.get("user_theses", [])
            if str(t.get("id", "")) != confirm_thesis
        ]
        if len(data["user_theses"]) < before:
            _save_user_data(data)
            history = st.session_state.get(_ai_thesis_history_key(), {})
            if confirm_thesis in history:
                history.pop(confirm_thesis, None)
        st.session_state.pop("_delete_pending_id", None)

    pending_synth = _take("delete_synth_pending")
    if pending_synth:
        try:
            st.session_state["_delete_pending_synth_idx"] = int(pending_synth)
            st.session_state.pop("_delete_pending_id", None)
        except ValueError:
            pass

    confirm_synth = _take("delete_synth_confirm")
    if confirm_synth:
        try:
            idx = int(confirm_synth)
            data = _load_user_data()
            user_synth = data.get("user_synthesis", [])
            if 0 <= idx < len(user_synth):
                deleted = user_synth.pop(idx)
                _save_user_data(data)
                history = st.session_state.get(_ai_thesis_history_key(), {})
                stale_keys = [k for k in history.keys() if k.startswith("synthesis-")]
                for k in stale_keys:
                    history.pop(k, None)
            st.session_state.pop("_delete_pending_synth_idx", None)
        except ValueError:
            pass


def _is_thesis_selected(thesis_id: str) -> bool:
    """Check if a thesis ID is in the current multi-select set."""
    sel = st.session_state.get("_delete_selection_thesis", set())
    return thesis_id in sel


def _is_synth_selected(idx: int) -> bool:
    """Check if a synth paragraph index is in the current multi-select set."""
    sel = st.session_state.get("_delete_selection_synth", set())
    return idx in sel


def _is_pending_delete(thesis_id: str) -> bool:
    """Return True if this thesis is in the 'pending confirmation' state.
    Kept for backward compat with v1.10.15."""
    return st.session_state.get("_delete_pending_id") == thesis_id


def _is_pending_delete_synth(idx: int) -> bool:
    """Kept for backward compat with v1.10.15."""
    return st.session_state.get("_delete_pending_synth_idx") == idx


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
    thesis_id = str(thesis.get("id", ""))

    arrow, trend_class, trend_label = _thesis_trend_arrow(thesis_id, score)

    # Truncate cross + risk for the card view (full text shows in tracker if needed)
    def trim(s: str, n: int) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else s[:n - 1] + "…"

    label_summary = "解說重點" if lang_zh else "Summary"
    label_cross = "交叉驗證" if lang_zh else "Cross-validation"
    label_risk = "風險 / 反證" if lang_zh else "Risk"
    label_validation = "目前驗證" if lang_zh else "Validation"
    label_claimed = "推估成立" if lang_zh else "Claimed"

    # v1.10.19: Action buttons in cards reverted to display-only lock
    # indicator. Selection is now handled in _render_user_content_manager
    # above the cards (with reliable Streamlit native widgets).
    if _is_user_added_thesis(thesis):
        # User-added — show a small "你新增" badge. Selection happens in manager.
        user_label = "✏️ 你新增" if lang_zh else "✏️ User-added"
        actions_html = (
            f'<div class="ai-card-actions">'
            f'  <span class="ai-card-action-btn ai-card-action-user">'
            f'     {escape(user_label)}</span>'
            f'</div>'
        )
    else:
        # Built-in (read-only) — show lock indicator
        lock_label = "🔒 內建" if lang_zh else "🔒 Built-in"
        actions_html = (
            f'<div class="ai-card-actions">'
            f'  <span class="ai-card-action-btn ai-card-action-locked">'
            f'     {escape(lock_label)}</span>'
            f'</div>'
        )

    return textwrap.dedent(f"""
        <div class="ai-card">
            {actions_html}
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

    # v1.10.15: Track user-synthesis index for delete buttons.
    # User-added paragraphs have IDs starting with "user-synth-".
    # Their position within user_synthesis (not within paragraphs) is what
    # we need for the delete URL.
    user_synth_idx_seen = -1

    card_html_parts: list[str] = []
    for idx, p in enumerate(paragraphs):
        v = para_validations[idx]
        lead = p.get("lead", "")
        body = p.get("body", "")
        is_user = _is_user_added_synth(p)
        if is_user:
            user_synth_idx_seen += 1
            user_synth_idx = user_synth_idx_seen
        else:
            user_synth_idx = None

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

        # v1.10.19: Action area is display-only. Deletion happens in
        # _render_user_content_manager (manager panel above cards).
        if is_user and user_synth_idx is not None:
            user_label = "✏️ 你新增" if lang_zh else "✏️ User-added"
            actions_html = (
                f'<div class="ai-card-actions">'
                f'  <span class="ai-card-action-btn ai-card-action-user">'
                f'     {escape(user_label)}</span>'
                f'</div>'
            )
        else:
            lock_label = "🔒 內建" if lang_zh else "🔒 Built-in"
            actions_html = (
                f'<div class="ai-card-actions">'
                f'  <span class="ai-card-action-btn ai-card-action-locked">'
                f'     {escape(lock_label)}</span>'
                f'</div>'
            )

        card_html_parts.append(
            f'<div class="ai-synthesis-card {border_class}">'
            f'  {actions_html}'
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


# ----------------------------------------------------------------------------
# v1.10.11 — Input form renderers (Streamlit forms inside expanders)
# ----------------------------------------------------------------------------
# These two renderers add UI for users to append new theses + synthesis
# paragraphs without editing code. They write to ai_analysis_data.json
# via _save_user_data, then trigger a Streamlit rerun via st.rerun() so
# the new item appears immediately.
#
# Design notes:
# - Forms are wrapped in st.expander so they stay collapsed by default
#   and don't dominate the page on first visit.
# - Inside the expander we use st.form, which batches widget values
#   into one submit + rerun (avoids re-running on every keystroke).
# - Validation points are dynamic — we let the user add up to 4 of them
#   per thesis. Each point's fields adjust based on the selected type.
# - Smart-detection chips appear above the validation-points section,
#   showing tickers / thresholds detected from the summary text.
# ----------------------------------------------------------------------------


def _render_thesis_input_form(lang_zh: bool) -> None:
    """v1.10.12: Batch import form. User pastes a TSV table (or uploads
    a CSV file) where each row is one thesis. We parse + auto-seed
    validation_points + auto-detect topics, then preview before commit.

    Expected columns (in this order):
        1. 影片可確認主題 / title              REQUIRED
        2. 解說重點 / summary                  REQUIRED
        3. 目前局勢交叉驗證 / cross_validation
        4. 風險 / 反證 / risk
        5. 推估成立機率 / probability
        6. 主題分類 / topic [OPTIONAL]
    """
    if lang_zh:
        expander_label = "➕ 批次匯入論點"
        instruction = (
            "**一次匯入多篇論點。** 從 Excel / Google Docs 複製你的表格"
            "(Tab 分隔),貼到下方;或下載為 CSV 檔上傳。\n\n"
            "**預期欄位**(順序要對):\n"
            "1. 影片可確認主題 · 2. 解說重點 · 3. 目前局勢交叉驗證 · "
            "4. 風險·反證 · 5. 推估成立機率 · 6. 主題分類(可選)"
        )
        tab_paste_label = "貼上表格 (TSV)"
        tab_csv_label = "上傳 CSV 檔"
        paste_input_label = "貼上表格 — 每列一篇論點"
        csv_input_label = "上傳 CSV / TSV 檔"
        preview_btn = "🔍 預覽匯入結果"
        no_data_msg = "尚未貼上任何表格內容。"
        parse_failed = "解析失敗:內容不是有效的表格格式"
        commit_btn_template = "💾 全部加入 (%d 篇)"
        commit_success_template = "已匯入 %d 篇論點!請看下方卡片區"
        commit_failed = "寫入檔案失敗 — 請檢查目錄寫入權限"
        sample_label = "📄 看範例表格"
        detected_template = "**偵測到 %d 篇論點**"
        vp_count_template = "🔍 驗證點(%d 個):"
    else:
        expander_label = "➕ Batch Import Theses"
        instruction = (
            "**Import multiple theses at once.** Copy a table from "
            "Excel / Google Docs (tab-separated), or upload a CSV file. "
            "Expected columns: title, summary, cross_validation, risk, "
            "probability, topic (optional)."
        )
        tab_paste_label = "Paste Table (TSV)"
        tab_csv_label = "Upload CSV"
        paste_input_label = "Paste table — one row per thesis"
        csv_input_label = "Upload CSV / TSV"
        preview_btn = "🔍 Preview Import"
        no_data_msg = "No table content provided yet."
        parse_failed = "Parse failed: not a valid table format"
        commit_btn_template = "💾 Save All (%d theses)"
        commit_success_template = "Imported %d theses! See cards below."
        commit_failed = "File write failed — check directory permissions"
        sample_label = "📄 View sample table"
        detected_template = "**Detected %d theses**"
        vp_count_template = "🔍 Validation points (%d):"

    sample_tsv = (
        "影片可確認主題\t解說重點\t目前局勢交叉驗證\t風險/反證\t推估成立機率\n"
        "AI財報點火,外資全翻多\t影片主軸是 AI 財報帶動市場信心,外資由偏空轉為積極買超\t"
        "5/7外資買超台股約464.11億元,同日加權指數盤中高點42,156.06、收41,933.78\t"
        "「外資全翻多」要打折看,因為5/7雖現貨買超,但外資指期淨空單仍超過5萬口\t中偏高,約60-65%\n"
        "台股衝上4萬後,是否繼續走多\t台股主升段尚未結束,但漲多後不會一路直線上攻\t"
        "5/7台股盤中已衝到42,156.06,5/8收41,603.94,代表4萬點突破後仍站穩\t"
        "短線從4萬快速衝到4.2萬附近,漲幅過快\t維持高檔震盪偏多:中偏高,約60-65%"
    )

    # v1.10.14: Toggle button instead of st.expander for clearer UX
    toggle_key = "_thesis_batch_form_open"
    is_open = st.session_state.get(toggle_key, False)
    if lang_zh:
        btn_label = "✕ 關閉批次匯入" if is_open else expander_label
    else:
        btn_label = "✕ Close Batch Import" if is_open else expander_label
    btn_type = "secondary" if is_open else "primary"
    if st.button(btn_label, key="thesis_batch_toggle", type=btn_type):
        st.session_state[toggle_key] = not is_open
        st.rerun()

    if is_open:
        st.markdown(instruction)

        with st.expander(sample_label, expanded=False):
            st.code(sample_tsv, language=None)

        tab_paste, tab_csv = st.tabs([tab_paste_label, tab_csv_label])

        with tab_paste:
            paste_text = st.text_area(paste_input_label, height=200,
                                       key="thesis_batch_paste")
            if st.button(preview_btn, key="thesis_batch_preview_paste"):
                if not paste_text.strip():
                    st.warning(no_data_msg)
                else:
                    try:
                        parsed_rows = _parse_table_text(paste_text, separator="\t")
                        st.session_state["_thesis_batch_preview"] = parsed_rows
                    except Exception as e:
                        st.error(f"{parse_failed}: {e}")

        with tab_csv:
            csv_file = st.file_uploader(csv_input_label, type=["csv", "tsv"],
                                          key="thesis_batch_csv")
            if csv_file is not None:
                try:
                    text = csv_file.read().decode("utf-8")
                    sep = "\t" if csv_file.name.endswith(".tsv") else ","
                    parsed_rows = _parse_table_text(text, separator=sep)
                    st.session_state["_thesis_batch_preview"] = parsed_rows
                except Exception as e:
                    st.error(f"{parse_failed}: {e}")

        # Display preview from session_state (persists across reruns)
        preview = st.session_state.get("_thesis_batch_preview", [])
        if preview:
            st.markdown("---")
            st.markdown(detected_template % len(preview))

            for idx, row in enumerate(preview):
                topic_cfg = AI_TOPIC_REGISTRY.get(row["topic"], AI_TOPIC_REGISTRY["uncategorized"])
                topic_emoji = topic_cfg.get("emoji", "🗂")
                topic_label = topic_cfg.get("label_zh" if lang_zh else "label_en", "")
                with st.container():
                    st.markdown(
                        f"**#{idx+1} {row['title']}**  ·  {topic_emoji} {topic_label}  "
                        f"·  {row['claimed_probability']}%"
                    )
                    if row["summary"]:
                        st.caption(f"📝 {row['summary'][:100]}")
                    if row["validation_points"]:
                        vp_labels = [
                            f"{p.get('label', p.get('type', '?'))} (權重 {p.get('weight', 1)})"
                            for p in row["validation_points"]
                        ]
                        st.caption(
                            (vp_count_template % len(vp_labels)) + " " + " · ".join(vp_labels)
                        )

            commit_label = commit_btn_template % len(preview)
            if st.button(commit_label, key="thesis_batch_commit", type="primary"):
                data = _load_user_data()
                for row in preview:
                    new_thesis = {
                        "id": _make_user_id("user-thesis"),
                        "topic": row["topic"],
                        "title": row["title"],
                        "summary": row["summary"],
                        "cross_validation": row["cross_validation"],
                        "risk": row["risk"],
                        "claimed_probability": row["claimed_probability"],
                        "issued_date": _time.strftime("%Y-%m-%d"),
                        "horizon_date": "",
                        "validation_points": row["validation_points"],
                    }
                    data["user_theses"].append(new_thesis)
                if _save_user_data(data):
                    st.success(commit_success_template % len(preview))
                    st.session_state.pop("_thesis_batch_preview", None)
                    st.rerun()
                else:
                    st.error(commit_failed)


def _render_synthesis_input_form(lang_zh: bool) -> None:
    """v1.10.13: Form for adding a new AI 整體判斷 paragraph.

    Workflow:
      1. User types lead + body in the OUTER text-area widgets (not in
         st.form, so we get reactive updates).
      2. User clicks "🔍 從內文自動偵測驗證點" button — system parses
         body via _auto_generate_validation_points() and stashes the
         result into session_state['_synth_auto_points'].
      3. User reviews + edits + saves via the inner st.form.

    The split (outer text-area + auto-detect, inner form for save) is
    necessary because st.form batches widget changes until form_submit
    — buttons inside the form can't trigger reruns to update other
    widgets in the same form.
    """
    if lang_zh:
        expander_label = "➕ 新增 AI 整體判斷"
        lead_label = "主旨(顯示為粗體黃色標題)*"
        body_label = "內文 *"
        detect_btn_label = "🔍 從內文自動偵測驗證點"
        clear_btn_label = "🧹 清除自動偵測"
        detect_no_body = "請先填內文"
        detect_found_template = "✓ 偵測到 %d 個驗證點 — 已預填到下方"
        detect_none = "從內文偵測不到具體驗證點 — 你可以手動加,或按「🧹 清除」並改用 fallback"
        vp_label = "驗證點(可選)"
        n_points_label = "驗證點數量(0 = 不驗證)"
        save_btn = "💾 儲存判斷"
        success_msg = "已儲存!新判斷已加入整體判斷區。"
        error_msg = "儲存失敗 — 請檢查必填欄位。"
        save_io_err = "寫入檔案失敗 — 請檢查目錄寫入權限。"
        helper_caption = (
            "💡 寫完內文後,按「🔍 從內文自動偵測驗證點」可以自動抽取數字 / 股票 / 指數,"
            "預填驗證點欄位。你之後可以再修改,然後按「💾 儲存」。"
        )
    else:
        expander_label = "➕ Add Synthesis Paragraph"
        lead_label = "Lead (bold yellow heading) *"
        body_label = "Body *"
        detect_btn_label = "🔍 Auto-detect validation points"
        clear_btn_label = "🧹 Clear auto-detection"
        detect_no_body = "Please type body text first"
        detect_found_template = "✓ Detected %d validation points — pre-filled below"
        detect_none = "No specific validation points detected from body — you can add manually"
        vp_label = "Validation points (optional)"
        n_points_label = "Number of validation points (0 = none)"
        save_btn = "💾 Save paragraph"
        success_msg = "Saved! Paragraph added to AI Overall Take."
        error_msg = "Save failed — please check required fields."
        save_io_err = "File write failed — check directory permissions."
        helper_caption = (
            "💡 After typing the body, click 'Auto-detect' to extract numbers / "
            "stocks / index levels and pre-fill validation-point fields. "
            "You can then edit and save."
        )

    # v1.10.14: Toggle button instead of st.expander for clearer UX
    toggle_key = "_synth_input_form_open"
    is_open = st.session_state.get(toggle_key, False)
    if lang_zh:
        btn_label = "✕ 關閉新增 AI 整體判斷" if is_open else expander_label
    else:
        btn_label = "✕ Close Add Synthesis" if is_open else expander_label
    btn_type = "secondary" if is_open else "primary"
    if st.button(btn_label, key="synth_input_toggle", type=btn_type):
        st.session_state[toggle_key] = not is_open
        st.rerun()

    if is_open:
        st.caption(helper_caption)

        # OUTER widgets — these can react to button clicks below
        # (Streamlit reruns whole script on widget change outside st.form)
        lead = st.text_input(lead_label, key="synth_outer_lead")
        body = st.text_area(body_label, height=140, key="synth_outer_body")

        # Smart detection hint (read-only, just shows what we found)
        detected_smart = _smart_detect(body or "")
        if detected_smart["tickers"] or detected_smart["thresholds"]:
            hint_parts = []
            if detected_smart["tickers"]:
                hint_parts.append(f"🏷 偵測到的股票: {', '.join(detected_smart['tickers'])}" if lang_zh
                                   else f"🏷 Tickers: {', '.join(detected_smart['tickers'])}")
            if detected_smart["thresholds"]:
                hint_parts.append(f"🎯 偵測到的點位: {', '.join(str(t) for t in detected_smart['thresholds'])}" if lang_zh
                                   else f"🎯 Levels: {', '.join(str(t) for t in detected_smart['thresholds'])}")
            st.info(" · ".join(hint_parts))

        # Auto-detect button — triggers a rerun, writes pre-filled points
        # to session_state which the inner form reads as defaults.
        col_detect, col_clear, _spacer = st.columns([1, 1, 2])
        with col_detect:
            if st.button(detect_btn_label, key="synth_btn_detect"):
                if not body:
                    st.warning(detect_no_body)
                else:
                    auto_points = _auto_generate_validation_points(lead or "", body)
                    if auto_points:
                        st.session_state["_synth_auto_points"] = auto_points
                        st.success(detect_found_template % len(auto_points))
                    else:
                        st.session_state.pop("_synth_auto_points", None)
                        st.info(detect_none)
        with col_clear:
            if st.button(clear_btn_label, key="synth_btn_clear"):
                st.session_state.pop("_synth_auto_points", None)
                st.rerun()

        # Resolve defaults from auto-detected points (if any)
        auto_points = st.session_state.get("_synth_auto_points", [])
        default_n_points = len(auto_points) if auto_points else 0

        st.markdown(f"**{vp_label}**")
        n_points = st.number_input(
            n_points_label, min_value=0, max_value=4,
            value=default_n_points, key="synth_form_n_points",
        )

        # INNER form — gathers validation-point details + save button
        with st.form(key="ai_synthesis_input_form", clear_on_submit=False):
            collected_points: list[dict] = []
            for i in range(int(n_points)):
                # Pre-fill from auto-detected if available
                preset = auto_points[i] if i < len(auto_points) else {}
                preset_type = preset.get("type", "stock_trend")
                preset_label = preset.get("label", "")
                preset_weight = float(preset.get("weight", 1.0))

                st.markdown(f"###### #{i+1}")
                col_t, col_w, col_lab = st.columns([1, 1, 2])
                with col_t:
                    type_options = ["index_level", "stock_trend", "support_zone", "rally_pace"]
                    try:
                        type_index = type_options.index(preset_type)
                    except ValueError:
                        type_index = 1  # default to stock_trend
                    vp_type = st.selectbox(
                        "type", type_options, index=type_index,
                        key=f"synth_form_vp_{i}_type",
                    )
                with col_w:
                    weight = st.number_input(
                        "weight", min_value=0.1, max_value=5.0, value=preset_weight,
                        step=0.1, key=f"synth_form_vp_{i}_weight",
                    )
                with col_lab:
                    vp_label_text = st.text_input(
                        "label", value=preset_label,
                        key=f"synth_form_vp_{i}_label",
                    )

                point_dict: dict = {"type": vp_type, "label": vp_label_text, "weight": weight}

                if vp_type == "index_level":
                    c1, c2, c3 = st.columns(3)
                    preset_thresh = preset.get("threshold", 41000) if preset.get("type") == "index_level" else 41000
                    preset_dir = preset.get("direction", "above") if preset.get("type") == "index_level" else "above"
                    preset_ticker = preset.get("ticker", "^TWII") if preset.get("type") == "index_level" else "^TWII"
                    with c1:
                        thresh = st.number_input("threshold", value=int(preset_thresh),
                                                  key=f"synth_form_vp_{i}_threshold")
                    with c2:
                        direction = st.selectbox(
                            "direction", ["above", "below"],
                            index=0 if preset_dir == "above" else 1,
                            key=f"synth_form_vp_{i}_direction",
                        )
                    with c3:
                        ticker = st.text_input("ticker", value=preset_ticker,
                                                key=f"synth_form_vp_{i}_ticker_il")
                    point_dict.update({"threshold": int(thresh), "direction": direction,
                                       "ticker": ticker, "consec_days": 5})
                elif vp_type == "stock_trend":
                    c1, c2, c3 = st.columns(3)
                    preset_ticker = preset.get("ticker", "0050.TW") if preset.get("type") == "stock_trend" else "0050.TW"
                    preset_pattern = preset.get("pattern", "rally") if preset.get("type") == "stock_trend" else "rally"
                    preset_rally_min = float(preset.get("rally_min_pct", 2.0)) if preset.get("type") == "stock_trend" else 2.0
                    with c1:
                        ticker = st.text_input("ticker", value=preset_ticker,
                                                key=f"synth_form_vp_{i}_ticker_st")
                    with c2:
                        pattern_options = ["rally", "consolidate", "weak"]
                        pattern = st.selectbox(
                            "pattern", pattern_options,
                            index=pattern_options.index(preset_pattern) if preset_pattern in pattern_options else 0,
                            key=f"synth_form_vp_{i}_pattern",
                        )
                    with c3:
                        rally_min = st.number_input("rally_min_pct", min_value=0.0, max_value=20.0,
                                                     value=preset_rally_min, step=0.5,
                                                     key=f"synth_form_vp_{i}_rally_min")
                    point_dict.update({"ticker": ticker, "pattern": pattern,
                                       "lookback": 5, "rally_min_pct": float(rally_min)})
                elif vp_type == "support_zone":
                    c1, c2 = st.columns(2)
                    preset_level = preset.get("level", 40700) if preset.get("type") == "support_zone" else 40700
                    preset_ticker = preset.get("ticker", "^TWII") if preset.get("type") == "support_zone" else "^TWII"
                    with c1:
                        level = st.number_input("level", value=int(preset_level),
                                                 key=f"synth_form_vp_{i}_level")
                    with c2:
                        ticker = st.text_input("ticker", value=preset_ticker,
                                                key=f"synth_form_vp_{i}_ticker_sz")
                    point_dict.update({"level": int(level), "ticker": ticker, "tolerance_pct": 0.5})
                elif vp_type == "rally_pace":
                    c1, c2, c3 = st.columns(3)
                    preset_ticker = preset.get("ticker", "^TWII") if preset.get("type") == "rally_pace" else "^TWII"
                    preset_imin = float(preset.get("ideal_min_pct", 2.0)) if preset.get("type") == "rally_pace" else 2.0
                    preset_imax = float(preset.get("ideal_max_pct", 8.0)) if preset.get("type") == "rally_pace" else 8.0
                    with c1:
                        ticker = st.text_input("ticker", value=preset_ticker,
                                                key=f"synth_form_vp_{i}_ticker_rp")
                    with c2:
                        ideal_min = st.number_input("ideal_min_pct", min_value=-20.0,
                                                     max_value=20.0, value=preset_imin, step=0.5,
                                                     key=f"synth_form_vp_{i}_imin")
                    with c3:
                        ideal_max = st.number_input("ideal_max_pct", min_value=-20.0,
                                                     max_value=20.0, value=preset_imax, step=0.5,
                                                     key=f"synth_form_vp_{i}_imax")
                    point_dict.update({"ticker": ticker, "lookback": 10,
                                       "ideal_min_pct": float(ideal_min),
                                       "ideal_max_pct": float(ideal_max)})

                collected_points.append(point_dict)

            submitted = st.form_submit_button(save_btn)

            if submitted:
                if not lead or not body:
                    st.error(error_msg)
                    return
                new_para = {
                    "id": _make_user_id("user-synth"),
                    "lead": lead,
                    "body": body,
                }
                if collected_points:
                    new_para["validation_points"] = collected_points
                data = _load_user_data()
                data["user_synthesis"].append(new_para)
                if _save_user_data(data):
                    st.success(success_msg)
                    # Clean up form state
                    st.session_state.pop("_synth_auto_points", None)
                    st.session_state.pop("synth_outer_lead", None)
                    st.session_state.pop("synth_outer_body", None)
                    st.rerun()
                else:
                    st.error(save_io_err)


def _render_user_content_manager(merged_theses: list[dict],
                                  merged_synthesis: dict,
                                  lang_zh: bool) -> None:
    """v1.10.19: User-content management section using native Streamlit widgets.

    Replaces the v1.10.16 HTML-anchor based selection UI which was unreliable
    on mobile (anchor clicks triggered hard page reloads that wiped session_state
    before our handlers could read URL params).

    This section appears ABOVE the cards grid. Lists every user-added item
    with a checkbox; provides a [🗑 刪除選取] button + confirmation flow.
    Built-in items don't appear here (they're not deletable anyway).

    All interactions go through st.button / st.checkbox which use Streamlit's
    WebSocket and PRESERVE session_state correctly.
    """
    # Find user-added items
    user_theses = [t for t in merged_theses if _is_user_added_thesis(t)]
    user_synth_paragraphs = [(idx_in_user_synth, p)
                              for idx_in_user_synth, p in enumerate(
                                  [pp for pp in merged_synthesis.get("paragraphs", [])
                                   if _is_user_added_synth(pp)]
                              )]

    # If no user-added content, nothing to manage
    if not user_theses and not user_synth_paragraphs:
        return

    # Header (collapsible toggle, like the input form pattern)
    toggle_key = "_user_manager_open"
    is_open = st.session_state.get(toggle_key, False)

    n_user_theses = len(user_theses)
    n_user_synth = len(user_synth_paragraphs)
    n_total = n_user_theses + n_user_synth

    if lang_zh:
        btn_label = (f"✕ 關閉管理面板"
                      if is_open else
                      f"🗂 管理你新增的論點 / 整體判斷 ({n_total} 篇)")
        section_title = "🗂 管理你新增的內容"
        thesis_section_label = f"論點({n_user_theses} 篇)"
        synth_section_label = f"整體判斷段落({n_user_synth} 段)"
        no_selection_msg = "勾選下面的項目,然後點「🗑 刪除選取」"
        delete_btn = "🗑 刪除選取"
        clear_btn = "✕ 全部取消"
        confirm_title = "⚠️ 確認刪除以下項目?"
        confirm_btn = "✓ 確定刪除"
        cancel_btn = "✕ 取消"
        warn_note = "刪除後無法復原。整體判斷的 7 日趨勢歷史也會一併清空。"
        select_all_btn = "全選"
        none_msg = "目前沒有你新增的內容,請先用上方表單新增"
    else:
        btn_label = ("✕ Close Manager"
                      if is_open else
                      f"🗂 Manage Your Added Items ({n_total})")
        section_title = "🗂 Manage Your Items"
        thesis_section_label = f"Theses ({n_user_theses})"
        synth_section_label = f"Synthesis ({n_user_synth})"
        no_selection_msg = "Check items below, then click 'Delete Selected'"
        delete_btn = "🗑 Delete Selected"
        clear_btn = "✕ Clear All"
        confirm_title = "⚠️ Confirm deletion?"
        confirm_btn = "✓ Confirm Delete"
        cancel_btn = "✕ Cancel"
        warn_note = "This cannot be undone. Synthesis trend history will also reset."
        select_all_btn = "Select All"
        none_msg = "No user-added content yet"

    btn_type = "secondary" if is_open else "primary"
    if st.button(btn_label, key="user_manager_toggle", type=btn_type):
        st.session_state[toggle_key] = not is_open
        st.rerun()

    if not is_open:
        return

    st.markdown(f"### {section_title}")

    # Initialize selection sets in session_state
    sel_thesis = st.session_state.setdefault("_delete_selection_thesis", set())
    sel_synth = st.session_state.setdefault("_delete_selection_synth", set())

    # ===== Thesis section =====
    if user_theses:
        st.markdown(f"**{thesis_section_label}**")

        # Select-all helper
        col_sa, _ = st.columns([1, 5])
        with col_sa:
            if st.button(select_all_btn, key="user_manager_select_all_thesis"):
                for t in user_theses:
                    sel_thesis.add(str(t.get("id", "")))
                st.rerun()

        # v1.10.20: Detect legacy duplicate IDs (from pre-v1.10.20 batch imports
        # where ID generation was second-precision). Warn user that ticking
        # one checkbox will delete all rows sharing that ID.
        from collections import Counter
        id_counts = Counter(str(t.get("id", "")) for t in user_theses)
        duplicate_ids = {tid for tid, n in id_counts.items() if n > 1}
        if duplicate_ids:
            if lang_zh:
                st.warning(
                    f"⚠️ 偵測到 {len(duplicate_ids)} 組 ID 重複的論點"
                    f"(舊版批次匯入造成,v1.10.20 已修)。"
                    f"勾選任一個 → 同 ID 的全部會一起刪除。"
                )
            else:
                st.warning(
                    f"⚠️ Detected {len(duplicate_ids)} group(s) of theses with "
                    f"duplicate IDs (legacy from pre-v1.10.20 batch imports). "
                    f"Ticking any one will delete all rows sharing that ID."
                )

        for list_idx, t in enumerate(user_theses):
            tid = str(t.get("id", ""))
            title = t.get("title", "(無標題)") if lang_zh else t.get("title", "(untitled)")
            prob = t.get("claimed_probability", 50)
            topic_key = t.get("topic", "uncategorized")
            topic_cfg = AI_TOPIC_REGISTRY.get(topic_key, AI_TOPIC_REGISTRY.get("uncategorized", {}))
            topic_emoji = topic_cfg.get("emoji", "🗂")

            # v1.10.20: Use list_idx in key, NOT just thesis_id, because legacy
            # data may have duplicate IDs (from v1.10.12-v1.10.19 batch imports
            # with second-precision timestamps). The list index is always unique.
            checkbox_key = f"user_manager_thesis_{list_idx}_{tid}"
            currently_selected = tid in sel_thesis
            new_state = st.checkbox(
                f"{topic_emoji} {title}  ·  推估 {prob}%" if lang_zh
                else f"{topic_emoji} {title}  ·  Claimed {prob}%",
                value=currently_selected,
                key=checkbox_key,
            )
            if new_state and not currently_selected:
                sel_thesis.add(tid)
            elif not new_state and currently_selected:
                sel_thesis.discard(tid)

    # ===== Synthesis section =====
    if user_synth_paragraphs:
        st.markdown(f"**{synth_section_label}**")

        col_sa, _ = st.columns([1, 5])
        with col_sa:
            if st.button(select_all_btn, key="user_manager_select_all_synth"):
                for idx, _ in user_synth_paragraphs:
                    sel_synth.add(idx)
                st.rerun()

        for idx_in_user_synth, p in user_synth_paragraphs:
            lead = p.get("lead", "(無主旨)" if lang_zh else "(no lead)")
            lead_short = lead if len(lead) <= 60 else lead[:59] + "…"

            checkbox_key = f"user_manager_synth_{idx_in_user_synth}"
            currently_selected = idx_in_user_synth in sel_synth
            new_state = st.checkbox(
                f"📝 {lead_short}",
                value=currently_selected,
                key=checkbox_key,
            )
            if new_state and not currently_selected:
                sel_synth.add(idx_in_user_synth)
            elif not new_state and currently_selected:
                sel_synth.discard(idx_in_user_synth)

    # ===== Action buttons =====
    n_selected = len(sel_thesis) + len(sel_synth)
    st.markdown("---")

    if n_selected == 0:
        st.caption(no_selection_msg)
        return

    if lang_zh:
        selected_count_msg = f"已選 **{n_selected} 篇**"
    else:
        selected_count_msg = f"**{n_selected}** selected"
    st.markdown(selected_count_msg)

    confirm_open = st.session_state.get("_user_manager_confirm_open", False)

    if not confirm_open:
        col_del, col_clr, _ = st.columns([2, 2, 4])
        with col_del:
            if st.button(delete_btn, key="user_manager_delete_btn",
                         type="primary", use_container_width=True):
                st.session_state["_user_manager_confirm_open"] = True
                st.rerun()
        with col_clr:
            if st.button(clear_btn, key="user_manager_clear_btn",
                         use_container_width=True):
                sel_thesis.clear()
                sel_synth.clear()
                st.rerun()
    else:
        # Confirmation panel
        st.error(confirm_title)

        # List items to be deleted
        if sel_thesis:
            st.markdown(f"**{thesis_section_label}**")
            for t in user_theses:
                if str(t.get("id", "")) in sel_thesis:
                    st.markdown(f"  • {t.get('title', '(無標題)')}")

        if sel_synth:
            st.markdown(f"**{synth_section_label}**")
            for idx, p in user_synth_paragraphs:
                if idx in sel_synth:
                    lead = p.get("lead", "(無主旨)")
                    st.markdown(f"  • {lead[:80]}")

        st.warning(f"⚠️ {warn_note}")

        col_cancel, col_confirm = st.columns(2)
        with col_cancel:
            if st.button(cancel_btn, key="user_manager_cancel_btn",
                         use_container_width=True):
                st.session_state["_user_manager_confirm_open"] = False
                st.rerun()
        with col_confirm:
            if st.button(confirm_btn, key="user_manager_confirm_btn",
                         type="primary", use_container_width=True):
                _execute_bulk_delete(sel_thesis, sel_synth)
                # Clear all delete-related state
                sel_thesis.clear()
                sel_synth.clear()
                st.session_state["_user_manager_confirm_open"] = False
                st.rerun()


def _execute_bulk_delete(sel_thesis: set, sel_synth: set) -> None:
    """v1.10.19: Actual delete logic, called from the manager UI button.
    Previously this was triggered via ?execute_delete=1 URL param in
    _resolve_delete_request — now called directly from a Streamlit button."""
    if not sel_thesis and not sel_synth:
        return

    data = _load_user_data()

    if sel_thesis:
        data["user_theses"] = [
            t for t in data.get("user_theses", [])
            if str(t.get("id", "")) not in sel_thesis
        ]
        history = st.session_state.get(_ai_thesis_history_key(), {})
        for tid in sel_thesis:
            history.pop(tid, None)

    if sel_synth:
        user_synth_list = data.get("user_synthesis", [])
        for idx in sorted(sel_synth, reverse=True):
            if 0 <= idx < len(user_synth_list):
                user_synth_list.pop(idx)
        history = st.session_state.get(_ai_thesis_history_key(), {})
        stale_keys = [k for k in list(history.keys()) if k.startswith("synthesis-")]
        for k in stale_keys:
            history.pop(k, None)

    _save_user_data(data)


# ----------------------------------------------------------------------------
# v1.10.19 — _render_selection_bar_and_confirm is kept as a no-op stub for
# backward compat (in case any caller still references it). The real work is
# now done in _render_user_content_manager above.
# ----------------------------------------------------------------------------
def _render_selection_bar_and_confirm(merged_theses, merged_synthesis, lang_zh):
    """DEPRECATED — replaced by _render_user_content_manager in v1.10.19.
    Kept as a no-op for any external code that might call it."""
    pass


def render_ai_analysis_share_dashboard() -> None:
    """Top-level entry for the 🤖 AI 分析分享 Dashboard. Called from
    generate_dashboard when:
      dashboard_mode == "General Market"
      AND dashboard_experience_level == "beginner"
    """
    lang_zh = _news_briefing_is_zh()
    _ensure_ai_analysis_css()

    # v1.10.15: Process pending delete URL params BEFORE we load user data
    # so the page renders with the post-delete state.
    _resolve_delete_request()

    # v1.10.11: Read user-added items from JSON every render (no caching)
    user_data = _load_user_data()
    user_theses = user_data.get("user_theses", [])
    user_synthesis_paragraphs = user_data.get("user_synthesis", [])

    # Merge built-in + user-added
    merged_theses = list(AI_ANALYSIS_THESES) + user_theses
    merged_synthesis = dict(AI_ANALYSIS_SYNTHESIS)
    merged_synthesis["paragraphs"] = (
        list(AI_ANALYSIS_SYNTHESIS.get("paragraphs", []))
        + user_synthesis_paragraphs
    )

    # 1. Fetch the universe of tickers used by the validation calculators
    needed_tickers: set[str] = {"^TWII", "2330.TW"}  # always need these
    for thesis in merged_theses:
        for point in thesis.get("validation_points", []) or []:
            t = point.get("ticker")
            if t:
                needed_tickers.add(t)
    for para in (merged_synthesis.get("paragraphs") or []):
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
    for thesis in merged_theses:
        validation = compute_thesis_validation_score(thesis, daily_data)
        if validation.get("ready"):
            _record_thesis_score_today(thesis.get("id", ""), validation["thesis_score"])
        thesis_results.append({"thesis": thesis, "validation": validation})

    # v1.10.11: Show input forms (collapsed by default)
    _render_thesis_input_form(lang_zh)
    _render_synthesis_input_form(lang_zh)

    # v1.10.19: User content manager — replaces the v1.10.16 HTML-anchor
    # selection bar with a native Streamlit checkbox+button UI.
    # Sits between the input forms and the cards so it's reachable.
    _render_user_content_manager(merged_theses, merged_synthesis, lang_zh)

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
    if merged_synthesis:
        _render_html_block(_render_ai_synthesis_html(merged_synthesis, lang_zh, daily_data=daily_data))

    # ----- Block 3: 每日驗證表 -----
    _render_html_block(_render_ai_validation_tracker_html(thesis_results, lang_zh))

    # Footer
    foot = (
        "💡 點上方「➕ 新增論點」/「➕ 新增 AI 整體判斷」可從 UI 加新項目;"
        "也可編輯 AI_ANALYSIS_THESES 直接新增內建項目。每張卡片的「目前驗證」分數每天從真實市場數據動態計算"
        if lang_zh else
        "Use the ➕ buttons above to add new theses / synthesis paragraphs from the UI, or edit "
        "AI_ANALYSIS_THESES in code. Validation scores recompute daily from market data."
    )
    _render_html_block(f'<div class="ai-share-foot">{escape(foot)}</div>')
