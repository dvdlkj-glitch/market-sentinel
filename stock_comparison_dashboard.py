"""
stock_comparison_dashboard.py
=============================

Individual Stock Comparison & Recommendation Dashboard — v1.11.0 (2026-05-11)

Extracted as a separate module (similar to ai_analysis_dashboard.py) so the
main file (already ~48,948 lines) doesn't grow further. This module owns
the entire "📊 個股對比與建議" full-page experience.

Layers
------
Layer 1 — 對比設置(Setup):
    User picks 2-5 tickers via three entry points:
      (a) Direct text input (comma-separated, e.g. "2330,2317,2454")
      (b) Multi-select from watchlist
      (c) Multi-select from a supply-chain group
    Selected tickers are stored as chips with X-to-remove.

Layer 2 — 對比總覽(Overview, the Hero):
    For each ticker:
      (1) Parallel fetch of 4-dimension evaluation card data (re-uses
          v1.10.27 ThreadPoolExecutor pattern)
      (2) Computes per-dimension scores + overall score
    Then renders:
      (a) 🏆 Ranking with verdict text ("2330 顯著領先 / 略勝 / 微幅領先")
      (b) 📋 Comparison table (5 rows: overall + 4 dimensions, with
          winner-by-dimension and gap)
      (c) 💡 Auto-generated insights (2-4 short paragraphs)

Layer 3 — 深入工作台(Deep Dive, TOMORROW polish):
    Per-ticker tab. Each tab uses render_ticker_page() from main file.
    Tomorrow's polish phase.

Public surface
--------------
  - render_stock_comparison_dashboard()    : top-level entry

Imports from main file (deferred via _main_module bridge)
---------------------------------------------------------
  - _fetch_eval_card_data(ticker, daily_df)
  - render_eval_card_html(ticker, name, tech, value, growth, chip, lang_zh)
  - _ensure_eval_card_css()
  - render_html_block(html)
  - get_language() / get_lang()
  - display_ticker_label(ticker)
  - is_taiwan_ticker(ticker)
  - fetch_daily_data(ticker)  — for tickers not in watchlist
  - SUPPLY_CHAIN_FOCUS_CONFIGS  — supply chain group constants

Tonight's scope (v1.11.0 phase A)
---------------------------------
  ✅ Layer 1 + Layer 2 only
  ✅ Comparison table + ranking + insights (text only, no radar chart)
  ✅ Parallel fetch
  ✅ Smoke tests
  ❌ Layer 3 (tabs) — tomorrow
  ❌ Plotly radar chart — tomorrow
  ❌ Mobile responsive polish — tomorrow

Note on .TWO (OTC) stocks
-------------------------
v1.10.31's SSL fallback for TPEx is not fully working (user-reported).
This means chip dimension for .TWO stocks shows "資料準備中". This is
graceful degradation — comparison for .TWO stocks works on 3 dimensions
(technical, value, growth) only. Fix scheduled for next week.
"""

from __future__ import annotations

import math
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


TW_TZ = ZoneInfo("Asia/Taipei")

# Tonight's scope: 2-5 tickers
COMPARISON_MIN_TICKERS = 2
COMPARISON_MAX_TICKERS = 5


# ---------------------------------------------------------------------------
# Deferred-import bridge to the main dashboard file.
# Pattern copied from ai_analysis_dashboard.py — required to avoid circular
# import at module-load time.
# ---------------------------------------------------------------------------

_MAIN_MODULE = None
_MAIN_MODULE_NAMES = (
    "stock_dashboard_web_enhanced_v5_live_news",
    "__main__",
)


def _resolve_main_module():
    """Find main module by trying known import names, then fall back to
    sys.modules scan. Cached after first resolve."""
    global _MAIN_MODULE
    if _MAIN_MODULE is not None:
        return _MAIN_MODULE

    import importlib
    import sys

    for name in _MAIN_MODULE_NAMES:
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "render_eval_card_html"):
            _MAIN_MODULE = mod
            return mod
        try:
            mod = importlib.import_module(name)
            if hasattr(mod, "render_eval_card_html"):
                _MAIN_MODULE = mod
                return mod
        except Exception:
            continue

    # Final fallback
    for mod in list(sys.modules.values()):
        if mod is not None and hasattr(mod, "render_eval_card_html"):
            _MAIN_MODULE = mod
            return mod

    return None


