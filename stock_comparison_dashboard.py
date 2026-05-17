"""
stock_comparison_dashboard.py
=============================

Individual Stock Comparison & Recommendation Dashboard — v1.12.0 (2026-05-11)

Extracted as a separate module (similar to ai_analysis_dashboard.py) so the
main file (already ~49,200 lines) doesn't grow further. This module owns
the entire "📊 個股對比與建議" full-page experience.

v1.12.0 ARCHITECTURE CHANGE (per user request):
-----------------------------------------------
Instead of a custom comparison render, this module now DELEGATES to the
main file's existing render_comparison_section() (line ~27645), which is
the existing "Comparison Arena" already used by Supply Chain Lab etc.
That brings:
  - 🏆 Winner card (existing)
  - 🎯 Opportunity radar (existing)
  - 3-tile hero (strongest / best 1Y / best news)
  - Comparison overview cards (digest_items grid)
  - Comparison focus detail (pill selector + drill-down)

The 4-dimension evaluation card data (tech/value/growth/chip) is fetched
in parallel here, then attached to each bundle as bundle["eval_scores"]
BEFORE passing to render_comparison_section. Main file's
build_comparison_digest_items + render_comparison_overview_cards have been
enhanced (v1.12.0) to display a 4-dim chip strip when eval_scores is present.

Layer 1 — 對比設置(Setup):
    Same as before. User picks 2-5 tickers via three entry points.

Layer 2 — 對比總覽(Overview, the Hero):
    NEW (v1.12.0): delegates to render_comparison_section().
    Eval card data attached to bundles upstream.

Layer 3 — 深入工作台(Deep Dive, TOMORROW polish):
    Per-ticker tab. Each tab uses render_ticker_page() from main file.

Public surface
--------------
  - render_stock_comparison_dashboard()    : top-level entry

Imports from main file (deferred via _main_module bridge)
---------------------------------------------------------
  - render_comparison_section(daily_data, intraday_data, tickers, lens_meta)
  - collect_ticker_context(daily_data, intraday_data, ticker, news_limit)
  - fetch_daily_data(tickers_list, period, interval)
  - fetch_intraday_data(tickers_list)
  - _fetch_eval_card_data(ticker, daily_df) — 4-dim scoring
  - render_eval_card_html, _ensure_eval_card_css
  - get_language, display_ticker_label, is_taiwan_ticker
  - SUPPLY_CHAIN_FOCUS_CONFIGS

Note on .TWO (OTC) stocks
-------------------------
TPEx 307 still unresolved (last attempted v1.10.31). Chip dimension for
.TWO stocks shows "資料準備中". Ranking still works on 3 dimensions
(tech + value + growth).
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


def _display_label(ticker: str, lang_zh: bool = True) -> str:
    """v1.13.8: Convert a ticker to a human-friendly label that includes
    the company name when available.

      "2330.TW" → "2330.TW 台積電"
      "3711.TW" → "3711.TW 日月光投控"
      "NVDA"    → "NVDA NVIDIA"
      "AAPL"    → "AAPL Apple"
      Unknown ticker → just "TICKER" (no suffix)

    Used in chip rendering, multiselect format_func, and any other UI
    spot that needs to show ticker + name together. Single source of
    truth — adjust here and all surfaces update.
    """
    if not ticker:
        return ""
    tk = str(ticker).upper().strip()
    resolver = _main("_resolve_ticker_display_name")
    if not callable(resolver):
        return tk
    try:
        name = resolver(tk) or ""
    except Exception:
        name = ""
    if name:
        return f"{tk} {name}"
    return tk


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
  font-size: 20px;
  font-weight: 600;
  color: #f1f5f9;
}

.comparison-subtitle {
  font-size: 13px;
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
  font-size: 12px;
  color: #98a2b8;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.ranking-trophy {
  font-size: 18px;
  margin-left: 6px;
}

.ranking-ticker {
  font-size: 17px;
  font-weight: 600;
  color: #f1f5f9;
  margin: 4px 0 6px 0;
}

.ranking-score {
  font-size: 28px;
  font-weight: 700;
  color: #f1f5f9;
}

.ranking-score-denom {
  font-size: 14px;
  color: #98a2b8;
  font-weight: 400;
}

.ranking-verdict-chip {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
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
  font-size: 15px;
}

.comp-table th, .comp-table td {
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid rgba(96,140,200,0.10);
}

.comp-table th {
  background: rgba(15,22,35,0.7);
  font-weight: 600;
  color: #98a2b8;
  font-size: 14px;
  letter-spacing: 0.03em;
}

.comp-table .row-overall td {
  font-weight: 600;
  background: rgba(96,140,200,0.04);
}

.comp-table .col-dim {
  color: #98a2b8;
  font-weight: 500;
  font-size: 14px;
}

.comp-table .col-score {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 15px;
  font-weight: 600;
}

.comp-table .score-good    { color: #5ed79a; }
.comp-table .score-neutral { color: #d4be7b; }
.comp-table .score-poor    { color: #e98787; }
.comp-table .score-na      { color: #6c7686; font-style: italic; }

.comp-table .col-winner {
  color: #c2cdde;
  font-size: 13px;
}

.comp-table .winner-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 8px;
  background: rgba(82,196,138,0.16);
  color: #6dc28a;
  font-size: 12px;
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
  font-size: 14px;
  font-weight: 600;
  color: #c2cdde;
  margin-bottom: 8px;
}

.insights-item {
  font-size: 14px;
  color: #d8e1ec;
  margin: 8px 0;
  padding-left: 16px;
  position: relative;
  line-height: 1.65;
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
  font-size: 12px;
  color: #98a2b8;
  font-style: italic;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed rgba(96,140,200,0.15);
}

@media (max-width: 768px) {
  .comparison-shell { padding: 16px 14px; }
  .comparison-title { font-size: 17px; }
  .comp-table { font-size: 13px; }
  .comp-table th, .comp-table td { padding: 9px 7px; }
  .comp-table th { font-size: 12px; }
  .comp-table .col-dim { font-size: 13px; }
  .comp-table .col-score { font-size: 14px; }
  .comp-table .col-winner { font-size: 12px; }
  .ranking-score { font-size: 24px; }
  .ranking-ticker { font-size: 16px; }
  .insights-item { font-size: 13px; }
}

/* v1.12.0d: Force visible Material icons + text on remove/clear-all buttons.
   ROOT CAUSE: Streamlit's default light theme renders secondary buttons with
   white-on-white in non-hover state — icon/text only becomes visible on hover.
   FIX: Use Streamlit's modern element key API (st.button now adds a
   `st-key-{key}` class to its parent div) to scope CSS to our specific
   buttons without affecting other secondary buttons in the app.
*/
.st-key-_comparison_clear_all_btn button,
div[class*="st-key-_comparison_remove_"] button {
    background: rgba(82, 196, 138, 0.12) !important;
    border: 1px solid rgba(82, 196, 138, 0.32) !important;
    color: #d8e1ec !important;
    transition: all 0.18s ease !important;
}
.st-key-_comparison_clear_all_btn button *,
div[class*="st-key-_comparison_remove_"] button * {
    color: #d8e1ec !important;
    fill: #d8e1ec !important;
}
.st-key-_comparison_clear_all_btn button svg,
div[class*="st-key-_comparison_remove_"] button svg {
    fill: #d8e1ec !important;
    color: #d8e1ec !important;
    stroke: #d8e1ec !important;
    opacity: 1 !important;
}
.st-key-_comparison_clear_all_btn button p,
div[class*="st-key-_comparison_remove_"] button p {
    color: #d8e1ec !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}
/* Hover: brighter green, white icon for clear feedback */
.st-key-_comparison_clear_all_btn button:hover,
div[class*="st-key-_comparison_remove_"] button:hover {
    background: rgba(82, 196, 138, 0.28) !important;
    border-color: rgba(82, 196, 138, 0.55) !important;
    transform: translateY(-1px);
}
.st-key-_comparison_clear_all_btn button:hover *,
div[class*="st-key-_comparison_remove_"] button:hover *,
.st-key-_comparison_clear_all_btn button:hover svg,
div[class*="st-key-_comparison_remove_"] button:hover svg {
    color: #ffffff !important;
    fill: #ffffff !important;
    stroke: #ffffff !important;
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

    v1.11.0a:
      - 2 expanders converted to st.toggle (project-wide standard from v1.10.30)
      - Text input + button aligned with label_visibility="collapsed"

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
    # v1.11.0a: Show label as markdown above so it's separate from the input row,
    # then text_input + button on the same row both with label_visibility="collapsed"
    # → vertically aligned.
    if lang_zh:
        st.markdown("**輸入 ticker(逗號分隔,例如 2330,2317,2454)**")
    else:
        st.markdown("**Enter tickers (comma-separated, e.g. 2330,2317,2454)**")

    col1, col2 = st.columns([4, 1])
    with col1:
        text_input = st.text_input(
            "ticker input",
            value="",
            key="_comparison_text_input",
            placeholder="2330, 2317, 2454" if lang_zh else "2330, 2317, 2454",
            label_visibility="collapsed",
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

    # === Entry point 2: From watchlist (toggle, project-wide standard) ===
    wl_toggle_label = "📋 從 Watchlist 加入" if lang_zh else "📋 Add from watchlist"
    wl_open = st.toggle(wl_toggle_label, key="_comparison_wl_toggle", value=False)
    if not wl_open:
        hint = "👆 開啟上方開關可顯示 Watchlist 多選" if lang_zh else "👆 Toggle on to show watchlist multi-select"
        st.markdown(
            f'<div style="color:#98a2b8; font-size:12px; font-style:italic; '
            f'margin: 4px 0 14px 0; padding-left: 4px;">{escape(hint)}</div>',
            unsafe_allow_html=True,
        )
    else:
        # v1.13.10: Accept ALL watchlist tickers (both 台股 + 美股).
        # Previously filtered by is_taiwan_ticker() which excluded US tickers
        # like INTC/MSFT/AMZN — even though Stock Comparison fully supports
        # mixed/US scopes. The filter was a leftover from an earlier
        # Taiwan-focused iteration.
        all_watchlist = list(watchlist_tickers) if watchlist_tickers else []
        if all_watchlist:
            # v1.13.8: format_func adds Chinese company name to each option
            # while keeping ticker as the underlying value.
            wl_picks = st.multiselect(
                "從 watchlist 多選" if lang_zh else "Multi-select from watchlist",
                options=all_watchlist,
                default=[],
                key="_comparison_wl_picks",
                format_func=lambda t: _display_label(t, lang_zh),
                label_visibility="collapsed",
            )
            wl_add_label = "加入所選" if lang_zh else "Add selected"
            if st.button(wl_add_label, key="_comparison_wl_add_btn"):
                for ticker in wl_picks:
                    if ticker not in st.session_state[setup_key]:
                        if len(st.session_state[setup_key]) < COMPARISON_MAX_TICKERS:
                            st.session_state[setup_key].append(ticker)
                st.rerun()
        else:
            st.info("Watchlist 是空的" if lang_zh else "Watchlist is empty")

    # === Entry point 3: From supply chain group (toggle) ===
    sc_toggle_label = "🔗 從供應鏈組群加入" if lang_zh else "🔗 Add from supply chain group"
    sc_open = st.toggle(sc_toggle_label, key="_comparison_sc_toggle", value=False)
    if not sc_open:
        hint = "👆 開啟上方開關可選供應鏈組群" if lang_zh else "👆 Toggle on to pick a supply chain group"
        st.markdown(
            f'<div style="color:#98a2b8; font-size:12px; font-style:italic; '
            f'margin: 4px 0 14px 0; padding-left: 4px;">{escape(hint)}</div>',
            unsafe_allow_html=True,
        )
    else:
        supply_chain_configs = _main("SUPPLY_CHAIN_FOCUS_CONFIGS")
        if supply_chain_configs:
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
                    # v1.13.8: Apply name resolution to supply chain group options too
                    group_picks = st.multiselect(
                        "選擇個股(來自此組群)" if lang_zh else "Pick tickers from this group",
                        options=group_tickers,
                        default=[],
                        key="_comparison_group_picks",
                        format_func=lambda t: _display_label(t, lang_zh),
                    )
                    grp_add_label = "加入所選" if lang_zh else "Add selected"
                    if st.button(grp_add_label, key="_comparison_grp_add_btn"):
                        for ticker in group_picks:
                            if ticker not in st.session_state[setup_key]:
                                if len(st.session_state[setup_key]) < COMPARISON_MAX_TICKERS:
                                    st.session_state[setup_key].append(ticker)
                        st.rerun()
                else:
                    st.info(
                        "此組群沒有 ticker"
                        if lang_zh else "No tickers in this group"
                    )
        else:
            st.info(
                "找不到供應鏈組群設定"
                if lang_zh else "Supply chain config not available"
            )

    # === Selected chips display ===
    selected = st.session_state[setup_key]
    if selected:
        if lang_zh:
            st.markdown(f"**已選 ({len(selected)}/{COMPARISON_MAX_TICKERS}):**")
        else:
            st.markdown(f"**Selected ({len(selected)}/{COMPARISON_MAX_TICKERS}):**")

        # v1.12.0c (Option D): HTML chip + per-ticker Material icon close button
        # + clear-all reset button below.
        # v1.13.8: chip now includes Chinese company name when resolvable
        # (e.g. "📌 2330.TW 台積電" instead of just "📌 2330.TW").
        cols = st.columns(min(len(selected), 5))
        for idx, ticker in enumerate(selected):
            with cols[idx % 5]:
                # v1.13.8: Use _display_label so name is appended when known.
                chip_label = _display_label(ticker, lang_zh)
                # Chip with proper contrast (dark text on themed background)
                chip_html = (
                    f'<div style="background: rgba(82, 196, 138, 0.14); '
                    f'border: 1px solid rgba(82, 196, 138, 0.35); '
                    f'border-radius: 18px; padding: 8px 14px; text-align: center; '
                    f'font-weight: 600; color: #c2cdde; font-size: 14px; '
                    f'margin-bottom: 6px; letter-spacing: 0.02em;">'
                    f'📌 {escape(chip_label)}'
                    f'</div>'
                )
                st.markdown(chip_html, unsafe_allow_html=True)

                # Per-ticker remove button — Material icon (Streamlit 1.34+).
                # Wrap in try/except for graceful fallback on older versions.
                remove_clicked = False
                btn_key = f"_comparison_remove_{ticker}"
                btn_help = f"移除 {ticker}" if lang_zh else f"Remove {ticker}"
                try:
                    # Streamlit 1.34+: empty label + icon = icon-only button
                    remove_clicked = st.button(
                        "",
                        icon=":material/close:",
                        key=btn_key,
                        help=btn_help,
                        use_container_width=True,
                    )
                except TypeError:
                    # Fallback for older Streamlit without icon parameter
                    remove_clicked = st.button(
                        "✕",
                        key=btn_key,
                        help=btn_help,
                        use_container_width=True,
                    )

                if remove_clicked:
                    st.session_state[setup_key] = [t for t in selected if t != ticker]
                    # Also clear locked state so user doesn't see stale comparison
                    st.session_state.pop("_comparison_locked_tickers", None)
                    st.rerun()

        # v1.12.0c: Clear-all reset button (handles "fresh start" case)
        st.markdown("")  # tiny spacer
        clear_all_label = "🗑 清空全部 ticker" if lang_zh else "🗑 Clear all tickers"
        clear_all_help = (
            "一鍵移除所有已選 ticker,從頭開始"
            if lang_zh else
            "Remove all selected tickers and start fresh"
        )
        if st.button(
            clear_all_label,
            key="_comparison_clear_all_btn",
            help=clear_all_help,
            use_container_width=True,
        ):
            st.session_state[setup_key] = []
            st.session_state.pop("_comparison_locked_tickers", None)
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

    v1.11.0a fix: use the actual main-file API signature for fetch_daily_data,
    which is `fetch_daily_data([ticker], period, interval)` returning a
    multi-ticker DataFrame; then extract per-ticker OHLCV via get_series().
    """
    _fetch_eval = _main("_fetch_eval_card_data")
    fetch_daily = _main("fetch_daily_data")
    get_series = _main("get_series")
    display_label = _main("display_ticker_label", lambda t: t)

    if not _fetch_eval or not fetch_daily or not get_series:
        return {}

    def _build_daily_df_for_ticker(ticker: str):
        """Wrap main file's fetch_daily_data + get_series into a single-ticker
        OHLCV DataFrame (the format _fetch_eval_card_data expects).

        v1.11.0b: dropped the misguided "^TWII batch" hack and added 1-retry
        for yfinance transient failures. Single-ticker fetch is more reliable
        for some Taiwan tickers (e.g. 2454.TW occasionally fails in batch mode).
        """
        def _try_fetch():
            try:
                multi_df = fetch_daily([ticker], "1y", "1d")
                if multi_df is None or multi_df.empty:
                    return None
                open_s = get_series(multi_df, "Open", ticker)
                high_s = get_series(multi_df, "High", ticker)
                low_s = get_series(multi_df, "Low", ticker)
                close_s = get_series(multi_df, "Close", ticker)
                vol_s = get_series(multi_df, "Volume", ticker)
                if close_s is None or len(close_s) < 30:
                    return None
                df = pd.concat({
                    "Open": open_s, "High": high_s, "Low": low_s,
                    "Close": close_s, "Volume": vol_s,
                }, axis=1).dropna(subset=["Close"])
                if len(df) < 30:
                    return None
                return df
            except Exception:
                return None

        # First attempt
        result = _try_fetch()
        if result is not None:
            return result

        # Retry once after a short pause (yfinance can have transient failures)
        import time
        time.sleep(0.6)
        return _try_fetch()

    def _fetch_one(ticker: str) -> tuple[str, dict | None]:
        try:
            daily_df = _build_daily_df_for_ticker(ticker)
            if daily_df is None:
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