def _main(attr_name: str, default=None):
    """Get an attribute from the main module, or return default if not found."""
    mod = _resolve_main_module()
    if mod is None:
        return default
    return getattr(mod, attr_name, default)


# ---------------------------------------------------------------------------
# CSS for comparison dashboard
# ---------------------------------------------------------------------------

_COMPARISON_CSS = """
<style>
.comparison-shell {
  background: linear-gradient(180deg, rgba(20,28,42,0.85), rgba(15,22,35,0.85));
  border: 1px solid rgba(96,140,200,0.18);
  border-radius: 16px;
  padding: 22px 26px;
  margin: 16px 0;
  color: #d8e1ec;
}

.comparison-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(96,140,200,0.15);
  margin-bottom: 18px;
}

.comparison-title {
  font-size: 18px;
  font-weight: 600;
  color: #f1f5f9;
}

.comparison-subtitle {
  font-size: 12px;
  color: #98a2b8;
}

/* Ranking cards */
.ranking-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin: 16px 0 20px 0;
}

.ranking-card {
  background: rgba(15,22,35,0.6);
  border: 1px solid rgba(96,140,200,0.15);
  border-radius: 12px;
  padding: 14px 16px;
  position: relative;
}

.ranking-card.rank-1 {
  border-color: rgba(82,196,138,0.4);
  background: linear-gradient(135deg, rgba(82,196,138,0.10), rgba(15,22,35,0.6));
}

.ranking-card.rank-2 {
  border-color: rgba(199,178,108,0.32);
}

.ranking-card.rank-3 {
  border-color: rgba(199,178,108,0.22);
}

.ranking-rank {
  font-size: 11px;
  color: #98a2b8;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.ranking-trophy {
  font-size: 16px;
  margin-left: 6px;
}

.ranking-ticker {
  font-size: 15px;
  font-weight: 600;
  color: #f1f5f9;
  margin: 4px 0 6px 0;
}

.ranking-score {
  font-size: 24px;
  font-weight: 700;
  color: #f1f5f9;
}

.ranking-score-denom {
  font-size: 13px;
  color: #98a2b8;
  font-weight: 400;
}

.ranking-verdict-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  margin-top: 6px;
}

.ranking-verdict-strong { background: rgba(82,196,138,0.18); color: #5ed79a; }
.ranking-verdict-good   { background: rgba(82,196,138,0.12); color: #6dc28a; }
.ranking-verdict-avg    { background: rgba(199,178,108,0.18); color: #d4be7b; }
.ranking-verdict-weak   { background: rgba(232,103,103,0.18); color: #e98787; }

.ranking-warning-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 10px;
  background: rgba(232,103,103,0.20);
  color: #ffadad;
  margin-top: 6px;
  margin-left: 6px;
}

/* Comparison table */
.comp-table-wrap {
  margin: 16px 0;
  overflow-x: auto;
}

.comp-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.comp-table th, .comp-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(96,140,200,0.10);
}

.comp-table th {
  background: rgba(15,22,35,0.7);
  font-weight: 600;
  color: #98a2b8;
  font-size: 12px;
  letter-spacing: 0.03em;
}

.comp-table .row-overall td {
  font-weight: 600;
  background: rgba(96,140,200,0.04);
}

.comp-table .col-dim {
  color: #98a2b8;
  font-weight: 500;
}

.comp-table .col-score {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 13px;
}

.comp-table .score-good    { color: #5ed79a; }
.comp-table .score-neutral { color: #d4be7b; }
.comp-table .score-poor    { color: #e98787; }
.comp-table .score-na      { color: #6c7686; font-style: italic; }

.comp-table .col-winner {
  color: #c2cdde;
  font-size: 12px;
}

.comp-table .winner-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(82,196,138,0.16);
  color: #6dc28a;
  font-size: 11px;
  font-weight: 500;
  margin-right: 4px;
}

/* Insights */
.insights-wrap {
  background: rgba(15,22,35,0.5);
  border-left: 3px solid rgba(96,140,200,0.4);
  padding: 14px 18px;
  margin-top: 18px;
  border-radius: 0 8px 8px 0;
}

.insights-title {
  font-size: 13px;
  font-weight: 600;
  color: #c2cdde;
  margin-bottom: 8px;
}

.insights-item {
  font-size: 13px;
  color: #d8e1ec;
  margin: 6px 0;
  padding-left: 16px;
  position: relative;
  line-height: 1.6;
}

.insights-item::before {
  content: "•";
  position: absolute;
  left: 4px;
  color: #6dc28a;
}

.insights-item.insight-warning::before { color: #e98787; }
.insights-item.insight-trade-off::before { color: #d4be7b; }

.comparison-disclaimer {
  font-size: 11px;
  color: #98a2b8;
  font-style: italic;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed rgba(96,140,200,0.15);
}

@media (max-width: 768px) {
  .comparison-shell { padding: 16px 14px; }
  .comp-table { font-size: 12px; }
  .comp-table th, .comp-table td { padding: 8px 6px; }
}
</style>
"""