def _render_four_dim_hero(bundles: list[dict], eval_scores_dict: dict, lang_zh: bool) -> None:
    """v1.12.0a: Prominent 4-dimension hero section rendered BEFORE the
    main Comparison Arena. Gives the user immediate visibility into the
    4-dim ranking without scrolling.

    Layout:
      ┌──────────────────────────────────────────────────────────┐
      │ 📊 4 維度評估對比                                          │
      │ Top 1: 2330 (avg 7.05)                                   │
      │                                                          │
      │ ┌────────────┐ ┌────────────┐ ┌────────────┐            │
      │ │ 2330 7.05  │ │ 2454 6.23  │ │ 2317 6.05  │            │
      │ │ 技 7.4 🟢  │ │ 技 6.5 🟢  │ │ 技 5.0 🟡  │            │
      │ │ 價 4.3 🟡  │ │ 價 5.1 🟡  │ │ 價 7.2 🟢  │            │
      │ │ 成 8.8 🟢  │ │ 成 7.0 🟢  │ │ 成 5.5 🟡  │            │
      │ │ 籌 7.7 🟢  │ │ 籌 6.3 🟢  │ │ 籌 6.5 🟢  │            │
      │ └────────────┘ └────────────┘ └────────────┘            │
      └──────────────────────────────────────────────────────────┘
    """
    render_html_block = _main("render_html_block")
    display_label = _main("display_ticker_label", lambda t: t)
    if not render_html_block:
        return

    # Build per-ticker summary
    items = []
    for bundle in bundles:
        ticker = bundle["ticker"]
        scores = eval_scores_dict.get(ticker)
        if not scores:
            continue
        dim_values = []
        for dim_key in ("tech", "value", "growth", "chip"):
            d = scores.get(dim_key)
            if d is not None:
                dim_values.append(d["overall_score"])
        if not dim_values:
            continue
        overall = round(sum(dim_values) / len(dim_values), 2)
        items.append({
            "ticker": ticker,
            "name": display_label(ticker),
            "overall": overall,
            "scores": scores,
            "dims_available": len(dim_values),
        })

    if not items:
        return  # no eval scores at all — skip silently

    # Sort by overall desc
    items.sort(key=lambda x: x["overall"], reverse=True)

    # Verdict
    top = items[0]
    if len(items) >= 2:
        gap = round(top["overall"] - items[1]["overall"], 2)
        if gap >= 1.5:
            verdict_zh = f"🏆 {top['name']} 顯著領先 (+{gap:.1f})"
            verdict_en = f"🏆 {top['name']} clearly leads (+{gap:.1f})"
        elif gap >= 0.5:
            verdict_zh = f"🏆 {top['name']} 略勝 (+{gap:.1f})"
            verdict_en = f"🏆 {top['name']} slightly ahead (+{gap:.1f})"
        elif gap >= 0.1:
            verdict_zh = f"🏆 {top['name']} 微幅領先 (+{gap:.1f})"
            verdict_en = f"🏆 {top['name']} marginally ahead (+{gap:.1f})"
        else:
            verdict_zh = "⚖️ 4 維度分數接近,看細節決定"
            verdict_en = "⚖️ 4-dim scores are close — check details"
    else:
        verdict_zh = f"{top['name']} (僅 1 檔可評)"
        verdict_en = f"{top['name']} (only 1 evaluable)"

    verdict = verdict_zh if lang_zh else verdict_en

    title = "📊 4 維度量化評估對比" if lang_zh else "📊 4-Dimension Quant Evaluation"
    subtitle = (
        "技術面 / 價值面 / 成長面 / 籌碼面 — 各維 0-10 分平均後的綜合排名"
        if lang_zh else
        "Technical / Value / Growth / Chip — averaged quant ranking across 4 dimensions"
    )

    # Color class helper
    def _score_class(score):
        if score >= 7: return "fdh-good"
        if score >= 4: return "fdh-mid"
        return "fdh-poor"

    dim_labels_zh = {"tech": "技術", "value": "價值", "growth": "成長", "chip": "籌碼"}
    dim_labels_en = {"tech": "Tech", "value": "Value", "growth": "Growth", "chip": "Chip"}
    dim_labels = dim_labels_zh if lang_zh else dim_labels_en

    # Build cards
    card_html_list = []
    for rank_idx, item in enumerate(items):
        rank = rank_idx + 1
        trophy = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        rank_class = f"fdh-rank-{rank}" if rank <= 3 else ""

        # Per-dim rows
        dim_rows = []
        for dim_key in ("tech", "value", "growth", "chip"):
            d = item["scores"].get(dim_key)
            label = dim_labels[dim_key]
            if d is None:
                dim_rows.append(
                    f'<div class="fdh-dim-row fdh-dim-na">'
                    f'<span class="fdh-dim-label">{escape(label)}</span>'
                    f'<span class="fdh-dim-score">—</span></div>'
                )
            else:
                score = d["overall_score"]
                pct = max(0, min(100, int(score * 10)))
                cls = _score_class(score)
                dim_rows.append(
                    f'<div class="fdh-dim-row {cls}">'
                    f'<span class="fdh-dim-label">{escape(label)}</span>'
                    f'<div class="fdh-dim-bar"><div class="fdh-dim-bar-fill" style="width:{pct}%;"></div></div>'
                    f'<span class="fdh-dim-score">{score:.1f}</span></div>'
                )

        # Partial data warning
        partial_warning = ""
        if item["dims_available"] < 4:
            warn_text = f"{item['dims_available']}/4 維度" if lang_zh else f"{item['dims_available']}/4 dims"
            partial_warning = f'<div class="fdh-partial">⚠️ {escape(warn_text)}</div>'

        card_html_list.append(f"""
        <div class="fdh-card {rank_class}">
            <div class="fdh-card-head">
                <span class="fdh-rank">{trophy}</span>
                <span class="fdh-ticker">{escape(item['name'])}</span>
            </div>
            <div class="fdh-overall">
                <span class="fdh-overall-num">{item['overall']:.1f}</span>
                <span class="fdh-overall-denom">/10</span>
            </div>
            <div class="fdh-dim-grid">
                {"".join(dim_rows)}
            </div>
            {partial_warning}
        </div>
        """)

    # Inline CSS scoped to fdh-* classes
    fdh_css = """
    <style>
    .fdh-shell {
        background: linear-gradient(180deg, rgba(20,28,42,0.85), rgba(15,22,35,0.85));
        border: 1px solid rgba(96,140,200,0.2);
        border-radius: 16px;
        padding: 22px 26px;
        margin: 16px 0;
    }
    .fdh-header {
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(96,140,200,0.15);
    }
    .fdh-title {
        font-size: 18px;
        font-weight: 600;
        color: #f1f5f9;
    }
    .fdh-subtitle {
        font-size: 12px;
        color: #98a2b8;
        margin-top: 2px;
    }
    .fdh-verdict {
        font-size: 16px;
        font-weight: 600;
        color: #f1f5f9;
        margin: 8px 0 14px 0;
    }
    .fdh-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px;
    }
    .fdh-card {
        background: rgba(15,22,35,0.6);
        border: 1px solid rgba(96,140,200,0.15);
        border-radius: 12px;
        padding: 14px 16px;
    }
    .fdh-card.fdh-rank-1 {
        border-color: rgba(82,196,138,0.4);
        background: linear-gradient(135deg, rgba(82,196,138,0.10), rgba(15,22,35,0.6));
    }
    .fdh-card.fdh-rank-2 { border-color: rgba(199,178,108,0.32); }
    .fdh-card.fdh-rank-3 { border-color: rgba(199,178,108,0.22); }

    .fdh-card-head {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 8px;
    }
    .fdh-rank { font-size: 18px; }
    .fdh-ticker {
        font-size: 16px;
        font-weight: 600;
        color: #f1f5f9;
    }
    .fdh-overall {
        margin-bottom: 12px;
    }
    .fdh-overall-num {
        font-size: 32px;
        font-weight: 700;
        color: #f1f5f9;
    }
    .fdh-overall-denom {
        font-size: 14px;
        color: #98a2b8;
    }
    .fdh-dim-grid {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    .fdh-dim-row {
        display: grid;
        grid-template-columns: 50px 1fr 40px;
        gap: 8px;
        align-items: center;
        font-size: 13px;
    }
    .fdh-dim-label {
        color: #98a2b8;
        font-size: 12px;
    }
    .fdh-dim-bar {
        background: rgba(255,255,255,0.06);
        height: 6px;
        border-radius: 3px;
        overflow: hidden;
    }
    .fdh-dim-bar-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.3s ease;
    }
    .fdh-good .fdh-dim-bar-fill { background: linear-gradient(90deg, #5ed79a, #6dc28a); }
    .fdh-mid  .fdh-dim-bar-fill { background: linear-gradient(90deg, #d4be7b, #c2ae6b); }
    .fdh-poor .fdh-dim-bar-fill { background: linear-gradient(90deg, #e98787, #d97777); }
    .fdh-good .fdh-dim-score { color: #6dc28a; font-weight: 600; }
    .fdh-mid  .fdh-dim-score { color: #d4be7b; font-weight: 600; }
    .fdh-poor .fdh-dim-score { color: #e98787; font-weight: 600; }
    .fdh-dim-na .fdh-dim-score { color: #6c7686; font-style: italic; }
    .fdh-dim-na .fdh-dim-bar-fill { background: transparent; }
    .fdh-dim-score {
        font-family: 'SF Mono', Menlo, monospace;
        font-size: 13px;
        text-align: right;
    }
    .fdh-partial {
        font-size: 11px;
        color: #d4be7b;
        margin-top: 8px;
        font-style: italic;
    }
    </style>
    """
    render_html_block(fdh_css)
    render_html_block(f"""
    <div class="fdh-shell">
        <div class="fdh-header">
            <div class="fdh-title">{escape(title)}</div>
            <div class="fdh-subtitle">{escape(subtitle)}</div>
        </div>
        <div class="fdh-verdict">{escape(verdict)}</div>
        <div class="fdh-grid">
            {"".join(card_html_list)}
        </div>
    </div>
    """)