def _ensure_comparison_css():
    """Inject CSS once per page render (idempotent — CSS overwrites OK)."""
    render_html_block = _main("render_html_block")
    if render_html_block:
        render_html_block(_COMPARISON_CSS)


# ---------------------------------------------------------------------------
# Layer 1 — Ticker selection
# ---------------------------------------------------------------------------

def _render_ticker_setup(watchlist_tickers: list[str]) -> list[str]:
    """Render the ticker selection UI. Returns the user's chosen tickers.

    Args:
        watchlist_tickers: tickers already in user's watchlist (for quick-add)

    Returns:
        list of selected tickers (deduplicated, valid Taiwan tickers)
    """
    is_taiwan_ticker = _main("is_taiwan_ticker", lambda t: False)
    lang_zh = (_main("get_language", lambda: "zh_TW")() == "zh_TW")

    setup_key = "_comparison_setup_tickers"
    if setup_key not in st.session_state:
        st.session_state[setup_key] = []

    if lang_zh:
        st.markdown("### 🎯 對比設置")
        st.caption(
            f"選擇 {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} 檔個股做對比。"
            "建議 2-3 檔為主要場景。"
        )
    else:
        st.markdown("### 🎯 Setup")
        st.caption(
            f"Select {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} tickers to compare. "
            "2-3 tickers is the sweet spot."
        )

    # === Entry point 1: Direct text input ===
    col1, col2 = st.columns([3, 1])
    with col1:
        input_label = "輸入 ticker(逗號分隔,例如 2330,2317,2454)" if lang_zh else "Enter tickers (comma-separated, e.g. 2330,2317,2454)"
        text_input = st.text_input(
            input_label,
            value="",
            key="_comparison_text_input",
            placeholder="2330, 2317, 2454" if lang_zh else "2330, 2317, 2454",
        )
    with col2:
        add_label = "➕ 加入" if lang_zh else "➕ Add"
        if st.button(add_label, key="_comparison_text_add_btn", use_container_width=True):
            for raw in text_input.split(","):
                ticker = raw.strip().upper()
                if not ticker:
                    continue
                # Auto-suffix .TW if just digits
                if ticker.isdigit():
                    ticker = f"{ticker}.TW"
                if ticker not in st.session_state[setup_key]:
                    if len(st.session_state[setup_key]) < COMPARISON_MAX_TICKERS:
                        st.session_state[setup_key].append(ticker)
            st.rerun()

    # === Entry point 2: From watchlist ===
    if watchlist_tickers:
        with st.expander("📋 從 Watchlist 加入" if lang_zh else "📋 Add from watchlist", expanded=False):
            tw_watchlist = [t for t in watchlist_tickers if is_taiwan_ticker(t)]
            if tw_watchlist:
                wl_picks = st.multiselect(
                    "從 watchlist 多選" if lang_zh else "Multi-select from watchlist",
                    options=tw_watchlist,
                    default=[],
                    key="_comparison_wl_picks",
                    label_visibility="collapsed",
                )
                wl_add_label = "加入" if lang_zh else "Add selected"
                if st.button(wl_add_label, key="_comparison_wl_add_btn"):
                    for ticker in wl_picks:
                        if ticker not in st.session_state[setup_key]:
                            if len(st.session_state[setup_key]) < COMPARISON_MAX_TICKERS:
                                st.session_state[setup_key].append(ticker)
                    st.rerun()
            else:
                st.info("Watchlist 沒有台股 ticker" if lang_zh else "No Taiwan tickers in watchlist")

    # === Entry point 3: From supply chain group ===
    supply_chain_configs = _main("SUPPLY_CHAIN_FOCUS_CONFIGS")
    if supply_chain_configs:
        with st.expander("🔗 從供應鏈組群加入" if lang_zh else "🔗 Add from supply chain group", expanded=False):
            group_options = list(supply_chain_configs.keys())
            group_label_map = {}
            for k, v in supply_chain_configs.items():
                if isinstance(v, dict):
                    label = v.get("label") or v.get("name") or k
                else:
                    label = k
                group_label_map[k] = label

            picked_group = st.selectbox(
                "選擇組群" if lang_zh else "Pick a group",
                options=group_options,
                format_func=lambda k: group_label_map.get(k, k),
                key="_comparison_group_pick",
            )
            if picked_group and picked_group in supply_chain_configs:
                cfg = supply_chain_configs[picked_group]
                if isinstance(cfg, dict):
                    group_tickers = cfg.get("tickers") or cfg.get("constituents") or []
                else:
                    group_tickers = []
                if group_tickers:
                    group_picks = st.multiselect(
                        "選擇個股(來自此組群)" if lang_zh else "Pick tickers from this group",
                        options=group_tickers,
                        default=[],
                        key="_comparison_group_picks",
                    )
                    grp_add_label = "加入" if lang_zh else "Add selected"
                    if st.button(grp_add_label, key="_comparison_grp_add_btn"):
                        for ticker in group_picks:
                            if ticker not in st.session_state[setup_key]:
                                if len(st.session_state[setup_key]) < COMPARISON_MAX_TICKERS:
                                    st.session_state[setup_key].append(ticker)
                        st.rerun()

    # === Selected chips display ===
    selected = st.session_state[setup_key]
    if selected:
        if lang_zh:
            st.markdown(f"**已選 ({len(selected)}/{COMPARISON_MAX_TICKERS}):**")
        else:
            st.markdown(f"**Selected ({len(selected)}/{COMPARISON_MAX_TICKERS}):**")

        # Render chips as columns with remove buttons
        cols = st.columns(min(len(selected), 5))
        for idx, ticker in enumerate(selected):
            with cols[idx % 5]:
                if st.button(f"❌ {ticker}", key=f"_comparison_remove_{ticker}",
                             help="點擊移除" if lang_zh else "Click to remove",
                             use_container_width=True):
                    st.session_state[setup_key] = [t for t in selected if t != ticker]
                    st.rerun()
    else:
        if lang_zh:
            st.info("👆 用上方任一方式加入 ticker")
        else:
            st.info("👆 Add tickers using any method above")

    return selected