def _compute_eval_scores_from_shared(daily_data, tickers: list[str]) -> dict:
    """v1.12.0b: Compute 4-dim eval scores using already-fetched daily_data.

    KEY DIFFERENCE from earlier versions: This does NOT re-fetch daily data.
    It re-uses the multi-ticker DataFrame that the main flow already fetched
    via fetch_daily_data(tickers, "1y", "1d"). Per-ticker OHLCV is extracted
    in-memory via get_series. This eliminates the yfinance race conditions
    that caused 2454/2308/etc to fail.

    yfinance.info for value/growth scoring is STILL fetched per-ticker
    (it's part of _fetch_eval_card_data internals), but daily-OHLCV is no
    longer re-fetched.

    Returns dict {ticker: {tech, value, growth, chip}} keyed by ticker.
    Tickers that fail compute (e.g. missing data) are silently omitted.
    """
    _fetch_eval = _main("_fetch_eval_card_data")
    get_series = _main("get_series")

    if not _fetch_eval or not get_series:
        return {}

    if daily_data is None or daily_data.empty:
        return {}

    def _extract_df(ticker: str):
        """Extract per-ticker OHLCV DataFrame from the shared multi-ticker frame."""
        try:
            open_s = get_series(daily_data, "Open", ticker)
            high_s = get_series(daily_data, "High", ticker)
            low_s = get_series(daily_data, "Low", ticker)
            close_s = get_series(daily_data, "Close", ticker)
            vol_s = get_series(daily_data, "Volume", ticker)
            if close_s is None or len(close_s) < 30:
                return None
            df = pd.concat({
                "Open": open_s, "High": high_s, "Low": low_s,
                "Close": close_s, "Volume": vol_s,
            }, axis=1).dropna(subset=["Close"])
            return df if len(df) >= 30 else None
        except Exception:
            return None

    def _compute_one(ticker: str):
        try:
            df = _extract_df(ticker)
            if df is None:
                return (ticker, None)
            return (ticker, _fetch_eval(ticker, df))
        except Exception:
            return (ticker, None)

    results: dict[str, dict] = {}
    # Still use ThreadPool to parallelize yfinance.info calls inside _fetch_eval
    # (value + growth dim fetches). But the daily-data part is now zero-fetch.
    with ThreadPoolExecutor(max_workers=min(5, len(tickers))) as executor:
        futures = {executor.submit(_compute_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, scores = future.result()
            if scores is not None:
                results[ticker] = scores
    return results


def _fetch_eval_scores_parallel(tickers: list[str]) -> dict:
    """v1.12.0: Parallel-fetch 4-dim eval card scores for all tickers.

    Returns dict {ticker: {tech, value, growth, chip}} for use as bundle["eval_scores"].
    Each ticker may have a None for some dims (e.g. chip dim for .TWO stocks).
    """
    _fetch_eval = _main("_fetch_eval_card_data")
    fetch_daily = _main("fetch_daily_data")
    get_series = _main("get_series")

    if not _fetch_eval or not fetch_daily or not get_series:
        return {}

    def _build_df(ticker):
        def _try():
            try:
                multi_df = fetch_daily([ticker], "1y", "1d")
                if multi_df is None or multi_df.empty:
                    return None
                open_s = get_series(multi_df, "Open", ticker)
                high_s = get_series(multi_df, "High", ticker)
                low_s = get_series(multi_df, "Low", ticker)
                close_s = get_series(multi_df, "Close", ticker)
                vol_s = get_series(multi_df, "Volume", ticker)
                if close_s is None or len(close_s) < 30:
                    return None
                df = pd.concat({
                    "Open": open_s, "High": high_s, "Low": low_s,
                    "Close": close_s, "Volume": vol_s,
                }, axis=1).dropna(subset=["Close"])
                return df if len(df) >= 30 else None
            except Exception:
                return None
        # 2 attempts with backoff
        df = _try()
        if df is not None:
            return df
        import time
        time.sleep(0.6)
        return _try()

    def _fetch_one(ticker):
        try:
            daily_df = _build_df(ticker)
            if daily_df is None:
                return (ticker, None)
            return (ticker, _fetch_eval(ticker, daily_df))
        except Exception:
            return (ticker, None)

    results = {}
    with ThreadPoolExecutor(max_workers=min(5, len(tickers))) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, scores = future.result()
            if scores is not None:
                results[ticker] = scores
    return results


def render_stock_comparison_dashboard(watchlist_tickers: list[str] | None = None) -> None:
    """v1.12.0: Top-level entry for the stock comparison dashboard.

    Delegates Layer 2 rendering to main file's existing render_comparison_section().
    This module retains responsibility for:
      - Layer 1: ticker selection UI (text input / watchlist / supply chain)
      - Eval scores parallel fetch
      - Bundle construction via collect_ticker_context
      - Attaching eval_scores to bundles before delegating
    """
    lang_zh = (_main("get_language", lambda: "zh_TW")() == "zh_TW")

    _ensure_comparison_css()
    render_html_block = _main("render_html_block")
    if not render_html_block:
        st.error("⚠️ Cannot resolve main module. Please refresh the page.")
        return

    # Header
    title = "📊 個股對比與建議" if lang_zh else "📊 Stock Comparison & Recommendation"
    subtitle = (
        f"選 {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} 檔個股 → 重用 Comparison Arena + 4 維度評分整合"
        if lang_zh else
        f"Pick {COMPARISON_MIN_TICKERS}-{COMPARISON_MAX_TICKERS} tickers → Reuses Comparison Arena + 4-dim score integration"
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

    locked = st.session_state.get("_comparison_locked_tickers")
    if not locked:
        info_msg = (
            "👆 點上方按鈕開始對比"
            if lang_zh else
            "👆 Click the button above to start comparison"
        )
        st.info(info_msg)
        return

    # === Step 1: Batch fetch daily + intraday using main file's APIs ===
    fetch_daily = _main("fetch_daily_data")
    fetch_intraday = _main("fetch_intraday_data")
    collect_ticker_context = _main("collect_ticker_context")
    render_comparison_section = _main("render_comparison_section")

    if not all([fetch_daily, fetch_intraday, collect_ticker_context, render_comparison_section]):
        st.error(
            "⚠️ 主模組元件解析失敗 — 請 reboot Streamlit"
            if lang_zh else
            "⚠️ Main module components not resolved — please reboot Streamlit"
        )
        return

    spinner_text = (
        f"正在抓取 {len(locked)} 檔個股資料(daily / intraday / 4 維度)..."
        if lang_zh else
        f"Fetching data for {len(locked)} tickers (daily / intraday / 4-dim)..."
    )
    with st.spinner(spinner_text):
        # Step 1: batch fetch daily + intraday (single yfinance call each)
        try:
            daily_data = fetch_daily(list(locked), "1y", "1d")
        except Exception as exc:
            st.error(f"Daily data fetch failed: {exc}")
            return

        try:
            intraday_data = fetch_intraday(list(locked))
        except Exception:
            intraday_data = None  # intraday is optional

        # Step 2: compute 4-dim eval scores from SHARED daily_data (v1.12.0b)
        # No re-fetch — uses the multi-ticker DataFrame we already have.
        # This eliminates the yfinance race conditions that caused 2454/2308/etc fails.
        eval_scores_dict = _compute_eval_scores_from_shared(daily_data, list(locked))

        # Step 3: build bundles via collect_ticker_context
        bundles_with_eval = []
        failed_tickers = []
        for ticker in locked:
            try:
                bundle = collect_ticker_context(daily_data, intraday_data, ticker, news_limit=8)
                if bundle is None:
                    failed_tickers.append(ticker)
                    continue
                # v1.12.0: attach eval scores to the bundle
                if ticker in eval_scores_dict:
                    bundle["eval_scores"] = eval_scores_dict[ticker]
                bundles_with_eval.append(bundle)
            except Exception:
                failed_tickers.append(ticker)

    # Failure notice
    if failed_tickers:
        msg = (
            f"⚠️ 部分 ticker 抓取失敗:{', '.join(failed_tickers)}"
            if lang_zh else
            f"⚠️ Some tickers failed to fetch: {', '.join(failed_tickers)}"
        )
        st.warning(msg)

    if not bundles_with_eval:
        msg = (
            "⚠️ 所有 ticker 都抓取失敗 — 請檢查 ticker 是否正確"
            if lang_zh else
            "⚠️ All tickers failed — please check the ticker symbols"
        )
        st.error(msg)
        return

    if len(bundles_with_eval) < 2:
        ticker_str = bundles_with_eval[0]["ticker"]
        msg = (
            f"⚠️ 只有 1 檔成功抓取({ticker_str}),需要至少 2 檔才能對比"
            if lang_zh else
            f"⚠️ Only 1 ticker fetched ({ticker_str}). Need at least 2 to compare"
        )
        st.warning(msg)
        return

    # === Step 4: PROMINENT 4-dim hero section (v1.12.0a) ===
    # Render the 4-dimension comparison BEFORE delegating to Comparison Arena.
    # This way the 4-dim view is hero-positioned, not buried in Top Picks.
    _render_four_dim_hero(bundles_with_eval, eval_scores_dict, lang_zh)

    # === Step 5: DELEGATE to main file's existing Comparison Arena ===
    # render_comparison_section handles:
    #   - Winner card
    #   - Opportunity radar
    #   - 3-tile hero (strongest / best 1Y / best news)
    #   - Comparison overview cards (now with 4-dim chip strip per v1.12.0)
    #   - Comparison focus detail
    valid_tickers = [b["ticker"] for b in bundles_with_eval]

    # We need to push eval_scores INTO the bundles that render_comparison_section
    # will re-build via collect_ticker_context. Approach: monkey-patch by
    # storing eval_scores in session_state for retrieval inside main file's
    # build_comparison_digest_items, OR pre-populate a session_state key.
    # SIMPLEST: render_comparison_section re-creates bundles, so we use a
    # session-state side-channel.
    st.session_state["_comparison_eval_scores_side_channel"] = eval_scores_dict

    try:
        render_comparison_section(daily_data, intraday_data, valid_tickers)
    except Exception as exc:
        st.error(
            f"Comparison Arena 渲染失敗:{exc}"
            if lang_zh else
            f"Comparison Arena render failed: {exc}"
        )
        return
    finally:
        # Clean up side channel
        st.session_state.pop("_comparison_eval_scores_side_channel", None)

    # Tomorrow note
    tomorrow_msg = (
        "🚧 Layer 3「深入工作台」明天上線,可點某一檔進完整工作台看新聞 / 評估卡 / 警示層"
        if lang_zh else
        "🚧 Layer 3 (deep-dive workspace tabs) coming tomorrow"
    )
    render_html_block(
        f'<div style="font-size:12px;color:#98a2b8;font-style:italic;margin-top:18px;'
        f'padding-top:12px;border-top:1px dashed rgba(96,140,200,0.15);">{escape(tomorrow_msg)}</div>'
    )