# ---------------------------------------------------------------------------
# Parallel fetch — 4-dimension scores for all tickers
# ---------------------------------------------------------------------------

def _fetch_comparison_data(tickers: list[str]) -> dict:
    """Parallel-fetch evaluation card data for all tickers.

    Returns dict keyed by ticker:
        {ticker: {"tech": ..., "value": ..., "growth": ..., "chip": ...,
                  "overall_score": float, "name": str}}

    Uses ThreadPoolExecutor for concurrency (max_workers=5).
    Each ticker re-uses the v1.10.29 day-cached data via _fetch_eval_card_data.
    """
    _fetch_eval = _main("_fetch_eval_card_data")
    fetch_daily = _main("fetch_daily_data")
    display_label = _main("display_ticker_label", lambda t: t)

    if not _fetch_eval or not fetch_daily:
        return {}

    def _fetch_one(ticker: str) -> tuple[str, dict | None]:
        try:
            daily_df = fetch_daily(ticker)
            if daily_df is None or len(daily_df) < 30:
                return (ticker, None)
            scores = _fetch_eval(ticker, daily_df)
            return (ticker, scores)
        except Exception:
            return (ticker, None)

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(tickers))) as executor:
        future_to_ticker = {executor.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(future_to_ticker):
            ticker, scores = future.result()
            if scores is None:
                continue
            # Compute overall = mean of available dimensions
            dim_scores = [
                scores[k]["overall_score"] for k in ("tech", "value", "growth", "chip")
                if scores.get(k) is not None
            ]
            overall = round(sum(dim_scores) / len(dim_scores), 1) if dim_scores else 0.0
            results[ticker] = {
                **scores,
                "overall_score": overall,
                "name": display_label(ticker),
                "ticker": ticker,
                "dimensions_available": len(dim_scores),
            }

    return results


# ---------------------------------------------------------------------------
# Layer 2 — Comparison overview rendering
# ---------------------------------------------------------------------------

def _build_ranking(comparison_data: dict) -> list[dict]:
    """Sort by overall_score descending. Returns list with rank info."""
    items = list(comparison_data.values())
    items.sort(key=lambda x: x["overall_score"], reverse=True)
    for idx, item in enumerate(items):
        item["rank"] = idx + 1
    return items


def _verdict_for_ranking(ranked: list[dict], lang_zh: bool) -> str:
    """Generate the top-line verdict text based on score gaps."""
    if not ranked:
        return "" if lang_zh else ""
    if len(ranked) == 1:
        return f"{ranked[0]['name']} (僅 1 檔,無對比)" if lang_zh else f"{ranked[0]['name']} (only 1 ticker, no comparison)"

    top = ranked[0]
    second = ranked[1]
    gap = round(top["overall_score"] - second["overall_score"], 1)

    if lang_zh:
        if gap >= 1.5:
            return f"🏆 {top['name']} 顯著領先 (+{gap:.1f})"
        elif gap >= 0.5:
            return f"🏆 {top['name']} 略勝 (+{gap:.1f})"
        elif gap >= 0.1:
            return f"🏆 {top['name']} 微幅領先 (+{gap:.1f})"
        else:
            return f"⚖️ 整體分數接近(差距 ≤0.1),建議看細節決定"
    else:
        if gap >= 1.5:
            return f"🏆 {top['name']} clearly leads (+{gap:.1f})"
        elif gap >= 0.5:
            return f"🏆 {top['name']} slightly ahead (+{gap:.1f})"
        elif gap >= 0.1:
            return f"🏆 {top['name']} marginally ahead (+{gap:.1f})"
        else:
            return f"⚖️ Overall scores are close (≤0.1 gap) — check details"


def _verdict_chip_class(score: float) -> tuple[str, str, str]:
    """Map score → (CSS class, zh label, en label)."""
    if score >= 7.5:
        return ("ranking-verdict-strong", "優", "Strong")
    elif score >= 6.0:
        return ("ranking-verdict-good", "良", "Good")
    elif score >= 4.0:
        return ("ranking-verdict-avg", "中", "Average")
    else:
        return ("ranking-verdict-weak", "弱", "Weak")


def _render_ranking_cards(ranked: list[dict], lang_zh: bool) -> str:
    """Build the HTML for the ranking grid (Top 3+ cards)."""
    cards_html = []
    for item in ranked:
        rank = item["rank"]
        rank_class = f"rank-{rank}" if rank <= 3 else ""
        trophy = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else ""
        score = item["overall_score"]
        chip_cls, zh_label, en_label = _verdict_chip_class(score)
        chip_label = zh_label if lang_zh else en_label

        # Warning chip: technical score < 2
        warning_html = ""
        tech = item.get("tech")
        if tech and tech.get("overall_score", 5) < 2.0:
            warning_text = "⚠️ 技術面極弱" if lang_zh else "⚠️ Very weak technical"
            warning_html = f'<span class="ranking-warning-chip">{escape(warning_text)}</span>'

        # Show how many dimensions are available
        dims_label = ""
        dims_count = item.get("dimensions_available", 4)
        if dims_count < 4:
            note_zh = f"({dims_count}/4 維度可用)"
            note_en = f"({dims_count}/4 dims available)"
            dims_label = f'<div style="font-size:10px;color:#98a2b8;margin-top:3px;">{escape(note_zh if lang_zh else note_en)}</div>'

        cards_html.append(f"""
        <div class="ranking-card {rank_class}">
            <div class="ranking-rank">RANK #{rank}<span class="ranking-trophy">{trophy}</span></div>
            <div class="ranking-ticker">{escape(item['name'])}</div>
            <div class="ranking-score">{score:.1f}<span class="ranking-score-denom">/10</span></div>
            <div>
                <span class="ranking-verdict-chip {chip_cls}">{escape(chip_label)}</span>
                {warning_html}
            </div>
            {dims_label}
        </div>
        """)
    return f'<div class="ranking-grid">{"".join(cards_html)}</div>'


def _render_comparison_table(ranked: list[dict], lang_zh: bool) -> str:
    """Render the 5-row × N-col comparison table."""
    dim_labels_zh = {"overall": "綜合", "tech": "技術面", "value": "價值面", "growth": "成長面", "chip": "籌碼面"}
    dim_labels_en = {"overall": "Overall", "tech": "Technical", "value": "Value", "growth": "Growth", "chip": "Chip Flow"}
    dim_labels = dim_labels_zh if lang_zh else dim_labels_en

    rows = ["overall", "tech", "value", "growth", "chip"]

    # Build header
    header_cells = ['<th>' + (escape("維度") if lang_zh else "Dim") + '</th>']
    for item in ranked:
        header_cells.append(f'<th>{escape(item["name"])}</th>')
    header_cells.append('<th>' + (escape("勝者") if lang_zh else "Winner") + '</th>')

    # Build rows
    body_rows = []
    for dim in rows:
        row_class = "row-overall" if dim == "overall" else ""
        cells = [f'<td class="col-dim">{escape(dim_labels[dim])}</td>']

        scores_for_dim = []  # (item, score or None)
        for item in ranked:
            if dim == "overall":
                score = item["overall_score"]
            else:
                d = item.get(dim)
                score = d["overall_score"] if d is not None else None
            scores_for_dim.append((item, score))

            # Score cell
            if score is None:
                cells.append(f'<td class="col-score score-na">—</td>')
            else:
                score_cls = "score-good" if score >= 7 else "score-neutral" if score >= 4 else "score-poor"
                cells.append(f'<td class="col-score {score_cls}">{score:.1f}</td>')

        # Winner column
        valid_scores = [(item, s) for item, s in scores_for_dim if s is not None]
        if len(valid_scores) >= 2:
            valid_scores.sort(key=lambda x: x[1], reverse=True)
            winner = valid_scores[0][0]
            runner_up_score = valid_scores[1][1]
            gap = round(valid_scores[0][1] - runner_up_score, 1)
            winner_html = f'<span class="winner-badge">{escape(winner["name"])}</span>+{gap:.1f}'
            cells.append(f'<td class="col-winner">{winner_html}</td>')
        elif len(valid_scores) == 1:
            winner = valid_scores[0][0]
            note = "資料不足" if lang_zh else "Partial data"
            cells.append(f'<td class="col-winner">{escape(winner["name"])} ({escape(note)})</td>')
        else:
            cells.append(f'<td class="col-winner">—</td>')

        body_rows.append(f'<tr class="{row_class}">{"".join(cells)}</tr>')

    return f"""
    <div class="comp-table-wrap">
        <table class="comp-table">
            <thead><tr>{"".join(header_cells)}</tr></thead>
            <tbody>{"".join(body_rows)}</tbody>
        </table>
    </div>
    """


def _generate_insights(ranked: list[dict], lang_zh: bool) -> list[tuple[str, str]]:
    """Generate auto-insights as list of (insight_type, text).
    insight_type ∈ {"good", "trade-off", "warning"}
    """
    insights: list[tuple[str, str]] = []
    if not ranked or len(ranked) < 2:
        return insights

    top = ranked[0]
    others = ranked[1:]

    # === Insight 1: Top dimension drives the leader ===
    # Find the dimension where top has the largest gap to next
    best_dim_gap = None
    best_dim_label = ""
    for dim_key, dim_label_zh, dim_label_en in [
        ("tech", "技術面", "Technical"),
        ("value", "價值面", "Value"),
        ("growth", "成長面", "Growth"),
        ("chip", "籌碼面", "Chip Flow"),
    ]:
        top_dim = top.get(dim_key)
        if top_dim is None:
            continue
        other_scores = [o.get(dim_key, {}).get("overall_score") if o.get(dim_key) else None for o in others]
        other_scores = [s for s in other_scores if s is not None]
        if not other_scores:
            continue
        gap = top_dim["overall_score"] - max(other_scores)
        if gap > 0 and (best_dim_gap is None or gap > best_dim_gap):
            best_dim_gap = gap
            best_dim_label = dim_label_zh if lang_zh else dim_label_en

    if best_dim_gap is not None and best_dim_gap >= 1.0:
        if lang_zh:
            insights.append(("good", f"{top['name']} 在「{best_dim_label}」拉開最大差距 (+{best_dim_gap:.1f}),是領先的主因"))
        else:
            insights.append(("good", f"{top['name']} leads most in {best_dim_label} (+{best_dim_gap:.1f}) — main driver"))

    # === Insight 2: Trade-off — value vs growth ===
    value_winner = None
    value_winner_score = -1
    growth_winner = None
    growth_winner_score = -1
    for item in ranked:
        v = item.get("value")
        g = item.get("growth")
        if v and v["overall_score"] > value_winner_score:
            value_winner = item
            value_winner_score = v["overall_score"]
        if g and g["overall_score"] > growth_winner_score:
            growth_winner = item
            growth_winner_score = g["overall_score"]

    if (value_winner and growth_winner and value_winner["ticker"] != growth_winner["ticker"]
            and value_winner_score >= 5 and growth_winner_score >= 5):
        if lang_zh:
            insights.append((
                "trade-off",
                f"取捨:價值面偏好 {value_winner['name']} ({value_winner_score:.1f}),"
                f"成長面偏好 {growth_winner['name']} ({growth_winner_score:.1f})"
            ))
        else:
            insights.append((
                "trade-off",
                f"Trade-off: Value favors {value_winner['name']} ({value_winner_score:.1f}), "
                f"Growth favors {growth_winner['name']} ({growth_winner_score:.1f})"
            ))

    # === Insight 3: Warning — anyone with very weak technical ===
    weak_tech = [item for item in ranked
                  if item.get("tech") and item["tech"]["overall_score"] < 2.0]
    if weak_tech:
        names = ", ".join(item["name"] for item in weak_tech)
        if lang_zh:
            insights.append((
                "warning",
                f"⚠️ {names} 技術面 <2 (空頭排列),短期不利,考量基本面取捨"
            ))
        else:
            insights.append((
                "warning",
                f"⚠️ {names} has very weak technicals (<2) — caution short-term"
            ))

    # === Insight 4: All-around strong ===
    if top["overall_score"] >= 7.5:
        if lang_zh:
            insights.append(("good", f"{top['name']} 綜合 ≥7.5 屬於「優」級,4 維度均衡發展"))
        else:
            insights.append(("good", f"{top['name']} scored ≥7.5 overall — strong all-around"))

    # === Insight 5: Partial data warning ===
    partial_data = [item for item in ranked if item.get("dimensions_available", 4) < 4]
    if partial_data:
        names = ", ".join(item["name"] for item in partial_data)
        if lang_zh:
            insights.append((
                "warning",
                f"⚠️ {names} 缺少部分維度資料(如 .TWO 上櫃股的籌碼面),排名僅供參考"
            ))
        else:
            insights.append((
                "warning",
                f"⚠️ {names} has partial data (e.g. chip dim missing for OTC) — ranking is indicative"
            ))

    return insights


def _render_insights(insights: list[tuple[str, str]], lang_zh: bool) -> str:
    """Build the insights block HTML."""
    if not insights:
        return ""
    title = "💡 分析洞察" if lang_zh else "💡 Insights"
    items_html = []
    for insight_type, text in insights:
        cls = "insight-warning" if insight_type == "warning" else "insight-trade-off" if insight_type == "trade-off" else ""
        items_html.append(f'<div class="insights-item {cls}">{escape(text)}</div>')
    return f"""
    <div class="insights-wrap">
        <div class="insights-title">{escape(title)}</div>
        {"".join(items_html)}
    </div>
    """


def _render_comparison_overview(comparison_data: dict, lang_zh: bool) -> None:
    """Main Layer 2 render — ranking + table + insights."""
    render_html_block = _main("render_html_block")
    if not render_html_block:
        st.error("Cannot render — main module not loaded")
        return

    ranked = _build_ranking(comparison_data)
    if not ranked:
        msg = "⚠️ 沒有可用資料(可能 ticker 不存在或抓取失敗)" if lang_zh else "⚠️ No data available (tickers may not exist or fetch failed)"
        st.warning(msg)
        return

    # Top-line verdict
    verdict_text = _verdict_for_ranking(ranked, lang_zh)
    st.markdown(f"### {verdict_text}")

    # Ranking cards
    ranking_html = _render_ranking_cards(ranked, lang_zh)
    render_html_block(ranking_html)

    # Comparison table
    table_html = _render_comparison_table(ranked, lang_zh)
    render_html_block(table_html)

    # Insights
    insights = _generate_insights(ranked, lang_zh)
    insights_html = _render_insights(insights, lang_zh)
    if insights_html:
        render_html_block(insights_html)

    # Disclaimer
    disclaimer = (
        "⚠️ 量化指標自動計算,僅供研究參考,不構成投資建議。"
        if lang_zh else
        "⚠️ Quantitative indicators — for research only, not investment advice."
    )
    render_html_block(f'<div class="comparison-disclaimer">{escape(disclaimer)}</div>')


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def render_stock_comparison_dashboard(watchlist_tickers: list[str] | None = None) -> None:
    """v1.11.0: Top-level entry for the stock comparison dashboard.

    Called from main file's generate_dashboard() via early-return dispatch
    when dashboard_mode == "Stock Comparison" (or the localized name).

    Args:
        watchlist_tickers: optional list of tickers from user's watchlist
                          (passed in for quick-add convenience)
    """
    lang_zh = (_main("get_language", lambda: "zh_TW")() == "zh_TW")

    # Inject CSS
    _ensure_comparison_css()
    render_html_block = _main("render_html_block")
    if not render_html_block:
        st.error("⚠️ Cannot resolve main module. Please refresh the page.")
        return

    # Header
    title = "📊 個股對比與建議" if lang_zh else "📊 Stock Comparison & Recommendation"
    subtitle = (
        f"選 {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} 檔個股 → 4 維度對比 → 排名 → 點進工作台看細節(明天上線)"
        if lang_zh else
        f"Pick {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} tickers → 4-dim comparison → ranking → deep-dive workspace (tomorrow)"
    )
    render_html_block(f"""
    <div class="comparison-header">
        <div>
            <div class="comparison-title">{escape(title)}</div>
            <div class="comparison-subtitle">{escape(subtitle)}</div>
        </div>
    </div>
    """)

    # Layer 1 — Setup
    selected_tickers = _render_ticker_setup(watchlist_tickers or [])

    # Validation
    if len(selected_tickers) < COMPARISON_MIN_TICKERS:
        msg = (
            f"👆 請先選擇至少 {COMPARISON_MIN_TICKERS} 檔個股"
            if lang_zh else
            f"👆 Please select at least {COMPARISON_MIN_TICKERS} tickers first"
        )
        st.info(msg)
        return

    # Compare button
    st.markdown("---")
    run_label = "▶ 開始對比 (Compare)" if lang_zh else "▶ Start Comparison"
    if st.button(run_label, key="_comparison_run_btn", type="primary", use_container_width=True):
        st.session_state["_comparison_locked_tickers"] = list(selected_tickers)

    # Show comparison if a run is locked
    locked = st.session_state.get("_comparison_locked_tickers")
    if not locked:
        info_msg = (
            "👆 點上方按鈕開始對比"
            if lang_zh else
            "👆 Click the button above to start comparison"
        )
        st.info(info_msg)
        return

    # Layer 2 — Fetch + render overview
    spinner_text = (
        f"正在平行抓取 {len(locked)} 檔個股的 4 維度評估資料..."
        if lang_zh else
        f"Fetching 4-dimension evaluation data for {len(locked)} tickers in parallel..."
    )
    with st.spinner(spinner_text):
        comparison_data = _fetch_comparison_data(locked)

    if not comparison_data:
        msg = (
            "⚠️ 所有 ticker 的資料抓取都失敗 — 請檢查 ticker 是否正確"
            if lang_zh else
            "⚠️ Failed to fetch data for all tickers — please check ticker symbols"
        )
        st.error(msg)
        return

    if len(comparison_data) < len(locked):
        failed = [t for t in locked if t not in comparison_data]
        msg = (
            f"⚠️ 部分 ticker 抓取失敗:{', '.join(failed)}"
            if lang_zh else
            f"⚠️ Some tickers failed to fetch: {', '.join(failed)}"
        )
        st.warning(msg)

    # Layer 2 render
    _render_comparison_overview(comparison_data, lang_zh)

    # Tomorrow note
    tomorrow_msg = (
        "🚧 Layer 3「深入工作台」明天上線,可點某一檔進完整工作台看新聞 / 評估卡 / 警示層"
        if lang_zh else
        "🚧 Layer 3 (deep-dive workspace tabs) coming tomorrow — click into each ticker for full workspace"
    )
    render_html_block(
        f'<div style="font-size:12px;color:#98a2b8;font-style:italic;margin-top:18px;'
        f'padding-top:12px;border-top:1px dashed rgba(96,140,200,0.15);">{escape(tomorrow_msg)}</div>'
    )
