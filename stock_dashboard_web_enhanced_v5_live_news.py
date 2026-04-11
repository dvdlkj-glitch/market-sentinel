#!/usr/bin/env python
from __future__ import annotations

import json
from html import escape, unescape
import re
import textwrap
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# ---------------------------
# Configuration
# ---------------------------
DEFAULT_TICKERS = ["NVDA", "2330.TW", "2454.TW"]
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
SUPPORTED_PERIODS = ["3mo", "6mo", "1y", "2y"]
SUPPORTED_INTERVALS = ["1d", "1wk"]

PLANNER_TIMEFRAME_OPTIONS = ["2w", "1m", "3m", "6m", "9m", "1y"]
PLANNER_TIMEFRAME_MONTHS = {"2w": 0.5, "1m": 1.0, "3m": 3.0, "6m": 6.0, "9m": 9.0, "1y": 12.0}
PLANNER_UPSIDE_MULTIPLIERS = {"2w": 0.42, "1m": 0.55, "3m": 0.72, "6m": 1.0, "9m": 1.18, "1y": 1.32}
PLANNER_STOP_MULTIPLIERS = {"2w": 0.62, "1m": 0.74, "3m": 0.84, "6m": 1.0, "9m": 1.10, "1y": 1.18}

PLANNER_ENTRY_FILL_PROBABILITIES = {
    "2w": (1.00, 0.32, 0.10),
    "1m": (1.00, 0.44, 0.18),
    "3m": (1.00, 0.58, 0.32),
    "6m": (1.00, 0.72, 0.48),
    "9m": (1.00, 0.82, 0.62),
    "1y": (1.00, 0.90, 0.74),
}
PLANNER_TARGET_PROGRESS = {"2w": 0.28, "1m": 0.40, "3m": 0.62, "6m": 0.82, "9m": 0.92, "1y": 1.00}
PLANNER_CONSERVATIVE_CAPS = {"2w": 10.0, "1m": 12.0, "3m": 16.0, "6m": 20.0, "9m": 23.0, "1y": 26.0}
PLANNER_BASE_CAPS = {"2w": 18.0, "1m": 22.0, "3m": 26.0, "6m": 32.0, "9m": 36.0, "1y": 40.0}
PLANNER_STRETCH_CAPS = {"2w": 26.0, "1m": 32.0, "3m": 36.0, "6m": 46.0, "9m": 52.0, "1y": 58.0}
PLANNER_STOP_TIGHT_CAPS = {"2w": 7.0, "1m": 8.0, "3m": 9.0, "6m": 10.5, "9m": 12.0, "1y": 13.5}
PLANNER_STOP_BALANCED_CAPS = {"2w": 9.0, "1m": 10.5, "3m": 12.0, "6m": 15.0, "9m": 16.8, "1y": 18.5}
PLANNER_STOP_WIDE_CAPS = {"2w": 12.0, "1m": 14.0, "3m": 16.0, "6m": 20.0, "9m": 22.0, "1y": 24.0}

TREND_LENSES = {
    "Fast Read": {
        "period": "3mo",
        "interval": "1d",
        "title": "Fast Read",
        "hook": "Best for fresh news reactions and short swing context.",
        "how_to_read": "Use this when you want to know whether the last few weeks of headlines are accelerating momentum or fading.",
        "watch_for": "Gap follow-through, recent support tests, and whether the signal is getting stronger or weaker quickly.",
    },
    "Swing Map": {
        "period": "6mo",
        "interval": "1d",
        "title": "Swing Map",
        "hook": "Best balance for active traders and medium-term setups.",
        "how_to_read": "This is the most practical lens for comparing current trend structure against the last few earnings or macro cycles.",
        "watch_for": "Repeated resistance zones, clean pullbacks, momentum resets, and breakout confirmation.",
    },
    "Position View": {
        "period": "1y",
        "interval": "1d",
        "title": "Position View",
        "hook": "Best for seeing whether the thesis still holds over a fuller trend year.",
        "how_to_read": "Use this when you care more about structural strength than daily noise.",
        "watch_for": "Price vs SMA 200, sustained trend quality, and whether news is supporting or fighting the bigger move.",
    },
    "Cycle View": {
        "period": "2y",
        "interval": "1wk",
        "title": "Cycle View",
        "hook": "Best for stepping back and judging the bigger regime.",
        "how_to_read": "This lens is for spotting full-cycle behavior, not precise entries.",
        "watch_for": "Major inflection points, long-term leadership, and whether the stock is still in a broad accumulation or deterioration phase.",
    },
}
DEFAULT_TREND_LENS = "Position View"

US_WATCHLIST_GROUPS = [
    "Tech & AI",
    "Semiconductors",
    "Financials",
    "Healthcare",
    "Consumer",
    "Industrials",
    "Energy",
    "Communication",
    "Utilities & REITs",
    "Transportation",
    "Market ETFs",
]

TAIWAN_WATCHLIST_GROUPS = [
    "Taiwan Semiconductors",
    "Taiwan AI Supply Chain",
    "Taiwan Financials",
    "Taiwan Shipping & Cyclicals",
    "Taiwan ETFs",
]

WATCHLIST_PRESETS = {
    "Tech & AI": ["NVDA", "AMD", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "TSLA", "AVGO", "QCOM", "CRM", "ADBE", "PLTR", "SMCI"],
    "Semiconductors": ["NVDA", "AMD", "AVGO", "QCOM", "INTC", "MU", "TXN", "AMAT", "LRCX", "KLAC", "MRVL", "ON"],
    "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "C", "SCHW", "AXP", "COF", "V", "MA"],
    "Healthcare": ["LLY", "JNJ", "UNH", "MRK", "ABBV", "PFE", "ISRG", "BSX", "TMO", "SYK"],
    "Consumer": ["WMT", "COST", "PG", "KO", "PEP", "MCD", "NKE", "SBUX", "HD", "LOW", "TGT"],
    "Industrials": ["GE", "CAT", "DE", "RTX", "LMT", "BA", "HON", "UNP", "UPS", "ETN"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY", "VLO", "KMI"],
    "Communication": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "T", "VZ", "CHTR", "CMCSA", "ROKU"],
    "Utilities & REITs": ["NEE", "DUK", "SO", "AEP", "EXC", "PLD", "AMT", "EQIX", "O", "SPG"],
    "Transportation": ["UBER", "FDX", "DAL", "UAL", "LUV", "CSX", "NSC", "ODFL", "JBHT", "EXPD"],
    "Market ETFs": ["SPY", "QQQ", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "SMH", "SOXX"],
    "Taiwan Semiconductors": ["2330.TW", "2454.TW", "2303.TW", "3711.TW", "3034.TW", "2379.TW", "2408.TW"],
    "Taiwan AI Supply Chain": ["2317.TW", "2382.TW", "3231.TW", "6669.TW", "2308.TW", "2357.TW", "2376.TW", "2345.TW", "3715.TW"],
    "Taiwan Financials": ["2881.TW", "2882.TW", "2891.TW", "2886.TW", "2884.TW", "2885.TW"],
    "Taiwan Shipping & Cyclicals": ["2603.TW", "2609.TW", "2615.TW", "1301.TW", "2002.TW"],
    "Taiwan ETFs": ["0050.TW", "0056.TW", "00878.TW", "006208.TW"],
}

MARKET_SCOPE_OPTIONS = {
    "Mixed (U.S. + Taiwan)": "Mixed (U.S. + Taiwan)",
    "U.S. only": "U.S. only",
    "Taiwan only": "Taiwan only",
}

MARKET_SCOPE_DEFAULT_GROUPS = {
    "Mixed (U.S. + Taiwan)": ["Tech & AI", "Semiconductors", "Market ETFs", "Taiwan Semiconductors", "Taiwan AI Supply Chain", "Taiwan ETFs"],
    "U.S. only": ["Tech & AI", "Semiconductors", "Financials", "Healthcare", "Consumer", "Industrials", "Energy", "Market ETFs"],
    "Taiwan only": ["Taiwan Semiconductors", "Taiwan AI Supply Chain", "Taiwan Financials", "Taiwan ETFs"],
}

TAIWAN_TICKER_METADATA = {
    "2330.TW": {"code": "2330", "zh": "台積電", "en": "TSMC"},
    "2454.TW": {"code": "2454", "zh": "聯發科", "en": "MediaTek"},
    "2303.TW": {"code": "2303", "zh": "聯電", "en": "UMC"},
    "3711.TW": {"code": "3711", "zh": "日月光投控", "en": "ASE", "aliases": ["ASE", "日月光", "日月光控股", "Advanced Semiconductor Engineering"]},
    "3715.TW": {"code": "3715", "zh": "定穎投控", "en": "Dynamic Holding", "aliases": ["定穎投資控股", "Dynamic Holding Co., Ltd.", "Dynamic Holding"]},
    "3034.TW": {"code": "3034", "zh": "聯詠", "en": "Novatek"},
    "2379.TW": {"code": "2379", "zh": "瑞昱", "en": "Realtek"},
    "2408.TW": {"code": "2408", "zh": "南亞科", "en": "Nanya"},
    "2317.TW": {"code": "2317", "zh": "鴻海", "en": "Foxconn"},
    "2382.TW": {"code": "2382", "zh": "廣達", "en": "Quanta"},
    "3231.TW": {"code": "3231", "zh": "緯創", "en": "Wistron"},
    "6669.TW": {"code": "6669", "zh": "緯穎", "en": "Wiwynn"},
    "2308.TW": {"code": "2308", "zh": "台達電", "en": "Delta"},
    "2357.TW": {"code": "2357", "zh": "華碩", "en": "ASUS"},
    "2376.TW": {"code": "2376", "zh": "技嘉", "en": "GIGABYTE"},
    "2345.TW": {"code": "2345", "zh": "智邦", "en": "Accton"},
    "2881.TW": {"code": "2881", "zh": "富邦金", "en": "Fubon Financial"},
    "2882.TW": {"code": "2882", "zh": "國泰金", "en": "Cathay Financial"},
    "2891.TW": {"code": "2891", "zh": "中信金", "en": "CTBC Financial"},
    "2886.TW": {"code": "2886", "zh": "兆豐金", "en": "Mega Financial"},
    "2884.TW": {"code": "2884", "zh": "玉山金", "en": "E.Sun Financial"},
    "2885.TW": {"code": "2885", "zh": "元大金", "en": "Yuanta Financial"},
    "2603.TW": {"code": "2603", "zh": "長榮", "en": "Evergreen Marine"},
    "2609.TW": {"code": "2609", "zh": "陽明", "en": "Yang Ming"},
    "2615.TW": {"code": "2615", "zh": "萬海", "en": "Wan Hai"},
    "1301.TW": {"code": "1301", "zh": "台塑", "en": "Formosa Plastics"},
    "2002.TW": {"code": "2002", "zh": "中鋼", "en": "China Steel"},
    "0050.TW": {"code": "0050", "zh": "元大台灣50", "en": "Yuanta Taiwan 50"},
    "0056.TW": {"code": "0056", "zh": "元大高股息", "en": "Yuanta High Dividend"},
    "00878.TW": {"code": "00878", "zh": "國泰永續高股息", "en": "Cathay ESG High Dividend"},
    "006208.TW": {"code": "006208", "zh": "富邦台50", "en": "Fubon Taiwan 50"},
}

DEFAULT_WATCHLIST_UNIVERSE = sorted({ticker for group in WATCHLIST_PRESETS.values() for ticker in group} | {"TSM"})
INTRADAY_PERIOD = "5d"
INTRADAY_INTERVAL = "5m"
PRICE_FIELDS_PRIORITY = ["Adj Close", "Close"]
US_TZ = ZoneInfo("America/New_York")
TW_TZ = ZoneInfo("Asia/Taipei")

POSITIVE_NEWS_KEYWORDS = {
    "beat", "beats", "upgrade", "upgrades", "surge", "surges", "gain", "gains",
    "growth", "record", "strong", "raises", "raise", "buyback", "partnership",
    "expansion", "expands", "wins", "outperform", "bullish", "rebound", "jump",
    "orders", "demand", "guidance raised", "margin expands", "breakthrough", "approval",
    "成長", "擴產", "上修", "調升", "看好", "受惠", "訂單", "需求強勁", "合作", "創高", "利多", "獲利成長",
}
NEGATIVE_NEWS_KEYWORDS = {
    "miss", "misses", "downgrade", "downgrades", "fall", "falls", "drop", "drops",
    "slump", "slumps", "cuts", "cut", "weak", "warning", "lawsuit", "probe",
    "investigation", "delay", "delays", "decline", "declines", "bearish", "selloff",
    "recall", "ban", "tariff", "fine", "antitrust", "layoff", "margin pressure",
    "下修", "調降", "衰退", "疲弱", "利空", "調查", "罰款", "延後", "出口限制", "裁員", "下滑",
}

TARGET_REFERENCE_KEYWORDS = {
    "price target", "target price", "target raised", "target cut", "target lowered",
    "analyst", "upgrade", "downgrade", "rating", "outperform", "underperform",
    "目標價", "調高", "調降", "上修", "下修", "外資", "法人", "買進", "中立", "賣出",
}

st.set_page_config(page_title="David Lau Stock Market Vision", page_icon="📈", layout="wide")



GLOBAL_REFERENCE_INDICES = [
    {"ticker": "^IXIC", "label_key": "global_market_nasdaq"},
    {"ticker": "^GSPC", "label_key": "global_market_sp500"},
    {"ticker": "^DJI", "label_key": "global_market_dow"},
    {"ticker": "^TWII", "label_key": "global_market_taiex"},
]

LANGUAGE_OPTIONS = {
    "English": "English",
    "繁體中文": "繁體中文",
}

DEVICE_CONTROL_OPTIONS = {
    "Auto detect": "Auto detect",
    "Manual override": "Manual override",
}

DEVICE_MODE_OPTIONS = {
    "Desktop": "Desktop",
    "iPad": "iPad",
    "Smartphone Fold Portrait": "Smartphone Fold Portrait",
    "Smartphone Fold Landscape": "Smartphone Fold Landscape",
    "Smartphone": "Smartphone",
}

LEGACY_DEVICE_MODE_ALIASES = {
    "Smartphone Fold": "Smartphone Fold Portrait",
}

NEWS_DISPLAY_OPTIONS = {
    "Original source": "Original source",
    "Bilingual assist": "Bilingual assist",
    "Chinese-first assist": "Chinese-first assist",
}

TRANSLATIONS = {
    "English": {
        "app_name": "David Lau Stock Market Vision",
        "top_intro": "A calmer, more premium market workspace focused on clarity, hierarchy, and deeper exploration across comparison, catalysts, news, and chart structure.",
        "language": "Language",
        "headline_note": "Interface language changes the dashboard chrome. Taiwan tickers now prefer Taiwan/Traditional Chinese news sources when available.",
        "command_layer": "Command Layer",
        "hero_title": "Institutional-style market research, redesigned with a calmer premium theme.",
        "hero_copy": "The new direction is cleaner, darker, and more focused. It reduces visual noise, strengthens hierarchy, and makes the journey from watchlist scan to deep ticker research feel more intentional.",
        "chip_news_flow": "News-first reading flow",
        "chip_winner": "Winner card with context",
        "chip_catalyst_guide": "Catalyst Engine reference guide",
        "chip_trading_lab": "Trading Lab interpretation",
        "chip_richer_journey": "Same theme, richer journey",
        "guide_title": "A more focused flow for deeper exploration",
        "guide_copy": "Each section now behaves like part of a deliberate workflow: scan, compare, understand the driver, then validate the setup.",
        "step_1": "Step 1",
        "step_2": "Step 2",
        "step_3": "Step 3",
        "step_4": "Step 4",
        "comparison_arena": "Comparison Arena",
        "comparison_arena_copy": "Scan the watchlist fast. This is the shortlist stage where you decide which names deserve attention first.",
        "winner_card": "Winner Card",
        "winner_card_copy": "See which selected stock currently has the strongest setup and why the edge exists versus the next name.",
        "catalyst_news_alerts": "Catalyst + News + Alerts",
        "catalyst_news_alerts_copy": "Find out what is actually driving the narrative, then check how each lens sees the setup: earnings, AI demand, regulation, macro, analysts, or supply chain can shift different lenses in different ways.",
        "trading_lab_candles": "Trading Lab + Candles",
        "trading_lab_candles_copy": "Only after the narrative makes sense should you confirm the structure with the active trend lens, MACD, Bollinger context, support, resistance, and candles.",
        "trend_lens": "Trend Lens",
        "best_use": "Best use",
        "how_to_read_it": "How to read it",
        "what_this_lens_good_at": "What this lens is good at",
        "watch_for": "Watch for",
        "most_useful_reference_points": "Most useful reference points",
        "winner_card_adapts": "The Winner Card and comparison scores now adapt to this active lens, so the strongest stock can change depending on whether you care about fresh reaction, swing structure, position strength, or cycle leadership.",
        "reference_guide_for": "Reference guide for {ticker}",
        "reference_copy": "This panel explains what matters most in the current setup, so readers understand why each section exists instead of just seeing another chart or score.",
        "what_to_watch_in_news": "What to watch in news",
        "what_gives_conviction": "What gives conviction",
        "trading_lens": "Trading lens",
        "decision_brief": "Decision Brief",
        "what_matters_now_for": "What matters now for {ticker}",
        "decision_brief_copy": "This is the quick executive read. It pulls the signal, catalyst engine, Trading Lab, and current alerts into one plain-language plan before the deeper research sections.",
        "current_stance": "Current stance",
        "dominant_catalyst": "Dominant catalyst",
        "best_execution_style": "Best execution style",
        "main_risk_flag": "Main risk flag",
        "lead_story_label": "Lead story",
        "next_best_action": "Next best action",
        "signal_deck": "Pro Signal Deck",
        "confidence": "Confidence",
        "news_pulse": "News Pulse",
        "intraday": "Intraday",
        "top_story": "Top Story",
        "estimated_effect_on": "Estimated effect on {ticker}: {probability}%",
        "why_this_matters_now": "Why this matters now",
        "setup_context": "{ticker} setup context",
        "estimated_effect": "Estimated effect",
        "chance_nudges": "Chance this story materially nudges {ticker} in the shown direction over the near term.",
        "open_article": "Open article ↗",
        "story": "Story {idx:02d}",
        "relevance": "Relevance",
        "why_this_could_matter": "Why this could matter to {ticker}:",
        "related_tickers": "Related tickers:",
        "top_news_stories": "Top News Stories",
        "news_board_copy": "Selected-stock stories first. Use the highlights board to spot what matters most, then move into the full story rows for detail, relevance, and directional context.",
        "no_recent_news": "No recent stock-specific news was returned for {ticker}.",
        "daily_briefing": "Daily Briefing",
        "alert_layer": "Alert Layer",
        "alert_layer_copy": "Each lens now has its own alert state, so the same stock can be Fast Read bullish while still being Cycle View mixed or laggard.",
        "control_center": "Control Center",
        "vision_deck": "Vision Deck",
        "vision_deck_copy": "Build a broader U.S. and Taiwan market watchlist, compare selected names side by side, and refresh the live tape in one modern control panel.",
        "market_scope": "Market scope",
        "market_scope_note": "Switch between U.S., Taiwan, or a blended cross-market watchlist. Taiwan numeric symbols entered manually will auto-map to Yahoo Finance format.",
        "market_scope_mixed": "Mixed (U.S. + Taiwan)",
        "market_scope_us": "U.S. only",
        "market_scope_tw": "Taiwan only",
        "watchlist_universe": "Watchlist universe",
        "preset_groups": "Preset groups",
        "expand_by_sector": "Expand by sector...",
        "tickers": "Tickers",
        "pick_watchlist_symbols": "Pick any watchlist symbols...",
        "custom_symbols": "Custom symbols",
        "custom_symbols_placeholder": "Add any U.S. or Taiwan symbol, e.g. HOOD, NET, 2330, 2454, 0050",
        "watchlist_caption": "Build a broader U.S. and Taiwan watchlist by group, then add any extra symbol manually. Custom entries are injected into the picker immediately, and Taiwan numeric codes like 2330, 3715, or 0050 auto-convert to Yahoo Finance format.",
        "manual_period_override": "Manual period override",
        "custom_lookback": "Custom lookback",
        "custom_interval": "Custom interval",
        "reference_lens": "Reference lens",
        "live_refresh": "Live refresh",
        "refresh_live_data": "Refresh live data",
        "refresh_caption": "News-first layout. Daily trend drives the Sentinel signal. Taiwan stocks now flow through the same comparison, decision brief, news, and candlestick structure as U.S. names.",
        "please_select_ticker": "Please select at least one ticker.",
        "loading_data": "Loading market data and stock-specific news...",
        "no_market_data": "No market data was returned. Please try again.",
        "footer_note": "This dashboard is for research and reference. The news effect percentages and directional labels are heuristic estimates, not guarantees or investment advice.",
        "explorer_navigation": "Explorer Navigation",
        "choose_ticker_workspace": "Choose a ticker below to enter its full market workspace",
        "explorer_nav_copy": "This is the transition from screening into deep research. Select any ticker tab below and the dashboard shifts into that stock’s own workspace with related news, catalyst mapping, lens-aware alerts, Trading Lab, and candlestick confirmation.",
        "what_happens_next": "What happens next",
        "open_ticker_workspace": "Open a ticker workspace ↓",
        "open_ticker_workspace_copy": "You’ll move into that stock’s dedicated workspace, where the news, catalysts, alerts, and chart structure are all focused on just that one name.",
        "news_display_mode": "News display mode",
        "news_display_note": "Choose whether news sections stay source-first or add a Chinese reading assist for Taiwan users.",
        "news_mode_original": "Original source",
        "news_mode_bilingual": "Bilingual assist",
        "news_mode_chinese_first": "Chinese-first assist",
        "news_helper_label": "Taiwan quick read",
        "news_reason_label": "Why it matters",
        "source_summary_label": "Source summary",
        "no_source_summary": "No source summary was provided.",
        "news_helper_template": "{ticker}: {direction}. Estimated short-term effect {probability}%. Confidence {confidence}, relevance {relevance}.",
        "directional_pressure": "Directional pressure",
        "directional_pressure_copy": "Reference estimate of how strongly the story could influence the selected stock in the near term.",
        "up_down_pressure": "Up {pos}% / Down {neg}%",
        "trend_lab": "Trend Lab",
        "candlestick_confirmation": "Candlestick confirmation",
        "trend_lab_copy": "This section stays near the bottom so readers first absorb the story, impact estimate, and signal stack before confirming structure with the active trend lens and live tape.",
        "last_daily_close": "Last daily close",
        "trading_lab": "Trading Lab",
        "trend_1y": "1Y trend",
        "comparison_title": "Modern side-by-side setup for price strength and signal quality",
        "comparison_copy": "Use this section to scan which stock has stronger trend structure, cleaner recommendation quality, and better news support before opening the full ticker workspace.",
        "strongest_pro_setup": "Strongest Pro setup",
        "best_1y_price_strength": "Best 1Y price strength",
        "best_current_news_tailwind": "Best current news tailwind",
        "side_by_side_profile": "Side-by-side profile",
        "lens_score": "Lens Score",
        "last_price": "Last price",
        "signal": "Signal",
        "intraday_move": "Intraday move",
        "recent_structure": "{ticker} recent structure",
        "research_view_only": "Research view only. The signal combines moving averages, RSI, volume confirmation, 1-year trend, and current stock-specific news pulse.",
        "lead_story_context": "Lead story context",
        "active_lens_focus": "Active lens focus",
        "no_extra_alert_context": "No extra alert context is active.",
        "bullish_count": "Bullish {count}",
        "neutral_count": "Neutral {count}",
        "bearish_count": "Bearish {count}",
    },
    "繁體中文": {
        "app_name": "David Lau 股票市場視野",
        "top_intro": "更沉穩、更高級的市場研究工作台，強調清晰層級、內容探索，以及比較、催化劑、新聞與圖表結構之間的串聯。",
        "language": "語言",
        "headline_note": "介面語言會切換儀表板文字與導覽，新聞標題仍保留原始來源語言。",
        "command_layer": "操作層",
        "hero_title": "以更沉穩高級的主題，重新設計機構風格的市場研究體驗。",
        "hero_copy": "新版方向更乾淨、更深色、更聚焦，降低視覺噪音、強化資訊層級，讓使用者從觀察清單掃描走到個股深度研究時更自然。",
        "chip_news_flow": "新聞優先閱讀流程",
        "chip_winner": "含脈絡的勝出卡",
        "chip_catalyst_guide": "Catalyst Engine 參考指南",
        "chip_trading_lab": "Trading Lab 解讀",
        "chip_richer_journey": "同一主題，更完整流程",
        "guide_title": "更聚焦、更適合深度探索的流程",
        "guide_copy": "每個區塊都像是研究流程的一部分：先掃描、再比較、理解驅動因子，最後確認型態。",
        "step_1": "步驟 1",
        "step_2": "步驟 2",
        "step_3": "步驟 3",
        "step_4": "步驟 4",
        "comparison_arena": "比較區",
        "comparison_arena_copy": "快速掃描觀察清單。這是建立候選名單的階段，先決定哪些標的值得優先關注。",
        "winner_card": "勝出卡",
        "winner_card_copy": "看出目前哪一檔最有優勢，並理解它相對其他標的為何更具吸引力。",
        "catalyst_news_alerts": "催化劑 + 新聞 + 警示",
        "catalyst_news_alerts_copy": "先找出真正驅動敘事的因素，再觀察不同鏡頭如何看待目前型態：財報、AI 需求、監管、總經、分析師動作或供應鏈，都可能讓不同鏡頭得出不同結論。",
        "trading_lab_candles": "Trading Lab + K 線",
        "trading_lab_candles_copy": "只有當敘事合理後，才用目前趨勢鏡頭、MACD、布林帶、支撐、壓力與 K 線來確認結構。",
        "trend_lens": "趨勢鏡頭",
        "best_use": "最佳用途",
        "how_to_read_it": "如何閱讀",
        "what_this_lens_good_at": "這個鏡頭最擅長什麼",
        "watch_for": "觀察重點",
        "most_useful_reference_points": "最有用的參考點",
        "winner_card_adapts": "Winner Card 與比較分數會依照目前鏡頭自動調整，所以最強標的會隨著你更重視短線反應、波段結構、部位強度或週期領導而改變。",
        "reference_guide_for": "{ticker} 參考指南",
        "reference_copy": "這個面板用來說明目前配置下最重要的觀察點，讓使用者理解每個區塊存在的原因，而不只是看到另一張圖或另一個分數。",
        "what_to_watch_in_news": "新聞觀察重點",
        "what_gives_conviction": "信心來源",
        "trading_lens": "交易風格",
        "decision_brief": "決策摘要",
        "what_matters_now_for": "{ticker} 當前重點",
        "decision_brief_copy": "這是快速高層摘要。它會把訊號、Catalyst Engine、Trading Lab 與目前警示整合成一個容易採取行動的說明，再進入更深入的研究區塊。",
        "current_stance": "目前立場",
        "dominant_catalyst": "主導催化劑",
        "best_execution_style": "較佳執行方式",
        "main_risk_flag": "主要風險",
        "lead_story_label": "主要新聞",
        "next_best_action": "下一步建議",
        "signal_deck": "專業訊號面板",
        "confidence": "信心",
        "news_pulse": "新聞脈動",
        "intraday": "盤中",
        "top_story": "焦點新聞",
        "estimated_effect_on": "對 {ticker} 的預估影響：{probability}%",
        "why_this_matters_now": "現在為什麼重要",
        "setup_context": "{ticker} 目前型態脈絡",
        "estimated_effect": "預估影響",
        "chance_nudges": "這則新聞在短期內，可能讓 {ticker} 朝目前方向產生明顯推動的機率。",
        "open_article": "開啟文章 ↗",
        "story": "新聞 {idx:02d}",
        "relevance": "關聯度",
        "why_this_could_matter": "這則新聞為何可能影響 {ticker}：",
        "related_tickers": "相關股票：",
        "top_news_stories": "重點新聞",
        "news_board_copy": "先看所選股票的新聞。先用 highlights 區看出重點，再進入完整新聞列查看細節、關聯度與方向脈絡。",
        "no_recent_news": "{ticker} 目前沒有抓到近期的個股新聞。",
        "daily_briefing": "每日摘要",
        "alert_layer": "警示層",
        "alert_layer_copy": "每個鏡頭都有自己的警示狀態，所以同一檔股票可能在 Fast Read 偏多，但在 Cycle View 仍屬混合或落後。",
        "control_center": "控制中心",
        "vision_deck": "Vision Deck",
        "vision_deck_copy": "建立更完整的美股與台股觀察清單、並排比較所選標的，並在同一個現代化控制面板中刷新即時資料。",
        "market_scope": "市場範圍",
        "market_scope_note": "可在美股、台股或混合觀察清單之間切換。手動輸入台股數字代號時，系統會自動轉成 Yahoo Finance 可用格式。",
        "market_scope_mixed": "混合（美股＋台股）",
        "market_scope_us": "僅美股",
        "market_scope_tw": "僅台股",
        "watchlist_universe": "觀察清單範圍",
        "preset_groups": "預設群組",
        "expand_by_sector": "依產業擴充…",
        "tickers": "股票代號",
        "pick_watchlist_symbols": "挑選觀察清單股票代號…",
        "custom_symbols": "自訂代號",
        "custom_symbols_placeholder": "加入任何美股或台股代號，例如 HOOD、NET、2330、2454、0050",
        "watchlist_caption": "你可以依群組建立更完整的美股與台股觀察清單，也能手動輸入額外代號。像 2330 或 0050 這種台股數字代號會自動轉成 Yahoo Finance 格式。",
        "manual_period_override": "手動覆寫期間",
        "custom_lookback": "自訂回看區間",
        "custom_interval": "自訂頻率",
        "reference_lens": "參考鏡頭",
        "live_refresh": "即時刷新",
        "refresh_live_data": "刷新即時資料",
        "refresh_caption": "以新聞為優先的版型。日線趨勢驅動 Sentinel 訊號。台股現在也會套用與美股相同的比較、Decision Brief、新聞與 K 線結構。",
        "please_select_ticker": "請至少選擇一個股票代號。",
        "loading_data": "正在載入市場資料與個股新聞…",
        "no_market_data": "沒有取得市場資料，請再試一次。",
        "footer_note": "本儀表板僅供研究與參考。新聞影響百分比與方向標籤屬於啟發式估計，並非保證，也不是投資建議。",
        "explorer_navigation": "探索導覽",
        "choose_ticker_workspace": "選擇下方股票，進入完整個股研究工作台",
        "explorer_nav_copy": "這是從初步篩選進入深度研究的轉換點。選擇任一股票分頁後，儀表板會切換成該股票的專屬工作台，集中顯示相關新聞、催化劑映射、鏡頭警示、Trading Lab 與 K 線確認。",
        "what_happens_next": "接下來會發生什麼",
        "open_ticker_workspace": "開啟個股工作台 ↓",
        "open_ticker_workspace_copy": "你會進入該股票的專屬研究頁，新聞、催化劑、警示與圖表結構都只聚焦這一檔。",
        "news_display_mode": "新聞顯示模式",
        "news_display_note": "可選擇維持原文新聞，或加入更適合台灣使用者的中文輔助閱讀。",
        "news_mode_original": "原始來源",
        "news_mode_bilingual": "雙語輔助",
        "news_mode_chinese_first": "中文優先輔助",
        "news_helper_label": "台灣使用者速讀",
        "news_reason_label": "為何重要",
        "source_summary_label": "原文摘要",
        "no_source_summary": "此來源未提供摘要。",
        "news_helper_template": "{ticker}：{direction}，預估短線影響約 {probability}%。信心 {confidence}，關聯度 {relevance}。",
        "directional_pressure": "方向壓力",
        "directional_pressure_copy": "這是新聞在短期內可能影響所選股票方向強度的參考估計。",
        "up_down_pressure": "上行 {pos}% / 下行 {neg}%",
        "trend_lab": "Trend Lab",
        "candlestick_confirmation": "K 線確認",
        "trend_lab_copy": "這一區放在較後面，讓讀者先吸收新聞、影響估計與訊號層，再用目前趨勢鏡頭與盤中走勢確認結構。",
        "last_daily_close": "最新日線收盤",
        "trading_lab": "Trading Lab",
        "trend_1y": "一年趨勢",
        "comparison_title": "更現代的並排比較，用來觀察價格強度與訊號品質",
        "comparison_copy": "用這一區快速掃描哪一檔擁有更強的趨勢結構、更乾淨的建議品質，以及更好的新聞支撐，再決定要深入哪個個股工作台。",
        "strongest_pro_setup": "最強 Pro 配置",
        "best_1y_price_strength": "最佳一年價格強度",
        "best_current_news_tailwind": "最佳當前新聞順風",
        "side_by_side_profile": "並排輪廓",
        "lens_score": "鏡頭分數",
        "last_price": "最新價格",
        "signal": "訊號",
        "intraday_move": "盤中變動",
        "recent_structure": "{ticker} 近期結構",
        "research_view_only": "僅供研究參考。此訊號綜合了均線、RSI、量能確認、一年趨勢與目前個股新聞脈動。",
        "lead_story_context": "主導新聞脈絡",
        "active_lens_focus": "目前鏡頭焦點",
        "no_extra_alert_context": "目前沒有額外警示脈絡。",
        "bullish_count": "偏多 {count}",
        "neutral_count": "中性 {count}",
        "bearish_count": "偏空 {count}",
    },
}


TRANSLATIONS["English"].update({
    "global_market_indicator": "Global Market Indicator",
    "global_market_copy": "A cross-market reference layer for the active lens. Use this to see whether U.S. and Taiwan benchmark trends are broadly supportive, mixed, or under pressure before drilling further into individual names.",
    "global_market_window": "Active window",
    "global_market_last": "Last price",
    "global_market_window_return": "Window return",
    "global_market_recent": "Recent 20-bar",
    "global_market_signal": "Trend state",
    "global_market_breadth": "Reference breadth",
    "global_market_breadth_risk_on": "{up} of {total} benchmarks are in positive trend alignment. Broad tone is leaning risk-on.",
    "global_market_breadth_risk_off": "{down} of {total} benchmarks are in negative trend alignment. Broad tone is leaning defensive.",
    "global_market_breadth_mixed": "Benchmarks are mixed across the active lens. Leadership is selective rather than broad.",
    "global_market_uptrend": "Uptrend",
    "global_market_pullback": "Pullback / mixed",
    "global_market_downtrend": "Downtrend",
    "global_market_nasdaq": "NASDAQ",
    "global_market_sp500": "S&P 500",
    "global_market_dow": "Dow Jones",
    "global_market_taiex": "TAIEX",
})

TRANSLATIONS["繁體中文"].update({
    "global_market_indicator": "全球市場指標",
    "global_market_copy": "這是配合目前趨勢鏡頭的跨市場參考層。先看美國與台灣主要指數現在是同步偏多、分歧，還是整體承壓，再深入研究個股會更有脈絡。",
    "global_market_window": "目前視窗",
    "global_market_last": "最新價格",
    "global_market_window_return": "視窗報酬",
    "global_market_recent": "近 20 根走勢",
    "global_market_signal": "趨勢狀態",
    "global_market_breadth": "基準廣度",
    "global_market_breadth_risk_on": "{up} / {total} 個基準指數呈現偏多對齊，整體風險偏好較佳。",
    "global_market_breadth_risk_off": "{down} / {total} 個基準指數呈現偏空對齊，整體氣氛較偏防守。",
    "global_market_breadth_mixed": "主要基準在目前鏡頭下呈現分歧，市場不是全面擴散，而是選股型盤勢。",
    "global_market_uptrend": "上升趨勢",
    "global_market_pullback": "拉回／分歧",
    "global_market_downtrend": "下降趨勢",
    "global_market_nasdaq": "NASDAQ 指數",
    "global_market_sp500": "標普 500",
    "global_market_dow": "道瓊工業指數",
    "global_market_taiex": "加權指數",
})



TRANSLATIONS["English"].update({
    "device_mode_control": "Layout mode",
    "device_mode_control_note": "Use Auto detect to apply a best-effort layout profile from the browser device hint, or switch to Manual override to force a specific layout.",
    "device_mode_auto": "Auto detect",
    "device_mode_manual": "Manual override",
    "device_mode_detected": "Detected profile",
    "device_mode": "Viewing device",
    "device_mode_note": "Choose a layout profile for desktop, iPad, smartphone fold portrait, smartphone fold landscape, or smartphone so spacing, width, and content density feel more comfortable on that screen.",
    "device_desktop": "Desktop",
    "device_ipad": "iPad",
    "device_smartphone_fold_portrait": "Smartphone Fold Portrait",
    "device_smartphone_fold_landscape": "Smartphone Fold Landscape",
    "device_smartphone": "Smartphone",
})

TRANSLATIONS["繁體中文"].update({
    "device_mode_control": "版型模式",
    "device_mode_control_note": "可使用自動偵測，依瀏覽器裝置提示套用最接近的版型；也可改成手動覆蓋，固定指定 Desktop、iPad、折疊機或手機版型。",
    "device_mode_auto": "自動偵測",
    "device_mode_manual": "手動覆蓋",
    "device_mode_detected": "目前偵測版型",
    "device_mode": "觀看裝置",
    "device_mode_note": "選擇 Desktop、iPad、Smart Phone Fold Portrait、Smart Phone Fold Landscape 或 Smart Phone 版型，Dashboard 會依裝置調整寬度、間距與內容密度，讓閱讀更舒適。",
    "device_desktop": "Desktop",
    "device_ipad": "iPad",
    "device_smartphone_fold_portrait": "Smart Phone Fold Portrait",
    "device_smartphone_fold_landscape": "Smart Phone Fold Landscape",
    "device_smartphone": "Smart Phone",
})
TERM_TRANSLATIONS = {
    "繁體中文": {
        "BUY": "買進",
        "HOLD": "觀望",
        "SELL": "賣出",
        "High": "高",
        "Medium": "中",
        "Low": "低",
        "Moderate": "中等",
        "Strong Uptrend": "強勢上升趨勢",
        "Moderate Uptrend": "中度上升趨勢",
        "Strong Downtrend": "強勢下降趨勢",
        "Mild Downtrend": "溫和下降趨勢",
        "Flat": "持平",
        "Momentum-led": "動能主導",
        "Pullback watch": "拉回觀察",
        "Risk-off": "風險趨避",
        "Balanced": "平衡",
        "Macro": "總經",
        "Earnings": "財報",
        "AI Demand": "AI 需求",
        "Regulation": "監管",
        "Analyst Action": "分析師動作",
        "Supply Chain": "供應鏈",
        "News tilt: bullish": "新聞傾向：偏多",
        "News tilt: bearish": "新聞傾向：偏空",
        "News tilt: mixed": "新聞傾向：混合",
        "Likely bullish": "可能偏多",
        "Likely bearish": "可能偏空",
        "Mildly bullish": "略偏多",
        "Mildly bearish": "略偏空",
        "Neutral / mixed": "中性／混合",
        "Fast Read bullish": "Fast Read 偏多",
        "Fast Read bearish": "Fast Read 偏空",
        "Fast Read mixed": "Fast Read 混合",
        "Swing Map improving": "Swing Map 改善中",
        "Swing Map weakening": "Swing Map 轉弱",
        "Swing Map balanced": "Swing Map 平衡",
        "Position View intact": "Position View 結構完整",
        "Position View broken": "Position View 結構受損",
        "Position View mixed": "Position View 混合",
        "Cycle View leader": "Cycle View 領先",
        "Cycle View laggard": "Cycle View 落後",
        "Cycle View mixed": "Cycle View 混合",
        "N/A": "無",
        "Unknown source": "未知來源",
        "Not provided": "未提供",
        "No strong lead story": "目前沒有明確主導新聞",
        "No urgent alert is active.": "目前沒有緊急警示。",
        "Direction currently mixed": "目前方向偏混合",
        "No stock-specific story returned": "目前沒有回傳個股專屬新聞",

        "Favor continuation entries only when price confirms above near-term resistance or re-tests support cleanly.": "只有當價格確認站上短線壓力，或回測支撐乾淨有效時，才偏向順勢進場。",
        "Stay defensive until price rebuilds above trend support and headline pressure stops worsening.": "在價格重新站回趨勢支撐、且新聞壓力不再惡化前，建議維持防守。",
        "Wait for the catalyst picture and chart structure to align before pressing directional risk.": "先等催化劑與圖表結構重新一致，再考慮承擔方向性風險。",
        "Momentum is leading. Breakouts and continuation days deserve more attention than deep dip-buy attempts.": "目前由動能主導。比起深度接刀，更應關注突破與延續日。",
        "The structure is in pullback mode. Patience matters more than speed, especially near support.": "目前屬於拉回模式，尤其接近支撐時，耐心比速度更重要。",
        "The tape is fragile. Capital protection matters more than forcing a setup.": "盤勢偏脆弱。與其硬做型態，資本保護更重要。",
        "The setup is balanced. Let the next strong catalyst or price confirmation set direction.": "目前型態偏平衡，讓下一個強催化劑或價格確認來決定方向。",
        "Headline tone is leaning negative and can overpower otherwise decent chart structure.": "新聞語氣偏負面，可能蓋過原本還不錯的圖表結構。",
        "Positive headline tone is helping the setup, but it still needs price confirmation.": "正面的新聞語氣正在幫助型態，但仍需要價格確認。",
        "No single risk is dominant, so watch whether the next story shifts the narrative.": "目前沒有單一風險主導，重點是觀察下一則新聞是否改變市場敘事。",
        "Price is above SMA 200, supporting the long-term uptrend.": "價格位於 SMA 200 之上，支撐長期上升趨勢。",
        "Price is below SMA 200, which weakens the long-term setup.": "價格位於 SMA 200 之下，削弱長期配置。",
        "SMA 50 is above SMA 200, confirming medium-term strength.": "SMA 50 高於 SMA 200，確認中期強勢。",
        "SMA 50 is below SMA 200, confirming medium-term weakness.": "SMA 50 低於 SMA 200，確認中期偏弱。",
        "SMA 20 is above SMA 50, so near-term momentum is supportive.": "SMA 20 高於 SMA 50，短線動能偏正向。",
        "SMA 20 is below SMA 50, so near-term momentum has cooled.": "SMA 20 低於 SMA 50，短線動能已降溫。",
        "RSI is in a healthy bullish range.": "RSI 處於健康的偏多區間。",
        "RSI is stretched, so upside may be more fragile short term.": "RSI 偏延伸，短線上行可能較脆弱。",
        "RSI is weak, which suggests sellers still have control.": "RSI 偏弱，顯示賣方仍具主導力。",
        "The stock is up strongly over the past year, which supports the broader trend.": "股票過去一年表現強勁，支撐更大的趨勢方向。",
        "The stock is down over the past year, which weakens the trend case.": "股票過去一年表現偏弱，削弱趨勢成立的基礎。",
        "Recent volume is above the 50-day average, giving the move more confirmation.": "近期量能高於 50 日平均，讓這波走勢更具確認性。",
        "Recent volume is light, so conviction behind the move is weaker.": "近期量能偏輕，代表這波走勢背後的信心較弱。",
        "Recent news flow has skewed bullish.": "近期新聞流偏向正面。",
        "Recent news flow has skewed bearish.": "近期新聞流偏向負面。",
        "Recent news flow is mixed and does not materially change the core trend picture.": "近期新聞流偏混合，尚未實質改變核心趨勢判讀。",
        "Trend structure and recent context are supportive for accumulation.": "趨勢結構與近期脈絡支持分批布局。",
        "Trend structure is weak or deteriorating, so risk remains elevated.": "趨勢結構偏弱或持續惡化，風險仍高。",
        "Signals are mixed, so waiting for better confirmation is more disciplined.": "訊號混合，先等待更好的確認會更有紀律。",
        "Headline language leans positive for demand, margins, upgrades, or growth.": "標題語氣偏向需求、利潤、升評或成長等正面訊號。",
        "Headline language leans negative for guidance, regulation, demand, or execution risk.": "標題語氣偏向財測、監管、需求或執行風險等負面訊號。",
        "Some positive wording is present, but the signal is not strong.": "出現一些正面措辭，但訊號強度不高。",
        "Some negative wording is present, but the signal is not strong.": "出現一些負面措辭，但訊號強度不高。",
        "The headline is informational or the signals conflict.": "標題偏資訊性，或正負訊號彼此衝突。",
        "Elevated": "偏高",
        "Light": "偏低",
        "Normal": "正常",
        "Most lenses are leaning constructive.": "多數鏡頭偏向建設性。",
        "Most lenses are leaning defensive.": "多數鏡頭偏向防守。",
        "The lenses disagree, so context matters more.": "各鏡頭看法分歧，因此脈絡更重要。",
        "Lens states are mixed.": "鏡頭狀態偏混合。",
        "Fast Read": "快速閱讀",
        "Swing Map": "波段地圖",
        "Position View": "部位視角",
        "Cycle View": "週期視角",
        "Fast Read favors fresh intraday strength.": "快速閱讀偏好最新盤中強勢。",
        "Fast Read penalizes weak live tape.": "快速閱讀會懲罰疲弱的即時盤勢。",
        "Fast Read rewards bullish news flow.": "快速閱讀會加分給偏多新聞流。",
        "Fast Read penalizes bearish news flow.": "快速閱讀會扣分給偏空新聞流。",
        "Fast Read likes active momentum.": "快速閱讀偏好活躍動能。",
        "Fast Read dislikes weak short-term momentum.": "快速閱讀不偏好弱勢短線動能。",
        "Swing Map rewards momentum-led setups.": "波段地圖會加分給動能主導型態。",
        "Swing Map likes controlled pullbacks.": "波段地圖偏好可控的拉回。",
        "Swing Map penalizes unstable structure.": "波段地圖會扣分給不穩定結構。",
        "Swing Map rewards volume confirmation.": "波段地圖會加分給量能確認。",
        "Swing Map discounts light participation.": "波段地圖會降低量能不足的權重。",
        "Position View prioritizes price above SMA 200.": "部位視角優先看價格是否站上 SMA 200。",
        "Position View penalizes price below SMA 200.": "部位視角會扣分給跌破 SMA 200。",
        "Position View rewards medium-term trend support.": "部位視角會加分給中期趨勢支撐。",
        "Position View penalizes weak medium-term structure.": "部位視角會扣分給中期結構偏弱。",
        "Position View rewards strong 1Y return.": "部位視角會加分給強勁的一年報酬。",
        "Position View penalizes weak 1Y return.": "部位視角會扣分給疲弱的一年報酬。",
        "Cycle View rewards long-cycle leadership.": "週期視角會加分給長週期領先。",
        "Cycle View penalizes deterioration.": "週期視角會扣分給惡化跡象。",
        "Cycle View likes broad trend alignment.": "週期視角偏好大方向一致。",
        "Cycle View discounts broken leadership.": "週期視角會降低失去領先地位的評價。",
        "Cycle View notes news, but does not over-weight it.": "週期視角會參考新聞，但不會給過高權重。",
        "Start here when you want one answer first. The winner card now adapts to the active Trend Lens, so leadership can change based on the question you are asking.": "當你想先得到一個答案時，先看這裡。Winner Card 會依目前趨勢鏡頭調整，因此領先者會隨你的問題而改變。",
        "Compared with {runner}, this setup currently has the cleaner edge for the active lens. Change the lens and the winner can change too.": "和 {runner} 相比，這個配置在目前鏡頭下更乾淨、更具優勢。切換鏡頭後，領先者也可能改變。",
        "This is the most active catalyst bucket right now. If new headlines keep leaning the same way, they can strengthen or weaken the current signal faster than technicals alone.": "這是目前最活躍的催化劑分類。如果新標題持續往同一方向傾斜，對目前訊號的強化或削弱速度可能比技術面更快。",
        "Confidence comes from trend structure, news pulse, and trade setup aligning. When those disagree, the dashboard tends to fall back to HOLD.": "信心來自趨勢結構、新聞脈動與交易型態彼此一致。當它們互相衝突時，儀表板通常會回到觀望。",
        "Use this as the action style: momentum-led means continuation is cleaner, pullback watch means patience matters, and risk-off means price can stay fragile.": "把這個當成執行風格：動能主導代表順勢延續較乾淨；拉回觀察代表耐心更重要；風險趨避代表價格可能持續脆弱。",
        "The lead story is the fastest narrative snapshot. Check whether its direction agrees with the Catalyst Engine before trusting it too much.": "主導新聞是最快速的敘事快照。在過度相信它之前，先確認它的方向是否與 Catalyst Engine 一致。",
        "No extra alert context is active.": "目前沒有額外警示脈絡。",
        "Current leader": "目前領先者",
        "Nearest rival": "最接近的對手",
        "Lens adjustment": "鏡頭調整",
        "Catalyst edge": "催化優勢",
        "Runner-up focus": "次名焦點",
        "Base score": "基礎分數",
        "Current leader": "目前領先者",

    }
}

TRANSLATIONS["English"].update(
    {
        "symbol_search": "Smart search",
        "symbol_search_placeholder": "Try NVDA, Apple, 台積電, 定穎, 3715, 6488, 富喬",
        "search_results": "Search results",
        "search_results_help": "Search by symbol, company name, or Taiwan code. Pick any result to add it into the watchlist picker immediately.",
        "search_results_empty": "No matching symbols were found. You can still type a raw ticker in Custom symbols.",
        "watchlist_caption": "Build a broader U.S. and Taiwan watchlist by group, then add any extra symbol manually. Smart search now matches symbols and company names, and Taiwan numeric codes auto-detect .TW / .TWO when possible.",
        "opportunity_radar": "Opportunity Radar",
        "opportunity_radar_copy": "Ranks the selected list by lens score, news support, and intraday pressure so you can spot where the strongest alignment is building first.",
        "radar_score": "Radar score",
        "fastest_intraday": "Fastest intraday",
        "news_backing": "News backing",
        "execution_note": "Execution note",
        "search_remote_note": "Search combines your current universe with live symbol lookup, so missing names can still be found quickly.",
    }
)
TRANSLATIONS["繁體中文"].update(
    {
        "symbol_search": "智慧搜尋",
        "symbol_search_placeholder": "可試試 NVDA、Apple、台積電、定穎、3715、6488、富喬",
        "search_results": "搜尋結果",
        "search_results_help": "可用代號、公司名稱或台股數字代碼搜尋。選取結果後會立刻加入下方清單。",
        "search_results_empty": "目前找不到符合的代號，你仍可在自訂代號直接輸入原始 ticker。",
        "watchlist_caption": "可先用群組建立更廣的美股與台股觀察清單，再手動加入額外代號。智慧搜尋已支援代號與公司名稱比對，台股純數字代碼也會盡量自動判斷 .TW / .TWO。",
        "opportunity_radar": "機會雷達",
        "opportunity_radar_copy": "依鏡頭分數、新聞助力與盤中壓力排序，讓你先看到哪一檔的條件最一致。",
        "radar_score": "雷達分數",
        "fastest_intraday": "盤中最強",
        "news_backing": "新聞助力",
        "execution_note": "執行提示",
        "search_remote_note": "搜尋會結合目前觀察池與即時代號查找，缺少的股票也能更快被找到。",
    }
)


TERM_TRANSLATIONS["繁體中文"].update(
    {
        "主導催化": "主導催化",
        "Constructive intraday pressure": "盤中買盤有利",
        "Mild intraday tailwind": "盤中略偏順風",
        "Intraday pressure is mixed": "盤中力道偏混合",
        "Intraday sellers are in control": "盤中賣壓主導",
        "Momentum + news are aligned. Keep this near the top of the watchlist.": "動能與新聞方向一致，建議放在觀察清單前段。",
        "Constructive, but not fully confirmed. Watch for cleaner price confirmation.": "條件不錯，但還未完全確認，觀察價格是否進一步轉強。",
        "Mixed setup. Let the next catalyst decide whether this climbs the list.": "條件仍混合，等待下一個催化劑決定是否往前排。",
        "Conditions are weak. Treat this as a defensive watch item until momentum improves.": "目前條件偏弱，先以防守觀察為主，等待動能改善。",
    }
)


GROUP_TRANSLATIONS = {
    "繁體中文": {
        "Tech & AI": "科技與 AI",
        "Semiconductors": "半導體",
        "Financials": "金融",
        "Healthcare": "醫療保健",
        "Consumer": "消費",
        "Industrials": "工業",
        "Energy": "能源",
        "Communication": "通訊媒體",
        "Utilities & REITs": "公用事業與 REITs",
        "Transportation": "運輸",
        "Market ETFs": "市場 ETF",
        "Taiwan Semiconductors": "台股半導體",
        "Taiwan AI Supply Chain": "台股 AI 供應鏈",
        "Taiwan Financials": "台股金融",
        "Taiwan Shipping & Cyclicals": "台股航運與景氣循環",
        "Taiwan ETFs": "台股 ETF",
    }
}

LENS_OPTION_LABELS = {
    "English": {
        "Fast Read": "Fast Read",
        "Swing Map": "Swing Map",
        "Position View": "Position View",
        "Cycle View": "Cycle View",
    },
    "繁體中文": {
        "Fast Read": "快速閱讀",
        "Swing Map": "波段地圖",
        "Position View": "部位視角",
        "Cycle View": "週期視角",
    },
}

LENS_TRANSLATIONS = {
    "繁體中文": {
        "Fast Read": {
            "title": "快速閱讀",
            "hook": "最適合觀察近期新聞反應與短波段脈絡。",
            "how_to_read": "當你想知道最近幾週的新聞是否正在加速動能或逐漸失效時，用這個鏡頭。",
            "watch_for": "觀察跳空後是否延續、近期支撐是否被測試，以及訊號是轉強還是轉弱。",
        },
        "Swing Map": {
            "title": "波段地圖",
            "hook": "最適合主動交易者與中期型態判讀。",
            "how_to_read": "這是最實用的鏡頭，適合比較目前趨勢結構與近幾次財報或總經循環。",
            "watch_for": "重複出現的壓力區、乾淨的拉回、動能重置，以及突破是否被確認。",
        },
        "Position View": {
            "title": "部位視角",
            "hook": "最適合檢查完整趨勢年內，投資邏輯是否仍成立。",
            "how_to_read": "當你更在意結構性強弱，而不是每日噪音時，用這個鏡頭。",
            "watch_for": "價格相對 SMA 200、趨勢品質是否持續，以及新聞是在支持還是對抗大方向。",
        },
        "Cycle View": {
            "title": "週期視角",
            "hook": "最適合拉遠看大級別市場狀態。",
            "how_to_read": "這個鏡頭用來看完整週期行為，不是拿來找精準進場點。",
            "watch_for": "重大轉折、長期領導力，以及股票仍在廣義累積還是開始惡化。",
        },
    }
}


TRANSLATIONS["English"].update({
    "saved_preferences_note": "Selections are now saved in the URL, so reload keeps the same language, news mode, market scope, watchlist, and lens.",
    "tw_benchmark_layer": "Taiwan Benchmark Layer",
    "tw_benchmark_copy": "Local context for Taiwan names. This layer compares the active ticker against TAIEX, 0050, and its closest sector peers over the active lens window.",
    "tw_benchmark_window": "Active window",
    "tw_sector_group": "Sector group",
    "tw_vs_taiex": "vs TAIEX",
    "tw_vs_0050": "vs 0050 ETF",
    "tw_peer_rank": "Sector peer rank",
    "tw_peer_median": "Peer median",
    "tw_best_peer": "Top peer",
    "tw_relative_state": "Relative strength state",
    "tw_outperforming": "Outperforming",
    "tw_lagging": "Lagging",
    "tw_in_line": "In line",
    "tw_strong_leader": "Strong leader",
    "tw_mild_leader": "Mild leader",
    "tw_mild_laggard": "Mild laggard",
    "tw_clear_laggard": "Clear laggard",
    "tw_benchmark_note_strong_leader": "The stock is leading both Taiwan benchmarks and its sector peers over the active lens window.",
    "tw_benchmark_note_mild_leader": "The stock is ahead of local benchmarks, but leadership is not yet dominant across every reference point.",
    "tw_benchmark_note_in_line": "The stock is trading broadly in line with Taiwan benchmarks and nearby peers.",
    "tw_benchmark_note_mild_laggard": "The stock is lagging local benchmarks enough that selectivity and entry timing matter more.",
    "tw_benchmark_note_clear_laggard": "The stock is clearly trailing Taiwan benchmarks and sector peers, so relative strength is a headwind.",
    "tw_rank_of": "#{rank} of {total}",
})

TRANSLATIONS["繁體中文"].update({
    "saved_preferences_note": "目前的設定會同步寫進網址，因此重新整理後也會保留相同的語言、新聞模式、市場範圍、觀察清單與趨勢鏡頭。",
    "tw_benchmark_layer": "台股基準層",
    "tw_benchmark_copy": "給台股的本地化脈絡。這一層會用目前鏡頭視窗，把個股拿去和加權指數、0050，以及最接近的同產業同儕比較。",
    "tw_benchmark_window": "目前視窗",
    "tw_sector_group": "產業群組",
    "tw_vs_taiex": "相對加權指數",
    "tw_vs_0050": "相對 0050 ETF",
    "tw_peer_rank": "同業排名",
    "tw_peer_median": "同業中位數",
    "tw_best_peer": "目前最強同業",
    "tw_relative_state": "相對強弱狀態",
    "tw_outperforming": "跑贏",
    "tw_lagging": "落後",
    "tw_in_line": "同步",
    "tw_strong_leader": "明顯領先",
    "tw_mild_leader": "溫和領先",
    "tw_mild_laggard": "溫和落後",
    "tw_clear_laggard": "明顯落後",
    "tw_benchmark_note_strong_leader": "這檔股票在目前鏡頭視窗下，同時領先台股基準與同產業同儕。",
    "tw_benchmark_note_mild_leader": "這檔股票領先本地基準，但領先優勢還沒有在所有參考點都完全擴大。",
    "tw_benchmark_note_in_line": "這檔股票目前大致與台股基準和附近同業同步。",
    "tw_benchmark_note_mild_laggard": "這檔股票已明顯落後本地基準，進場節奏與挑選點位會更重要。",
    "tw_benchmark_note_clear_laggard": "這檔股票明顯跑輸台股基準與同業，相對強弱目前是逆風。",
    "tw_rank_of": "第 {rank} / {total} 名",
})

TRANSLATIONS["English"].update({
    "target_watch": "Target Watch",
    "target_watch_copy": "Consensus target-price references and recent target-change signals that can help frame upside, downside, and revision risk.",
    "consensus_target": "Consensus target",
    "target_gap": "Target gap",
    "current_price": "Current price",
    "high_low_band": "High / low band",
    "analyst_view": "Analyst view",
    "analyst_count": "Analyst count",
    "latest_revision": "Latest revision",
    "target_headlines": "Target-change headlines",
    "no_structured_target": "No structured analyst target-price data was returned for this ticker right now.",
    "target_reference_note": "Use analyst targets as a live reference layer, not as a prediction. They work best when target direction, catalysts, and price structure are aligned.",
    "upside_to_mean": "Upside to mean",
    "downside_to_low": "Downside to low",
    "target_reference_source": "Yahoo Finance analyst consensus + target-related headlines",
    "sticky_global_note": "Pinned macro tape",
    "bias_bullish": "Bullish",
    "bias_bearish": "Bearish",
    "bias_mixed": "Mixed",
})

TRANSLATIONS["繁體中文"].update({
    "target_watch": "目標價觀測",
    "target_watch_copy": "把共識目標價、近期調升/調降線索與上下行空間整理成同一層，方便快速判讀。",
    "consensus_target": "共識目標價",
    "target_gap": "目標價差",
    "current_price": "目前股價",
    "high_low_band": "高低區間",
    "analyst_view": "分析師看法",
    "analyst_count": "分析師數量",
    "latest_revision": "最新調整",
    "target_headlines": "目標價相關新聞",
    "no_structured_target": "目前沒有回傳這檔股票的結構化分析師目標價資料。",
    "target_reference_note": "把目標價當成即時參考層，不要當成保證預測。當目標價方向、催化與價格結構一致時，參考價值最高。",
    "upside_to_mean": "距均值上行空間",
    "downside_to_low": "距低值下行空間",
    "target_reference_source": "資料來源：Yahoo Finance 分析師共識 + 目標價相關新聞",
    "sticky_global_note": "置頂宏觀指標",
    "bias_bullish": "偏多",
    "bias_bearish": "偏空",
    "bias_mixed": "中性混合",
})

def get_lang() -> str:
    return st.session_state.get("dashboard_language", "English")


def get_language() -> str:
    lang = get_lang()
    return "zh_TW" if lang == "繁體中文" else "en"



def is_compact_device_mode() -> bool:
    return get_effective_device_mode() in {
        "iPad",
        "Smartphone Fold Portrait",
        "Smartphone Fold Landscape",
        "Smartphone",
    }


def planner_status_text(section: str, item_count: int | None = None) -> str:
    lang_zh = get_language() == "zh_TW"
    compact = is_compact_device_mode()
    count = max(int(item_count or 0), 0)

    if section == "scenario":
        return "多股規劃" if lang_zh and count > 1 else "單股規劃" if lang_zh else "Multi-stock" if count > 1 else "Single-stock"
    if section == "comparison":
        return "多檔比較" if lang_zh else "Multi-ticker"
    if section == "target":
        return "目標價追蹤" if lang_zh else "Target tracking"
    if section == "brief":
        return "決策摘要" if lang_zh else "Decision brief"
    if section == "alert":
        return "鏡頭警示" if lang_zh else "Lens alerts"
    if section == "trend":
        return "K 線結構" if lang_zh else "Candlestick structure"
    return "緊湊模式" if lang_zh and compact else "桌面模式" if lang_zh else "Compact mode" if compact else "Desktop mode"


def planner_status_badge(section: str, item_count: int | None = None) -> str:
    return f"● {planner_status_text(section, item_count)}"


def planner_expander_badges(section: str, item_count: int | None = None) -> str:
    lang_zh = get_language() == "zh_TW"
    count = max(int(item_count or 0), 0)
    mode = get_effective_device_mode()
    mode_label_map = {
        "Desktop": "Desktop",
        "iPad": "iPad",
        "Smartphone Fold Portrait": "Fold Portrait",
        "Smartphone Fold Landscape": "Fold Landscape",
        "Smartphone": "Smartphone",
    }
    mode_label = mode_label_map.get(mode, mode)
    if lang_zh:
        mode_label = {
            "Desktop": "桌面",
            "iPad": "iPad",
            "Fold Portrait": "折疊直向",
            "Fold Landscape": "折疊橫向",
            "Smartphone": "手機",
        }.get(mode_label, mode_label)

    count_label = ""
    if section in {"comparison", "scenario", "target", "brief"} and count > 0:
        count_label = f"{count} 檔" if lang_zh else f"{count} tickers"

    section_cls = {
        "scenario": "is-scenario",
        "comparison": "is-comparison",
        "target": "is-target",
        "brief": "is-brief",
        "alert": "is-alert",
        "trend": "is-trend",
    }.get(section, "")

    pill_html = [
        f'<span class="planner-expander-pill {section_cls}">{escape(planner_status_text(section, item_count))}</span>',
        f'<span class="planner-expander-pill is-device">{escape(mode_label)}</span>',
    ]
    if count_label:
        pill_html.append(f'<span class="planner-expander-pill is-device">{escape(count_label)}</span>')
    return '<div class="planner-expander-badge-row">' + "".join(pill_html) + '</div>'


def planner_auto_expand(section: str, item_count: int | None = None) -> bool:
    mode = get_effective_device_mode()
    count = max(int(item_count or 0), 0)
    single = count <= 1
    small_multi = 2 <= count <= 3
    large_multi = count >= 4

    if section == "scenario":
        if mode == "Desktop":
            return True
        if mode == "iPad":
            return not large_multi
        if "Fold" in mode:
            return single or small_multi
        return single

    if section == "target":
        if mode == "Desktop":
            return count <= 3
        if mode == "iPad":
            return count <= 2
        if "Fold" in mode:
            return single
        return single

    if section == "brief":
        if mode == "Desktop":
            return count <= 3
        if mode == "iPad":
            return count <= 2
        if "Fold" in mode:
            return single
        return single

    if section == "comparison":
        if count < 2:
            return False
        if mode == "Desktop":
            return count <= 5
        if mode == "iPad":
            return count <= 3
        if "Fold" in mode:
            return count <= 2
        return False

    if section == "alert":
        if mode == "Desktop":
            return single
        if mode == "iPad":
            return False
        return False

    if section == "trend":
        if mode == "Desktop":
            return single
        if mode == "iPad":
            return single
        return False

    return True


def planner_expander_label(base_label: str, section: str, item_count: int | None = None) -> str:
    return f"{base_label} · {planner_status_badge(section, item_count)}"


def planner_expander_helper(base_text: str, section: str, item_count: int | None = None) -> str:
    lang_zh = get_language() == "zh_TW"
    mode = get_effective_device_mode()
    count = max(int(item_count or 0), 0)

    mode_text_map = {
        "Desktop": "桌面優先展開" if lang_zh else "desktop-first default",
        "iPad": "iPad 平衡展開" if lang_zh else "iPad-balanced default",
        "Smartphone Fold Portrait": "折疊直向偏重點展開" if lang_zh else "fold-portrait priority",
        "Smartphone Fold Landscape": "折疊橫向平衡展開" if lang_zh else "fold-landscape balance",
        "Smartphone": "手機優先收合" if lang_zh else "smartphone-first collapsed",
    }
    mode_text = mode_text_map.get(mode, mode)

    if section == "comparison":
        scope_text = f"目前比較 {count} 檔，適合做跨股票強弱排序。" if lang_zh else f"Currently comparing {count} tickers for cross-ticker ranking."
    elif section == "scenario":
        scope_text = f"目前納入 {count} 檔，適合規劃資金、進場、停利與風險。" if lang_zh else f"Currently planning across {count} tickers for capital, entry, exit, and risk."
    elif section == "target":
        scope_text = f"目前追蹤 {count} 檔的目標價區間與修正脈動。" if lang_zh else f"Tracking target bands and revision tone across {count} tickers."
    elif section == "brief":
        scope_text = f"目前整理 {count} 檔的決策重點與執行摘要。" if lang_zh else f"Summarizing the decision points and execution brief for {count} tickers."
    elif section == "alert":
        scope_text = "聚焦鏡頭多空狀態與當前警示。" if lang_zh else "Focuses on lens-state risk and current alerts."
    elif section == "trend":
        scope_text = "聚焦 K 線結構、支撐壓力與交易節奏。" if lang_zh else "Focuses on candlestick structure, support/resistance, and trade rhythm."
    else:
        scope_text = "依目前版型自動調整預設展開狀態。" if lang_zh else "Default expanded state adapts to the current layout mode."

    return f"{base_text} · {scope_text} · {mode_text}"


def normalize_device_mode(value: str | None) -> str:
    if not value:
        return "Desktop"
    value = LEGACY_DEVICE_MODE_ALIASES.get(value, value)
    return value if value in DEVICE_MODE_OPTIONS else "Desktop"


def get_device_control_mode() -> str:
    value = st.session_state.get("dashboard_device_control_mode", "Auto detect")
    return value if value in DEVICE_CONTROL_OPTIONS else "Auto detect"


def get_request_user_agent() -> str:
    try:
        context = getattr(st, "context", None)
        headers = getattr(context, "headers", None)
        if headers:
            getter = getattr(headers, "get", None)
            if callable(getter):
                return str(getter("user-agent") or getter("User-Agent") or "")
    except Exception:
        pass
    return ""


def detect_device_mode_from_user_agent() -> str:
    ua = get_request_user_agent().lower()
    if not ua:
        return "Desktop"

    is_ipad = "ipad" in ua or ("macintosh" in ua and "touch" in ua)
    is_mobile = any(token in ua for token in ("iphone", "android", "mobile", "phone"))
    is_tablet = is_ipad or "tablet" in ua

    if "fold" in ua:
        return "Smartphone Fold Portrait" if is_mobile else "Smartphone Fold Landscape"
    if is_ipad or ("android" in ua and not is_mobile):
        return "iPad"
    if is_tablet:
        return "iPad"
    if is_mobile:
        return "Smartphone"
    return "Desktop"


def get_effective_device_mode() -> str:
    control_mode = get_device_control_mode()
    manual_mode = normalize_device_mode(st.session_state.get("dashboard_device_mode", "Desktop"))
    if control_mode == "Manual override":
        return manual_mode
    detected = normalize_device_mode(st.session_state.get("dashboard_detected_device_mode"))
    if detected == "Desktop" and not st.session_state.get("dashboard_detected_device_mode"):
        detected = detect_device_mode_from_user_agent()
        st.session_state["dashboard_detected_device_mode"] = detected
    return detected


def get_device_mode() -> str:
    return get_effective_device_mode()


def device_control_mode_label(value: str) -> str:
    labels = {
        "Auto detect": t("device_mode_auto"),
        "Manual override": t("device_mode_manual"),
    }
    return labels.get(value, value)


def device_mode_label(value: str) -> str:
    labels = {
        "Desktop": t("device_desktop"),
        "iPad": t("device_ipad"),
        "Smartphone Fold Portrait": t("device_smartphone_fold_portrait"),
        "Smartphone Fold Landscape": t("device_smartphone_fold_landscape"),
        "Smartphone": t("device_smartphone"),
    }
    return labels.get(value, value)

def get_news_mode() -> str:
    return st.session_state.get("dashboard_news_mode", "Original source")

def news_mode_prefers_helper() -> bool:
    return get_news_mode() in {"Bilingual assist", "Chinese-first assist"}

def news_mode_prefers_chinese_first() -> bool:
    return get_news_mode() == "Chinese-first assist"

def t(key: str, **kwargs) -> str:
    lang = get_lang()
    value = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["English"].get(key, key))
    return value.format(**kwargs) if kwargs else value

def tr_term(value):
    if value is None:
        return value
    lang = get_lang()
    return TERM_TRANSLATIONS.get(lang, {}).get(str(value), str(value))

def tr_group(value):
    if value is None:
        return value
    return GROUP_TRANSLATIONS.get(get_lang(), {}).get(str(value), str(value))

def tr_lens_name(value: str) -> str:
    return LENS_OPTION_LABELS.get(get_lang(), {}).get(value, value)

def tr_lens_meta(meta: dict) -> dict:
    lang = get_lang()
    translated = dict(meta)
    base_key = meta.get("title")
    localized = LENS_TRANSLATIONS.get(lang, {}).get(base_key)
    if localized:
        translated.update(localized)
    return translated

def tr_confidence(value):
    return tr_term(value)

def tr_signal(value):
    return tr_term(value)

def tr_relevance(value):
    return tr_term(value)

def tr_setup(value):
    return tr_term(value)

def tr_news_label(value):
    return tr_term(value)

def tr_direction(value):
    return tr_term(value)

def tr_reason_text(value):
    return tr_term(value)

def coerce_float(value):
    if value is None or value is pd.NA:
        return pd.NA
    try:
        number = float(value)
    except (TypeError, ValueError):
        return pd.NA
    return pd.NA if pd.isna(number) else number

def format_local_price(value, ticker: str | None = None):
    value = coerce_float(value)
    if pd.isna(value):
        return "N/A"
    prefix = "NT$" if ticker and is_taiwan_ticker(ticker) else "$"
    return f"{prefix}{value:,.2f}"

def analyst_bias_label(summary: dict) -> str:
    buy_votes = int(summary.get("strong_buy", 0)) + int(summary.get("buy", 0))
    hold_votes = int(summary.get("hold", 0))
    sell_votes = int(summary.get("sell", 0)) + int(summary.get("strong_sell", 0))
    total = buy_votes + hold_votes + sell_votes
    if total <= 0:
        return t("bias_mixed")
    if buy_votes >= max(hold_votes, sell_votes) and buy_votes >= sell_votes + 2:
        return t("bias_bullish")
    if sell_votes >= max(hold_votes, buy_votes) and sell_votes >= buy_votes + 2:
        return t("bias_bearish")
    return t("bias_mixed")

def extract_target_headlines(news_items: list[dict], max_items: int = 3) -> list[dict]:
    ranked = []
    for item in news_items:
        title = str(item.get("title", "") or "")
        summary = str(item.get("summary", "") or "")
        text = f"{title} {summary}".lower()
        score = sum(1 for keyword in TARGET_REFERENCE_KEYWORDS if keyword.lower() in text)
        if score <= 0:
            continue
        score += min(int(item.get("relevance", 0)), 4)
        ranked.append({
            "title": title,
            "url": item.get("url"),
            "provider": item.get("provider", ""),
            "score": score,
            "published": item.get("published", pd.NaT),
        })
    ranked.sort(
        key=lambda row: (
            row["score"],
            pd.Timestamp.min.tz_localize("UTC") if pd.isna(row["published"]) else row["published"],
        ),
        reverse=True,
    )
    return ranked[:max_items]

@st.cache_data(ttl=1800)
def fetch_analyst_target_snapshot(ticker: str) -> dict:
    snapshot = {
        "mean_target": pd.NA,
        "high_target": pd.NA,
        "low_target": pd.NA,
        "current_price": pd.NA,
        "analyst_count": None,
        "bias": t("bias_mixed"),
        "latest_revision": "",
        "error": None,
    }
    try:
        tk = yf.Ticker(ticker)
    except Exception as exc:
        snapshot["error"] = str(exc)
        return snapshot

    try:
        raw_targets = getattr(tk, "analyst_price_targets", {}) or {}
        if hasattr(raw_targets, "to_dict"):
            raw_targets = raw_targets.to_dict()
        if isinstance(raw_targets, dict):
            snapshot["mean_target"] = coerce_float(raw_targets.get("mean") or raw_targets.get("targetMeanPrice"))
            snapshot["high_target"] = coerce_float(raw_targets.get("high") or raw_targets.get("targetHighPrice"))
            snapshot["low_target"] = coerce_float(raw_targets.get("low") or raw_targets.get("targetLowPrice"))
            snapshot["current_price"] = coerce_float(raw_targets.get("current") or raw_targets.get("currentPrice"))
    except Exception:
        pass

    try:
        summary = getattr(tk, "recommendations_summary", None)
        if summary is not None and hasattr(summary, "empty") and not summary.empty:
            row = summary.iloc[-1]
            recommendation_summary = {
                "strong_buy": int(row.get("strongBuy", 0) or 0),
                "buy": int(row.get("buy", 0) or 0),
                "hold": int(row.get("hold", 0) or 0),
                "sell": int(row.get("sell", 0) or 0),
                "strong_sell": int(row.get("strongSell", 0) or 0),
            }
            snapshot["analyst_count"] = sum(recommendation_summary.values()) or snapshot["analyst_count"]
            snapshot["bias"] = analyst_bias_label(recommendation_summary)
    except Exception:
        pass

    try:
        upgrades = getattr(tk, "upgrades_downgrades", None)
        if upgrades is not None and hasattr(upgrades, "empty") and not upgrades.empty:
            latest = upgrades.dropna(how="all").tail(1)
            if not latest.empty:
                row = latest.iloc[0]
                action_bits = [str(row.get("Firm", "") or "").strip()]
                action = str(row.get("Action", "") or "").strip()
                to_grade = str(row.get("ToGrade", "") or "").strip()
                if action:
                    action_bits.append(action)
                if to_grade:
                    action_bits.append(to_grade)
                snapshot["latest_revision"] = " · ".join(bit for bit in action_bits if bit)
    except Exception:
        pass

    if pd.isna(snapshot["current_price"]):
        try:
            fast_info = getattr(tk, "fast_info", {}) or {}
            if hasattr(fast_info, "get"):
                snapshot["current_price"] = coerce_float(
                    fast_info.get("lastPrice") or fast_info.get("regularMarketPrice") or fast_info.get("previousClose")
                )
        except Exception:
            pass

    return snapshot

def build_target_watch_context(ticker: str, price_series: pd.Series, news_items: list[dict], timeframe: str = "6m") -> dict:
    timeframe = normalize_planner_timeframe(timeframe)
    snapshot = fetch_analyst_target_snapshot(ticker)
    current_price = coerce_float(snapshot.get("current_price"))
    if pd.isna(current_price) and price_series is not None and not price_series.empty:
        current_price = coerce_float(price_series.iloc[-1])

    mean_target = coerce_float(snapshot.get("mean_target"))
    high_target = coerce_float(snapshot.get("high_target"))
    low_target = coerce_float(snapshot.get("low_target"))
    analyst_count = snapshot.get("analyst_count")
    target_headlines = extract_target_headlines(news_items)

    progress = PLANNER_TARGET_PROGRESS.get(timeframe, PLANNER_TARGET_PROGRESS["6m"])

    def _project_target(level):
        level = coerce_float(level)
        if pd.isna(level) or pd.isna(current_price):
            return level
        return float(current_price + (level - current_price) * progress)

    projected_mean_target = _project_target(mean_target)
    projected_high_target = _project_target(high_target)
    projected_low_target = _project_target(low_target)

    upside_to_mean = pd.NA
    downside_to_low = pd.NA
    if pd.notna(current_price) and current_price != 0:
        if pd.notna(projected_mean_target):
            upside_to_mean = ((projected_mean_target / current_price) - 1) * 100
        if pd.notna(projected_low_target):
            downside_to_low = ((projected_low_target / current_price) - 1) * 100

    band_text = (
        f"{format_local_price(projected_low_target, ticker)} → {format_local_price(projected_high_target, ticker)}"
        if pd.notna(projected_low_target) or pd.notna(projected_high_target)
        else "N/A"
    )

    if get_language() == "zh_TW":
        horizon_note = f"已按 {planner_timeframe_label(timeframe)} 投資期限調整目標價區間。"
    else:
        horizon_note = f"Target band scaled to a {planner_timeframe_label(timeframe)} investment horizon."

    return {
        "available": pd.notna(projected_mean_target) or bool(target_headlines) or bool(snapshot.get("latest_revision")),
        "timeframe": timeframe,
        "timeframe_label": planner_timeframe_label(timeframe),
        "current_price": current_price,
        "mean_target": projected_mean_target,
        "high_target": projected_high_target,
        "low_target": projected_low_target,
        "full_mean_target": mean_target,
        "full_high_target": high_target,
        "full_low_target": low_target,
        "upside_to_mean": upside_to_mean,
        "downside_to_low": downside_to_low,
        "band_text": band_text,
        "bias": snapshot.get("bias", t("bias_mixed")),
        "analyst_count_text": str(int(analyst_count)) if analyst_count else "N/A",
        "latest_revision": str(snapshot.get("latest_revision", "") or "").strip(),
        "target_headlines": target_headlines,
        "source_note": t("target_reference_source"),
        "warning": t("no_structured_target") if not pd.notna(projected_mean_target) else "",
        "horizon_note": horizon_note,
    }
def build_news_helper_text(item: dict, ticker: str, probability: int) -> str:
    direction_text, _, _ = article_direction_meta(item)
    confidence = tr_confidence(item.get("confidence", "N/A"))
    relevance = relevance_label(int(item.get("relevance", 0)))
    helper = t(
        "news_helper_template",
        ticker=display_ticker_label(ticker),
        direction=direction_text,
        probability=probability,
        confidence=confidence,
        relevance=relevance,
    )
    reason = str(item.get("impact_reason", "") or "").strip()
    if reason:
        helper += f" {t('news_reason_label')}: {tr_reason_text(reason)}"
    return helper

def build_news_summary_html(item: dict, ticker: str, probability: int, block_class: str = "story-row-summary") -> str:
    source_summary = str(item.get("summary") or item.get("impact_reason") or "").strip()
    mode = get_news_mode()
    source_html = f'<div class="{block_class}"><strong>{t("source_summary_label")}</strong> {escape(source_summary or t("no_source_summary"))}</div>'
    if mode == "Original source":
        return f'<div class="{block_class}">{escape(source_summary or t("no_source_summary"))}</div>'
    helper_html = f'<div class="{block_class}"><strong>{t("news_helper_label")}</strong> {escape(build_news_helper_text(item, ticker, probability))}</div>'
    if news_mode_prefers_chinese_first():
        return helper_html + source_html
    return source_html + helper_html

def build_compact_summary_text(item: dict, ticker: str, probability: int, limit: int = 180) -> str:
    source_summary = str(item.get("summary") or item.get("impact_reason") or "").strip()
    if get_news_mode() == "Original source":
        return source_summary[:limit] or t("no_source_summary")
    return build_news_helper_text(item, ticker, probability)[:limit]


def html_block(markup: str) -> str:
    return textwrap.dedent(markup).strip()


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def build_news_aliases(ticker: str) -> set[str]:
    ticker_upper = str(ticker).upper()
    base_code = ticker_base_code(ticker_upper)
    aliases = {ticker_upper, base_code}
    meta = TAIWAN_TICKER_METADATA.get(ticker_upper)
    if meta:
        aliases.update(
            {
                meta.get("code", "").upper(),
                meta.get("en", "").upper(),
                meta.get("zh", "").upper(),
            }
        )
    return {alias for alias in aliases if alias}


def score_news_relevance(title: str, summary: str, related: list[str], aliases: set[str]) -> int:
    text_blob = f"{title} {summary}".upper()
    related_set = {str(value).upper() for value in related or []}
    relevance = 0
    if aliases & related_set:
        relevance += 4
    if any(alias in text_blob for alias in aliases if alias):
        relevance += 2
    if any(keyword in text_blob for keyword in ("EARNINGS", "GUIDANCE", "AI", "CHIPS", "DEMAND", "REVENUE", "EXPORT", "TARIFF", "財報", "AI", "晶片", "需求", "營收", "出口", "關稅")):
        relevance += 1
    return relevance


def normalize_google_news_url(url: str) -> str:
    return unescape(str(url or "")).strip()


def split_google_title(title: str) -> tuple[str, str]:
    clean = unescape(str(title or "")).strip()
    if " - " in clean:
        head, tail = clean.rsplit(" - ", 1)
        return head.strip(), tail.strip()
    return clean, "Google News"


def clean_google_description(description: str) -> str:
    raw = unescape(str(description or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def parse_google_news_rss(query: str, max_items: int = 10) -> list[dict]:
    feed_url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    req = Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=8) as response:
            xml_bytes = response.read()
    except Exception:
        return []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for node in root.findall(".//item")[:max_items]:
        raw_title = node.findtext("title", default="").strip()
        title, provider = split_google_title(raw_title)
        link = normalize_google_news_url(node.findtext("link", default="").strip())
        description = clean_google_description(node.findtext("description", default="").strip())
        pub_date = pd.to_datetime(node.findtext("pubDate", default=""), utc=True, errors="coerce")
        items.append(
            {
                "title": title or "Untitled",
                "summary": description,
                "provider": provider or "Google News",
                "url": link,
                "published": pub_date,
                "related": [],
            }
        )
    return items


def fetch_taiwan_local_news(ticker: str, max_items: int = 12) -> list[dict]:
    if not is_taiwan_ticker(ticker):
        return []

    meta = TAIWAN_TICKER_METADATA.get(str(ticker).upper(), {})
    code = meta.get("code", ticker_base_code(ticker))
    zh_name = meta.get("zh", code)
    en_name = meta.get("en", code)
    aliases = build_news_aliases(ticker)

    query_parts = [zh_name]
    if en_name and en_name.upper() != zh_name.upper():
        query_parts.append(f'"{en_name}"')
    if code:
        query_parts.append(code)
    query = " OR ".join(part for part in query_parts if part)

    items = []
    for item in parse_google_news_rss(query, max_items=max_items * 2):
        relevance = score_news_relevance(item["title"], item["summary"], item.get("related", []), aliases)
        if contains_cjk(item["title"]):
            relevance += 2
        impact_label, impact_score, impact_reason = infer_news_impact(item["title"], item["summary"])
        confidence = infer_news_confidence(relevance, impact_score)
        item.update(
            {
                "related": [str(ticker).upper()],
                "relevance": relevance,
                "impact_label": impact_label,
                "impact_score": impact_score,
                "impact_reason": impact_reason,
                "confidence": confidence,
                "source_origin": "tw_local",
            }
        )
        items.append(item)

    items.sort(
        key=lambda x: (
            x.get("relevance", 0),
            1 if contains_cjk(x.get("title", "")) else 0,
            pd.Timestamp.min.tz_localize("UTC") if pd.isna(x.get("published")) else x.get("published"),
        ),
        reverse=True,
    )
    return items[:max_items]


def dedupe_news_items(items: list[dict], max_items: int = 12) -> list[dict]:
    deduped = []
    seen: set[str] = set()
    for item in items:
        title_key = re.sub(r"\s+", " ", str(item.get("title", "")).strip().lower())
        url_key = str(item.get("url", "")).strip().lower()
        key = url_key or title_key
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(
        key=lambda x: (
            x.get("relevance", 0),
            1 if x.get("source_origin") == "tw_local" else 0,
            1 if contains_cjk(x.get("title", "")) else 0,
            pd.Timestamp.min.tz_localize("UTC") if pd.isna(x.get("published")) else x.get("published"),
        ),
        reverse=True,
    )
    return deduped[:max_items]


def ticker_base_code(ticker: str) -> str:
    return str(ticker).split(".", 1)[0].upper()


def is_taiwan_ticker(ticker: str) -> bool:
    ticker_upper = str(ticker).upper()
    return ticker_upper.endswith(".TW") or ticker_upper.endswith(".TWO") or ticker_upper in TAIWAN_TICKER_METADATA


def _normalize_symbol_lookup_token(value: str) -> str:
    return "".join(str(value or "").upper().split())


def build_taiwan_alias_index() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for ticker, meta in TAIWAN_TICKER_METADATA.items():
        normalized_ticker = str(ticker).upper()
        alias_candidates = {
            normalized_ticker,
            ticker_base_code(normalized_ticker),
            meta.get("zh", ""),
            meta.get("en", ""),
        }
        alias_candidates.update(meta.get("aliases", []))
        for alias in alias_candidates:
            token = _normalize_symbol_lookup_token(alias)
            if token:
                alias_map[token] = normalized_ticker
    return alias_map


TAIWAN_ALIAS_INDEX = build_taiwan_alias_index()


RUNTIME_SYMBOL_METADATA_KEY = "dashboard_runtime_symbol_metadata"


def runtime_symbol_metadata() -> dict[str, dict]:
    return st.session_state.setdefault(RUNTIME_SYMBOL_METADATA_KEY, {})


def register_runtime_symbol_metadata(symbol: str, *, name: str = "", exchange: str = "", market: str = "") -> None:
    normalized_symbol = str(symbol or "").upper().strip()
    if not normalized_symbol:
        return
    metadata = runtime_symbol_metadata()
    current = dict(metadata.get(normalized_symbol, {}))
    if name:
        current["name"] = str(name).strip()
    if exchange:
        current["exchange"] = str(exchange).strip()
    if market:
        current["market"] = str(market).strip()
    metadata[normalized_symbol] = current
    st.session_state[RUNTIME_SYMBOL_METADATA_KEY] = metadata


def get_runtime_symbol_metadata(symbol: str) -> dict:
    return runtime_symbol_metadata().get(str(symbol or "").upper().strip(), {})


def scope_allows_ticker(scope: str, ticker: str) -> bool:
    normalized_ticker = str(ticker or "").upper().strip()
    if not normalized_ticker:
        return False
    if scope == "Taiwan only":
        return is_taiwan_ticker(normalized_ticker)
    if scope == "U.S. only":
        return not is_taiwan_ticker(normalized_ticker)
    return True


@st.cache_data(ttl=86400, show_spinner=False)
def yahoo_symbol_has_history(symbol: str) -> bool:
    try:
        history = yf.Ticker(symbol).history(period="1mo", interval="1d", auto_adjust=False)
        return history is not None and not history.empty
    except Exception:
        return False


def resolve_taiwan_numeric_symbol(symbol: str) -> str:
    numeric_code = str(symbol or "").strip()
    if not numeric_code:
        return ""
    for suffix in (".TW", ".TWO"):
        candidate = f"{numeric_code}{suffix}"
        if candidate in TAIWAN_TICKER_METADATA:
            return candidate
    for suffix in (".TW", ".TWO"):
        candidate = f"{numeric_code}{suffix}"
        if yahoo_symbol_has_history(candidate):
            return candidate
    return f"{numeric_code}.TW"


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_remote_symbol_search(query: str, max_results: int = 12) -> list[dict]:
    search_query = str(query or "").strip()
    if len(search_query) < 1:
        return []

    url = (
        "https://query1.finance.yahoo.com/v1/finance/search"
        f"?q={quote_plus(search_query)}&quotesCount={max_results * 3}&newsCount=0&listsCount=0&enableFuzzyQuery=true"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return []
    except Exception:
        return []

    results: list[dict] = []
    for quote in payload.get("quotes", []):
        raw_symbol = str(quote.get("symbol", "") or "").upper().strip()
        if not raw_symbol:
            continue

        quote_type = str(quote.get("quoteType", "") or quote.get("typeDisp", "")).upper()
        if quote_type and not any(token in quote_type for token in ("EQUITY", "ETF", "FUND")):
            continue

        display_name = (
            quote.get("shortname")
            or quote.get("longname")
            or quote.get("dispSecIndFlag")
            or raw_symbol
        )
        exchange = " / ".join(
            str(value).strip()
            for value in (
                quote.get("exchange"),
                quote.get("exchDisp"),
            )
            if str(value or "").strip()
        )

        normalized_symbol = normalize_dashboard_ticker(raw_symbol)
        if not normalized_symbol:
            continue

        results.append(
            {
                "symbol": normalized_symbol,
                "name": str(display_name).strip(),
                "exchange": exchange,
            }
        )

    return results


def build_symbol_search_text(symbol: str) -> str:
    normalized_symbol = str(symbol or "").upper().strip()
    meta = TAIWAN_TICKER_METADATA.get(normalized_symbol, {})
    runtime_meta = get_runtime_symbol_metadata(normalized_symbol)
    parts = [
        normalized_symbol,
        ticker_base_code(normalized_symbol),
        meta.get("zh", ""),
        meta.get("en", ""),
        runtime_meta.get("name", ""),
        runtime_meta.get("exchange", ""),
    ]
    parts.extend(meta.get("aliases", []))
    return " ".join(str(part) for part in parts if str(part).strip())


def _search_match_score(query_token: str, symbol: str, haystack: str) -> int:
    normalized_symbol = _normalize_symbol_lookup_token(symbol)
    normalized_text = _normalize_symbol_lookup_token(haystack)
    if not query_token or not normalized_text:
        return 0
    if query_token == normalized_symbol:
        return 140
    if query_token == normalized_text:
        return 120
    if normalized_symbol.startswith(query_token):
        return 100
    if query_token in normalized_symbol:
        return 80
    if query_token in normalized_text:
        return 60
    return 0


def build_scope_search_universe(scope: str) -> list[str]:
    symbols = set(DEFAULT_WATCHLIST_UNIVERSE)
    symbols.update(TAIWAN_TICKER_METADATA.keys())
    symbols.update(runtime_symbol_metadata().keys())
    return sorted(symbol for symbol in symbols if scope_allows_ticker(scope, symbol))


def build_symbol_search_results(query: str, scope: str, max_results: int = 12) -> list[str]:
    query_text = str(query or "").strip()
    if not query_text:
        return []

    query_token = _normalize_symbol_lookup_token(query_text)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    local_universe = build_scope_search_universe(scope)
    for symbol in local_universe:
        score = _search_match_score(query_token, symbol, build_symbol_search_text(symbol))
        if score > 0:
            scored.append((score, symbol))
            seen.add(symbol)

    for item in fetch_remote_symbol_search(query_text, max_results=max_results):
        symbol = normalize_dashboard_ticker(item.get("symbol", ""))
        if not symbol or not scope_allows_ticker(scope, symbol):
            continue
        register_runtime_symbol_metadata(symbol, name=item.get("name", ""), exchange=item.get("exchange", ""))
        haystack = " ".join([symbol, item.get("name", ""), item.get("exchange", "")])
        score = _search_match_score(query_token, symbol, haystack) + 10
        scored.append((score, symbol))
        seen.add(symbol)

    if query_text.isdigit() and len(query_text) in {4, 5, 6}:
        numeric_symbol = resolve_taiwan_numeric_symbol(query_text)
        if numeric_symbol and scope_allows_ticker(scope, numeric_symbol):
            scored.append((160, numeric_symbol))
            seen.add(numeric_symbol)

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    results: list[str] = []
    for _, symbol in scored:
        if symbol not in results:
            results.append(symbol)
        if len(results) >= max_results:
            break
    return results


def normalize_dashboard_ticker(raw_symbol: str) -> str:
    symbol_raw = str(raw_symbol).strip()
    symbol = symbol_raw.upper().replace(" ", "")
    if not symbol:
        return ""
    alias_hit = TAIWAN_ALIAS_INDEX.get(_normalize_symbol_lookup_token(symbol_raw))
    if alias_hit:
        return alias_hit
    if symbol in TAIWAN_TICKER_METADATA:
        return symbol
    if symbol.endswith(".TW") or symbol.endswith(".TWO"):
        return symbol
    if symbol.isdigit() and len(symbol) in {4, 5, 6}:
        return resolve_taiwan_numeric_symbol(symbol)
    return symbol


def market_scope_group_options(scope: str) -> list[str]:
    if scope == "U.S. only":
        return US_WATCHLIST_GROUPS
    if scope == "Taiwan only":
        return TAIWAN_WATCHLIST_GROUPS
    return US_WATCHLIST_GROUPS + TAIWAN_WATCHLIST_GROUPS


def display_ticker_label(ticker: str) -> str:
    ticker_upper = str(ticker).upper()
    meta = TAIWAN_TICKER_METADATA.get(ticker_upper)
    runtime_meta = get_runtime_symbol_metadata(ticker_upper)

    if meta:
        company = meta["zh"] if get_lang() == "繁體中文" else meta["en"]
        return f"{meta['code']} {company}"

    runtime_name = str(runtime_meta.get("name", "")).strip()
    if runtime_name:
        if is_taiwan_ticker(ticker_upper):
            return f"{ticker_base_code(ticker_upper)} {runtime_name}"
        return f"{ticker_upper} {runtime_name}"

    if is_taiwan_ticker(ticker_upper):
        base = ticker_base_code(ticker_upper)
        return f"{base} 台股" if get_lang() == "繁體中文" else f"{base} Taiwan"
    return str(ticker).upper()


def market_scope_label(scope: str) -> str:
    return {
        "Mixed (U.S. + Taiwan)": t("market_scope_mixed"),
        "U.S. only": t("market_scope_us"),
        "Taiwan only": t("market_scope_tw"),
    }.get(scope, scope)



def sort_ticker_options(options) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in options:
        normalized = normalize_dashboard_ticker(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return sorted(cleaned, key=lambda ticker: display_ticker_label(ticker).casefold())


def sync_multiselect_state(
    state_key: str,
    valid_options: list[str],
    fallback: list[str] | None = None,
    normalizer=None,
) -> list[str]:
    normalize = normalizer or (lambda value: value)
    normalized_to_option: dict[str, str] = {}
    for option in valid_options:
        normalized = normalize(option)
        if normalized and normalized not in normalized_to_option:
            normalized_to_option[normalized] = option

    current = []
    for value in st.session_state.get(state_key, []):
        normalized = normalize(value)
        if normalized in normalized_to_option:
            current.append(normalized_to_option[normalized])

    if not current and fallback:
        for value in fallback:
            normalized = normalize(value)
            if normalized in normalized_to_option:
                current.append(normalized_to_option[normalized])

    deduped_current = list(dict.fromkeys(current))
    st.session_state[state_key] = deduped_current
    return deduped_current



def dedupe_keep_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def filter_tickers_for_market_scope(tickers: list[str], market_scope: str) -> list[str]:
    filtered: list[str] = []
    for ticker in tickers:
        normalized = normalize_dashboard_ticker(ticker)
        if not normalized:
            continue
        if market_scope == "Taiwan only" and not is_taiwan_ticker(normalized):
            continue
        if market_scope == "U.S. only" and is_taiwan_ticker(normalized):
            continue
        filtered.append(normalized)
    return dedupe_keep_order(filtered)


def default_tickers_for_market_scope(market_scope: str) -> list[str]:
    if market_scope == "Mixed (U.S. + Taiwan)":
        return DEFAULT_TICKERS.copy()
    return [
        ticker
        for ticker in DEFAULT_TICKERS
        if (market_scope == "Taiwan only" and is_taiwan_ticker(ticker))
        or (market_scope == "U.S. only" and not is_taiwan_ticker(ticker))
    ]


def merge_ticker_selection(existing: list[str], additions: list[str], market_scope: str) -> list[str]:
    merged = dedupe_keep_order(filter_tickers_for_market_scope(existing + additions, market_scope))
    return merged


EMPTY_SELECTION_SENTINEL = "__none__"


def _csv_encode(values: list[str], empty_sentinel: str | None = None) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if cleaned:
        return ",".join(cleaned)
    return empty_sentinel or ""


def _csv_decode(value: str, empty_sentinel: str | None = None) -> list[str]:
    raw = str(value or "").strip()
    if empty_sentinel and raw == empty_sentinel:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _query_param_exists(key: str) -> bool:
    try:
        query_params = st.query_params
        if hasattr(query_params, "get_all"):
            values = query_params.get_all(key)
            if values is not None:
                return len(values) > 0
        return key in query_params
    except Exception:
        pass
    try:
        params = st.experimental_get_query_params()
        return key in params
    except Exception:
        return False


def _query_param_first(key: str) -> str:
    try:
        query_params = st.query_params
        if hasattr(query_params, "get_all"):
            values = query_params.get_all(key)
            if values:
                return str(values[0])
        value = query_params.get(key)
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value) if value is not None else ""
    except Exception:
        pass
    try:
        params = st.experimental_get_query_params()
        value = params.get(key, [""])
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _current_query_param_map() -> dict[str, str]:
    keys = ["lang", "devicectl", "device", "news", "scope", "groups", "picks", "custom", "search", "lens", "manual", "period", "interval"]
    return {key: _query_param_first(key) for key in keys if _query_param_first(key)}


def save_dashboard_preferences(params: dict[str, str]) -> None:
    clean = {key: str(value) for key, value in params.items() if value not in (None, "")}
    if clean == _current_query_param_map():
        return
    try:
        query_params = st.query_params
        if hasattr(query_params, "clear"):
            query_params.clear()
        for key, value in clean.items():
            query_params[key] = value
        return
    except Exception:
        pass
    try:
        st.experimental_set_query_params(**clean)
    except Exception:
        return


def load_dashboard_preferences() -> None:
    if st.session_state.get("_dashboard_prefs_loaded"):
        return

    language = _query_param_first("lang") or st.session_state.get("dashboard_language", "English")
    if language not in LANGUAGE_OPTIONS:
        language = "English"

    news_mode = _query_param_first("news") or st.session_state.get("dashboard_news_mode", "Original source")
    if news_mode not in NEWS_DISPLAY_OPTIONS:
        news_mode = "Original source"

    device_control_mode = _query_param_first("devicectl") or st.session_state.get("dashboard_device_control_mode", "Auto detect")
    if device_control_mode not in DEVICE_CONTROL_OPTIONS:
        device_control_mode = "Auto detect"

    device_mode = normalize_device_mode(_query_param_first("device") or st.session_state.get("dashboard_device_mode", "Desktop"))

    market_scope = _query_param_first("scope") or st.session_state.get("dashboard_market_scope", "Mixed (U.S. + Taiwan)")
    if market_scope not in MARKET_SCOPE_OPTIONS:
        market_scope = "Mixed (U.S. + Taiwan)"

    groups = _csv_decode(_query_param_first("groups"))
    groups = [group for group in groups if group in market_scope_group_options(market_scope)]
    if not groups:
        groups = list(MARKET_SCOPE_DEFAULT_GROUPS[market_scope])

    picks_param_present = _query_param_exists("picks")
    picks = [
        normalize_dashboard_ticker(value)
        for value in _csv_decode(_query_param_first("picks"), empty_sentinel=EMPTY_SELECTION_SENTINEL)
    ]
    picks = filter_tickers_for_market_scope(picks, market_scope)
    custom_symbols = _query_param_first("custom") or st.session_state.get("dashboard_custom_symbols", "")
    symbol_search = _query_param_first("search") or st.session_state.get("dashboard_symbol_search", "")

    lens_name = _query_param_first("lens") or st.session_state.get("dashboard_lens_name", DEFAULT_TREND_LENS)
    if lens_name not in TREND_LENSES:
        lens_name = DEFAULT_TREND_LENS

    manual_override = (_query_param_first("manual") or "0") == "1"
    manual_period = _query_param_first("period") or st.session_state.get("dashboard_manual_period", DEFAULT_PERIOD)
    if manual_period not in SUPPORTED_PERIODS:
        manual_period = DEFAULT_PERIOD
    manual_interval = _query_param_first("interval") or st.session_state.get("dashboard_manual_interval", DEFAULT_INTERVAL)
    if manual_interval not in SUPPORTED_INTERVALS:
        manual_interval = DEFAULT_INTERVAL

    st.session_state["dashboard_language"] = language
    st.session_state["dashboard_news_mode"] = news_mode
    st.session_state["dashboard_device_control_mode"] = device_control_mode
    st.session_state["dashboard_device_mode"] = device_mode
    st.session_state["dashboard_detected_device_mode"] = detect_device_mode_from_user_agent()
    st.session_state["dashboard_market_scope"] = market_scope
    st.session_state["dashboard_selected_groups"] = groups
    st.session_state["dashboard_selected_tickers"] = picks
    st.session_state["dashboard_selected_tickers_initialized"] = picks_param_present or bool(picks)
    st.session_state["dashboard_custom_symbols"] = custom_symbols
    st.session_state["dashboard_symbol_search"] = symbol_search
    st.session_state["dashboard_lens_name"] = lens_name
    st.session_state["dashboard_manual_override"] = manual_override
    st.session_state["dashboard_manual_period"] = manual_period
    st.session_state["dashboard_manual_interval"] = manual_interval
    st.session_state["_dashboard_prefs_loaded"] = True


def taiwan_sector_group(ticker: str) -> str:
    ticker_upper = str(ticker).upper()
    for group in TAIWAN_WATCHLIST_GROUPS:
        if ticker_upper in {symbol.upper() for symbol in WATCHLIST_PRESETS.get(group, [])}:
            return group
    return "Taiwan Semiconductors"


def taiwan_sector_peers(ticker: str, limit: int = 6) -> list[str]:
    group = taiwan_sector_group(ticker)
    ticker_upper = str(ticker).upper()
    peers = [symbol for symbol in WATCHLIST_PRESETS.get(group, []) if str(symbol).upper() != ticker_upper]
    return peers[:limit]


def compute_window_return_pct(series: pd.Series | None) -> float:
    if series is None:
        return float("nan")
    clean = ensure_datetime_index(series).dropna()
    if len(clean) < 2:
        return float("nan")
    start = clean.iloc[0]
    end = clean.iloc[-1]
    if pd.isna(start) or pd.isna(end) or start == 0:
        return float("nan")
    return float(((end / start) - 1) * 100)


def compute_recent_return_pct(series: pd.Series | None, window: int = 20) -> float:
    if series is None:
        return float("nan")
    clean = ensure_datetime_index(series).dropna()
    if len(clean) < 2:
        return float("nan")
    tail = clean.tail(min(window, len(clean)))
    return compute_window_return_pct(tail)


def percent_spread(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right):
        return float("nan")
    return float(left - right)


def taiwan_relative_state_label(score: float) -> str:
    if pd.isna(score):
        return t("tw_in_line")
    if score >= 12:
        return t("tw_strong_leader")
    if score >= 4:
        return t("tw_mild_leader")
    if score <= -12:
        return t("tw_clear_laggard")
    if score <= -4:
        return t("tw_mild_laggard")
    return t("tw_in_line")


def taiwan_relative_state_note(score: float) -> str:
    if pd.isna(score):
        return t("tw_benchmark_note_in_line")
    if score >= 12:
        return t("tw_benchmark_note_strong_leader")
    if score >= 4:
        return t("tw_benchmark_note_mild_leader")
    if score <= -12:
        return t("tw_benchmark_note_clear_laggard")
    if score <= -4:
        return t("tw_benchmark_note_mild_laggard")
    return t("tw_benchmark_note_in_line")


def benchmark_delta_label(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    direction = t("tw_outperforming") if value >= 0 else t("tw_lagging")
    return f"{direction} {format_percent(value)}"



@st.cache_data(ttl=300)
def fetch_global_reference_data(period: str, interval: str):
    return fetch_daily_data([item["ticker"] for item in GLOBAL_REFERENCE_INDICES], period, interval)


def global_market_trend_state(window_return: float, recent_return: float) -> str:
    if pd.isna(window_return) or pd.isna(recent_return):
        return t("global_market_pullback")
    if window_return >= 4 and recent_return >= 0:
        return t("global_market_uptrend")
    if window_return <= -4 and recent_return <= 0:
        return t("global_market_downtrend")
    return t("global_market_pullback")


def build_global_market_indicator(reference_data: pd.DataFrame | None, lens_meta: dict | None = None) -> dict:
    period = (lens_meta or {}).get("period", DEFAULT_PERIOD)
    interval = (lens_meta or {}).get("interval", DEFAULT_INTERVAL)

    cards = []
    up = down = 0
    for item in GLOBAL_REFERENCE_INDICES:
        ticker = item["ticker"]
        series, _ = get_price_series(reference_data, ticker)
        window_return = compute_window_return_pct(series)
        recent_return = compute_recent_return_pct(series, 20)
        last_price = series.iloc[-1] if series is not None and not series.empty else float("nan")
        state = global_market_trend_state(window_return, recent_return)
        if state == t("global_market_uptrend"):
            up += 1
        elif state == t("global_market_downtrend"):
            down += 1
        cards.append({
            "ticker": ticker,
            "label": t(item["label_key"]),
            "last_price": last_price,
            "window_return": window_return,
            "recent_return": recent_return,
            "state": state,
        })

    total = len(cards)
    if up >= 3:
        breadth_copy = t("global_market_breadth_risk_on", up=up, total=total)
    elif down >= 3:
        breadth_copy = t("global_market_breadth_risk_off", down=down, total=total)
    else:
        breadth_copy = t("global_market_breadth_mixed")

    return {
        "period": period,
        "interval": interval,
        "cards": cards,
        "up_count": up,
        "down_count": down,
        "breadth_copy": breadth_copy,
    }


def render_global_market_indicator(indicator: dict):
    cards = indicator.get("cards", [])
    if not cards:
        return

    card_html = "".join(
        textwrap.dedent(
            f"""
            <div class="global-indicator-card">
                <div class="global-indicator-card-top">
                    <div class="global-indicator-label">{escape(card['label'])}</div>
                    <div class="global-indicator-state-chip">{escape(card['state'])}</div>
                </div>
                <div class="global-indicator-value">{format_price(card['last_price'])}</div>
                <div class="global-indicator-grid">
                    <div>
                        <div class="global-indicator-mini-label">{t("global_market_window_return")}</div>
                        <div class="global-indicator-mini-value">{format_percent(card['window_return'])}</div>
                    </div>
                    <div>
                        <div class="global-indicator-mini-label">{t("global_market_recent")}</div>
                        <div class="global-indicator-mini-value">{format_percent(card['recent_return'])}</div>
                    </div>
                </div>
            </div>
            """
        ).strip()
        for card in cards
    )

    shell_html = textwrap.dedent(
        f"""
        <div class="global-indicator-shell global-indicator-shell-compact">
            <div class="global-indicator-header">
                <div>
                    <div class="section-header" style="margin:0; color:#f5ead8;">{t("global_market_indicator")}</div>
                    <div class="global-indicator-title">{t("global_market_breadth")}</div>
                    <div class="global-indicator-copy">{escape(indicator.get("breadth_copy", ""))}</div>
                </div>
                <div class="global-indicator-side">
                    <div class="global-indicator-pill-row">
                        <span class="global-indicator-pill">{t("sticky_global_note")}</span>
                        <span class="global-indicator-pill">{t("global_market_window")}: {escape(indicator["period"])} / {escape(indicator["interval"])}</span>
                    </div>
                    <div class="global-indicator-pill-row global-indicator-pill-row-tight">
                        <span class="global-indicator-pill">{t("global_market_indicator")}: NASDAQ · S&P 500 · Dow · TAIEX</span>
                    </div>
                </div>
            </div>
            <div class="global-indicator-card-grid">
                {card_html}
            </div>
        </div>
        """
    ).strip()

    render_html_block(shell_html)

def build_taiwan_benchmark_context(ticker: str, price_series: pd.Series, lens_meta: dict | None = None) -> dict:
    if not is_taiwan_ticker(ticker):
        return {}

    period = (lens_meta or {}).get("period", DEFAULT_PERIOD)
    interval = (lens_meta or {}).get("interval", DEFAULT_INTERVAL)
    peers = taiwan_sector_peers(ticker)
    benchmark_symbols = sorted(set(["^TWII", "0050.TW"] + peers))
    benchmark_data = fetch_daily_data(benchmark_symbols, period, interval)

    ticker_return = compute_window_return_pct(price_series)
    taiex_series, _ = get_price_series(benchmark_data, "^TWII")
    etf_series, _ = get_price_series(benchmark_data, "0050.TW")
    taiex_return = compute_window_return_pct(taiex_series)
    etf_return = compute_window_return_pct(etf_series)

    peer_rows = []
    for peer in peers:
        peer_series, _ = get_price_series(benchmark_data, peer)
        peer_return = compute_window_return_pct(peer_series)
        if pd.notna(peer_return):
            peer_rows.append({"ticker": peer, "label": display_ticker_label(peer), "return": peer_return})

    peer_returns = [row["return"] for row in peer_rows if pd.notna(row["return"])]
    peer_median = float(pd.Series(peer_returns).median()) if peer_returns else float("nan")
    peer_rank = (1 + sum(value > ticker_return for value in peer_returns)) if pd.notna(ticker_return) else None
    peer_total = len(peer_returns) + (1 if pd.notna(ticker_return) else 0)
    best_peer = max(peer_rows, key=lambda row: row["return"]) if peer_rows else None

    recent_relative = percent_spread(compute_recent_return_pct(price_series, 20), compute_recent_return_pct(taiex_series, 20))
    blended_score = pd.Series(
        [
            percent_spread(ticker_return, taiex_return),
            percent_spread(ticker_return, etf_return),
            percent_spread(ticker_return, peer_median),
            recent_relative,
        ],
        dtype="float64",
    ).dropna()
    relative_score = float(blended_score.mean()) if not blended_score.empty else float("nan")

    return {
        "group": taiwan_sector_group(ticker),
        "period": period,
        "interval": interval,
        "ticker_return": ticker_return,
        "taiex_return": taiex_return,
        "etf_return": etf_return,
        "vs_taiex": percent_spread(ticker_return, taiex_return),
        "vs_0050": percent_spread(ticker_return, etf_return),
        "peer_median": peer_median,
        "peer_rank": peer_rank,
        "peer_total": peer_total,
        "best_peer": best_peer,
        "recent_relative": recent_relative,
        "relative_score": relative_score,
        "state": taiwan_relative_state_label(relative_score),
        "note": taiwan_relative_state_note(relative_score),
    }


def render_taiwan_benchmark_layer(ticker: str, benchmark: dict):
    if not benchmark:
        return

    rank_text = "N/A"
    if benchmark.get("peer_rank") and benchmark.get("peer_total"):
        rank_text = t("tw_rank_of", rank=int(benchmark["peer_rank"]), total=int(benchmark["peer_total"]))

    best_peer_label = benchmark["best_peer"]["label"] if benchmark.get("best_peer") else "N/A"
    best_peer_return = format_percent(benchmark["best_peer"]["return"]) if benchmark.get("best_peer") else "N/A"

    st.markdown(
        f"""
        <div class="benchmark-shell">
            <div class="section-header" style="margin:0; color:#f5ead8;">{t("tw_benchmark_layer")}</div>
            <div class="benchmark-title">{escape(display_ticker_label(ticker))} · {escape(benchmark['state'])}</div>
            <div class="benchmark-copy">{t("tw_benchmark_copy")}</div>
            <div class="benchmark-grid">
                <div class="benchmark-box">
                    <div class="benchmark-label">{t("tw_benchmark_window")}</div>
                    <div class="benchmark-value">{escape(benchmark["period"])} / {escape(benchmark["interval"])}</div>
                    <div class="benchmark-sub">{t("tw_sector_group")}: {escape(tr_group(benchmark["group"]))}</div>
                </div>
                <div class="benchmark-box">
                    <div class="benchmark-label">{t("tw_vs_taiex")}</div>
                    <div class="benchmark-value">{format_percent(benchmark["vs_taiex"])}</div>
                    <div class="benchmark-sub">{benchmark_delta_label(benchmark["vs_taiex"])}</div>
                </div>
                <div class="benchmark-box">
                    <div class="benchmark-label">{t("tw_vs_0050")}</div>
                    <div class="benchmark-value">{format_percent(benchmark["vs_0050"])}</div>
                    <div class="benchmark-sub">{benchmark_delta_label(benchmark["vs_0050"])}</div>
                </div>
                <div class="benchmark-box">
                    <div class="benchmark-label">{t("tw_peer_rank")}</div>
                    <div class="benchmark-value">{escape(rank_text)}</div>
                    <div class="benchmark-sub">{t("tw_peer_median")}: {format_percent(benchmark["peer_median"])}</div>
                </div>
            </div>
            <div class="benchmark-table">
                <div class="benchmark-row">
                    <div class="benchmark-row-label">{t("tw_relative_state")}</div>
                    <div class="benchmark-row-value">{escape(benchmark["state"])}</div>
                    <div class="benchmark-row-note">{escape(benchmark["note"])}</div>
                </div>
                <div class="benchmark-row">
                    <div class="benchmark-row-label">{t("tw_best_peer")}</div>
                    <div class="benchmark-row-value">{escape(best_peer_label)}</div>
                    <div class="benchmark-row-note">{best_peer_return}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------
# Styling
# ---------------------------
def inject_css():
    st.markdown(
        """
        <style>
        :root {
            --page: #f4f1ea;
            --page-2: #ece8de;
            --paper: #fffdf8;
            --card: #ffffff;
            --card-soft: #f8f5ee;
            --ink: #18202b;
            --ink-soft: #4f5867;
            --ink-muted: #727b89;
            --line: #d9d2c5;
            --line-strong: #bfc8f5;
            --navy: #0f1728;
            --navy-2: #15203a;
            --brand: #5468ff;
            --brand-2: #45b8ff;
            --accent: #ff8b5e;
            --green: #10a36f;
            --red: #d95959;
            --amber: #d6a443;
            --shadow-lg: 0 24px 60px rgba(15, 23, 40, 0.10);
            --shadow-md: 0 16px 34px rgba(15, 23, 40, 0.08);
            --radius-xl: 28px;
            --radius-lg: 22px;
            --radius-md: 18px;
        }

        html, body, [class*="css"], .stApp, .stMarkdown, .stButton button, .stSelectbox label,
        .stMultiSelect label, .stCaption, .stDataFrame, input, textarea, select {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(84,104,255,0.06) 0%, rgba(84,104,255,0) 26%),
                radial-gradient(circle at top right, rgba(69,184,255,0.05) 0%, rgba(69,184,255,0) 20%),
                linear-gradient(180deg, var(--page) 0%, #f6f3ec 48%, var(--page-2) 100%);
            color: var(--ink);
        }

        .block-container {
            max-width: 1540px;
            padding-top: 1.1rem;
            padding-bottom: 2.4rem;
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--ink) !important;
            letter-spacing: -0.03em;
        }

        p, label, .stCaption, .stMarkdown, .stText, .st-emotion-cache-10trblm, .st-emotion-cache-1c7y2kd {
            color: var(--ink-soft);
        }

        section[data-testid="stSidebar"] {
            background:
                radial-gradient(circle at top left, rgba(84,104,255,0.18) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, #11192b 0%, #0b1221 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }

        section[data-testid="stSidebar"] * {
            color: #eef2ff !important;
        }

        .top-kicker, .hero-kicker, .guide-label, .section-header, .reference-label, .lens-label,
        .compare-hero-label, .compare-card-kicker, .catalyst-label, .alert-label, .lab-label,
        .winner-mini-label, .explorer-nav-kicker, .explorer-nav-panel-label, .side-eyebrow, .side-group-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: var(--ink-muted) !important;
        }

        .top-kicker {
            margin-bottom: 8px;
        }

        .top-intro {
            font-size: 15px;
            line-height: 1.68;
            color: var(--ink-soft);
            max-width: 980px;
            margin-top: 10px;
            margin-bottom: 18px;
        }

        .side-hero {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(124,140,255,.16) 0%, rgba(124,140,255,0) 32%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.92) 0%, rgba(10, 16, 33, 0.96) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-lg);
            padding: 18px 16px;
            box-shadow: 0 18px 36px rgba(0,0,0,.22);
            margin-bottom: 16px;
        }

        .side-title {
            font-size: 24px;
            font-weight: 900;
            color: #ffffff !important;
            line-height: 1.02;
            margin-top: 8px;
        }

        .side-copy {
            font-size: 13px;
            line-height: 1.58;
            color: rgba(238,242,255,.78) !important;
            margin-top: 8px;
        }

        section[data-testid="stSidebar"] [data-baseweb="select"] > div,
        section[data-testid="stSidebar"] [data-baseweb="input"] > div,
        section[data-testid="stSidebar"] .stTextInput > div > div {
            background: rgba(255,255,255,.05) !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            border-radius: 18px !important;
            min-height: 54px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.02), 0 10px 24px rgba(0,0,0,.18);
        }

        section[data-testid="stSidebar"] [data-baseweb="input"] input,
        section[data-testid="stSidebar"] .stTextInput input,
        section[data-testid="stSidebar"] .stNumberInput input {
            background: transparent !important;
            color: #0f1728 !important;
            -webkit-text-fill-color: #0f1728 !important;
            caret-color: #0f1728 !important;
            font-weight: 700 !important;
        }

        section[data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
        section[data-testid="stSidebar"] .stTextInput input::placeholder,
        section[data-testid="stSidebar"] .stNumberInput input::placeholder {
            color: rgba(15,23,40,.42) !important;
            -webkit-text-fill-color: rgba(15,23,40,.42) !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] [data-baseweb="select"] span,
        section[data-testid="stSidebar"] [data-baseweb="select"] div {
            color: #eef2ff !important;
        }

        section[data-testid="stSidebar"] [data-baseweb="tag"] {
            background: rgba(124,140,255,.18) !important;
            border: 1px solid rgba(124,140,255,.28) !important;
            border-radius: 999px !important;
            color: #eef2ff !important;
            font-weight: 800 !important;
        }

        section[data-testid="stSidebar"] .stButton > button {
            background: linear-gradient(135deg, rgba(84,104,255,0.26) 0%, rgba(69,184,255,0.14) 100%);
            border: 1px solid rgba(124,140,255,0.24);
            color: #ffffff;
            min-height: 50px;
            border-radius: 18px;
            font-weight: 900;
            box-shadow: 0 14px 30px rgba(0,0,0,.20);
        }

        .editorial-hero {
            background:
                radial-gradient(circle at top left, rgba(84,104,255,0.08) 0%, rgba(84,104,255,0) 28%),
                linear-gradient(180deg, var(--paper) 0%, #fbf8f1 100%);
            border: 1px solid var(--line);
            border-radius: var(--radius-xl);
            padding: 22px 22px 18px 22px;
            box-shadow: var(--shadow-lg);
            margin: 14px 0 16px 0;
        }

        .hero-title {
            font-size: 44px;
            font-weight: 900;
            line-height: 1.02;
            letter-spacing: -0.035em;
            color: var(--ink) !important;
            margin-top: 8px;
            max-width: 980px;
        }

        .hero-copy {
            font-size: 14px;
            line-height: 1.68;
            color: var(--ink-soft);
            margin-top: 10px;
            max-width: 980px;
        }

        .hero-chip-row, .chip-row, .tag-row, .lens-alert-row, .explorer-nav-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 14px;
        }

        .hero-chip, .chip, .compare-table-chip, .explorer-nav-chip, .small-pill, .impact-tag, .pro-tag, .lens-alert-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            background: linear-gradient(180deg, #f7f3ea 0%, #ffffff 100%);
            border: 1px solid var(--line);
            color: var(--ink);
        }

        .chip-buy, .crypto-buy, .pro-tag-up, .lens-alert-bull {background: rgba(16,163,111,0.10) !important; border-color: rgba(16,163,111,0.22) !important; color: #0c8d61 !important;}
        .chip-hold, .crypto-hold, .pro-tag-neutral, .lens-alert-neutral {background: rgba(214,164,67,0.10) !important; border-color: rgba(214,164,67,0.22) !important; color: #b27f14 !important;}
        .chip-sell, .crypto-sell, .pro-tag-down, .lens-alert-bear {background: rgba(217,89,89,0.10) !important; border-color: rgba(217,89,89,0.22) !important; color: #c24747 !important;}
        .chip-info {background: rgba(84,104,255,0.10) !important; border-color: rgba(84,104,255,0.18) !important; color: #4559ea !important;}

        .guide-shell, .lens-shell, .compare-shell, .reference-shell {
            background: linear-gradient(180deg, var(--paper) 0%, #fbf8f1 100%);
            border: 1px solid var(--line);
            border-radius: var(--radius-xl);
            padding: 20px 20px 18px 20px;
            box-shadow: var(--shadow-md);
            margin: 14px 0 16px 0;
        }

        .winner-shell, .catalyst-shell, .alert-shell, .lab-shell, .explorer-nav-shell, .trend-shell,
        .compare-table-shell, .compare-chart-shell, .chart-shell, .story-stream-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.14) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.94) 0%, rgba(10, 16, 33, 0.97) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-xl);
            padding: 20px 20px 18px 20px;
            box-shadow: 0 24px 52px rgba(0,0,0,.22);
            margin: 14px 0 16px 0;
            color: #eef2ff;
        }

        .winner-shell::after, .catalyst-shell::after, .alert-shell::after, .lab-shell::after, .explorer-nav-shell::after,
        .trend-shell::after, .chart-shell::after {
            content: "";
            position: absolute;
            right: -90px;
            top: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(69,184,255,0.10) 0%, rgba(69,184,255,0) 72%);
            pointer-events: none;
        }

        .guide-title, .reference-title, .lens-title, .compare-title, .winner-title, .catalyst-title,
        .alert-title, .lab-title, .trend-title, .chart-title, .explorer-nav-title {
            font-size: 26px;
            font-weight: 900;
            line-height: 1.02;
            letter-spacing: -0.035em;
            color: var(--ink) !important;
        }

        .winner-title, .catalyst-title, .alert-title, .lab-title, .trend-title, .chart-title, .explorer-nav-title {
            color: #ffffff !important;
        }

        .guide-copy, .reference-copy, .lens-copy, .compare-copy, .winner-copy, .catalyst-copy,
        .alert-copy, .lab-copy, .trend-sub, .chart-copy, .explorer-nav-copy, .explorer-nav-panel-copy {
            font-size: 14px;
            line-height: 1.66;
            color: var(--ink-soft);
        }

        .winner-copy, .catalyst-copy, .alert-copy, .lab-copy, .trend-sub, .chart-copy, .explorer-nav-copy, .explorer-nav-panel-copy {
            color: rgba(238,242,255,.76);
        }

        .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid {
            display: grid;
            gap: 12px;
            margin-top: 14px;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }

        .guide-card, .reference-card, .compare-hero-tile, .compare-card, .winner-mini,
        .catalyst-box, .alert-box, .lab-box, .lens-card, .explorer-nav-panel, .compare-table-row,
        .mini-candle-card {
            background: linear-gradient(180deg, var(--card-soft) 0%, #ffffff 100%);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 14px 14px 12px 14px;
            box-shadow: 0 10px 26px rgba(15, 23, 40, 0.06);
        }

        .winner-mini, .catalyst-box, .alert-box, .lab-box, .explorer-nav-panel, .compare-card, .compare-table-row, .mini-candle-card {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.10);
            color: #eef2ff;
            box-shadow: none;
        }

        .guide-head, .reference-head, .lens-head, .compare-hero-value {
            font-size: 18px;
            font-weight: 900;
            color: var(--ink);
            line-height: 1.12;
            margin-top: 8px;
        }

        .winner-mini-value, .catalyst-value, .alert-value, .lab-value, .explorer-nav-panel-value,
        .compare-card-title, .compare-card-price, .winner-main-title {
            font-size: 18px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.12;
            margin-top: 8px;
        }

        .winner-main-title {font-size: 24px;}
        .compare-card-price {font-size: 24px;}

        .guide-sub, .reference-sub, .lens-sub {
            font-size: 12.5px;
            line-height: 1.58;
            color: var(--ink-soft);
            margin-top: 6px;
        }

        .winner-mini-sub, .catalyst-sub, .alert-sub, .lab-sub, .explorer-nav-panel-copy, .compare-card-meta {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.76);
            margin-top: 6px;
        }

        .news-brief-card {
            background: linear-gradient(180deg, var(--paper) 0%, #fbf8f1 100%);
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            padding: 18px 18px 16px 18px;
            box-shadow: var(--shadow-md);
        }

        .lead-story, .crypto-card {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.16) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.96) 0%, rgba(10, 16, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-xl);
            padding: 20px 20px 18px 20px;
            box-shadow: 0 24px 52px rgba(0,0,0,.22);
        }
        .lead-story::after {
            content: "";
            position: absolute;
            right: -90px;
            top: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(69,184,255,0.10) 0%, rgba(69,184,255,0) 72%);
            pointer-events: none;
        }
        .lead-kicker {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: rgba(238,242,255,.60);
        }
        .lead-title {
            font-size: 30px;
            line-height: 1.06;
            font-weight: 900;
            color: #ffffff;
            margin-top: 8px;
            max-width: 900px;
        }
        .lead-summary {
            font-size: 14px;
            line-height: 1.68;
            color: rgba(238,242,255,.80) !important;
            margin-top: 10px;
            max-width: 920px;
        }
        .lead-meta-row {
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin-top: 14px;
        }
        .lead-story-board {
            display:grid;
            grid-template-columns: 1.1fr .9fr;
            gap: 14px;
            margin-top: 16px;
        }
        .lead-story-panel {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 20px;
            padding: 14px 14px 12px 14px;
            backdrop-filter: blur(12px);
        }
        .lead-panel-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(238,242,255,.62);
        }
        .lead-panel-value {
            font-size: 18px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.12;
            margin-top: 8px;
        }
        .lead-panel-copy {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.76);
            margin-top: 6px;
        }

        .brief-item {padding: 14px 0; border-bottom: 1px solid rgba(24, 32, 43, 0.08);}
        .brief-item:last-child {border-bottom: none;}

        .brief-meta, .news-meta, .story-row-meta, .lead-eyebrow {
            font-size: 12px;
            font-weight: 700;
            color: var(--ink-muted);
            margin-bottom: 8px;
        }

        .lead-eyebrow, .lead-title, .lead-summary, .crypto-sub, .winner-main-copy, .crypto-reasons, .winner-reason-list {
            color: rgba(238,242,255,.82) !important;
        }

        .brief-headline {
            font-size: 18px;
            line-height: 1.28;
            font-weight: 900;
            color: var(--ink);
            margin-bottom: 10px;
        }

        .brief-summary {
            font-size: 14px;
            line-height: 1.55;
            color: var(--ink-soft);
        }

        .lead-title, .story-row-title {
            font-size: 24px;
            line-height: 1.18;
            font-weight: 900;
            color: #ffffff;
        }

        .story-row {
            background: linear-gradient(180deg, rgba(255,255,255,.04) 0%, rgba(255,255,255,.02) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 20px;
            padding: 18px;
            box-shadow: none;
            margin-bottom: 14px;
        }

        .story-row-title, .story-row-summary, .story-row-meta {
            color: #eef2ff !important;
        }

        .story-row-summary {color: rgba(238,242,255,.78) !important;}

        .news-board-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.16) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.96) 0%, rgba(10, 16, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-xl);
            padding: 20px 20px 18px 20px;
            box-shadow: 0 24px 52px rgba(0,0,0,.22);
            margin: 14px 0 16px 0;
            color: #eef2ff;
        }
        .news-board-shell::after {
            content: "";
            position: absolute;
            right: -90px;
            top: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(69,184,255,0.10) 0%, rgba(69,184,255,0) 72%);
            pointer-events: none;
        }
        .news-board-copy {
            font-size: 13px;
            line-height: 1.62;
            color: rgba(238,242,255,.76);
            margin-top: 6px;
            max-width: 980px;
        }
        .highlight-shell {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 22px;
            padding: 16px 16px 14px 16px;
            backdrop-filter: blur(12px);
            margin-top: 14px;
        }
        .highlight-title {
            font-size: 20px;
            font-weight: 900;
            line-height: 1.08;
            color: #ffffff;
        }
        .highlight-copy {
            font-size: 13px;
            line-height: 1.58;
            color: rgba(238,242,255,.74);
            margin-top: 6px;
        }
        .highlight-row {
            display:grid;
            grid-template-columns: .9fr 2.5fr .9fr;
            gap: 12px;
            align-items: center;
            background: linear-gradient(135deg, rgba(255,255,255,.05) 0%, rgba(255,255,255,.02) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 18px;
            padding: 14px 14px 12px 14px;
            margin-top: 10px;
        }
        .highlight-tag {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            padding: 8px 11px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            border: 1px solid rgba(255,255,255,.10);
            width: fit-content;
        }
        .highlight-up {
            background: rgba(16,163,111,0.14);
            border-color: rgba(16,163,111,0.24);
            color: #98efc2;
        }
        .highlight-down {
            background: rgba(217,89,89,0.14);
            border-color: rgba(217,89,89,0.24);
            color: #ffc0c0;
        }
        .highlight-mixed {
            background: rgba(214,164,67,0.12);
            border-color: rgba(214,164,67,0.22);
            color: #ffe3a3;
        }
        .highlight-head {
            font-size: 17px;
            font-weight: 900;
            line-height: 1.18;
            color: #ffffff;
            margin-top: 0;
        }
        .soft-note {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.74);
        }

        .winner-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(84,104,255,.14);
            border: 1px solid rgba(84,104,255,.24);
            color: #d8deff;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .06em;
            text-transform: uppercase;
        }

        .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid {
            display: grid;
            grid-template-columns: 1.25fr .95fr;
            gap: 16px;
        }

        .compare-card-grid, .crypto-grid, .winner-rail-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 14px;
        }

        .compare-stat-label, .crypto-mini-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: .09em;
            color: rgba(238,242,255,.60);
            font-weight: 800;
        }

        .compare-stat-value, .crypto-mini-value, .crypto-main-number {
            font-size: 18px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.08;
            margin-top: 4px;
        }

        .crypto-main-number {font-size: 44px; margin-top: 12px;}
        .crypto-signal {margin-top: 12px; width: fit-content;}

        .impact-meter, .row-meter, .impact-bar-wrap, .catalyst-meter {
            background: rgba(255,255,255,.10);
            border-radius: 999px;
            overflow: hidden;
            height: 11px;
        }

        .impact-pos, .row-meter-fill-up, .impact-bar-pos, .catalyst-meter-fill {
            background: linear-gradient(90deg, #0f766e, var(--brand-2));
            color: transparent;
            height: 100%;
        }

        .impact-neg, .row-meter-fill-down, .impact-bar-neg {
            background: linear-gradient(90deg, #ef4444, var(--accent));
            color: transparent;
            height: 100%;
        }

        .impact-flat, .row-meter-fill-flat, .impact-bar-neu {
            background: linear-gradient(90deg, rgba(255,255,255,.22), rgba(255,255,255,.10));
            color: transparent;
            height: 100%;
        }

        a.inline-link, .brief-link {
            color: var(--brand-2);
            text-decoration: none;
            font-weight: 800;
        }

        a.inline-link:hover, .brief-link:hover {
            text-decoration: underline;
        }

        .footer-note, .disclaimer {
            font-size: 12px;
            line-height: 1.58;
            color: var(--ink-muted);
            margin-top: 14px;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background: rgba(255,255,255,.58);
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 10px;
            box-shadow: var(--shadow-md);
            margin-bottom: 12px;
        }

        .stTabs [data-baseweb="tab-list"]::before {
            content: "Open a ticker page for its full research workspace";
            display: block;
            width: 100%;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .09em;
            text-transform: uppercase;
            color: var(--ink-muted);
            margin-bottom: 4px;
            padding: 0 4px;
        }

        .stTabs [data-baseweb="tab"] {
            position: relative;
            background: linear-gradient(180deg, #f7f3ea 0%, #ffffff 100%);
            border: 1px solid var(--line);
            border-radius: 999px;
            color: var(--ink);
            font-weight: 800;
            padding: 12px 18px;
            min-height: 50px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.6);
        }

        .stTabs [data-baseweb="tab"]:hover {
            transform: translateY(-1px);
            border-color: var(--line-strong);
            box-shadow: 0 10px 18px rgba(84,104,255,.10);
        }

        .stTabs [aria-selected="true"] {
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.16) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, #172345 0%, #0b1221 100%) !important;
            color: #ffffff !important;
            border-color: rgba(84,104,255,.28) !important;
            box-shadow: 0 14px 28px rgba(0,0,0,.18), inset 0 -2px 0 rgba(255,138,91,.82) !important;
        }

        .stTabs [aria-selected="true"] * {
            color: #ffffff !important;
        }

        .stTabs [data-baseweb="tab-panel"] {
            padding-top: 0.4rem;
        }

        .compare-table-head {
            display:grid;
            grid-template-columns: 1.2fr 1fr 1fr 1.15fr 1fr 1fr 1.35fr;
            gap: 10px;
            padding: 0 12px 10px 12px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(238,242,255,.60);
        }

        .compare-table-body {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 14px;
        }

        .compare-table-row {
            display:grid;
            grid-template-columns: 1.2fr 1fr 1fr 1.15fr 1fr 1fr 1.35fr;
            gap: 10px;
            align-items: stretch;
            margin-bottom: 0;
        }

        .compare-table-cell {
            display:flex;
            flex-direction:column;
            justify-content:center;
            gap: 4px;
            min-width: 0;
        }

        .compare-table-ticker {
            font-size: 20px;
            font-weight: 900;
            color: #ffffff;
        }

        .compare-table-sub, .compare-table-note {
            font-size: 12px;
            color: rgba(238,242,255,.74);
        }

        .compare-table-value {
            font-size: 16px;
            font-weight: 900;
            color: #ffffff;
        }

        .mini-candle-name {
            font-size: 18px;
            font-weight: 900;
            color: #ffffff;
        }

        .mini-candle-sub {
            font-size: 12px;
            color: rgba(238,242,255,.74);
            margin-top: 6px;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, var(--card-soft) 0%, #ffffff 100%);
            border: 1px solid var(--line);
            padding: 16px 18px;
            border-radius: 20px;
            box-shadow: var(--shadow-md);
            min-height: 126px;
        }

        div[data-testid="stMetricLabel"] > div,
        div[data-testid="stMetricLabel"] label,
        [data-testid="stMetricLabel"] {
            color: var(--ink-muted) !important;
            font-weight: 800 !important;
            letter-spacing: .03em;
        }

        div[data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] {
            color: var(--ink) !important;
            font-weight: 900 !important;
        }

        div[data-testid="stMetricDelta"] > div,
        [data-testid="stMetricDelta"] {
            color: #2f72dd !important;
            font-weight: 800 !important;
        }


        .stNumberInput [data-baseweb="input"] > div {
            background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.98) 100%) !important;
            border: 1px solid rgba(214,164,67,0.28) !important;
            border-radius: 18px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.92), 0 10px 24px rgba(0,0,0,.12) !important;
        }

        .stNumberInput input {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            caret-color: #111827 !important;
            font-weight: 800 !important;
        }

        .stNumberInput input::placeholder {
            color: rgba(17,24,39,.48) !important;
            -webkit-text-fill-color: rgba(17,24,39,.48) !important;
            opacity: 1 !important;
        }

        .stNumberInput button {
            color: #111827 !important;
            background: rgba(255,255,255,.90) !important;
            border-color: rgba(214,164,67,0.24) !important;
        }

        .stNumberInput button:hover {
            background: rgba(248,250,252,.98) !important;
        }

        .stNumberInput [data-baseweb="input"] input:focus,
        .stNumberInput [data-baseweb="input"] input:active {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            caret-color: #111827 !important;
        }

        .block-container .stTextInput [data-baseweb="input"] > div {
            background: #ffffff !important;
            border: 1px solid rgba(214,164,67,0.24) !important;
            border-radius: 18px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.72), 0 10px 24px rgba(0,0,0,.12);
        }

        .block-container .stTextInput input,
        .block-container .stTextInput [data-baseweb="input"] input {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            caret-color: #111827 !important;
            font-weight: 800 !important;
        }

        .block-container .stTextInput input::placeholder,
        .block-container .stTextInput [data-baseweb="input"] input::placeholder {
            color: #6b7280 !important;
            -webkit-text-fill-color: #6b7280 !important;
            opacity: 1 !important;
        }

        .stDataFrame, div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.90);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: var(--shadow-md);
            overflow: hidden;
        }

        .stNumberInput [data-baseweb="input"] > div {
            background: #ffffff !important;
            border: 1px solid rgba(214,164,67,0.24) !important;
            border-radius: 18px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.72), 0 10px 24px rgba(0,0,0,.12);
        }

        .stNumberInput input,
        .stNumberInput [data-baseweb="input"] input {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            caret-color: #111827 !important;
            font-weight: 800 !important;
        }

        .stNumberInput input::placeholder,
        .stNumberInput [data-baseweb="input"] input::placeholder {
            color: #6b7280 !important;
            opacity: 1 !important;
        }

        .stNumberInput button {
            color: #0f1728 !important;
        }

        .scenario-table-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.12) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.94) 0%, rgba(10, 16, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-xl);
            box-shadow: 0 24px 52px rgba(0,0,0,.22);
            margin-top: 14px;
            overflow-x: auto;
        }

        .scenario-table-shell::after {
            content: "";
            position: absolute;
            right: -90px;
            top: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(69,184,255,0.10) 0%, rgba(69,184,255,0) 72%);
            pointer-events: none;
        }

        .scenario-table-scroll {
            overflow-x: auto;
            position: relative;
            z-index: 1;
        }

        .scenario-table {
            width: 100%;
            min-width: 1060px;
            border-collapse: separate;
            border-spacing: 0;
        }

        .scenario-table thead th {
            position: sticky;
            top: 0;
            z-index: 2;
            background: linear-gradient(180deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            color: #d8c39a;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            padding: 14px 14px 12px 14px;
            border-bottom: 1px solid rgba(255,255,255,.08);
            white-space: nowrap;
            text-align: left;
        }

        .scenario-table tbody td {
            padding: 14px;
            border-bottom: 1px solid rgba(255,255,255,.07);
            color: #eef2ff;
            font-size: 14px;
            line-height: 1.45;
            vertical-align: top;
            white-space: nowrap;
        }

        .scenario-table tbody tr:hover td {
            background: rgba(255,255,255,.035);
        }

        .scenario-table tbody tr:last-child td {
            border-bottom: none;
        }

        .scenario-table-primary {
            font-size: 16px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.15;
        }

        .scenario-table-secondary {
            font-size: 12px;
            color: rgba(238,242,255,.72);
            margin-top: 5px;
            line-height: 1.45;
            white-space: normal;
        }

        .scenario-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 7px 11px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            border: 1px solid rgba(255,255,255,.10);
        }

        .scenario-pill-up {
            background: rgba(16,163,111,0.12);
            border-color: rgba(16,163,111,0.24);
            color: #9ae7c4;
        }

        .scenario-pill-neutral {
            background: rgba(214,164,67,0.12);
            border-color: rgba(214,164,67,0.22);
            color: #ffe3a3;
        }

        .scenario-pill-down {
            background: rgba(217,89,89,0.12);
            border-color: rgba(217,89,89,0.22);
            color: #ffc0c0;
        }

        .scenario-summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px;
            margin: 14px 0 18px 0;
        }

        .scenario-summary-card {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.12) 0%, rgba(84,104,255,0) 32%),
                linear-gradient(180deg, rgba(18, 28, 46, 0.94) 0%, rgba(12, 19, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 24px;
            padding: 20px 22px 18px 22px;
            box-shadow: 0 18px 40px rgba(0,0,0,.18);
            min-height: 148px;
        }

        .scenario-summary-label {
            font-size: 13px;
            font-weight: 800;
            letter-spacing: .03em;
            color: #90a0ba;
        }

        .scenario-summary-value {
            font-size: 28px;
            line-height: 1.04;
            letter-spacing: -0.03em;
            font-weight: 900;
            color: #f8fbff;
            margin-top: 12px;
            word-break: break-word;
        }

        .scenario-summary-value-gold {
            color: #f4c56a;
        }

        .scenario-summary-sub {
            margin-top: 12px;
            font-size: 13px;
            line-height: 1.5;
            color: rgba(238,242,255,.76);
        }

        .scenario-summary-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: fit-content;
            margin-top: 12px;
            padding: 7px 11px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            background: rgba(34, 211, 238, 0.12);
            border: 1px solid rgba(34, 211, 238, 0.22);
            color: #9aefff;
        }

        
        .scenario-summary-badge-warn {
            background: rgba(244,197,106,0.12);
            border-color: rgba(244,197,106,0.22);
            color: #f9d88f;
        }

        .scenario-summary-badge-danger {
            background: rgba(217,89,89,0.12);
            border-color: rgba(217,89,89,0.22);
            color: #ffc0c0;
        }

        .scenario-single-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(84,104,255,.10) 0%, rgba(84,104,255,0) 30%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.94) 0%, rgba(10, 16, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: var(--radius-xl);
            padding: 18px 18px 16px 18px;
            box-shadow: 0 22px 48px rgba(0,0,0,.22);
            margin: 14px 0 12px 0;
        }

        .scenario-single-grid {
            display: grid;
            grid-template-columns: 1.1fr .9fr;
            gap: 14px;
            margin-top: 14px;
        }

        .scenario-single-card {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 22px;
            padding: 15px 15px 13px 15px;
        }

        .scenario-single-value {
            font-size: 22px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.08;
            margin-top: 8px;
        }

        .scenario-single-copy {
            font-size: 13px;
            line-height: 1.58;
            color: rgba(238,242,255,.76);
            margin-top: 6px;
        }

        .scenario-ladder {
            display: grid;
            gap: 9px;
            margin-top: 12px;
        }

        .scenario-ladder-row {
            display: grid;
            grid-template-columns: 92px 1fr;
            gap: 10px;
            align-items: start;
            padding: 10px 12px;
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.02) 100%);
            border: 1px solid rgba(255,255,255,.08);
        }

        .scenario-ladder-tag {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: fit-content;
            padding: 7px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            background: rgba(84,104,255,.12);
            border: 1px solid rgba(84,104,255,.22);
            color: #d9e1ff;
        }

        .scenario-ladder-tag-up {
            background: rgba(16,163,111,0.12);
            border-color: rgba(16,163,111,0.24);
            color: #9ae7c4;
        }

        .scenario-ladder-tag-down {
            background: rgba(217,89,89,0.12);
            border-color: rgba(217,89,89,0.24);
            color: #ffc0c0;
        }


.planner-slider-locked-note {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 8px;
    padding: 10px 12px;
    border-radius: 16px;
    border: 1px solid rgba(244,197,106,0.16);
    background: linear-gradient(135deg, rgba(244,197,106,0.10) 0%, rgba(255,255,255,0.03) 100%);
    color: rgba(238,242,255,.84);
    font-size: 12.5px;
    line-height: 1.45;
}

.planner-slider-locked-note strong {
    color: #f4c56a;
    font-weight: 900;
    white-space: nowrap;
}

.planner-slider-locked-note-soft {
    border-color: rgba(69,184,255,0.16);
    background: linear-gradient(135deg, rgba(69,184,255,0.10) 0%, rgba(255,255,255,0.03) 100%);
}

        .scenario-ratio-shell {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.02) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 22px;
            padding: 14px 16px 14px 16px;
            margin-top: 12px;
        }

        .scenario-ratio-title {
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
            color: rgba(244, 197, 106, 0.82);
        }

        .scenario-ratio-copy {
            font-size: 12.5px;
            line-height: 1.55;
            color: rgba(238,242,255,.72);
            margin-top: 6px;
        }

        .scenario-ratio-value {
            font-size: 22px;
            font-weight: 900;
            color: #ffffff;
            margin-top: 10px;
            line-height: 1.08;
        }

        .scenario-ratio-bars {
            display: grid;
            gap: 8px;
            margin-top: 12px;
        }

        .scenario-ratio-bar {
            display: grid;
            grid-template-columns: 78px 1fr 56px;
            gap: 10px;
            align-items: center;
        }

        .scenario-ratio-bar-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: rgba(238,242,255,.66);
        }

        .scenario-ratio-track {
            height: 10px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(255,255,255,.08);
        }

        .scenario-ratio-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, rgba(244,197,106,0.72) 0%, rgba(84,104,255,0.82) 100%);
        }

        .scenario-ratio-fill-up {
            background: linear-gradient(90deg, rgba(16,163,111,0.78) 0%, rgba(69,184,255,0.88) 100%);
        }

        .scenario-ratio-distribution {
            display: flex;
            width: 100%;
            height: 16px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(255,255,255,.08);
            border: 1px solid rgba(255,255,255,.08);
            margin-top: 12px;
        }

        .scenario-ratio-segment {
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 0;
            font-size: 10px;
            font-weight: 900;
            letter-spacing: .05em;
            color: #ffffff;
            white-space: nowrap;
        }

        .scenario-ratio-segment-1 {
            background: linear-gradient(90deg, rgba(244,197,106,0.90) 0%, rgba(225,172,66,0.96) 100%);
            color: #24190a;
        }

        .scenario-ratio-segment-2 {
            background: linear-gradient(90deg, rgba(84,104,255,0.88) 0%, rgba(109,123,255,0.96) 100%);
        }

        .scenario-ratio-segment-3 {
            background: linear-gradient(90deg, rgba(16,163,111,0.84) 0%, rgba(69,184,255,0.90) 100%);
        }

        .scenario-ratio-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }

        .scenario-ratio-legend-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.05);
            border: 1px solid rgba(255,255,255,.08);
            font-size: 11px;
            font-weight: 800;
            color: rgba(238,242,255,.86);
        }

        .scenario-ratio-legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            flex: 0 0 10px;
        }

        .scenario-ratio-legend-dot-1 {
            background: rgba(244,197,106,0.92);
        }

        .scenario-ratio-legend-dot-2 {
            background: rgba(96,113,255,0.94);
        }

        .scenario-ratio-legend-dot-3 {
            background: rgba(27,176,134,0.94);
        }

        .scenario-ratio-pct {
            font-size: 13px;
            font-weight: 900;
            color: #ffffff;
            text-align: right;
        }

        .planner-decision-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top right, rgba(244,197,106,.12) 0%, rgba(244,197,106,0) 26%),
                radial-gradient(circle at top left, rgba(84,104,255,.10) 0%, rgba(84,104,255,0) 30%),
                linear-gradient(180deg, rgba(18, 28, 46, 0.96) 0%, rgba(10, 16, 31, 0.99) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 26px;
            padding: 18px 18px 16px 18px;
            box-shadow: 0 22px 52px rgba(0,0,0,.22);
            margin: 12px 0 16px 0;
        }

        .planner-decision-head {
            display: grid;
            grid-template-columns: 1.2fr .9fr;
            gap: 14px;
            align-items: start;
        }

        .planner-decision-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 14px;
        }

        .planner-decision-card {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 22px;
            padding: 15px 15px 13px 15px;
            min-height: 136px;
        }

        .planner-decision-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
            color: rgba(244,197,106,0.80);
        }

        .planner-decision-kpi {
            font-size: 30px;
            line-height: 1.02;
            font-weight: 900;
            color: #ffffff;
            letter-spacing: -0.03em;
            margin-top: 10px;
        }

        .planner-decision-kpi-up {
            color: #9ae7c4;
        }

        .planner-decision-kpi-gold {
            color: #f4c56a;
        }

        .planner-decision-copy {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.74);
            margin-top: 8px;
        }

        .planner-decision-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            justify-content: flex-end;
        }

        .planner-decision-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            background: rgba(244,197,106,0.10);
            border: 1px solid rgba(244,197,106,0.22);
            color: #f6d695;
        }

        .planner-decision-chip-good {
            background: rgba(16,163,111,0.12);
            border-color: rgba(16,163,111,0.24);
            color: #9ae7c4;
        }

        .planner-decision-chip-warn {
            background: rgba(214,164,67,0.12);
            border-color: rgba(214,164,67,0.22);
            color: #ffe3a3;
        }

        .planner-decision-chip-bad {
            background: rgba(217,89,89,0.12);
            border-color: rgba(217,89,89,0.22);
            color: #ffc0c0;
        }

        .planner-decision-action {
            margin-top: 14px;
            border-radius: 22px;
            padding: 16px 16px 14px 16px;
            border: 1px solid rgba(255,255,255,.10);
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
        }

        .planner-decision-action-good {
            background: linear-gradient(135deg, rgba(16,163,111,.16) 0%, rgba(16,163,111,.05) 100%);
            border-color: rgba(16,163,111,.26);
        }

        .planner-decision-action-warn {
            background: linear-gradient(135deg, rgba(214,164,67,.16) 0%, rgba(214,164,67,.05) 100%);
            border-color: rgba(214,164,67,.24);
        }

        .planner-decision-action-bad {
            background: linear-gradient(135deg, rgba(217,89,89,.15) 0%, rgba(217,89,89,.05) 100%);
            border-color: rgba(217,89,89,.24);
        }

        .planner-decision-action-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
            color: rgba(244,197,106,0.80);
        }

        .planner-decision-action-title {
            font-size: 22px;
            line-height: 1.08;
            font-weight: 900;
            color: #ffffff;
            margin-top: 8px;
            letter-spacing: -0.03em;
        }

        .planner-decision-action-copy {
            font-size: 13px;
            line-height: 1.6;
            color: rgba(238,242,255,.78);
            margin-top: 8px;
            max-width: 960px;
        }

        .planner-decision-action-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }

        .planner-decision-action-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 11px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            background: rgba(255,255,255,.07);
            border: 1px solid rgba(255,255,255,.10);
            color: #f6f8ff;
        }

        .scenario-ladder-main {
            font-size: 14px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.45;
        }

        .scenario-ladder-sub {
            font-size: 12px;
            color: rgba(238,242,255,.70);
            margin-top: 4px;
            line-height: 1.5;
        }

        @media (max-width: 980px) {
            .scenario-single-grid {
                grid-template-columns: 1fr;
            }
        }

@media (max-width: 1100px) {
            .scenario-summary-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 640px) {
            .scenario-summary-grid {
                grid-template-columns: 1fr;
                gap: 12px;
            }
            .scenario-summary-card {
                min-height: 132px;
                padding: 18px;
            }
            .scenario-summary-value {
                font-size: 24px;
            }
        }

        .scenario-num {
            font-size: 16px;
            font-weight: 900;
            color: #ffffff;
        }

        .scenario-num-muted {
            font-size: 13px;
            font-weight: 800;
            color: rgba(238,242,255,.80);
        }

        .scenario-text-wrap {
            white-space: normal;
            min-width: 220px;
        }

        @media (max-width: 768px) {
            .scenario-table-shell {
                border-radius: 18px;
            }
            .scenario-table {
                min-width: 920px;
            }
            .scenario-table thead th,
            .scenario-table tbody td {
                padding: 12px;
            }
            .scenario-table-primary {
                font-size: 15px;
            }
        }

        @media (max-width: 980px) {
            .block-container {
                padding-left: 0.7rem;
                padding-right: 0.7rem;
            }
            .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid, .lead-story-board {
                grid-template-columns: 1fr;
            }
            .hero-title {font-size: 34px;}
            .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid {
                grid-template-columns: 1fr 1fr;
            }
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 0.6rem !important;
                padding-left: 0.55rem !important;
                padding-right: 0.55rem !important;
                padding-bottom: 1.2rem !important;
            }
            .hero-title, .guide-title, .winner-title, .compare-title, .catalyst-title, .alert-title, .lab-title, .trend-title, .explorer-nav-title, .reference-title {
                font-size: 22px !important;
            }
            .side-title {font-size: 22px !important;}
            .top-intro, .hero-copy, .guide-copy, .reference-copy, .lens-copy, .compare-copy, .winner-copy,
            .catalyst-copy, .alert-copy, .lab-copy, .trend-sub, .chart-copy, .explorer-nav-copy {
                font-size: 13px !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                overflow-x: auto !important;
                scrollbar-width: none;
            }
            .stTabs [data-baseweb="tab"] {
                white-space: nowrap !important;
                min-width: max-content !important;
                padding: 10px 14px !important;
                font-size: 13px !important;
                min-height: 46px !important;
            }
            .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid,
            .alert-grid, .lens-grid, .compare-card-grid, .crypto-grid, .winner-rail-grid {
                grid-template-columns: 1fr !important;
            }
            .target-watch-headline-grid {
                grid-template-columns: 1fr !important;
            }
            .highlight-row {
                grid-template-columns: 1fr !important;
            }
            .compare-table-head {display:none !important;}
            .compare-table-row {
                grid-template-columns: 1fr !important;
                gap: 10px !important;
                padding: 14px !important;
                border-radius: 18px !important;
            }
            .compare-table-cell {
                display:grid !important;
                grid-template-columns: minmax(92px, 110px) 1fr !important;
                gap: 10px !important;
                align-items: start !important;
                padding-bottom: 6px !important;
                border-bottom: 1px solid rgba(255,255,255,.07);
            }
            .compare-table-cell:last-child {
                border-bottom:none !important;
                padding-bottom:0 !important;
            }
            .compare-table-value {font-size: 17px !important;}
            div[data-testid="stMetric"] {
                min-height: 104px !important;
                padding: 14px !important;
            }
        }

        @media (max-width: 520px) {
            .hero-title {font-size: 20px !important;}
            .crypto-main-number {font-size: 34px !important;}
            .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid {
                grid-template-columns: 1fr !important;
            }
            .compare-table-cell {
                grid-template-columns: 1fr !important;
                gap: 4px !important;
            }
            .chip, .hero-chip, .small-pill, .impact-tag, .pro-tag, .lens-alert-chip, .explorer-nav-chip {
                width: 100%;
                justify-content: center;
            }
        }

        .brief-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.12) 0%, rgba(244, 197, 106, 0) 28%),
                linear-gradient(180deg, rgba(23, 24, 29, 0.98) 0%, rgba(14, 16, 21, 0.99) 100%);
            border: 1px solid rgba(255, 215, 128, 0.14);
            border-radius: 28px;
            padding: 20px 20px 18px 20px;
            box-shadow: 0 24px 52px rgba(0,0,0,.24);
            margin: 14px 0 16px 0;
            color: #f7f2e8;
        }

        .brief-shell::after {
            content: "";
            position: absolute;
            right: -80px;
            top: -74px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(244, 197, 106, 0.12) 0%, rgba(244, 197, 106, 0) 72%);
            pointer-events: none;
        }

        .brief-title {
            font-size: 26px;
            font-weight: 900;
            line-height: 1.02;
            letter-spacing: -0.03em;
            color: #fff8ee;
        }

        .brief-copy {
            font-size: 14px;
            line-height: 1.66;
            color: rgba(247, 242, 232, 0.76);
            max-width: 980px;
            margin-top: 8px;
        }

        .brief-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
            margin-top: 14px;
        }

        .brief-box {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 20px;
            padding: 14px;
            backdrop-filter: blur(12px);
        }

        .brief-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(244, 229, 201, 0.72);
        }

        .brief-value {
            font-size: 20px;
            font-weight: 900;
            line-height: 1.15;
            color: #fff8ee;
            margin-top: 8px;
        }

        .brief-risk {
            font-size: 17px;
        }

        .brief-sub {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(247, 242, 232, 0.76);
            margin-top: 6px;
        }

        .brief-action {
            margin-top: 14px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
            color: rgba(244, 229, 201, 0.78);
        }

        
        .compare-mosaic {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 14px;
            margin-top: 16px;
        }

        .compare-mosaic-card {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(255,196,87,.10) 0%, rgba(255,196,87,0) 28%),
                linear-gradient(180deg, rgba(20, 29, 56, 0.96) 0%, rgba(10, 16, 33, 0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 22px;
            padding: 16px 16px 14px 16px;
            box-shadow: 0 18px 36px rgba(0,0,0,.20);
            min-height: 100%;
        }

        .compare-mosaic-rank {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,.06);
            border: 1px solid rgba(255,255,255,.10);
            color: rgba(255,244,220,.84);
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
        }

        .compare-mosaic-title {
            font-size: 22px;
            font-weight: 900;
            line-height: 1.12;
            color: #ffffff;
            margin-top: 12px;
        }

        .compare-mosaic-price {
            font-size: 22px;
            font-weight: 900;
            color: #fff7ea;
            margin-top: 8px;
        }

        .compare-mosaic-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 14px;
        }

        .compare-mosaic-stat-label {
            font-size: 11px;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: rgba(238,242,255,.60);
        }

        .compare-mosaic-stat-value {
            font-size: 16px;
            font-weight: 900;
            color: #ffffff;
            margin-top: 4px;
            line-height: 1.1;
        }

        .compare-mosaic-meta {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.76);
            margin-top: 14px;
            border-top: 1px solid rgba(255,255,255,.08);
            padding-top: 12px;
        }

        .compare-layout-note {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(238,242,255,.74);
            margin-top: 10px;
        }

        @media (max-width: 768px) {
            .compare-mosaic-grid {
                grid-template-columns: 1fr;
            }
            .compare-mosaic-title,
            .compare-mosaic-price {
                font-size: 20px;
            }
        }

        
        .stMultiSelect [data-baseweb="select"] > div {
            background:
                radial-gradient(circle at top left, rgba(84,214,255,.10) 0%, rgba(84,214,255,0) 28%),
                linear-gradient(180deg, rgba(15,22,39,.98) 0%, rgba(9,15,28,.99) 100%) !important;
            border: 1px solid rgba(227,184,102,.16) !important;
            border-radius: 18px !important;
            min-height: 52px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.03), 0 10px 24px rgba(0,0,0,.18);
            transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
        }

        .stMultiSelect [data-baseweb="select"] > div:hover {
            border-color: rgba(227,184,102,.28) !important;
            box-shadow: 0 12px 28px rgba(0,0,0,.20);
            transform: translateY(-1px);
        }

        .stMultiSelect [data-baseweb="tag"] {
            background: linear-gradient(135deg, rgba(227,184,102,.18) 0%, rgba(170,126,53,.24) 100%) !important;
            border: 1px solid rgba(227,184,102,.24) !important;
            border-radius: 12px !important;
            color: #fff4df !important;
            font-weight: 800 !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
        }

        .stMultiSelect [data-baseweb="tag"] span,
        .stMultiSelect [data-baseweb="tag"] svg {
            color: #fff4df !important;
            fill: #fff4df !important;
        }

        div[data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="popover"] ul {
            background: linear-gradient(180deg, rgba(15,22,39,.99) 0%, rgba(9,15,28,1) 100%) !important;
            border: 1px solid rgba(227,184,102,.16) !important;
            border-radius: 16px !important;
            box-shadow: 0 18px 42px rgba(0,0,0,.34) !important;
            padding: 6px !important;
        }

        div[data-baseweb="popover"] [role="option"],
        div[data-baseweb="popover"] li {
            color: #eef4ff !important;
            border-radius: 12px !important;
        }

        div[data-baseweb="popover"] [role="option"][aria-selected="true"],
        div[data-baseweb="popover"] li[aria-selected="true"] {
            background: rgba(227,184,102,.14) !important;
        }

        .comparison-focus-preview {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
            margin-bottom: 8px;
        }

        .comparison-focus-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 999px;
            background: linear-gradient(135deg, rgba(227,184,102,.16) 0%, rgba(170,126,53,.22) 100%);
            border: 1px solid rgba(227,184,102,.22);
            color: #fff4df;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
        }

        .comparison-focus-note {
            color: rgba(238,242,255,.68);
            font-size: 12px;
            line-height: 1.56;
            margin-bottom: 14px;
        }

        .comparison-focus-preview {
            padding: 2px 0 0 0;
        }

        .comparison-focus-chip {
            box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 8px 18px rgba(0,0,0,.14);
        }


        
        /* Micro-typography tuning for planner / decision-board labels */
        .section-header,
        .top-kicker,
        .hero-kicker,
        .guide-label,
        .reference-label,
        .lens-label,
        .compare-hero-label,
        .compare-card-kicker,
        .catalyst-label,
        .alert-label,
        .lab-label,
        .winner-mini-label,
        .explorer-nav-kicker,
        .explorer-nav-panel-label,
        .side-eyebrow,
        .side-group-label {
            font-size: 12px !important;
            letter-spacing: .12em !important;
        }

        .planner-decision-label {
            font-size: 13px !important;
            letter-spacing: .10em !important;
        }

        .planner-decision-chip,
        .planner-decision-action-pill {
            font-size: 12px !important;
        }

        .scenario-ratio-title {
            font-size: 13px !important;
            letter-spacing: .10em !important;
        }

        .scenario-ratio-copy {
            font-size: 13px !important;
        }

        .scenario-ratio-bar-label {
            font-size: 12px !important;
            letter-spacing: .06em !important;
        }

        .scenario-ratio-segment {
            font-size: 11px !important;
        }

        .scenario-ratio-pct {
            font-size: 14px !important;
        }

        .scenario-summary-label {
            font-size: 14px !important;
        }

        @media (max-width: 768px) {
            .planner-decision-label,
            .scenario-ratio-title,
            .scenario-ratio-bar-label,
            .scenario-summary-label {
                font-size: 12px !important;
            }

            .planner-decision-chip,
            .planner-decision-action-pill,
            .scenario-ratio-segment {
                font-size: 11px !important;
            }
        }

        
        /* Typography hierarchy pass: premium gold micro-heads + clearer subtitle system */
        :root {
            --type-gold-main: rgba(244, 197, 106, 0.92);
            --type-gold-soft: rgba(244, 197, 106, 0.78);
            --type-subtle-warm: rgba(230, 220, 198, 0.78);
            --type-subtle-cool: rgba(238, 242, 255, 0.82);
            --type-subtle-muted: rgba(238, 242, 255, 0.68);
        }

        h1, h2, h3, h4, h5, h6 {
            letter-spacing: -0.034em;
        }

        .top-intro,
        .hero-copy,
        .guide-copy,
        .reference-copy,
        .lens-copy,
        .compare-copy,
        .winner-copy,
        .catalyst-copy,
        .alert-copy,
        .lab-copy,
        .trend-sub,
        .chart-copy,
        .explorer-nav-copy,
        .news-board-copy,
        .global-indicator-copy,
        .target-watch-copy,
        .scenario-intro-copy,
        .planner-decision-copy {
            font-size: 14.25px !important;
            line-height: 1.7 !important;
            color: var(--type-subtle-cool) !important;
        }

        .guide-sub,
        .reference-sub,
        .lens-sub,
        .winner-mini-sub,
        .catalyst-sub,
        .alert-sub,
        .lab-sub,
        .explorer-nav-panel-copy,
        .compare-card-meta,
        .scenario-ratio-copy,
        .scenario-ladder-sub,
        .target-watch-meta,
        .target-watch-sub {
            font-size: 13.25px !important;
            line-height: 1.62 !important;
            color: var(--type-subtle-warm) !important;
        }

        .section-header,
        .top-kicker,
        .hero-kicker,
        .guide-label,
        .reference-label,
        .lens-label,
        .compare-hero-label,
        .compare-card-kicker,
        .catalyst-label,
        .alert-label,
        .lab-label,
        .winner-mini-label,
        .explorer-nav-kicker,
        .explorer-nav-panel-label,
        .side-eyebrow,
        .side-group-label,
        .planner-decision-label,
        .scenario-ratio-title,
        .scenario-single-label,
        .target-watch-label,
        .target-watch-board-label,
        .global-indicator-label {
            font-size: 13px !important;
            font-weight: 900 !important;
            letter-spacing: .12em !important;
            text-transform: uppercase;
            color: var(--type-gold-main) !important;
        }

        .planner-decision-copy,
        .scenario-ratio-copy {
            color: var(--type-subtle-cool) !important;
        }

        .planner-decision-kpi {
            font-size: 31px !important;
        }

        .planner-decision-chip,
        .planner-decision-action-pill,
        .scenario-ratio-bar-label,
        .scenario-ratio-segment,
        .scenario-summary-chip,
        .target-watch-chip,
        .global-indicator-pill {
            font-size: 12px !important;
            letter-spacing: .055em !important;
        }

        .scenario-ratio-value,
        .target-watch-headline-title,
        .target-watch-stat-value {
            letter-spacing: -0.028em !important;
        }

        .brief-headline,
        .highlight-title,
        .story-row-title,
        .lead-title,
        .target-watch-title,
        .global-indicator-title {
            letter-spacing: -0.032em !important;
        }

        .brief-summary,
        .highlight-copy,
        .story-row-summary,
        .lead-summary,
        .target-watch-copy,
        .soft-note,
        .news-board-copy {
            color: var(--type-subtle-cool) !important;
        }

        .scenario-ratio-segment {
            min-height: 18px;
        }

        @media (max-width: 980px) {
            .section-header,
            .top-kicker,
            .hero-kicker,
            .guide-label,
            .reference-label,
            .lens-label,
            .compare-hero-label,
            .compare-card-kicker,
            .catalyst-label,
            .alert-label,
            .lab-label,
            .winner-mini-label,
            .explorer-nav-kicker,
            .explorer-nav-panel-label,
            .side-eyebrow,
            .side-group-label,
            .planner-decision-label,
            .scenario-ratio-title,
            .scenario-single-label,
            .target-watch-label,
            .target-watch-board-label,
            .global-indicator-label {
                font-size: 12.25px !important;
            }

            .top-intro,
            .hero-copy,
            .guide-copy,
            .reference-copy,
            .lens-copy,
            .compare-copy,
            .winner-copy,
            .catalyst-copy,
            .alert-copy,
            .lab-copy,
            .trend-sub,
            .chart-copy,
            .explorer-nav-copy,
            .news-board-copy,
            .global-indicator-copy,
            .target-watch-copy,
            .scenario-intro-copy,
            .planner-decision-copy {
                font-size: 13.5px !important;
            }

            .guide-sub,
            .reference-sub,
            .lens-sub,
            .winner-mini-sub,
            .catalyst-sub,
            .alert-sub,
            .lab-sub,
            .explorer-nav-panel-copy,
            .compare-card-meta,
            .scenario-ratio-copy,
            .scenario-ladder-sub,
            .target-watch-meta,
            .target-watch-sub {
                font-size: 12.75px !important;
            }
        }

        @media (max-width: 640px) {
            .planner-decision-chip,
            .planner-decision-action-pill,
            .scenario-ratio-bar-label,
            .scenario-ratio-segment,
            .scenario-summary-chip,
            .target-watch-chip,
            .global-indicator-pill {
                font-size: 11px !important;
            }
        }

        
                .planner-expander-wrap,
        .section-expander-wrap {
            margin: 10px 0 18px 0;
        }

        .planner-stack-spacer {
            height: 18px;
        }

        .candlestick-section-spacer {
            height: 18px;
        }

        .streamlit-expanderHeader,
        details[data-testid="stExpander"] summary {
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.10) 0%, rgba(244, 197, 106, 0) 34%),
                linear-gradient(180deg, rgba(255,255,255,.07) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(244, 197, 106, 0.14);
            border-radius: 18px;
            color: #f8f1e5 !important;
            font-weight: 900 !important;
            letter-spacing: .03em;
            padding: 13px 16px !important;
            box-shadow: 0 14px 30px rgba(0,0,0,.18);
        }

        details[data-testid="stExpander"] summary:hover {
            border-color: rgba(244, 197, 106, 0.24);
            box-shadow: 0 16px 34px rgba(0,0,0,.22);
        }

        details[data-testid="stExpander"] {
            border: none !important;
            background: transparent !important;
        }

        details[data-testid="stExpander"] {
            margin: 10px 0 18px 0;
            border: none !important;
            background: transparent !important;
        }

        details[data-testid="stExpander"] > div[role="group"] {
            padding: 12px 10px 2px 10px;
            border-radius: 0 0 20px 20px;
            background: linear-gradient(180deg, rgba(255,255,255,.015) 0%, rgba(255,255,255,.01) 100%);
        }

        details[data-testid="stExpander"][open] > summary {
            border-bottom-left-radius: 14px;
            border-bottom-right-radius: 14px;
            box-shadow: 0 18px 36px rgba(0,0,0,.22);
        }

        details[data-testid="stExpander"] summary svg {
            color: #f4c56a !important;
        }

        details[data-testid="stExpander"] summary p {
            font-size: 1.02rem !important;
            line-height: 1.35 !important;
        }

        details[data-testid="stExpander"] > div[role="group"] > div[data-testid="stVerticalBlock"] {
            background: transparent !important;
        }

        details[data-testid="stExpander"] > div[role="group"] div[data-testid="stVerticalBlockBorderWrapper"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }

        details[data-testid="stExpander"] > div[role="group"] div[data-testid="element-container"] {
            background: transparent !important;
        }

        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] > p:empty,
        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"]:empty,
        details[data-testid="stExpander"] div[data-testid="stMarkdown"]:empty,
        details[data-testid="stExpander"] div[data-testid="element-container"]:empty {
            display: none !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        details[data-testid="stExpander"] div[data-testid="element-container"]:has(> div[data-testid="stMarkdown"]:empty),
        details[data-testid="stExpander"] div[data-testid="element-container"]:has(> div[data-testid="stMarkdownContainer"]:empty) {
            display: none !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        details[data-testid="stExpander"] div[data-testid="stMarkdown"] {
            background: transparent !important;
        }

        .planner-expander-meta {
            display: block;
            margin: 0;
            padding: 0;
        }

        .planner-expander-helper {
            font-size: 13px;
            line-height: 1.62;
            color: rgba(245, 234, 216, 0.76);
            margin: 6px 2px 8px 2px;
        }

        .planner-expander-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 0 2px 12px 2px;
        }

        .planner-expander-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 7px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .07em;
            text-transform: uppercase;
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(255,255,255,.05);
            color: #f8f1e5;
        }

        .planner-expander-pill.is-scenario {
            background: rgba(244,197,106,.12);
            border-color: rgba(244,197,106,.26);
            color: #ffd78f;
        }

        .planner-expander-pill.is-comparison {
            background: rgba(84,214,255,.12);
            border-color: rgba(84,214,255,.22);
            color: #b2eeff;
        }

        .planner-expander-pill.is-target {
            background: rgba(122,149,255,.13);
            border-color: rgba(122,149,255,.24);
            color: #d7e0ff;
        }

        .planner-expander-pill.is-brief {
            background: rgba(131,224,167,.12);
            border-color: rgba(131,224,167,.24);
            color: #d6ffe3;
        }

        .planner-expander-pill.is-alert {
            background: rgba(255,112,112,.12);
            border-color: rgba(255,112,112,.22);
            color: #ffd1d1;
        }

        .planner-expander-pill.is-trend {
            background: rgba(255,154,98,.12);
            border-color: rgba(255,154,98,.22);
            color: #ffd9c2;
        }

        .planner-expander-pill.is-device {
            background: rgba(255,255,255,.06);
            border-color: rgba(255,255,255,.12);
            color: rgba(248,241,229,.82);
        }

        
.group-ticker-kicker {
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: #f3d79f;
            margin: 2px 0 10px 2px;
        }

        .target-tracking-focus {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            padding: 14px 16px;
            margin: 8px 0 14px 0;
            border-radius: 22px;
            background:
                radial-gradient(circle at top right, rgba(84, 214, 255, 0.10) 0%, rgba(84, 214, 255, 0) 34%),
                linear-gradient(135deg, rgba(255, 204, 115, 0.08) 0%, rgba(16, 26, 43, 0.90) 44%, rgba(9, 17, 31, 0.94) 100%);
            border: 1px solid rgba(255, 204, 115, 0.16);
            box-shadow: 0 14px 30px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255,255,255,0.03);
        }

        .target-tracking-focus-left {
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }

        .target-tracking-focus-index {
            width: 40px;
            height: 40px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, rgba(255, 204, 115, 0.26) 0%, rgba(255, 154, 98, 0.18) 100%);
            border: 1px solid rgba(255, 204, 115, 0.20);
            color: #ffe7b0;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: .04em;
            flex: 0 0 auto;
        }

        .target-tracking-focus-copy {
            min-width: 0;
        }

        .target-tracking-focus-kicker {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: rgba(255, 231, 176, 0.72);
            margin-bottom: 4px;
        }

        .target-tracking-focus-name {
            font-size: 24px;
            line-height: 1.08;
            font-weight: 900;
            color: #fff7e6;
            letter-spacing: -0.02em;
            word-break: break-word;
        }

        .target-tracking-focus-symbol {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 9px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.10);
            color: rgba(248,241,229,.90);
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
            flex: 0 0 auto;
        }

        .group-stack-divider {
            height: 10px;
        }


        /* Layout hardening pass for HTML-heavy premium sections */
        .global-indicator-shell,
        .global-indicator-card,
        .scenario-single-shell,
        .scenario-single-card,
        .target-watch-shell,
        .benchmark-shell,
        .compare-shell,
        .decision-brief-shell,
        .alert-shell,
        .trend-shell {
            min-width: 0;
        }

        .global-indicator-shell *,
        .global-indicator-card *,
        .scenario-single-shell *,
        .scenario-single-card *,
        .target-watch-shell *,
        .benchmark-shell * {
            writing-mode: horizontal-tb !important;
        }

        .global-indicator-card-grid {
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            align-items: stretch;
        }

        .global-indicator-card {
            min-width: 0;
        }

        .global-indicator-card-top {
            align-items: flex-start;
            flex-wrap: wrap;
        }

        .global-indicator-label,
        .global-indicator-state-chip,
        .global-indicator-mini-label,
        .global-indicator-mini-value {
            white-space: nowrap;
        }

        .global-indicator-state-chip {
            flex: 0 0 auto;
            text-align: left;
        }

        .scenario-single-grid {
            grid-template-columns: minmax(0, 1.08fr) minmax(300px, 0.92fr);
            align-items: start;
        }

        .scenario-single-grid > div,
        .scenario-single-card,
        .scenario-ladder-row > div {
            min-width: 0;
        }

        .scenario-ladder-row {
            grid-template-columns: 96px minmax(0, 1fr);
        }

        .scenario-ladder-tag {
            flex: 0 0 auto;
            white-space: nowrap;
        }

        .scenario-ladder-main,
        .scenario-ladder-sub,
        .scenario-single-copy {
            white-space: normal;
            word-break: normal;
            overflow-wrap: anywhere;
        }

        .scenario-ladder-main {
            max-width: 100%;
        }

        @media (max-width: 1200px) {
            .global-indicator-card-grid {
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
        }

        @media (max-width: 980px) {
            .scenario-single-grid {
                grid-template-columns: 1fr;
            }

            .global-indicator-label,
            .global-indicator-state-chip,
            .global-indicator-mini-label,
            .global-indicator-mini-value {
                white-space: normal;
            }
        }

        @media (max-width: 768px) {
            .target-tracking-focus {
                align-items: flex-start;
                flex-direction: column;
            }

            .target-tracking-focus-symbol {
                margin-left: 52px;
            }

            .target-tracking-focus-name {
                font-size: 20px;
            }
        }


</style>
        """,
        unsafe_allow_html=True,
    )



def inject_premium_overrides():
    st.markdown(
        """
        <style>
        :root {
            --page: #07111f;
            --page-2: #0b1426;
            --paper: rgba(12, 19, 33, 0.84);
            --card: rgba(16, 26, 43, 0.88);
            --card-soft: rgba(255, 255, 255, 0.03);
            --ink: #f7f9ff;
            --ink-soft: #c6d0e1;
            --ink-muted: #8f9bb0;
            --line: rgba(255, 255, 255, 0.10);
            --line-strong: rgba(122, 149, 255, 0.38);
            --navy: #07111f;
            --navy-2: #0b1426;
            --brand: #7a95ff;
            --brand-2: #54d6ff;
            --accent: #ff9a62;
            --green: #24c18b;
            --red: #ff7070;
            --amber: #ffcc73;
            --shadow-lg: 0 28px 80px rgba(0, 0, 0, 0.40);
            --shadow-md: 0 18px 46px rgba(0, 0, 0, 0.24);
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(84, 214, 255, 0.10) 0%, rgba(84, 214, 255, 0) 24%),
                radial-gradient(circle at top right, rgba(122, 149, 255, 0.14) 0%, rgba(122, 149, 255, 0) 24%),
                radial-gradient(circle at bottom right, rgba(255, 154, 98, 0.09) 0%, rgba(255, 154, 98, 0) 18%),
                linear-gradient(180deg, #050b15 0%, #08111f 44%, #040811 100%) !important;
            color: var(--ink) !important;
        }

        .block-container {
            max-width: 1500px;
            padding-top: 1rem;
            padding-bottom: 2.6rem;
        }

        html {
            scroll-behavior: smooth;
        }

        ::selection {
            background: rgba(122, 149, 255, 0.28);
        }

        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-thumb {
            background: linear-gradient(180deg, rgba(122,149,255,.55) 0%, rgba(84,214,255,.45) 100%);
            border-radius: 999px;
            border: 2px solid transparent;
            background-clip: padding-box;
        }

        h1, h2, h3, h4, h5, h6,
        p, label, .stCaption, .stMarkdown, .stText {
            color: inherit !important;
        }

        .top-kicker {
            color: #9eb1d1 !important;
            letter-spacing: .18em;
        }

        .top-intro {
            max-width: 860px;
            color: #b7c4da !important;
            font-size: 14px;
            line-height: 1.72;
            margin-bottom: 20px;
        }

        section[data-testid="stSidebar"] {
            background:
                radial-gradient(circle at top left, rgba(122,149,255,.18) 0%, rgba(122,149,255,0) 26%),
                linear-gradient(180deg, rgba(6, 11, 21, 0.98) 0%, rgba(7, 13, 24, 0.99) 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset -1px 0 0 rgba(255,255,255,0.04);
        }

        section[data-testid="stSidebar"] [data-baseweb="select"] > div,
        section[data-testid="stSidebar"] [data-baseweb="input"] > div,
        section[data-testid="stSidebar"] .stTextInput > div > div {
            background: rgba(255,255,255,.04) !important;
            border: 1px solid rgba(255,255,255,.09) !important;
            border-radius: 18px !important;
            min-height: 52px;
            backdrop-filter: blur(12px);
            transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
        }

        section[data-testid="stSidebar"] [data-baseweb="select"] > div:hover,
        section[data-testid="stSidebar"] [data-baseweb="input"] > div:hover,
        section[data-testid="stSidebar"] .stTextInput > div > div:hover {
            border-color: rgba(122,149,255,.28) !important;
            box-shadow: 0 10px 24px rgba(0,0,0,.18);
            transform: translateY(-1px);
        }

        .stMultiSelect [data-baseweb="select"] > div,
        .stSelectbox [data-baseweb="select"] > div,
        .stTextInput > div > div,
        .stNumberInput > div > div {
            background: linear-gradient(180deg, rgba(18, 27, 45, 0.96) 0%, rgba(10, 16, 29, 0.98) 100%) !important;
            border: 1px solid rgba(255, 215, 128, 0.18) !important;
            border-radius: 18px !important;
            min-height: 52px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 12px 28px rgba(0,0,0,.20);
            transition: border-color .18s ease, box-shadow .18s ease, transform .18s ease;
        }

        .stMultiSelect [data-baseweb="select"] > div:hover,
        .stSelectbox [data-baseweb="select"] > div:hover,
        .stTextInput > div > div:hover,
        .stNumberInput > div > div:hover {
            border-color: rgba(255, 215, 128, 0.28) !important;
            box-shadow: 0 14px 30px rgba(0,0,0,.24);
            transform: translateY(-1px);
        }

        .stMultiSelect [data-baseweb="tag"],
        .stSelectbox [data-baseweb="tag"] {
            background: linear-gradient(135deg, rgba(227,184,102,.18) 0%, rgba(170,126,53,.24) 100%) !important;
            border: 1px solid rgba(255, 215, 128, 0.24) !important;
            color: #fff4df !important;
            border-radius: 999px !important;
            font-weight: 800 !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
        }

        .stMultiSelect [data-baseweb="select"] input,
        .stSelectbox [data-baseweb="select"] input,
        .stTextInput input,
        .stNumberInput input {
            color: #f7f9ff !important;
            -webkit-text-fill-color: #f7f9ff !important;
            caret-color: #f7f9ff !important;
        }

        .stSelectbox [data-baseweb="select"] > div [data-testid="stMarkdownContainer"],
        .stSelectbox [data-baseweb="select"] > div [data-testid="stMarkdownContainer"] p,
        .stSelectbox [data-baseweb="select"] > div span,
        .stSelectbox [data-baseweb="select"] > div div,
        .stSelectbox [data-baseweb="select"] > div * {
            color: #f7f9ff !important;
            -webkit-text-fill-color: #f7f9ff !important;
        }

        .stSelectbox [data-baseweb="select"] > div [aria-selected="true"],
        .stSelectbox [data-baseweb="select"] > div [data-baseweb="select"] * {
            color: #fff4df !important;
            -webkit-text-fill-color: #fff4df !important;
        }

        .stSelectbox [data-baseweb="select"] > div input::placeholder,
        .stTextInput input::placeholder,
        .stNumberInput input::placeholder {
            color: rgba(229, 236, 249, 0.56) !important;
            -webkit-text-fill-color: rgba(229, 236, 249, 0.56) !important;
            opacity: 1 !important;
        }

        .stMultiSelect [data-baseweb="select"] svg,
        .stSelectbox [data-baseweb="select"] svg {
            color: #d8c29a !important;
            fill: #d8c29a !important;
        }

        .stMultiSelect [data-baseweb="select"] [aria-invalid="true"],
        .stMultiSelect [data-baseweb="select"] > div[aria-invalid="true"] {
            border-color: rgba(255, 215, 128, 0.28) !important;
            box-shadow: 0 0 0 1px rgba(255, 215, 128, 0.18), 0 14px 30px rgba(0,0,0,.24) !important;
        }

        div[data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="menu"] {
            background: linear-gradient(180deg, rgba(18, 27, 45, 0.98) 0%, rgba(9, 14, 26, 1.0) 100%) !important;
            border: 1px solid rgba(255, 215, 128, 0.16) !important;
            border-radius: 18px !important;
            box-shadow: 0 24px 60px rgba(0,0,0,.30) !important;
        }

        div[data-baseweb="popover"] [role="option"],
        div[data-baseweb="menu"] [role="option"] {
            color: #edf2ff !important;
            background: transparent !important;
        }

        div[data-baseweb="popover"] [role="option"][aria-selected="true"],
        div[data-baseweb="menu"] [role="option"][aria-selected="true"] {
            background: rgba(227,184,102,.12) !important;
            color: #fff4df !important;
        }

        div[data-baseweb="popover"] [role="option"]:hover,
        div[data-baseweb="menu"] [role="option"]:hover {
            background: rgba(122,149,255,.10) !important;
        }


        section[data-testid="stSidebar"] .stButton > button,
        .stButton > button {
            border-radius: 16px !important;
            border: 1px solid rgba(122,149,255,.22) !important;
            background:
                radial-gradient(circle at top left, rgba(84,214,255,.18) 0%, rgba(84,214,255,0) 30%),
                linear-gradient(135deg, rgba(40,57,103,.96) 0%, rgba(18,28,50,.98) 100%) !important;
            color: #f9fbff !important;
            font-weight: 800 !important;
            box-shadow: 0 14px 30px rgba(0,0,0,.22);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        }

        section[data-testid="stSidebar"] .stButton > button:hover,
        .stButton > button:hover {
            transform: translateY(-1px);
            border-color: rgba(84,214,255,.28) !important;
            box-shadow: 0 18px 36px rgba(0,0,0,.28);
        }

        section[data-testid="stSidebar"] [data-baseweb="tag"],
        .hero-chip, .chip, .compare-table-chip, .explorer-nav-chip, .small-pill, .impact-tag, .pro-tag, .lens-alert-chip,
        .side-lens-chip {
            background: rgba(255,255,255,.05) !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            color: #e9efff !important;
            backdrop-filter: blur(10px);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
        }

        .chip-buy, .crypto-buy, .pro-tag-up, .lens-alert-bull,
        .highlight-up, .winner-badge {
            background: rgba(36,193,139,.13) !important;
            border-color: rgba(36,193,139,.24) !important;
            color: #9df0c8 !important;
        }

        .chip-hold, .crypto-hold, .pro-tag-neutral, .lens-alert-neutral,
        .highlight-mixed {
            background: rgba(255,204,115,.12) !important;
            border-color: rgba(255,204,115,.22) !important;
            color: #ffe0a7 !important;
        }

        .chip-sell, .crypto-sell, .pro-tag-down, .lens-alert-bear,
        .highlight-down {
            background: rgba(255,112,112,.12) !important;
            border-color: rgba(255,112,112,.22) !important;
            color: #ffc3c3 !important;
        }

        .chip-info {
            background: rgba(122,149,255,.14) !important;
            border-color: rgba(122,149,255,.24) !important;
            color: #d9e1ff !important;
        }

        .editorial-hero, .guide-shell, .lens-shell, .compare-shell, .reference-shell,
        .winner-shell, .catalyst-shell, .alert-shell, .lab-shell, .explorer-nav-shell,
        .trend-shell, .compare-table-shell, .compare-chart-shell, .chart-shell,
        .story-stream-shell, .news-board-shell, .lead-story, .crypto-card,
        .news-brief-card, .compare-card, .mini-candle-card {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(122,149,255,.12) 0%, rgba(122,149,255,0) 30%),
                linear-gradient(180deg, rgba(12, 19, 33, 0.92) 0%, rgba(8, 13, 24, 0.96) 100%) !important;
            border: 1px solid rgba(255,255,255,.09) !important;
            box-shadow: 0 24px 60px rgba(0,0,0,.28) !important;
            backdrop-filter: blur(16px);
        }

        .editorial-hero::after, .guide-shell::after, .lens-shell::after, .compare-shell::after,
        .reference-shell::after, .winner-shell::after, .catalyst-shell::after, .alert-shell::after,
        .lab-shell::after, .explorer-nav-shell::after, .trend-shell::after, .chart-shell::after,
        .news-board-shell::after, .lead-story::after, .crypto-card::after {
            content: "";
            position: absolute;
            right: -88px;
            top: -82px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(84,214,255,.10) 0%, rgba(84,214,255,0) 72%);
            pointer-events: none;
        }

        .guide-card, .reference-card, .compare-hero-tile, .winner-mini,
        .catalyst-box, .alert-box, .lab-box, .lens-card, .explorer-nav-panel,
        .compare-table-row, .highlight-shell, .highlight-row, .story-row, .prob-box {
            position: relative;
            overflow: hidden;
            border-radius: 22px;
            padding: 18px 18px 16px 18px;
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.12) 0%, rgba(244, 197, 106, 0) 32%),
                linear-gradient(180deg, #1D212B 0%, #15171D 100%) !important;
            border: 1px solid rgba(255, 215, 128, 0.18) !important;
            box-shadow:
                inset 0 1px 0 rgba(255,255,255,0.03),
                0 18px 40px rgba(0,0,0,0.30) !important;
            backdrop-filter: blur(14px);
            min-height: 100%;
        }

        .prob-box::after {
            content: "";
            position: absolute;
            right: -46px;
            top: -46px;
            width: 136px;
            height: 136px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(246, 211, 101, 0.18) 0%, rgba(246, 211, 101, 0) 72%);
            pointer-events: none;
        }

        .guide-card:hover, .reference-card:hover, .compare-hero-tile:hover, .winner-mini:hover,
        .catalyst-box:hover, .alert-box:hover, .lab-box:hover, .lens-card:hover,
        .explorer-nav-panel:hover, .compare-card:hover, .compare-table-row:hover,
        .mini-candle-card:hover, .story-row:hover, .highlight-row:hover {
            transform: translateY(-2px);
            border-color: rgba(122,149,255,.24) !important;
            box-shadow: 0 14px 28px rgba(0,0,0,.18) !important;
        }

        .hero-kicker, .guide-label, .section-header, .reference-label, .lens-label,
        .compare-hero-label, .compare-card-kicker, .catalyst-label, .alert-label,
        .lab-label, .winner-mini-label, .explorer-nav-kicker, .explorer-nav-panel-label,
        .side-eyebrow, .side-group-label, .lead-kicker, .lead-panel-label,
        .compare-stat-label, .crypto-mini-label, .prob-label {
            color: #B8A98A !important;
            letter-spacing: .18em;
        }

        .hero-title, .guide-title, .reference-title, .lens-title, .compare-title,
        .winner-title, .catalyst-title, .alert-title, .lab-title, .trend-title,
        .chart-title, .explorer-nav-title, .lead-title, .highlight-title,
        .brief-headline, .story-row-title, .compare-card-title, .compare-card-price,
        .winner-main-title, .compare-table-ticker, .compare-table-value,
        .winner-mini-value, .catalyst-value, .alert-value, .lab-value,
        .explorer-nav-panel-value, .guide-head, .reference-head, .lens-head,
        .compare-hero-value, .lead-panel-value, .mini-candle-name,
        .crypto-main-number, .crypto-mini-value, .compare-stat-value {
            color: #f8fbff !important;
        }

        .hero-title {
            font-size: 40px;
            max-width: 760px;
        }

        .hero-copy, .guide-copy, .reference-copy, .lens-copy, .compare-copy,
        .winner-copy, .catalyst-copy, .alert-copy, .lab-copy, .trend-sub,
        .chart-copy, .explorer-nav-copy, .explorer-nav-panel-copy, .lead-summary,
        .highlight-copy, .brief-summary, .story-row-summary, .guide-sub,
        .reference-sub, .lens-sub, .winner-mini-sub, .catalyst-sub, .alert-sub,
        .lab-sub, .compare-card-meta, .soft-note, .news-board-copy, .lead-panel-copy,
        .mini-candle-sub, .compare-table-sub, .compare-table-note, .footer-note {
            color: #b8c5da !important;
        }

        .lead-title {
            font-size: 28px;
            max-width: 720px;
        }

        .story-row {
            padding: 18px 18px 16px 18px;
            border-radius: 22px;
            transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
        }

        .prob-box {
            position: relative;
            overflow: hidden;
            border-radius: 22px;
            padding: 18px 18px 16px 18px;
            background:
                radial-gradient(circle at top left, rgba(34, 211, 238, 0.10) 0%, rgba(34, 211, 238, 0) 30%),
                linear-gradient(180deg, #172234 0%, #101827 100%) !important;
            border: 1px solid rgba(96, 165, 250, 0.18) !important;
            box-shadow:
                inset 0 1px 0 rgba(255,255,255,0.03),
                0 18px 40px rgba(0,0,0,0.28) !important;
            backdrop-filter: blur(14px);
            min-height: 100%;
        }

        .prob-box::after {
            content: "";
            position: absolute;
            right: -48px;
            top: -48px;
            width: 140px;
            height: 140px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(59, 130, 246, 0.18) 0%, rgba(59, 130, 246, 0) 72%);
            pointer-events: none;
        }

        .prob-label {
            color: #93A4C3 !important;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .prob-value {
            color: #FFF9EE;
            font-size: 36px;
            font-weight: 900;
            line-height: 1;
            margin-top: 10px;
            text-shadow: 0 1px 12px rgba(244, 197, 106, 0.10);
        }

        .prob-sub {
            color: rgba(255, 249, 238, 0.82);
            font-size: 14px;
            line-height: 1.6;
            margin-top: 10px;
            max-width: 28ch;
        }

        .prob-meter {
            height: 10px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(255, 237, 201, 0.08);
            border: 1px solid rgba(255, 215, 128, 0.10);
            margin-top: 14px;
            position: relative;
            z-index: 1;
        }

        .prob-meter-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #E7B95E 0%, #F6D365 100%);
            box-shadow: 0 0 18px rgba(246, 211, 101, 0.24);
        }

        .impact-meter, .row-meter, .impact-bar-wrap, .catalyst-meter {
            background: rgba(255,255,255,.08);
            height: 10px;
        }

        .stTabs [data-baseweb="tab-list"] {
            position: sticky;
            top: 0.6rem;
            z-index: 5;
            background: rgba(9, 16, 29, 0.78) !important;
            border: 1px solid rgba(255,255,255,.08) !important;
            backdrop-filter: blur(16px);
            box-shadow: 0 18px 42px rgba(0,0,0,.26) !important;
        }

        .stTabs [data-baseweb="tab-list"]::before {
            content: "Ticker workspaces";
            color: #8fa0bc !important;
        }

        .stTabs [data-baseweb="tab"] {
            background: rgba(255,255,255,.04) !important;
            border: 1px solid rgba(255,255,255,.08) !important;
            color: #cfd7ea !important;
            box-shadow: none !important;
            transition: transform .18s ease, border-color .18s ease, background .18s ease;
        }

        .stTabs [data-baseweb="tab"]:hover {
            background: rgba(255,255,255,.06) !important;
            border-color: rgba(122,149,255,.24) !important;
            box-shadow: 0 12px 22px rgba(0,0,0,.16) !important;
        }

        .stTabs [aria-selected="true"] {
            background:
                radial-gradient(circle at top left, rgba(84,214,255,.14) 0%, rgba(84,214,255,0) 26%),
                linear-gradient(180deg, rgba(34, 50, 88, 0.98) 0%, rgba(14, 24, 44, 0.98) 100%) !important;
            border-color: rgba(122,149,255,.30) !important;
            box-shadow: 0 14px 28px rgba(0,0,0,.22), inset 0 -2px 0 rgba(84,214,255,.72) !important;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(18, 28, 46, 0.92) 0%, rgba(12, 19, 33, 0.96) 100%) !important;
            border: 1px solid rgba(255,255,255,.08) !important;
            box-shadow: 0 14px 30px rgba(0,0,0,.18) !important;
            min-height: 122px;
        }

        div[data-testid="stMetricLabel"] > div,
        div[data-testid="stMetricLabel"] label,
        [data-testid="stMetricLabel"] {
            color: #90a0ba !important;
        }

        div[data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] {
            color: #f8fbff !important;
        }

        div[data-testid="stMetricDelta"] > div,
        [data-testid="stMetricDelta"] {
            color: #7dd7ff !important;
        }

        .stDataFrame, div[data-testid="stDataFrame"] {
            background: rgba(10, 16, 29, 0.88) !important;
            border: 1px solid rgba(255,255,255,.08) !important;
            box-shadow: 0 18px 42px rgba(0,0,0,.22) !important;
        }

        div[data-testid="stDataFrame"] * {
            color: #dbe4f5 !important;
        }

        .element-container iframe {
            border-radius: 20px;
        }

        .footer-note, .disclaimer {
            color: #8999b2 !important;
        }

        .story-stream-shell {
            display: none;
        }

        a.inline-link, .brief-link {
            color: #7dd7ff !important;
        }

        a.inline-link:hover, .brief-link:hover {
            color: #b6ebff !important;
        }

        @media (max-width: 980px) {
            .hero-title {
                font-size: 32px !important;
            }
            .lead-title {
                font-size: 24px !important;
            }
        }

        @media (max-width: 768px) {
            .stTabs [data-baseweb="tab-list"] {
                top: 0.25rem;
            }
            .hero-title, .guide-title, .reference-title, .compare-title,
            .winner-title, .catalyst-title, .alert-title, .lab-title,
            .trend-title, .explorer-nav-title {
                font-size: 22px !important;
            }
            .top-intro, .hero-copy, .guide-copy, .reference-copy, .lens-copy,
            .compare-copy, .winner-copy, .catalyst-copy, .alert-copy, .lab-copy,
            .trend-sub, .chart-copy, .explorer-nav-copy {
                font-size: 13px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )




SAFE_HTML_WRAPPER_EXACT = {
    '</div>',
    '<div></div>',
    '<div class="planner-stack-spacer"></div>',
    '<div class="candlestick-section-spacer"></div>',
    '<div class="group-stack-divider"></div>',
}

SAFE_HTML_WRAPPER_PREFIXES = (
    '<div class="section-expander-wrap',
    '<div class="planner-expander-wrap',
)

SAFE_HTML_LEADING_STRIP_CLASSES = (
    'lead-story-board',
    'target-watch-board',
    'brief-grid',
    'compare-table-body',
    'planner-expander-badge-row',
)

def _is_wrapper_only_html(fragment: str) -> bool:
    probe = textwrap.dedent(str(fragment)).strip()
    if not probe:
        return True
    if probe in SAFE_HTML_WRAPPER_EXACT:
        return True
    if any(probe.startswith(prefix) and probe.endswith('>') and '</div>' not in probe for prefix in SAFE_HTML_WRAPPER_PREFIXES):
        return True
    return False

def _strip_known_wrapper_tokens(html: str) -> str:
    cleaned = textwrap.dedent(str(html)).strip()
    if not cleaned:
        return ""

    lines = [line.rstrip() for line in cleaned.splitlines()]
    while lines and _is_wrapper_only_html(lines[0]):
        lines.pop(0)
    while lines and _is_wrapper_only_html(lines[-1]):
        lines.pop()

    cleaned = "\n".join(lines).strip()
    if not cleaned:
        return ""

    # Only strip unmatched leading closing tags when the real block is one of our known safe roots.
    safe_root_pattern = "|".join(re.escape(cls) for cls in SAFE_HTML_LEADING_STRIP_CLASSES)
    cleaned = re.sub(
        rf"^(?:\s*</div>\s*)+(?=<div class=\"(?:{safe_root_pattern})\")",
        "",
        cleaned,
        flags=re.DOTALL,
    ).strip()

    # Strip standalone opening wrappers only when they are the entire remaining fragment.
    if any(cleaned.startswith(prefix) and cleaned.endswith('>') and '</div>' not in cleaned for prefix in SAFE_HTML_WRAPPER_PREFIXES):
        return ""

    return cleaned

def render_html_block(html: str):
    if html is None:
        return

    cleaned = _strip_known_wrapper_tokens(html)
    if not cleaned:
        return

    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def render_expander_meta(section: str, item_count: int | None, helper_base: str):
    helper_text = planner_expander_helper(helper_base, section, item_count)
    meta_html = (
        '<div class="planner-expander-meta">'
        + planner_expander_badges(section, item_count)
        + f'<div class="planner-expander-helper">{escape(helper_text)}</div>'
        + '</div>'
    )
    render_html_block(meta_html)

# ---------------------------
# Data Fetch
# ---------------------------
@st.cache_data(ttl=300)
def fetch_daily_data(tickers: list[str], period: str, interval: str):
    return yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=True,
        prepost=False,
    )


@st.cache_data(ttl=120)
def fetch_intraday_data(tickers: list[str]):
    return yf.download(
        tickers=tickers,
        period=INTRADAY_PERIOD,
        interval=INTRADAY_INTERVAL,
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=True,
        prepost=True,
    )


@st.cache_data(ttl=600)
def fetch_ticker_news(ticker: str, max_items: int = 12):
    raw_news = []
    last_error = None
    news_candidates = [ticker]
    base_code = ticker_base_code(ticker)
    if is_taiwan_ticker(ticker) and base_code != str(ticker).upper():
        news_candidates.append(base_code)

    for candidate in news_candidates:
        try:
            tk = yf.Ticker(candidate)
            try:
                raw_news = tk.news or []
            except Exception:
                raw_news = tk.get_news() or []
            if raw_news:
                break
        except Exception as e:
            last_error = e

    if raw_news is None:
        raw_news = []

    items = []
    ticker_upper = str(ticker).upper()
    news_aliases = build_news_aliases(ticker_upper)

    for item in raw_news:
        if not isinstance(item, dict):
            continue

        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        title = content.get("title") or item.get("title") or "Untitled"
        summary = content.get("summary") or item.get("summary") or ""
        provider_dict = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        provider = provider_dict.get("displayName") or item.get("publisher") or item.get("provider") or "Unknown source"

        canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
        clickthrough = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
        url = canonical.get("url") or clickthrough.get("url") or item.get("link") or item.get("url")

        published_raw = content.get("pubDate") or item.get("providerPublishTime") or item.get("published")
        published_ts = pd.NaT
        if published_raw is not None:
            try:
                if isinstance(published_raw, (int, float)):
                    published_ts = pd.to_datetime(published_raw, unit="s", utc=True)
                else:
                    published_ts = pd.to_datetime(published_raw, utc=True)
            except Exception:
                published_ts = pd.NaT

        related = []
        for key in ("relatedTickers", "tickers", "symbols"):
            candidate = content.get(key) if key in content else item.get(key)
            if isinstance(candidate, list):
                related.extend([str(x).upper() for x in candidate])

        relevance = score_news_relevance(title, summary, related, news_aliases)
        impact_label, impact_score, impact_reason = infer_news_impact(title, summary)
        confidence = infer_news_confidence(relevance, impact_score)

        items.append({
            "title": title,
            "summary": summary,
            "provider": provider,
            "url": url,
            "published": published_ts,
            "related": related,
            "relevance": relevance,
            "impact_label": impact_label,
            "impact_score": impact_score,
            "impact_reason": impact_reason,
            "confidence": confidence,
            "source_origin": "yahoo",
        })

    local_tw_items = fetch_taiwan_local_news(ticker, max_items=max_items * 2) if is_taiwan_ticker(ticker) else []
    merged_items = dedupe_news_items(local_tw_items + items, max_items=max_items * 3)
    filtered_items = [x for x in merged_items if x.get("relevance", 0) > 0]

    if last_error and not merged_items:
        return [], f"News unavailable for {display_ticker_label(ticker)}: {last_error}"
    return (filtered_items or merged_items)[:max_items], None


# ---------------------------
# Helpers
# ---------------------------
def get_series(data: pd.DataFrame | None, field: str, ticker: str):
    if data is None or data.empty:
        return None
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if (field, ticker) in data.columns:
                return data[(field, ticker)].dropna()
            if (ticker, field) in data.columns:
                return data[(ticker, field)].dropna()
            if field in data.columns.get_level_values(0):
                sub = data[field]
                if isinstance(sub, pd.DataFrame) and ticker in sub.columns:
                    return sub[ticker].dropna()
            if ticker in data.columns.get_level_values(0):
                sub = data[ticker]
                if isinstance(sub, pd.DataFrame) and field in sub.columns:
                    return sub[field].dropna()
            return None
        if field in data.columns:
            series = data[field]
            if isinstance(series, pd.DataFrame):
                if ticker in series.columns:
                    return series[ticker].dropna()
                return None
            return series.dropna()
        return None
    except Exception:
        return None


def get_price_series(data: pd.DataFrame | None, ticker: str):
    for field in PRICE_FIELDS_PRIORITY:
        s = get_series(data, field, ticker)
        if s is not None and not s.empty:
            return ensure_datetime_index(s), field
    return None, None


def ensure_datetime_index(series: pd.Series | None):
    if series is None or series.empty:
        return series
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s


def localize_timestamp(ts):
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        return ts.tz_localize(US_TZ)
    return ts.tz_convert(US_TZ)


def format_us_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return "N/A"
    return localize_timestamp(ts).strftime("%Y-%m-%d %H:%M %Z")


def format_tw_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return "N/A"
    return localize_timestamp(ts).tz_convert(TW_TZ).strftime("%Y-%m-%d %H:%M %Z")


def format_price(value):
    if pd.isna(value):
        return "N/A"
    return f"${value:,.2f}"


def format_percent(value):
    if pd.isna(value):
        return "N/A"
    return f"{value:+.2f}%"


def rsi_signal(rsi_value):
    if pd.isna(rsi_value):
        return "N/A"
    if rsi_value >= 70:
        return "Overbought"
    if rsi_value <= 30:
        return "Oversold"
    if rsi_value >= 55:
        return "Bullish Momentum"
    if rsi_value <= 45:
        return "Weak Momentum"
    return "Neutral"


def trend_label(one_year_return):
    if pd.isna(one_year_return):
        return "N/A"
    if one_year_return >= 25:
        return "Strong Uptrend"
    if one_year_return > 0:
        return "Moderate Uptrend"
    if one_year_return <= -20:
        return "Strong Downtrend"
    if one_year_return < 0:
        return "Mild Downtrend"
    return "Flat"



def to_numeric_series(series: pd.Series | None, *, keep_index: bool = True):
    if series is None:
        return pd.Series(dtype="float64")
    s = series.copy() if isinstance(series, pd.Series) else pd.Series(series)
    if keep_index:
        try:
            s = ensure_datetime_index(s)
        except Exception:
            pass
    return pd.to_numeric(s, errors="coerce")


def empty_analysis_payload(ticker: str, indicators: pd.DataFrame | None = None, news_items: list[dict] | None = None):
    indicators = indicators if indicators is not None else pd.DataFrame()
    news_pulse = build_news_pulse(news_items or [])
    return {
        "signal": "HOLD",
        "confidence": "Low",
        "score": 0,
        "summary": "Data is limited right now, so the dashboard is staying neutral until cleaner price history is available.",
        "reasons": ["Price history is incomplete or non-numeric, so advanced indicators were safely skipped."],
        "trend": "N/A",
        "one_year_return": pd.NA,
        "rsi14": pd.NA,
        "rsi_status": "N/A",
        "last_price": pd.NA,
        "sma20": pd.NA,
        "sma50": pd.NA,
        "sma200": pd.NA,
        "indicators": indicators,
        "latest_daily_ts": indicators.index[-1] if not indicators.empty else None,
        "volume_status": "N/A",
        "news_pulse": news_pulse,
        "ticker": ticker,
    }


def calculate_rsi(series: pd.Series, period: int = 14):
    price = to_numeric_series(series).dropna()
    if price.empty or len(price) < period + 1:
        return pd.Series(dtype="float64")

    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    zero_gain = avg_gain.eq(0)
    zero_loss = avg_loss.eq(0)

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    rsi = rsi.mask(zero_loss & ~zero_gain, 100.0)
    rsi = rsi.mask(zero_gain & ~zero_loss, 0.0)
    rsi = rsi.mask(zero_gain & zero_loss, 50.0)

    return pd.to_numeric(rsi, errors="coerce")

def build_indicator_frame(price_series: pd.Series):
    price_series = to_numeric_series(price_series)
    if price_series.empty:
        return pd.DataFrame(columns=["Price", "SMA 20", "SMA 50", "SMA 200", "RSI 14", "1Y Return %"])

    df = pd.DataFrame({"Price": price_series.copy()})
    df["SMA 20"] = price_series.rolling(20, min_periods=20).mean()
    df["SMA 50"] = price_series.rolling(50, min_periods=50).mean()
    df["SMA 200"] = price_series.rolling(200, min_periods=200).mean()
    df["RSI 14"] = calculate_rsi(price_series)

    valid_price = price_series.dropna()
    base_price = valid_price.iloc[0] if not valid_price.empty else np.nan
    if pd.notna(base_price) and base_price != 0:
        df["1Y Return %"] = ((price_series / base_price) - 1.0) * 100.0
    else:
        df["1Y Return %"] = np.nan

    return df

def get_ohlc_frame(data: pd.DataFrame | None, ticker: str, tail: int | None = None):
    open_series = get_series(data, "Open", ticker)
    high_series = get_series(data, "High", ticker)
    low_series = get_series(data, "Low", ticker)
    close_series, _ = get_price_series(data, ticker)

    if open_series is None or high_series is None or low_series is None or close_series is None:
        return pd.DataFrame()

    frame = pd.concat(
        [
            ensure_datetime_index(open_series),
            ensure_datetime_index(high_series),
            ensure_datetime_index(low_series),
            ensure_datetime_index(close_series),
        ],
        axis=1,
    )
    frame.columns = ["Open", "High", "Low", "Close"]
    frame = frame.dropna()

    if frame.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close"])

    frame = frame.reset_index()

    # The index column can be named Date, Datetime, index, or something else.
    first_col = frame.columns[0]
    if first_col != "Date":
        frame = frame.rename(columns={first_col: "Date"})

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])

    if tail is not None:
        frame = frame.tail(tail).copy()

    return frame


def render_candlestick_chart(ohlc: pd.DataFrame, title: str, subtitle: str = "", height: int = 420, show_ma: bool = False):
    if ohlc is None or ohlc.empty:
        st.info("Chart data is not available.")
        return

    chart_df = ohlc.copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])
    chart_df["Up"] = chart_df["Close"] >= chart_df["Open"]
    chart_df["Color"] = chart_df["Up"].map({True: "#19c37d", False: "#ff5b5b"})

    if show_ma:
        chart_df["SMA 20"] = chart_df["Close"].rolling(20).mean()
        chart_df["SMA 50"] = chart_df["Close"].rolling(50).mean()

    st.markdown(
        f"""
        <div class="chart-shell">
            <div class="chart-title">{escape(title)}</div>
            <div class="chart-copy">{escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    base = alt.Chart(chart_df).encode(
        x=alt.X(
            "Date:T",
            axis=alt.Axis(
                title=None,
                labelColor="#c9d4f0",
                grid=False,
                tickColor="#334155",
                domainColor="rgba(201,212,240,0.18)",
                labelPadding=10,
            ),
        ),
        tooltip=[
            alt.Tooltip("Date:T", title="Date"),
            alt.Tooltip("Open:Q", format=",.2f"),
            alt.Tooltip("High:Q", format=",.2f"),
            alt.Tooltip("Low:Q", format=",.2f"),
            alt.Tooltip("Close:Q", format=",.2f"),
        ],
    )

    wick = base.mark_rule(strokeWidth=1.3).encode(
        y=alt.Y(
            "Low:Q",
            axis=alt.Axis(
                title=None,
                labelColor="#c9d4f0",
                gridColor="rgba(201,212,240,0.12)",
                domain=False,
                tickColor="#334155",
            ),
        ),
        y2="High:Q",
        color=alt.Color("Color:N", scale=None, legend=None),
    )

    body = base.mark_bar(size=7).encode(
        y=alt.Y(
            "Open:Q",
            axis=alt.Axis(
                title=None,
                labelColor="#c9d4f0",
                gridColor="rgba(201,212,240,0.12)",
                domain=False,
                tickColor="#334155",
            ),
        ),
        y2="Close:Q",
        color=alt.Color("Color:N", scale=None, legend=None),
    )

    layers = [wick, body]

    if show_ma:
        sma20 = base.mark_line(color="#7cc7ff", strokeWidth=1.6).encode(y="SMA 20:Q")
        sma50 = base.mark_line(color="#f3b94d", strokeWidth=1.6).encode(y="SMA 50:Q")
        layers.extend([sma20, sma50])

    chart = (
        alt.layer(*layers)
        .resolve_scale(y="shared")
        .properties(height=height)
        .configure(background="#0f172a")
        .configure_view(stroke=None, fill="#0f172a")
        .configure_axis(
            domain=False,
            labelFont="Inter",
            titleFont="Inter",
            labelColor="#c9d4f0",
            gridColor="rgba(201,212,240,0.12)",
        )
    )

    st.altair_chart(chart, use_container_width=True)


def get_intraday_snapshot(intraday_data: pd.DataFrame | None, ticker: str):
    price_series, field_name = get_price_series(intraday_data, ticker)
    volume_series = get_series(intraday_data, "Volume", ticker)
    if price_series is None or price_series.empty:
        return {
            "available": False,
            "last_price": pd.NA,
            "change_pct": pd.NA,
            "timestamp": None,
            "field_name": "N/A",
            "volume": pd.NA,
            "chart": pd.DataFrame(),
        }
    latest_ts = price_series.index[-1]
    last_price = price_series.iloc[-1]
    prev_price = price_series.iloc[-2] if len(price_series) >= 2 else pd.NA
    change_pct = ((last_price / prev_price) - 1) * 100 if pd.notna(prev_price) and prev_price != 0 else pd.NA
    chart = pd.DataFrame({"Intraday Price": price_series.tail(78)})
    return {
        "available": True,
        "last_price": last_price,
        "change_pct": change_pct,
        "timestamp": latest_ts,
        "field_name": field_name,
        "volume": volume_series.iloc[-1] if volume_series is not None and not volume_series.empty else pd.NA,
        "chart": chart,
    }


def infer_news_impact(title: str, summary: str = ""):
    text = f"{title} {summary}".lower()
    pos = sum(1 for kw in POSITIVE_NEWS_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_NEWS_KEYWORDS if kw in text)
    score = pos - neg

    if score >= 2:
        return "Likely bullish", score, "Headline language leans positive for demand, margins, upgrades, or growth."
    if score <= -2:
        return "Likely bearish", score, "Headline language leans negative for guidance, regulation, demand, or execution risk."
    if score > 0:
        return "Mildly bullish", score, "Some positive wording is present, but the signal is not strong."
    if score < 0:
        return "Mildly bearish", score, "Some negative wording is present, but the signal is not strong."
    return "Neutral / mixed", score, "The headline is informational or the signals conflict."


def infer_news_confidence(relevance: int, impact_score: int):
    strength = abs(impact_score)
    total = relevance + strength
    if total >= 6:
        return "High"
    if total >= 3:
        return "Medium"
    return "Low"


def build_news_pulse(news_items: list[dict]):
    if not news_items:
        return {"score": 0.0, "label": "Flat", "up": 0, "down": 0, "neutral": 0}
    weighted = 0.0
    up = down = neutral = 0
    for item in news_items:
        weight = 1 + min(item.get("relevance", 0), 4) * 0.25
        score = item.get("impact_score", 0)
        weighted += score * weight
        label = item.get("impact_label", "Neutral / mixed")
        if "bullish" in label.lower():
            up += 1
        elif "bearish" in label.lower():
            down += 1
        else:
            neutral += 1
    avg = weighted / max(len(news_items), 1)
    if avg >= 1.4:
        label = "News tilt: bullish"
    elif avg <= -1.4:
        label = "News tilt: bearish"
    else:
        label = "News tilt: mixed"
    return {"score": avg, "label": label, "up": up, "down": down, "neutral": neutral}




CATALYST_KEYWORDS = {
    "Earnings": {"earnings", "revenue", "guidance", "eps", "beat", "miss", "forecast", "quarter", "margin"},
    "AI Demand": {"ai", "gpu", "data center", "chips", "accelerator", "server", "inference", "training", "demand"},
    "Regulation": {"regulation", "regulator", "antitrust", "probe", "ban", "export", "tariff", "lawsuit", "fine"},
    "Macro": {"inflation", "rates", "fed", "economy", "macro", "cpi", "ppi", "jobs", "treasury", "recession"},
    "Analyst Action": {"upgrade", "downgrade", "price target", "outperform", "underperform", "buy rating", "sell rating"},
    "Supply Chain": {"supply", "shipment", "capacity", "factory", "shortage", "inventory", "lead time", "wafer", "production"},
}


def classify_catalyst(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('impact_reason','')}".lower()
    scores = {}
    for category, keywords in CATALYST_KEYWORDS.items():
        scores[category] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get) if scores else "Macro"
    return best if scores.get(best, 0) > 0 else "Macro"


def build_catalyst_engine(news_items: list[dict]) -> dict:
    categories = {name: {"count": 0, "score": 0.0} for name in CATALYST_KEYWORDS}
    if not news_items:
        return {
            "dominant": "Macro",
            "net_score": 0.0,
            "rows": [],
            "headline": "Catalysts are light and mixed.",
            "turning_point": "No strong category is dominating current news flow.",
        }

    for item in news_items:
        category = classify_catalyst(item)
        weight = 1 + min(int(item.get("relevance", 0)), 4) * 0.25
        impact = float(item.get("impact_score", 0))
        categories[category]["count"] += 1
        categories[category]["score"] += impact * weight

    rows = []
    for category, values in categories.items():
        count = values["count"]
        score = values["score"]
        bias = "Bullish" if score > 0.4 else "Bearish" if score < -0.4 else "Mixed"
        intensity = min(100, int(abs(score) * 18 + count * 10)) if count else 8
        rows.append({
            "category": category,
            "count": count,
            "score": score,
            "bias": bias,
            "intensity": intensity,
        })

    rows.sort(key=lambda row: (row["count"], abs(row["score"])), reverse=True)
    dominant = rows[0]["category"] if rows else "Macro"
    net_score = sum(row["score"] for row in rows)

    if net_score >= 2:
        headline = f"{dominant} is the main upside catalyst right now."
    elif net_score <= -2:
        headline = f"{dominant} is the main pressure point right now."
    else:
        headline = f"{dominant} is active, but the broader catalyst mix is still balanced."

    turning_point = {
        "Earnings": "Watch whether the next report confirms or breaks the current narrative.",
        "AI Demand": "Demand commentary can quickly accelerate momentum in semis and infrastructure names.",
        "Regulation": "Policy or legal headlines can shift valuation fast even without a change in operations.",
        "Macro": "Rate and inflation sensitivity can overpower stock-specific news in the short term.",
        "Analyst Action": "Analyst revisions often act as short, sharp catalyst bursts rather than long trends.",
        "Supply Chain": "Shipment, inventory, and capacity updates often show up in margins before price follows.",
    }.get(dominant, "The catalyst picture is mixed.")

    return {
        "dominant": dominant,
        "net_score": net_score,
        "rows": rows,
        "headline": headline,
        "turning_point": turning_point,
    }


def calculate_macd(series: pd.Series):
    s = to_numeric_series(series).dropna()
    if s.empty:
        empty = pd.Series(dtype="float64")
        return empty, empty, empty

    ema12 = s.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = s.ewm(span=26, adjust=False, min_periods=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd_line - signal_line

    return (
        pd.to_numeric(macd_line, errors="coerce"),
        pd.to_numeric(signal_line, errors="coerce"),
        pd.to_numeric(hist, errors="coerce"),
    )

def build_trading_lab(price_series: pd.Series, volume_series: pd.Series | None) -> dict:
    series = to_numeric_series(price_series).dropna()
    if series.empty:
        return {}

    macd_line, signal_line, hist = calculate_macd(series)
    sma20 = series.rolling(20, min_periods=20).mean()
    std20 = series.rolling(20, min_periods=20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20

    last_price = series.iloc[-1]
    tail20 = series.tail(20)
    support = tail20.nsmallest(min(3, len(tail20))).mean() if not tail20.empty else np.nan
    resistance = tail20.nlargest(min(3, len(tail20))).mean() if not tail20.empty else np.nan

    tags = []
    if not upper.empty and pd.notna(upper.iloc[-1]) and last_price > upper.iloc[-1]:
        tags.append("Breakout stretch")
    elif not lower.empty and pd.notna(lower.iloc[-1]) and last_price < lower.iloc[-1]:
        tags.append("Breakdown risk")
    elif not sma20.empty and pd.notna(sma20.iloc[-1]) and pd.notna(support) and last_price < sma20.iloc[-1] and last_price > support:
        tags.append("Pullback zone")
    else:
        tags.append("Trend continuation")

    hist_valid = hist.dropna()
    if len(hist_valid) >= 2:
        if hist_valid.iloc[-1] > 0 and hist_valid.iloc[-1] > hist_valid.iloc[-2]:
            tags.append("MACD improving")
        elif hist_valid.iloc[-1] < 0 and hist_valid.iloc[-1] < hist_valid.iloc[-2]:
            tags.append("MACD weakening")

    volume_ratio = pd.NA
    if volume_series is not None and not volume_series.empty:
        vol = to_numeric_series(volume_series).dropna()
        if not vol.empty:
            avg50 = vol.tail(50).mean()
            if pd.notna(avg50) and avg50 != 0:
                volume_ratio = vol.iloc[-1] / avg50
                if volume_ratio >= 1.3:
                    tags.append("Volume confirmation")
                elif volume_ratio <= 0.8:
                    tags.append("Light volume")

    setup = "Balanced"
    if len([t for t in tags if t in ("Trend continuation", "MACD improving", "Volume confirmation")]) >= 2:
        setup = "Momentum-led"
    elif "Pullback zone" in tags:
        setup = "Pullback watch"
    elif "Breakdown risk" in tags or "MACD weakening" in tags:
        setup = "Risk-off"

    bb_upper = upper.iloc[-1] if not upper.empty else pd.NA
    bb_mid = sma20.iloc[-1] if not sma20.empty else pd.NA
    bb_lower = lower.iloc[-1] if not lower.empty else pd.NA
    macd_last = macd_line.dropna().iloc[-1] if not macd_line.dropna().empty else pd.NA
    signal_last = signal_line.dropna().iloc[-1] if not signal_line.dropna().empty else pd.NA
    hist_last = hist_valid.iloc[-1] if not hist_valid.empty else pd.NA

    return {
        "macd": macd_last,
        "macd_signal": signal_last,
        "macd_hist": hist_last,
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        "support": support,
        "resistance": resistance,
        "volume_ratio": volume_ratio,
        "setup": setup,
        "tags": tags,
    }

def enrich_pro_analysis(analysis: dict, price_series: pd.Series, volume_series: pd.Series | None, news_items: list[dict], active_lens_title: str | None = None, intraday: dict | None = None) -> dict:
    catalyst = build_catalyst_engine(news_items)
    trading_lab = build_trading_lab(price_series, volume_series)

    pro_score = analysis["score"]
    if catalyst["net_score"] >= 2:
        pro_score += 1
    elif catalyst["net_score"] <= -2:
        pro_score -= 1

    tags = []
    for tag in trading_lab.get("tags", []):
        if "Breakout" in tag or "improving" in tag or "confirmation" in tag:
            tags.append(("up", tag))
        elif "Breakdown" in tag or "weakening" in tag:
            tags.append(("down", tag))
        else:
            tags.append(("neutral", tag))

    alerts = []
    if analysis["signal"] == "HOLD" and pro_score >= 4:
        alerts.append("Setup is close to flipping from HOLD to BUY.")
    if analysis["signal"] == "BUY" and catalyst["net_score"] < -1.5:
        alerts.append("News pulse is deteriorating against the bullish trend.")
    if analysis["signal"] == "SELL" and trading_lab.get("setup") == "Pullback watch":
        alerts.append("Selling pressure is still present, but a reactive bounce zone is forming.")
    if abs(catalyst["net_score"]) >= 3:
        alerts.append(f"{catalyst['dominant']} headlines are now a major directional driver.")

    analysis["catalyst_engine"] = catalyst
    analysis["trading_lab"] = trading_lab
    analysis["pro_tags"] = tags
    analysis["alerts"] = alerts
    analysis["pro_score"] = pro_score
    analysis["active_lens_title"] = active_lens_title or "Position View"
    analysis["lens_alerts"] = build_lens_alerts(analysis, intraday or {})
    return analysis


def render_catalyst_engine(analysis: dict, ticker: str):
    catalyst = analysis.get("catalyst_engine", {})
    rows = catalyst.get("rows", [])[:6]
    if not rows:
        return
    rows_html = ""
    for row in rows:
        rows_html += f"""
        <div class="catalyst-row">
            <div>
                <div class="catalyst-label">{escape(row['category'])}</div>
                <div class="catalyst-sub">{escape(row['bias'])} · {row['count']} stories</div>
            </div>
            <div class="catalyst-meter"><div class="catalyst-meter-fill" style="width:{row['intensity']}%;"></div></div>
            <div class="catalyst-sub" style="text-align:right;">{row['score']:+.1f}</div>
        </div>
        """
    st.markdown(
        f"""
        <div class="catalyst-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">Catalyst Engine</div>
            <div class="catalyst-title">{escape(catalyst.get('headline', 'Catalysts are mixed.'))}</div>
            <div class="catalyst-copy">{escape(catalyst.get('turning_point', ''))}</div>
            <div class="catalyst-grid">
                <div class="catalyst-box">
                    <div class="catalyst-label">Dominant category</div>
                    <div class="catalyst-value">{escape(catalyst.get('dominant', 'Macro'))}</div>
                    <div class="catalyst-sub">Net catalyst score {catalyst.get('net_score', 0):+.1f}</div>
                </div>
                <div class="catalyst-box">
                    <div class="catalyst-label">Current pulse</div>
                    <div class="catalyst-value">{escape(analysis['news_pulse']['label'])}</div>
                    <div class="catalyst-sub">Grouped into earnings, AI demand, regulation, macro, analyst action, and supply chain.</div>
                </div>
            </div>
            <div style="margin-top:14px;">{rows_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trading_lab_panel(analysis: dict):
    lab = analysis.get("trading_lab", {})
    if not lab:
        return
    tag_html = ""
    for kind, tag in analysis.get("pro_tags", []):
        cls = "pro-tag-up" if kind == "up" else "pro-tag-down" if kind == "down" else "pro-tag-neutral"
        tag_html += f'<span class="pro-tag {cls}">{escape(tag)}</span>'
    st.markdown(
        f"""
        <div class="lab-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">Trading Lab</div>
            <div class="lab-title">{escape(lab.get('setup', 'Balanced'))} setup</div>
            <div class="lab-copy">MACD, Bollinger Bands, volume confirmation, and support/resistance are combined here to frame the current trade structure.</div>
            <div class="lab-grid">
                <div class="lab-box">
                    <div class="lab-label">MACD</div>
                    <div class="lab-value">{lab.get('macd', 0):+.2f}</div>
                    <div class="lab-sub">Signal {lab.get('macd_signal', 0):+.2f} · Hist {lab.get('macd_hist', 0):+.2f}</div>
                </div>
                <div class="lab-box">
                    <div class="lab-label">Bollinger Bands</div>
                    <div class="lab-value">{format_price(lab.get('bb_mid', pd.NA))}</div>
                    <div class="lab-sub">Upper {format_price(lab.get('bb_upper', pd.NA))} · Lower {format_price(lab.get('bb_lower', pd.NA))}</div>
                </div>
                <div class="lab-box">
                    <div class="lab-label">Support / Resistance</div>
                    <div class="lab-value">{format_price(lab.get('support', pd.NA))}</div>
                    <div class="lab-sub">Resistance {format_price(lab.get('resistance', pd.NA))}</div>
                </div>
                <div class="lab-box">
                    <div class="lab-label">Volume ratio</div>
                    <div class="lab-value">{"N/A" if pd.isna(lab.get('volume_ratio', pd.NA)) else f"{lab.get('volume_ratio'):.2f}x"}</div>
                    <div class="lab-sub">Latest volume versus the 50-period average.</div>
                </div>
            </div>
            <div class="tag-row">{tag_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def resolve_trend_lens(lens_name: str, manual_override: bool, manual_period: str, manual_interval: str):
    if manual_override:
        return {
            "title": "Custom Lens",
            "hook": "Manual view for special cases.",
            "how_to_read": f"Custom chart using {manual_period} at {manual_interval} resolution.",
            "watch_for": "Use this when you already know the exact timeframe you want to inspect.",
            "period": manual_period,
            "interval": manual_interval,
        }
    return TREND_LENSES.get(lens_name, TREND_LENSES[DEFAULT_TREND_LENS])


def render_active_trend_lens(lens_meta: dict):
    lens_meta = tr_lens_meta(lens_meta)
    st.markdown(
        f"""
        <div class="lens-shell">
            <div class="section-header" style="margin:0;">{t('trend_lens')}</div>
            <div class="lens-title">{escape(lens_meta.get('title', t('trend_lens')))}</div>
            <div class="lens-copy">{escape(lens_meta.get('hook', ''))}</div>
            <div class="lens-grid">
                <div class="lens-card">
                    <div class="lens-label">{t('best_use')}</div>
                    <div class="lens-head">{escape(lens_meta.get('title', t('trend_lens')))}</div>
                    <div class="lens-sub">{escape(lens_meta.get('hook', ''))}</div>
                </div>
                <div class="lens-card">
                    <div class="lens-label">{t('how_to_read_it')}</div>
                    <div class="lens-head">{t('what_this_lens_good_at')}</div>
                    <div class="lens-sub">{escape(lens_meta.get('how_to_read', ''))}</div>
                </div>
                <div class="lens-card">
                    <div class="lens-label">{t('watch_for')}</div>
                    <div class="lens-head">{t('most_useful_reference_points')}</div>
                    <div class="lens-sub">{escape(lens_meta.get('watch_for', ''))}</div>
                </div>
            </div>
            <div class="lens-copy" style="margin-top:12px;">{t('winner_card_adapts')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_explore_hero():
    st.markdown(
        f"""
        <div class="editorial-hero">
            <div class="hero-kicker">{t('command_layer')}</div>
            <div class="hero-title">{t('hero_title')}</div>
            <div class="hero-copy">{t('hero_copy')}</div>
            <div class="hero-chip-row">
                <span class="hero-chip">{t('chip_news_flow')}</span>
                <span class="hero-chip">{t('chip_winner')}</span>
                <span class="hero-chip">{t('chip_catalyst_guide')}</span>
                <span class="hero-chip">{t('chip_trading_lab')}</span>
                <span class="hero-chip">{t('chip_richer_journey')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_guide():
    st.markdown(
        f"""
        <div class="guide-shell">
            <div class="guide-title">{t('guide_title')}</div>
            <div class="guide-copy">{t('guide_copy')}</div>
            <div class="guide-grid">
                <div class="guide-card">
                    <div class="guide-label">{t('step_1')}</div>
                    <div class="guide-head">{t('comparison_arena')}</div>
                    <div class="guide-sub">{t('comparison_arena_copy')}</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">{t('step_2')}</div>
                    <div class="guide-head">{t('winner_card')}</div>
                    <div class="guide-sub">{t('winner_card_copy')}</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">{t('step_3')}</div>
                    <div class="guide-head">{t('catalyst_news_alerts')}</div>
                    <div class="guide-sub">{t('catalyst_news_alerts_copy')}</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">{t('step_4')}</div>
                    <div class="guide-head">{t('trading_lab_candles')}</div>
                    <div class="guide-sub">{t('trading_lab_candles_copy')}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_reference_guide(analysis: dict, ticker: str, news_items: list[dict]):
    lead = news_items[0] if news_items else {}
    catalyst = analysis.get('catalyst_engine', {})
    lab = analysis.get('trading_lab', {})
    st.markdown(
        f"""
        <div class="reference-shell">
            <div class="reference-title">{t("reference_guide_for", ticker=escape(display_ticker_label(ticker)))}</div>
            <div class="reference-copy">{t("reference_copy")}</div>
            <div class="reference-grid">
                <div class="reference-card">
                    <div class="reference-label">{t("what_to_watch_in_news")}</div>
                    <div class="reference-head">{escape(tr_term(catalyst.get('dominant', 'Macro')))}</div>
                    <div class="reference-sub">{escape(tr_term("This is the most active catalyst bucket right now. If new headlines keep leaning the same way, they can strengthen or weaken the current signal faster than technicals alone."))}</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">{t("what_gives_conviction")}</div>
                    <div class="reference-head">{escape(tr_confidence(analysis.get('confidence', 'Moderate')))}</div>
                    <div class="reference-sub">{escape(tr_term("Confidence comes from trend structure, news pulse, and trade setup aligning. When those disagree, the dashboard tends to fall back to HOLD."))}</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">{t("trading_lens")}</div>
                    <div class="reference-head">{escape(tr_setup(lab.get('setup', 'Balanced')))}</div>
                    <div class="reference-sub">{escape(tr_term("Use this as the action style: momentum-led means continuation is cleaner, pullback watch means patience matters, and risk-off means price can stay fragile."))}</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">{t("lead_story_context")}</div>
                    <div class="reference-head">{escape((lead.get('title') or tr_term('No strong lead story'))[:56])}</div>
                    <div class="reference-sub">{escape(tr_term("The lead story is the fastest narrative snapshot. Check whether its direction agrees with the Catalyst Engine before trusting it too much."))}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_news_highlights(ticker: str, news_items: list[dict]):
    if not news_items:
        return
    rows = []
    for item in news_items[:3]:
        label = item.get('impact_label', 'Neutral / mixed')
        cls = 'highlight-up' if 'bullish' in label.lower() else 'highlight-down' if 'bearish' in label.lower() else 'highlight-mixed'
        provider = escape(str(item.get('provider', 'Unknown source')))
        title = escape(item.get('title', 'Untitled'))
        reason = escape(item.get('impact_reason', ''))
        probability = article_probability(item)
        rows.append(f"""
        <div class="highlight-row">
            <div><span class="highlight-tag {cls}">{escape(label)}</span></div>
            <div>
                <div class="highlight-head">{title}</div>
                <div class="soft-note">{provider} · Why it matters to {escape(display_ticker_label(ticker))}: {reason}</div>
            </div>
            <div class="soft-note" style="text-align:right;"><strong style="font-size:18px; color:#ffffff;">{probability}%</strong><br>estimated effect</div>
        </div>
        """)
    st.markdown(
        f"""
        <div class="highlight-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">News Highlights Worth Exploring</div>
            <div class="highlight-copy">These are the most immediately relevant stories for the selected stock. Treat them as directional clues, then confirm them in the Catalyst Engine and Trading Lab.</div>
            <div style="margin-top:10px;">{''.join(rows)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def lens_signal_state(score: int) -> str:
    if score >= 5:
        return "bullish"
    if score <= -3:
        return "bearish"
    return "neutral"


def label_lens_state(state: str, lens_title: str) -> str:
    mapping = {
        "Fast Read": {"bullish": "Fast Read bullish", "bearish": "Fast Read bearish", "neutral": "Fast Read mixed"},
        "Swing Map": {"bullish": "Swing Map improving", "bearish": "Swing Map weakening", "neutral": "Swing Map balanced"},
        "Position View": {"bullish": "Position View intact", "bearish": "Position View broken", "neutral": "Position View mixed"},
        "Cycle View": {"bullish": "Cycle View leader", "bearish": "Cycle View laggard", "neutral": "Cycle View mixed"},
    }
    value = mapping.get(lens_title, {}).get(state, f"{lens_title} {state}")
    return tr_term(value)


def build_lens_alerts(analysis: dict, intraday: dict) -> dict:
    alerts = {}
    summaries = {}
    for lens_name, lens_meta in TREND_LENSES.items():
        adj, reasons = compute_lens_adjustment(analysis, intraday, lens_meta)
        base_score = analysis.get("pro_score", analysis.get("score", 0))
        lens_score = base_score + adj
        state = lens_signal_state(lens_score)
        label = label_lens_state(state, lens_meta["title"])
        alerts[lens_name] = {
            "title": lens_meta["title"],
            "score": lens_score,
            "state": state,
            "label": label,
            "reasons": reasons[:2],
        }
        summaries[lens_name] = label

    state_counts = {
        "bullish": sum(1 for item in alerts.values() if item["state"] == "bullish"),
        "bearish": sum(1 for item in alerts.values() if item["state"] == "bearish"),
        "neutral": sum(1 for item in alerts.values() if item["state"] == "neutral"),
    }

    if state_counts["bullish"] >= 3:
        headline = "Most lenses are leaning constructive."
    elif state_counts["bearish"] >= 3:
        headline = "Most lenses are leaning defensive."
    else:
        headline = "The lenses disagree, so context matters more."

    return {
        "headline": headline,
        "states": alerts,
        "counts": state_counts,
    }


def render_alert_layer(analysis: dict, intraday: dict):
    alert_map = analysis.get("lens_alerts", {})
    states = alert_map.get("states", {})
    counts = alert_map.get("counts", {})
    if not states:
        return

    active_title = analysis.get("active_lens_title", "Position View")
    active_state = states.get(active_title, next(iter(states.values())))
    chip_html = []
    for lens_name in ["Fast Read", "Swing Map", "Position View", "Cycle View"]:
        state = states.get(lens_name)
        if not state:
            continue
        cls = "lens-alert-bull" if state["state"] == "bullish" else "lens-alert-bear" if state["state"] == "bearish" else "lens-alert-neutral"
        chip_html.append(f'<span class="lens-alert-chip {cls}">{escape(state["label"])} · {state["score"]:+d}</span>')

    reasons_html = "".join(f"<li>{escape(tr_term(item))}</li>" for item in active_state.get("reasons", [])) or f"<li>{escape(t('no_extra_alert_context'))}</li>"

    render_html_block(
        html_block(
            f"""
            <div class="alert-shell">
                <div class="section-header" style="margin:0; color:#eef4ff;">{t("alert_layer")}</div>
                <div class="alert-title">{escape(tr_term(alert_map.get('headline', 'Lens states are mixed.')))}</div>
                <div class="alert-copy">{t("alert_layer_copy")}</div>
                <div class="alert-grid">
                    <div class="alert-box">
                        <div class="alert-label">{escape(tr_lens_name("Fast Read"))}</div>
                        <div class="alert-value">{escape(tr_term(states.get('Fast Read', {}).get('label', 'N/A')))}</div>
                        <div class="alert-sub">Score {states.get('Fast Read', {}).get('score', 0):+d}</div>
                    </div>
                    <div class="alert-box">
                        <div class="alert-label">{escape(tr_lens_name("Swing Map"))}</div>
                        <div class="alert-value">{escape(tr_term(states.get('Swing Map', {}).get('label', 'N/A')))}</div>
                        <div class="alert-sub">Score {states.get('Swing Map', {}).get('score', 0):+d}</div>
                    </div>
                    <div class="alert-box">
                        <div class="alert-label">{escape(tr_lens_name("Position View"))}</div>
                        <div class="alert-value">{escape(tr_term(states.get('Position View', {}).get('label', 'N/A')))}</div>
                        <div class="alert-sub">Score {states.get('Position View', {}).get('score', 0):+d}</div>
                    </div>
                    <div class="alert-box">
                        <div class="alert-label">{escape(tr_lens_name("Cycle View"))}</div>
                        <div class="alert-value">{escape(tr_term(states.get('Cycle View', {}).get('label', 'N/A')))}</div>
                        <div class="alert-sub">Score {states.get('Cycle View', {}).get('score', 0):+d}</div>
                    </div>
                </div>
                <div class="lens-alert-row">{''.join(chip_html)}</div>
                <div class="lens-alert-note"><strong>{t("active_lens")}</strong> {escape(tr_lens_name(active_title))} · {escape(tr_term(active_state['label']))}</div>
                <ul class="lens-alert-list">{reasons_html}</ul>
            </div>
            """
        )
    )

def compute_lens_adjustment(analysis: dict, intraday: dict, lens_meta: dict | None = None) -> tuple[int, list[str]]:
    lens_title = (lens_meta or {}).get("title", "Position View")
    adj = 0
    reasons = []

    rsi14 = analysis.get("rsi14", pd.NA)
    one_year_return = analysis.get("one_year_return", pd.NA)
    news_score = analysis.get("news_pulse", {}).get("score", 0.0)
    trading_lab = analysis.get("trading_lab", {})
    intraday_change = intraday.get("change_pct", pd.NA) if intraday else pd.NA

    if lens_title == "Fast Read":
        if pd.notna(intraday_change):
            if intraday_change > 1.0:
                adj += 2
                reasons.append("Fast Read favors fresh intraday strength.")
            elif intraday_change < -1.0:
                adj -= 2
                reasons.append("Fast Read penalizes weak live tape.")
        if news_score >= 1.4:
            adj += 1
            reasons.append("Fast Read rewards bullish news flow.")
        elif news_score <= -1.4:
            adj -= 1
            reasons.append("Fast Read penalizes bearish news flow.")
        if pd.notna(rsi14):
            if 52 <= rsi14 <= 72:
                adj += 1
                reasons.append("Fast Read likes active momentum.")
            elif rsi14 < 42:
                adj -= 1
                reasons.append("Fast Read dislikes weak short-term momentum.")

    elif lens_title == "Swing Map":
        setup = trading_lab.get("setup", "Balanced")
        if setup == "Momentum-led":
            adj += 2
            reasons.append("Swing Map rewards momentum-led setups.")
        elif setup == "Pullback watch":
            adj += 1
            reasons.append("Swing Map likes controlled pullbacks.")
        elif setup == "Risk-off":
            adj -= 2
            reasons.append("Swing Map penalizes unstable structure.")
        volume_ratio = trading_lab.get("volume_ratio", pd.NA)
        if pd.notna(volume_ratio):
            if volume_ratio >= 1.2:
                adj += 1
                reasons.append("Swing Map rewards volume confirmation.")
            elif volume_ratio <= 0.8:
                adj -= 1
                reasons.append("Swing Map discounts light participation.")

    elif lens_title == "Position View":
        if analysis.get("last_price", pd.NA) > analysis.get("sma200", pd.NA):
            adj += 2
            reasons.append("Position View prioritizes price above SMA 200.")
        else:
            adj -= 2
            reasons.append("Position View penalizes price below SMA 200.")
        if analysis.get("sma50", pd.NA) > analysis.get("sma200", pd.NA):
            adj += 1
            reasons.append("Position View rewards medium-term trend support.")
        else:
            adj -= 1
            reasons.append("Position View penalizes weak medium-term structure.")
        if pd.notna(one_year_return):
            if one_year_return > 15:
                adj += 1
                reasons.append("Position View rewards strong 1Y return.")
            elif one_year_return < -10:
                adj -= 1
                reasons.append("Position View penalizes weak 1Y return.")

    elif lens_title == "Cycle View":
        if pd.notna(one_year_return):
            if one_year_return > 30:
                adj += 2
                reasons.append("Cycle View rewards long-cycle leadership.")
            elif one_year_return < -15:
                adj -= 2
                reasons.append("Cycle View penalizes deterioration.")
        if analysis.get("sma50", pd.NA) > analysis.get("sma200", pd.NA):
            adj += 1
            reasons.append("Cycle View likes broad trend alignment.")
        else:
            adj -= 1
            reasons.append("Cycle View discounts broken leadership.")
        if abs(news_score) >= 2.0:
            reasons.append("Cycle View notes news, but does not over-weight it.")

    return adj, reasons


def compute_lens_winner_fields(bundle: dict, lens_meta: dict | None = None) -> dict:
    analysis = bundle["analysis"]
    intraday = bundle["intraday"]
    base_score = analysis.get("pro_score", analysis.get("score", 0))
    lens_adj, lens_reasons = compute_lens_adjustment(analysis, intraday, lens_meta)
    lens_score = base_score + lens_adj
    return {
        "base_score": base_score,
        "lens_adjustment": lens_adj,
        "lens_score": lens_score,
        "lens_reasons": lens_reasons,
        "lens_title": (lens_meta or {}).get("title", "Position View"),
    }


def render_winner_card(bundles: list[dict], lens_meta: dict | None = None):
    if len(bundles) < 2:
        return

    scored = []
    for bundle in bundles:
        fields = compute_lens_winner_fields(bundle, lens_meta)
        scored.append((bundle, fields))

    scored.sort(key=lambda item: item[1]["lens_score"], reverse=True)
    leader, leader_fields = scored[0]
    runner, runner_fields = scored[1]
    diff = leader_fields["lens_score"] - runner_fields["lens_score"]

    leader_analysis = leader["analysis"]
    catalyst = leader_analysis.get("catalyst_engine", {}).get("dominant", "Macro")
    runner_catalyst = runner["analysis"].get("catalyst_engine", {}).get("dominant", "Macro")
    guide = tr_term("Start here when you want one answer first. The winner card now adapts to the active Trend Lens, so leadership can change based on the question you are asking.")
    why = leader_fields["lens_reasons"][:3] or leader_analysis["reasons"][:3]

    if get_lang() == "繁體中文":
        hero_title = f"{display_ticker_label(leader['ticker'])} 目前在 {tr_lens_name(leader_fields['lens_title'])} 下領先"
        hero_copy = f"和 {display_ticker_label(runner['ticker'])} 相比，這個配置在目前鏡頭下更乾淨、更具優勢。切換鏡頭後，領先者也可能改變。"
        current_leader_label = "目前領先者"
        nearest_rival_label = "最接近的對手"
        lens_adjustment_label = "鏡頭調整"
        catalyst_edge_label = "催化優勢"
        lens_score_leader = f"鏡頭分數 {leader_fields['lens_score']:+d} · {tr_signal(leader_analysis['signal'])}"
        lens_score_runner = f"鏡頭分數 {runner_fields['lens_score']:+d} · {tr_signal(runner['analysis']['signal'])}"
        lens_adjustment_sub = f"基礎分數 {leader_fields['base_score']:+d}，再由目前鏡頭進一步調整。"
        catalyst_sub = f"次名焦點：{tr_term(runner_catalyst)} · 目前優勢 {diff:+d}"
        compare_label = "智慧比較"
        winner_badge = "勝出卡"
    else:
        hero_title = f"{display_ticker_label(leader['ticker'])} is leading under {tr_lens_name(leader_fields['lens_title'])}"
        hero_copy = f"Compared with {display_ticker_label(runner['ticker'])}, this setup currently has the cleaner edge for the active lens. Change the lens and the winner can change too."
        current_leader_label = "Current leader"
        nearest_rival_label = "Nearest rival"
        lens_adjustment_label = "Lens adjustment"
        catalyst_edge_label = "Catalyst edge"
        lens_score_leader = f"Lens score {leader_fields['lens_score']:+d} · {tr_signal(leader_analysis['signal'])}"
        lens_score_runner = f"Lens score {runner_fields['lens_score']:+d} · {tr_signal(runner['analysis']['signal'])}"
        lens_adjustment_sub = f"Base score {leader_fields['base_score']:+d} adjusted by the active lens."
        catalyst_sub = f"Runner-up focus: {tr_term(runner_catalyst)} · Current edge {diff:+d}"
        compare_label = "Smart Compare"
        winner_badge = "Winner Card"

    why_html = ''.join(f'<li>{escape(tr_term(item))}</li>' for item in why)

    st.markdown(
        f"""
        <div class="winner-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">{compare_label}</div>
            <div class="winner-copy">{escape(guide)}</div>
            <div class="winner-hero">
                <div class="winner-hero-main">
                    <span class="winner-badge">{winner_badge}</span>
                    <div class="winner-main-title">{escape(hero_title)}</div>
                    <div class="winner-main-copy">{escape(hero_copy)}</div>
                    <ul class="winner-reason-list">{why_html}</ul>
                </div>
                <div class="winner-hero-side">
                    <div class="winner-rail-grid">
                        <div class="winner-mini">
                            <div class="winner-mini-label">{current_leader_label}</div>
                            <div class="winner-mini-value">{escape(display_ticker_label(leader['ticker']))}</div>
                            <div class="winner-mini-sub">{escape(lens_score_leader)}</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">{nearest_rival_label}</div>
                            <div class="winner-mini-value">{escape(display_ticker_label(runner['ticker']))}</div>
                            <div class="winner-mini-sub">{escape(lens_score_runner)}</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">{lens_adjustment_label}</div>
                            <div class="winner-mini-value">{leader_fields['lens_adjustment']:+d}</div>
                            <div class="winner-mini-sub">{escape(lens_adjustment_sub)}</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">{catalyst_edge_label}</div>
                            <div class="winner-mini-value">{escape(tr_term(catalyst))}</div>
                            <div class="winner-mini-sub">{escape(catalyst_sub)}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def analyze_market_sentinel(price_series: pd.Series, volume_series: pd.Series | None, news_items: list[dict], ticker: str):
    indicators = build_indicator_frame(price_series)
    if indicators.empty:
        return empty_analysis_payload(ticker, indicators=indicators, news_items=news_items)

    latest = indicators.iloc[-1]
    last_price = latest.get("Price", pd.NA)
    sma20 = latest.get("SMA 20", pd.NA)
    sma50 = latest.get("SMA 50", pd.NA)
    sma200 = latest.get("SMA 200", pd.NA)
    rsi14 = latest.get("RSI 14", pd.NA)
    one_year_return = latest.get("1Y Return %", pd.NA)

    numeric_fields = [last_price, sma20, sma50, sma200, rsi14, one_year_return]
    if all(pd.isna(value) for value in numeric_fields):
        return empty_analysis_payload(ticker, indicators=indicators, news_items=news_items)

    score = 0
    reasons = []

    if pd.notna(last_price) and pd.notna(sma200):
        if last_price > sma200:
            score += 2
            reasons.append("Price is above SMA 200, supporting the long-term uptrend.")
        else:
            score -= 2
            reasons.append("Price is below SMA 200, which weakens the long-term setup.")
    if pd.notna(sma50) and pd.notna(sma200):
        if sma50 > sma200:
            score += 2
            reasons.append("SMA 50 is above SMA 200, confirming medium-term strength.")
        else:
            score -= 2
            reasons.append("SMA 50 is below SMA 200, confirming medium-term weakness.")
    if pd.notna(sma20) and pd.notna(sma50):
        if sma20 > sma50:
            score += 1
            reasons.append("SMA 20 is above SMA 50, so near-term momentum is supportive.")
        else:
            score -= 1
            reasons.append("SMA 20 is below SMA 50, so near-term momentum has cooled.")
    if pd.notna(rsi14):
        if 50 <= rsi14 <= 68:
            score += 1
            reasons.append("RSI is in a healthy bullish range.")
        elif rsi14 > 75:
            score -= 1
            reasons.append("RSI is stretched, so upside may be more fragile short term.")
        elif rsi14 < 35:
            score -= 1
            reasons.append("RSI is weak, which suggests sellers still have control.")
    if pd.notna(one_year_return):
        if one_year_return > 15:
            score += 1
            reasons.append("The stock is up strongly over the past year, which supports the broader trend.")
        elif one_year_return < -10:
            score -= 1
            reasons.append("The stock is down over the past year, which weakens the trend case.")

    volume_status = "N/A"
    if volume_series is not None and not volume_series.empty:
        volume_numeric = to_numeric_series(volume_series).dropna()
        if not volume_numeric.empty:
            avg_volume_50 = volume_numeric.tail(50).mean()
            vol_ratio = (volume_numeric.iloc[-1] / avg_volume_50) if pd.notna(avg_volume_50) and avg_volume_50 != 0 else pd.NA
            if pd.notna(vol_ratio) and vol_ratio >= 1.2:
                volume_status = "Elevated"
                score += 1
                reasons.append("Recent volume is above the 50-day average, giving the move more confirmation.")
            elif pd.notna(vol_ratio) and vol_ratio <= 0.8:
                volume_status = "Light"
                reasons.append("Recent volume is light, so conviction behind the move is weaker.")
            else:
                volume_status = "Normal"

    news_pulse = build_news_pulse(news_items)
    if news_pulse["score"] >= 1.4:
        score += 1
        reasons.append("Recent news flow has skewed bullish.")
    elif news_pulse["score"] <= -1.4:
        score -= 1
        reasons.append("Recent news flow has skewed bearish.")
    else:
        reasons.append("Recent news flow is mixed and does not materially change the core trend picture.")

    if score >= 4:
        signal = "BUY"
        confidence = "High" if score >= 6 else "Moderate"
        summary = "Trend structure and recent context are supportive for accumulation."
    elif score <= -3:
        signal = "SELL"
        confidence = "High" if score <= -5 else "Moderate"
        summary = "Trend structure is weak or deteriorating, so risk remains elevated."
    else:
        signal = "HOLD"
        confidence = "Moderate"
        summary = "Signals are mixed, so waiting for better confirmation is more disciplined."

    return {
        "signal": signal,
        "confidence": confidence,
        "score": score,
        "summary": summary,
        "reasons": reasons,
        "trend": trend_label(one_year_return),
        "one_year_return": one_year_return,
        "rsi14": rsi14,
        "rsi_status": rsi_signal(rsi14),
        "last_price": last_price,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "indicators": indicators,
        "latest_daily_ts": indicators.index[-1] if not indicators.empty else None,
        "volume_status": volume_status,
        "news_pulse": news_pulse,
        "ticker": ticker,
    }

def signal_class(signal: str) -> str:
    return {"BUY": "chip-buy", "HOLD": "chip-hold", "SELL": "chip-sell"}.get(signal, "chip-info")


def badge_html(text: str, kind: str = "info") -> str:
    klass = {
        "buy": "chip chip-buy",
        "hold": "chip chip-hold",
        "sell": "chip chip-sell",
        "info": "chip chip-info",
    }.get(kind, "chip")
    return f'<span class="{klass}">{escape(text)}</span>'


def impact_bar(item: dict) -> str:
    score = item.get("impact_score", 0)
    width = min(100, max(18, abs(score) * 28 + item.get("relevance", 0) * 8))
    if score > 0:
        inner = f'<div class="impact-bar-pos" style="width:{width}%"></div>'
    elif score < 0:
        inner = f'<div class="impact-bar-neg" style="width:{width}%"></div>'
    else:
        inner = f'<div class="impact-bar-neu" style="width:{width}%"></div>'
    return f'<div class="impact-bar-wrap">{inner}</div>'




# ---------------------------
# Rendering
# ---------------------------
def relevance_label(relevance: int) -> str:
    if relevance >= 4:
        return tr_relevance("High")
    if relevance >= 2:
        return tr_relevance("Medium")
    return tr_relevance("Low")


def article_probability(item: dict) -> int:
    score = abs(int(item.get("impact_score", 0)))
    relevance = int(item.get("relevance", 0))
    if "neutral" in item.get("impact_label", "").lower() or "mixed" in item.get("impact_label", "").lower():
        base = 40
    else:
        base = 48
    probability = base + score * 12 + relevance * 5
    return max(38, min(89, probability))


def article_direction_meta(item: dict) -> tuple[str, str, str]:
    label = item.get("impact_label", "Neutral / mixed")
    label_l = label.lower()
    if "bullish" in label_l:
        return ("可能支撐上行" if get_lang() == "繁體中文" else "Likely to support upside"), "impact-up", "row-meter-fill-up"
    if "bearish" in label_l:
        return ("可能帶來下行壓力" if get_lang() == "繁體中文" else "Likely to pressure downside"), "impact-down", "row-meter-fill-down"
    return ("可能維持方向混合" if get_lang() == "繁體中文" else "Likely to keep direction mixed"), "impact-flat", "row-meter-fill-flat"


def signal_css_class(signal: str) -> str:
    return {"BUY": "crypto-buy", "HOLD": "crypto-hold", "SELL": "crypto-sell"}.get(signal, "crypto-hold")


def compact_story_line(item: dict, ticker: str) -> str:
    direction_text, tag_class, _ = article_direction_meta(item)
    prob = article_probability(item)
    title = escape(item.get("title", "Untitled"))
    summary = escape(build_compact_summary_text(item, ticker, prob))
    provider = escape(str(item.get("provider", "Unknown source")))
    us_time = format_us_timestamp(item.get("published"))
    link_html = ""
    if item.get("url"):
        link_html = f'<a class="brief-link" href="{escape(str(item["url"]))}" target="_blank">{t("open_article")}</a>'
    helper_chip = f'<span class="news-helper-chip">{t("news_mode_bilingual")}</span>' if news_mode_prefers_helper() else ""
    return (
        f'<div class="brief-item">'
        f'<div class="brief-meta">{provider} · {us_time}</div>'
        f'<div class="brief-headline">{title}</div>'
        f'<div class="brief-summary">{summary}</div>'
        f'<div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">'
        f'<span class="impact-tag {tag_class}">{escape(direction_text)}</span>'
        f'<span class="impact-tag impact-flat">{t("estimated_effect")} {prob}%</span>'
        f'{helper_chip}'
        f'</div>'
        f'{link_html}'
        f'</div>'
    )


def render_daily_briefing(ticker: str, news_items: list[dict]):
    top_items = news_items[:3]
    if not top_items:
        st.info(t("no_recent_news", ticker=display_ticker_label(ticker)))
        return
    body = "".join(compact_story_line(item, ticker) for item in top_items)
    st.markdown(
        html_block(
            f"""
            <div class="news-brief-card">
                <div class="section-header">{t("daily_briefing")}</div>
                {body}
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def render_feature_story(ticker: str, analysis: dict, news_items: list[dict]):
    if news_items:
        lead = news_items[0]
        direction_text, _, _ = article_direction_meta(lead)
        probability = article_probability(lead)
        title = escape(lead.get("title", f"{ticker} market setup"))
        summary_html = build_news_summary_html(lead, ticker, probability, block_class="lead-summary")
        provider = escape(str(lead.get("provider", "Unknown source")))
        meta = f"{provider} · Taiwan {format_tw_timestamp(lead.get('published'))}"
        link_html = ""
        if lead.get("url"):
            link_html = f'<a class="small-pill" href="{escape(str(lead["url"]))}" target="_blank">{t("open_article")}</a>'
        pos = probability if "bullish" in lead.get("impact_label", "").lower() else max(100 - probability, 18)
        neg = probability if "bearish" in lead.get("impact_label", "").lower() else max(100 - probability, 18)
        why_copy = escape(tr_reason_text(lead.get("impact_reason", analysis["summary"])))
    else:
        lead = None
        direction_text = tr_term("Direction currently mixed")
        probability = 50
        title = escape(f"{ticker} is trading on technical and news cross-currents")
        summary_html = f'<div class="lead-summary">{escape(tr_reason_text(analysis["summary"]))}</div>'
        meta = tr_term("No stock-specific story returned")
        link_html = ""
        pos = neg = 50
        why_copy = escape(tr_reason_text(analysis["summary"]))

    render_html_block(
        html_block(
            f"""
            <div class="lead-story">
                <div class="section-header" style="margin:0; color:#eef4ff;">{t("top_story")}</div>
                <div class="lead-kicker">{escape(meta)}</div>
                <div class="lead-title">{title}</div>
                {summary_html}
                <div class="lead-meta-row">
                    <span class="small-pill">{escape(direction_text)}</span>
                    <span class="small-pill">{t("estimated_effect_on", ticker=escape(display_ticker_label(ticker)), probability=probability)}</span>
                    <span class="small-pill">{escape(tr_news_label(analysis['news_pulse']['label']))}</span>
                    {link_html}
                </div>
                <div class="lead-story-board">
                    <div class="lead-story-panel">
                        <div class="lead-panel-label">{t("why_this_matters_now")}</div>
                        <div class="lead-panel-value">{t("setup_context", ticker=escape(display_ticker_label(ticker)))}</div>
                        <div class="lead-panel-copy">{why_copy}</div>
                    </div>
                    <div class="lead-story-panel">
                        <div class="lead-panel-label">{t("directional_pressure")}</div>
                        <div class="lead-panel-value">{t("up_down_pressure", pos=pos, neg=neg)}</div>
                        <div class="lead-panel-copy">{t("directional_pressure_copy")}</div>
                        <div class="impact-meter" style="margin-top:12px;">
                            <div class="impact-pos" style="width:{pos}%;"></div>
                        </div>
                    </div>
                </div>
            </div>
            """
        )
    )

def render_signal_panel(ticker: str, analysis: dict, intraday: dict, news_items: list[dict]):
    pulse = analysis["news_pulse"]
    signal = analysis["signal"]
    signal_class = signal_css_class(signal)
    intraday_price = format_price(intraday["last_price"]) if intraday.get("available") else "N/A"
    intraday_change = format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A"
    latest_trend_date = format_us_timestamp(analysis["latest_daily_ts"])
    top_reasons = "".join(f"<li>{escape(tr_reason_text(r))}</li>" for r in analysis["reasons"][:3])
    alert_html = "".join(f"<li>{escape(tr_reason_text(a))}</li>" for a in analysis.get("alerts", [])[:2]) or f"<li>{escape(tr_term('No urgent alert is active.'))}</li>"
    render_html_block(
        html_block(
            f"""
            <div class="crypto-card">
                <div class="crypto-kicker">{t("signal_deck")}</div>
                <div class="crypto-signal {signal_class}">{escape(tr_signal(signal))}</div>
                <div class="crypto-main-number">{analysis.get('pro_score', analysis['score']):+d}</div>
                <div class="crypto-sub">{escape(tr_reason_text(analysis['summary']))}</div>
                <div class="crypto-grid">
                    <div class="crypto-mini">
                        <div class="crypto-mini-label">{t("confidence")}</div>
                        <div class="crypto-mini-value">{escape(tr_confidence(analysis['confidence']))}</div>
                        <div class="crypto-mini-sub">{t("trend_1y")}: {escape(tr_term(analysis['trend']))}</div>
                    </div>
                    <div class="crypto-mini">
                        <div class="crypto-mini-label">{t("news_pulse")}</div>
                        <div class="crypto-mini-value">{pulse['up']}/{pulse['down']}</div>
                        <div class="crypto-mini-sub">{escape(tr_news_label(pulse['label']))}</div>
                    </div>
                    <div class="crypto-mini">
                        <div class="crypto-mini-label">{t("intraday")}</div>
                        <div class="crypto-mini-value">{intraday_change}</div>
                        <div class="crypto-mini-sub">{intraday_price}</div>
                    </div>
                    <div class="crypto-mini">
                        <div class="crypto-mini-label">{t("trading_lab")}</div>
                        <div class="crypto-mini-value">{escape(tr_setup(analysis.get('trading_lab', {}).get('setup', 'Balanced')))}</div>
                        <div class="crypto-mini-sub">{latest_trend_date}</div>
                    </div>
                </div>
                <ul class="crypto-reasons">{top_reasons}</ul>
                <ul class="crypto-reasons">{alert_html}</ul>
            </div>
            """
        )
    )

def render_news_first_section(ticker: str, analysis: dict, intraday: dict, news_items: list[dict]):
    left, center, right = st.columns([0.95, 1.95, 1.0], gap="large")
    with left:
        render_daily_briefing(ticker, news_items)
    with center:
        render_feature_story(ticker, analysis, news_items)
    with right:
        render_signal_panel(ticker, analysis, intraday, news_items)
    render_catalyst_engine(analysis, ticker)



def build_decision_brief(analysis: dict, intraday: dict, news_items: list[dict]) -> dict:
    catalyst = analysis.get("catalyst_engine", {})
    lab = analysis.get("trading_lab", {})
    signal = analysis.get("signal", "HOLD")
    pulse = analysis.get("news_pulse", {})
    alerts = analysis.get("alerts", [])
    lead_story = (news_items[0].get("title") if news_items else "") or "No strong lead story"
    dominant = catalyst.get("dominant", "Macro")
    setup = lab.get("setup", "Balanced")
    intraday_move = format_percent(intraday.get("change_pct", pd.NA)) if intraday.get("available") else "N/A"

    if signal == "BUY":
        action = "Favor continuation entries only when price confirms above near-term resistance or re-tests support cleanly."
    elif signal == "SELL":
        action = "Stay defensive until price rebuilds above trend support and headline pressure stops worsening."
    else:
        action = "Wait for the catalyst picture and chart structure to align before pressing directional risk."

    if setup == "Momentum-led":
        execution = "Momentum is leading. Breakouts and continuation days deserve more attention than deep dip-buy attempts."
    elif setup == "Pullback watch":
        execution = "The structure is in pullback mode. Patience matters more than speed, especially near support."
    elif setup == "Risk-off":
        execution = "The tape is fragile. Capital protection matters more than forcing a setup."
    else:
        execution = "The setup is balanced. Let the next strong catalyst or price confirmation set direction."

    if alerts:
        risk_flag = alerts[0]
    elif pulse.get("score", 0) <= -1.4:
        risk_flag = "Headline tone is leaning negative and can overpower otherwise decent chart structure."
    elif pulse.get("score", 0) >= 1.4:
        risk_flag = "Positive headline tone is helping the setup, but it still needs price confirmation."
    else:
        risk_flag = "No single risk is dominant, so watch whether the next story shifts the narrative."

    return {
        "stance": signal,
        "signal_class": signal_css_class(signal),
        "dominant": dominant,
        "setup": setup,
        "action": action,
        "execution": execution,
        "risk_flag": risk_flag,
        "lead_story": lead_story,
        "intraday_move": intraday_move,
        "news_label": pulse.get("label", "News tilt: mixed"),
        "confidence": analysis.get("confidence", "Moderate"),
    }


def render_decision_brief(ticker: str, analysis: dict, intraday: dict, news_items: list[dict]):
    brief = build_decision_brief(analysis, intraday, news_items)
    render_html_block(
        html_block(
            f"""
            <div class="brief-shell">
                <div class="section-header" style="margin:0; color:#f5ead8;">{t('decision_brief')}</div>
                <div class="brief-title">{t('what_matters_now_for', ticker=escape(display_ticker_label(ticker)))}</div>
                <div class="brief-copy">{t('decision_brief_copy')}</div>
                <div class="brief-grid">
                    <div class="brief-box">
                        <div class="brief-label">{t('current_stance')}</div>
                        <div style="margin-top:10px;"><span class="crypto-signal {brief['signal_class']}">{escape(tr_signal(brief['stance']))}</span></div>
                        <div class="brief-sub">{escape(tr_confidence(brief['confidence']))} · {t('intraday')} {escape(brief['intraday_move'])}</div>
                    </div>
                    <div class="brief-box">
                        <div class="brief-label">{t('dominant_catalyst')}</div>
                        <div class="brief-value">{escape(tr_term(brief['dominant']))}</div>
                        <div class="brief-sub">{escape(tr_news_label(brief['news_label']))}</div>
                    </div>
                    <div class="brief-box">
                        <div class="brief-label">{t('best_execution_style')}</div>
                        <div class="brief-value">{escape(tr_setup(brief['setup']))}</div>
                        <div class="brief-sub">{escape(tr_term(brief['execution']))}</div>
                    </div>
                    <div class="brief-box">
                        <div class="brief-label">{t('main_risk_flag')}</div>
                        <div class="brief-value brief-risk">{escape((tr_term(brief['risk_flag']))[:68])}</div>
                        <div class="brief-sub">{t('lead_story_label')}: {escape((brief['lead_story'])[:90])}</div>
                    </div>
                </div>
                <div class="brief-action">Next step</div>
                <div class="brief-copy" style="margin-top:6px;">{escape(brief['action'])}</div>
            </div>
            """
        )
    )

def render_story_row(item: dict, ticker: str, idx: int):
    direction_text, tag_class, meter_class = article_direction_meta(item)
    probability = article_probability(item)
    title = escape(item.get("title", "Untitled"))
    summary_html = build_news_summary_html(item, ticker, probability)
    provider = escape(str(item.get("provider", "Unknown source")))
    related = ", ".join(item.get("related", [])[:5]) if item.get("related") else "Not provided"
    meta = f"{provider} · US {format_us_timestamp(item.get('published'))} · Taiwan {format_tw_timestamp(item.get('published'))}"
    relevance = relevance_label(int(item.get("relevance", 0)))
    link_html = ""
    if item.get("url"):
        link_html = f'<a class="inline-link" href="{escape(str(item["url"]))}" target="_blank">{t("open_article")}</a>'
    st.markdown(
        f"""
        <div class="story-row">
            <div class="story-row-head">
                <div>
                    <div class="story-row-meta">{t("story", idx=idx)} · {escape(meta)}</div>
                    <div class="story-row-title">{title}</div>
                    <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">
                        <span class="impact-tag {tag_class}">{escape(direction_text)}</span>
                        <span class="impact-tag impact-flat">{t("confidence")} {escape(tr_confidence(item.get('confidence', 'N/A')))}</span>
                        <span class="impact-tag impact-flat">{t("relevance")} {escape(relevance)}</span>
                    </div>
                </div>
            </div>
            <div class="story-row-grid">
                <div>
                    {summary_html}
                    <div class="story-row-summary"><strong>{t("why_this_could_matter", ticker=escape(display_ticker_label(ticker)))}</strong> {escape(tr_reason_text(item.get('impact_reason', '')))}</div>
                    <div class="story-row-summary"><strong>{t("related_tickers")}</strong> {escape(tr_term(related))}</div>
                    <div class="row-meter"><div class="{meter_class}" style="width:{probability}%;"></div></div>
                    <div style="margin-top:10px;">{link_html}</div>
                </div>
                <div class="prob-box">
                    <div class="prob-label">{t("estimated_effect")}</div>
                    <div class="prob-value">{probability}%</div>
                    <div class="prob-sub">{t("chance_nudges", ticker=escape(display_ticker_label(ticker)))}</div>
                    <div class="prob-meter">
                        <div class="prob-meter-fill" style="width:{probability}%;"></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_news_stream(ticker: str, news_items: list[dict]):
    st.markdown(
        f"""
        <div class="news-board-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">{t("top_news_stories")}</div>
            <div class="news-board-copy">{t("news_board_copy")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not news_items:
        st.info(t("no_recent_news", ticker=display_ticker_label(ticker)))
        return
    render_news_highlights(ticker, news_items)
    for idx, item in enumerate(news_items, start=1):
        render_story_row(item, ticker, idx)

def render_trend_section(analysis: dict, intraday: dict, lens_meta: dict | None = None, daily_ohlc: pd.DataFrame | None = None, intraday_ohlc: pd.DataFrame | None = None, selected_count: int = 1):
    lens_display = tr_lens_meta(lens_meta or {"title": "Position View", "how_to_read": "Use this view to confirm structure."})
    trend_base_label = (
        "展開／收合 Trend Lab 與 K 線確認"
        if get_language() == "zh_TW"
        else "Expand / collapse Trend Lab & candlestick confirmation"
    )
    trend_helper_base = (
        "檢視日線／盤中 K 線、技術指標與目前的交易結構。"
        if get_language() == "zh_TW"
        else "Review daily and intraday candlesticks, technical indicators, and the current trade structure."
    )

    with st.expander(
        planner_expander_label(trend_base_label, "trend", selected_count),
        expanded=planner_auto_expand("trend", selected_count),
    ):
        render_expander_meta("trend", selected_count, trend_helper_base)

        st.markdown(
            f"""
            <div class="trend-shell">
                <div class="trend-header">
                    <div>
                        <div class="section-header" style="margin:0;">{t("trend_lab")}</div>
                        <div class="trend-title">{t("candlestick_confirmation")}</div>
                        <div class="trend-sub">{t("trend_lab_copy")}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("last_daily_close"), format_price(analysis["last_price"]))
        c2.metric("SMA 50 vs 200", f"{format_price(analysis['sma50'])} / {format_price(analysis['sma200'])}")
        c3.metric("RSI 14", "N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}")
        c4.metric(t("intraday_move"), format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A")

        render_trading_lab_panel(analysis)

        render_candlestick_chart(
            daily_ohlc.tail(252) if daily_ohlc is not None else pd.DataFrame(),
            t("candlestick_confirmation"),
            f"{lens_display.get('title', tr_lens_name((lens_meta or {}).get('title', 'Trend Lens')))}: {lens_display.get('how_to_read', (lens_meta or {}).get('how_to_read', 'Use this view to confirm structure.'))}" if lens_meta else "Daily candlesticks with SMA 20 and SMA 50 overlays for structure confirmation.",
            height=440,
            show_ma=True,
        )

        if intraday.get("available") and intraday_ohlc is not None and not intraday_ohlc.empty:
            render_candlestick_chart(
                intraday_ohlc.tail(78),
                "Live intraday candlestick tape (5m)" if get_lang() == "English" else "即時盤中 K 線 (5 分)",
                "Latest intraday price action in the same dark premium theme." if get_lang() == "English" else "以相同高級深色主題呈現最新盤中價格結構。",
                height=300,
                show_ma=False,
            )

        st.markdown(
            f'<div class="footer-note">{t("research_view_only")}</div>',
            unsafe_allow_html=True,
        )
    render_html_block('</div>')

def build_snapshot_row(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str, lens_meta: dict | None = None):
    price_series, field_name = get_price_series(daily_data, ticker)
    volume_series = get_series(daily_data, "Volume", ticker)
    intraday = get_intraday_snapshot(intraday_data, ticker)
    news_items, _ = fetch_ticker_news(ticker, max_items=8)

    if price_series is None or price_series.empty:
        return {
            "Ticker": ticker,
            "Signal": "N/A",
            "Confidence": "N/A",
            "Daily Close": "N/A",
            "Intraday": "N/A",
            "1Y Trend": "N/A",
            "News Pulse": "N/A",
            "Price Source": field_name or "N/A",
        }

    analysis = analyze_market_sentinel(price_series, volume_series, news_items, ticker)
    analysis = enrich_pro_analysis(
        analysis,
        price_series,
        volume_series,
        news_items,
        active_lens_title=(lens_meta or {}).get("title", "Position View"),
        intraday=intraday,
    )
    return {
        "Ticker": ticker,
        "Signal": analysis["signal"],
        "Confidence": analysis["confidence"],
        "Daily Close": format_price(analysis["last_price"]),
        "Intraday": format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A",
        "1Y Trend": analysis["trend"],
        "News Pulse": analysis["news_pulse"]["label"],
        "Price Source": field_name,
    }


def collect_ticker_context(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str, news_limit: int = 10, lens_meta: dict | None = None):
    price_series, field_name = get_price_series(daily_data, ticker)
    volume_series = get_series(daily_data, "Volume", ticker)
    news_items, news_error = fetch_ticker_news(ticker, max_items=news_limit)
    intraday = get_intraday_snapshot(intraday_data, ticker)
    if price_series is None or price_series.empty:
        return None
    analysis = analyze_market_sentinel(price_series, volume_series, news_items, ticker)
    analysis = enrich_pro_analysis(
        analysis,
        price_series,
        volume_series,
        news_items,
        active_lens_title=(lens_meta or {}).get("title", "Position View"),
        intraday=intraday,
    )
    return {
        "ticker": ticker,
        "field_name": field_name,
        "price_series": price_series,
        "volume_series": volume_series,
        "news_items": news_items,
        "news_error": news_error,
        "intraday": intraday,
        "analysis": analysis,
        "daily_ohlc": get_ohlc_frame(daily_data, ticker, tail=252),
        "intraday_ohlc": get_ohlc_frame(intraday_data, ticker, tail=78),
    }





def opportunity_radar_score(bundle: dict, lens_meta: dict | None = None) -> float:
    analysis = bundle["analysis"]
    intraday = bundle.get("intraday", {})
    lens_fields = compute_lens_winner_fields(bundle, lens_meta)
    score = float(lens_fields["lens_score"])
    news_score = float(analysis.get("news_pulse", {}).get("score", 0))
    score += max(min(news_score, 2.5), -2.5)

    intraday_change = intraday.get("change_pct", pd.NA)
    if pd.notna(intraday_change):
        if intraday_change >= 1.2:
            score += 1.5
        elif intraday_change > 0:
            score += 0.7
        elif intraday_change <= -1.2:
            score -= 1.5
        else:
            score -= 0.7

    signal = analysis.get("signal", "HOLD")
    if signal == "BUY":
        score += 0.8
    elif signal == "SELL":
        score -= 0.8
    return score


def opportunity_execution_note(bundle: dict) -> str:
    analysis = bundle["analysis"]
    setup = analysis.get("trading_lab", {}).get("setup", "Balanced")
    signal = analysis.get("signal", "HOLD")
    news_score = float(analysis.get("news_pulse", {}).get("score", 0))

    if signal == "BUY" and setup == "Momentum-led" and news_score >= 0:
        return "Momentum + news are aligned. Keep this near the top of the watchlist."
    if signal == "BUY":
        return "Constructive, but not fully confirmed. Watch for cleaner price confirmation."
    if signal == "HOLD":
        return "Mixed setup. Let the next catalyst decide whether this climbs the list."
    return "Conditions are weak. Treat this as a defensive watch item until momentum improves."


def intraday_pressure_note(bundle: dict) -> str:
    change_pct = bundle.get("intraday", {}).get("change_pct", pd.NA)
    if pd.isna(change_pct):
        return tr_term("Intraday pressure is mixed")
    if change_pct >= 1.0:
        return tr_term("Constructive intraday pressure")
    if change_pct > 0:
        return tr_term("Mild intraday tailwind")
    if change_pct <= -1.0:
        return tr_term("Intraday sellers are in control")
    return tr_term("Intraday pressure is mixed")


def render_opportunity_radar(bundles: list[dict], lens_meta: dict | None = None):
    if not bundles:
        return

    scored = []
    for bundle in bundles:
        scored.append((bundle, opportunity_radar_score(bundle, lens_meta)))
    scored.sort(key=lambda item: item[1], reverse=True)

    leader, leader_score = scored[0]
    fastest = max(
        bundles,
        key=lambda item: item.get("intraday", {}).get("change_pct", -10**9)
        if pd.notna(item.get("intraday", {}).get("change_pct", pd.NA))
        else -10**9,
    )
    news_backing = max(bundles, key=lambda item: item["analysis"].get("news_pulse", {}).get("score", -10**9))

    row_html = []
    for rank, (bundle, radar_score) in enumerate(scored[:6], start=1):
        analysis = bundle["analysis"]
        catalyst = analysis.get("catalyst_engine", {}).get("dominant", "Macro")
        intraday_note = intraday_pressure_note(bundle)
        execution_note = tr_term(opportunity_execution_note(bundle))
        row_template = textwrap.dedent(
            """
            <div class="compare-table-row">
                <div class="compare-table-cell">
                    <div class="compare-table-sub">#{rank}</div>
                    <div class="compare-table-ticker">{ticker_label}</div>
                    <div class="compare-table-note">{signal_label} · {confidence_label}</div>
                </div>
                <div class="compare-table-cell">
                    <div class="compare-table-sub">{radar_score_label}</div>
                    <div class="compare-table-value">{radar_score_value}</div>
                    <div class="compare-table-note">{intraday_note}</div>
                </div>
                <div class="compare-table-cell">
                    <div class="compare-table-sub">{news_backing_label}</div>
                    <div class="compare-table-value">{news_label}</div>
                    <div class="compare-table-note">{news_score}</div>
                </div>
                <div class="compare-table-cell">
                    <div class="compare-table-sub">{dominant_catalyst_label}</div>
                    <div class="compare-table-value">{catalyst_value}</div>
                    <div class="compare-table-note">{setup_value}</div>
                </div>
                <div class="compare-table-cell">
                    <div class="compare-table-sub">{execution_note_label}</div>
                    <div class="compare-table-note">{execution_note}</div>
                </div>
            </div>
            """
        ).strip()
        row_html.append(
            row_template.format(
                rank=rank,
                ticker_label=escape(display_ticker_label(bundle["ticker"])),
                signal_label=escape(tr_signal(analysis.get("signal", "HOLD"))),
                confidence_label=escape(tr_confidence(analysis.get("confidence", "Moderate"))),
                radar_score_label=t("radar_score"),
                radar_score_value=f"{radar_score:+.1f}",
                intraday_note=escape(intraday_note),
                news_backing_label=t("news_backing"),
                news_label=escape(tr_news_label(analysis.get("news_pulse", {}).get("label", "News tilt: mixed"))),
                news_score=f'{analysis.get("news_pulse", {}).get("score", 0):+.1f}',
                dominant_catalyst_label=escape(tr_term("Dominant catalyst" if get_lang() == "English" else "主導催化")),
                catalyst_value=escape(tr_term(catalyst)),
                setup_value=escape(tr_setup(analysis.get("trading_lab", {}).get("setup", "Balanced"))),
                execution_note_label=t("execution_note"),
                execution_note=escape(execution_note),
            )
        )

    radar_template = textwrap.dedent(
        """
        <div class="compare-table-shell">
            <div class="compare-table-title">{title}</div>
            <div class="compare-table-copy">{copy}</div>
            <div class="compare-hero-grid">
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">{current_stance_label}</div>
                    <div class="compare-hero-value">{leader_label}</div>
                    <div class="compare-hero-sub">{radar_score_label} {leader_score} · {leader_signal}</div>
                </div>
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">{fastest_intraday_label}</div>
                    <div class="compare-hero-value">{fastest_label}</div>
                    <div class="compare-hero-sub">{fastest_change} · {fastest_note}</div>
                </div>
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">{news_backing_label}</div>
                    <div class="compare-hero-value">{news_backing_ticker}</div>
                    <div class="compare-hero-sub">{news_backing_summary}</div>
                </div>
            </div>
            <div class="compare-table-body">{rows_html}</div>
        </div>
        """
    ).strip()

    radar_html = radar_template.format(
        title=t("opportunity_radar"),
        copy=t("opportunity_radar_copy"),
        current_stance_label=t("current_stance"),
        leader_label=escape(display_ticker_label(leader["ticker"])),
        radar_score_label=t("radar_score"),
        leader_score=f"{leader_score:+.1f}",
        leader_signal=escape(tr_signal(leader["analysis"].get("signal", "HOLD"))),
        fastest_intraday_label=t("fastest_intraday"),
        fastest_label=escape(display_ticker_label(fastest["ticker"])),
        fastest_change=format_percent(fastest.get("intraday", {}).get("change_pct", pd.NA)),
        fastest_note=escape(intraday_pressure_note(fastest)),
        news_backing_label=t("news_backing"),
        news_backing_ticker=escape(display_ticker_label(news_backing["ticker"])),
        news_backing_summary=escape(tr_news_label(news_backing["analysis"].get("news_pulse", {}).get("label", "News tilt: mixed"))),
        rows_html="".join(row_html),
    )

    render_html_block(radar_html)





def render_comparison_overview_cards(bundles: list[dict], lens_meta: dict | None = None):
    if not bundles:
        return

    if len(bundles) <= 4:
        card_cols = st.columns(len(bundles))
        for col, bundle in zip(card_cols, bundles):
            analysis = bundle["analysis"]
            intraday = bundle["intraday"]
            signal = analysis["signal"]
            signal_class_name = signal_css_class(signal)
            pulse = analysis["news_pulse"]["label"]
            with col:
                st.markdown(
                    f"""
                    <div class="compare-card">
                        <div class="compare-card-kicker">{t("side_by_side_profile")}</div>
                        <div style="margin-top:10px;"><span class="crypto-signal {signal_class_name}">{escape(tr_signal(signal))}</span></div>
                        <div class="compare-card-title">{escape(display_ticker_label(bundle['ticker']))}</div>
                        <div class="compare-card-price">{format_price(analysis['last_price'])}</div>
                        <div class="compare-card-grid">
                            <div class="compare-stat">
                                <div class="compare-stat-label">{t("trend_1y")}</div>
                                <div class="compare-stat-value">{format_percent(analysis['one_year_return'])}</div>
                            </div>
                            <div class="compare-stat">
                                <div class="compare-stat-label">{t("confidence")}</div>
                                <div class="compare-stat-value">{escape(tr_confidence(analysis["confidence"]))}</div>
                            </div>
                            <div class="compare-stat">
                                <div class="compare-stat-label">{t("lens_score")}</div>
                                <div class="compare-stat-value">{compute_lens_winner_fields(bundle, lens_meta)['lens_score']:+d}</div>
                            </div>
                            <div class="compare-stat">
                                <div class="compare-stat-label">RSI 14</div>
                                <div class="compare-stat-value">{"N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}"}</div>
                            </div>
                        </div>
                        <div class="compare-card-meta">
                            {t('intraday')} <strong>{format_percent(intraday['change_pct']) if intraday.get('available') else 'N/A'}</strong> · {t('news_pulse')} <strong>{escape(tr_news_label(pulse))}</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        return

    sorted_bundles = sorted(
        bundles,
        key=lambda bundle: (
            compute_lens_winner_fields(bundle, lens_meta)["lens_score"],
            bundle["analysis"]["one_year_return"] if pd.notna(bundle["analysis"]["one_year_return"]) else -10**9,
        ),
        reverse=True,
    )

    card_html_parts: list[str] = []
    for rank, bundle in enumerate(sorted_bundles, start=1):
        analysis = bundle["analysis"]
        intraday = bundle["intraday"]
        pulse = tr_news_label(analysis["news_pulse"]["label"])
        signal_class_name = signal_css_class(analysis["signal"])
        card_html_parts.append(
            "".join(
                [
                    '<div class="compare-mosaic-card">',
                    f'<div class="compare-mosaic-rank">#{rank}</div>',
                    f'<div style="margin-top:12px;"><span class="crypto-signal {signal_class_name}">{escape(tr_signal(analysis["signal"]))}</span></div>',
                    f'<div class="compare-mosaic-title">{escape(display_ticker_label(bundle["ticker"]))}</div>',
                    f'<div class="compare-mosaic-price">{format_price(analysis["last_price"])}</div>',
                    '<div class="compare-mosaic-grid">',
                    f'<div><div class="compare-mosaic-stat-label">{t("trend_1y")}</div><div class="compare-mosaic-stat-value">{format_percent(analysis["one_year_return"])}</div></div>',
                    f'<div><div class="compare-mosaic-stat-label">{t("confidence")}</div><div class="compare-mosaic-stat-value">{escape(tr_confidence(analysis["confidence"]))}</div></div>',
                    f'<div><div class="compare-mosaic-stat-label">{t("lens_score")}</div><div class="compare-mosaic-stat-value">{compute_lens_winner_fields(bundle, lens_meta)["lens_score"]:+d}</div></div>',
                    f'<div><div class="compare-mosaic-stat-label">RSI 14</div><div class="compare-mosaic-stat-value">{"N/A" if pd.isna(analysis["rsi14"]) else f"{analysis["rsi14"]:.2f}"}</div></div>',
                    '</div>',
                    f'<div class="compare-mosaic-meta">{t("intraday")} <strong>{format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A"}</strong> · {t("news_pulse")} <strong>{escape(pulse)}</strong></div>',
                    '</div>',
                ]
            )
        )

    layout_note = (
        "已選超過 4 檔，自動切換為網格化比較，避免卡片互相擠壓。"
        if get_language() == "zh_TW"
        else "More than four names selected, so the comparison switches to a ranked mosaic layout to preserve readability."
    )
    render_html_block(
        "".join(
            [
                '<div class="compare-mosaic">',
                "".join(card_html_parts),
                '</div>',
                f'<div class="compare-layout-note">{escape(layout_note)}</div>',
            ]
        )
    )



def sync_comparison_candle_focus(candle_options: list[str], key: str, max_items: int = 4) -> list[str]:
    normalized_options = [normalize_dashboard_ticker(ticker) for ticker in candle_options if ticker]
    if not normalized_options:
        return []

    previous_focus = st.session_state.get(key, [])
    if not isinstance(previous_focus, list):
        previous_focus = []

    previous_focus = [
        normalize_dashboard_ticker(ticker)
        for ticker in previous_focus
        if normalize_dashboard_ticker(ticker) in normalized_options
    ]

    target_count = min(max_items, len(normalized_options))
    for ticker in normalized_options:
        if ticker not in previous_focus:
            previous_focus.append(ticker)
        if len(previous_focus) >= target_count:
            break

    desired_focus = previous_focus[:target_count]
    if st.session_state.get(key) != desired_focus:
        st.session_state[key] = desired_focus

    return desired_focus




def planner_market_currency(ticker: str) -> str:
    return "TWD" if is_taiwan_ticker(ticker) else "USD"


def planner_currency_symbol(currency: str) -> str:
    return "NT$" if currency == "TWD" else "$"


def planner_market_title(currency: str) -> str:
    if get_language() == "zh_TW":
        return "台股情境試算" if currency == "TWD" else "美股情境試算"
    return "Taiwan scenario planner" if currency == "TWD" else "U.S. scenario planner"


def planner_market_caption(currency: str) -> str:
    if get_language() == "zh_TW":
        return "金額會以新台幣試算，漲幅區間與止損區間都只是參考情境，不是保證。"
    return "Capital is modeled in local currency. Upside and stop ranges are scenario references, not guarantees."


def planner_allocation_label(method: str) -> str:
    if get_language() == "zh_TW":
        return {
            "equal": "平均分配",
            "score_weighted": "依訊號強度分配",
        }.get(method, method)
    return {
        "equal": "Equal weight",
        "score_weighted": "Signal-weighted",
    }.get(method, method)


def planner_stop_profile_label(profile: str) -> str:
    if get_language() == "zh_TW":
        return {
            "tight": "偏緊止損",
            "balanced": "平衡止損",
            "wide": "寬鬆止損",
        }.get(profile, profile)
    return {
        "tight": "Tight stop",
        "balanced": "Balanced stop",
        "wide": "Wide stop",
    }.get(profile, profile)


def normalize_planner_timeframe(timeframe: str) -> str:
    timeframe = str(timeframe or "6m").strip()
    return timeframe if timeframe in PLANNER_TIMEFRAME_OPTIONS else "6m"


def planner_timeframe_label(timeframe: str) -> str:
    timeframe = normalize_planner_timeframe(timeframe)
    if get_language() == "zh_TW":
        return {
            "2w": "2 週",
            "1m": "1 個月",
            "3m": "3 個月",
            "6m": "6 個月",
            "9m": "9 個月",
            "1y": "1 年",
        }.get(timeframe, timeframe)
    return {
        "2w": "2 weeks",
        "1m": "1 month",
        "3m": "3 months",
        "6m": "6 months",
        "9m": "9 months",
        "1y": "1 year",
    }.get(timeframe, timeframe)


def active_target_watch_timeframe(ticker: str) -> str:
    currency = planner_market_currency(ticker)
    session_key = "scenario_planner_twd_timeframe" if currency == "TWD" else "scenario_planner_usd_timeframe"
    return normalize_planner_timeframe(st.session_state.get(session_key, st.session_state.get("dashboard_target_watch_timeframe", "6m")))



def planner_single_stock_title(bundle: dict, currency: str) -> str:
    label = display_ticker_label(bundle["ticker"])
    if get_language() == "zh_TW":
        return f"{label} 個股情境面板"
    return f"{label} single-stock scenario panel"


def planner_single_stock_caption(bundle: dict, currency: str) -> str:
    analysis = bundle.get("analysis", {}) or {}
    signal = tr_signal(analysis.get("signal", "HOLD"))
    confidence = tr_confidence(analysis.get("confidence", "Medium"))
    if get_language() == "zh_TW":
        return f"這裡不做多檔比較，而是把 {display_ticker_label(bundle['ticker'])} 的投入金額、分批進場、分批停利與風險容忍整理成單檔操作面板。當前訊號：{signal} · {confidence}。"
    return f"This panel focuses only on {display_ticker_label(bundle['ticker'])}, turning capital, staged entries, staged take-profit levels, and risk tolerance into a single-name action plan. Current signal: {signal} · {confidence}."




def planner_ratio_text(weights: list[int] | tuple[int, int, int]) -> str:
    return ", ".join(str(int(x)) for x in weights)


def parse_planner_ratio_input(raw_value: str | None, default: tuple[int, int, int]) -> list[int]:
    if raw_value is None:
        return list(default)
    text_value = str(raw_value).strip()
    if not text_value:
        return list(default)
    tokens = [token for token in re.split(r"[,%/|;\s]+", text_value) if token]
    try:
        values = [float(token) for token in tokens]
    except Exception:
        return list(default)
    if len(values) != 3 or any(value <= 0 for value in values):
        return list(default)
    total = sum(values)
    if total <= 0:
        return list(default)
    scaled = [int(round(value / total * 100.0)) for value in values]
    diff = 100 - sum(scaled)
    scaled[-1] += diff
    if any(value <= 0 for value in scaled):
        return list(default)
    return scaled


def normalize_planner_ratio_weights(stage_one: int, stage_two: int, default: tuple[int, int, int]) -> list[int]:
    try:
        first = int(stage_one)
        second = int(stage_two)
    except Exception:
        return list(default)

    first = max(5, min(90, first))
    second = max(5, second)
    if first + second >= 95:
        second = max(5, 95 - first)
    third = 100 - first - second
    if third < 5:
        third = 5
        second = max(5, 100 - first - third)
    weights = [first, second, 100 - first - second]
    if any(value <= 0 for value in weights) or sum(weights) != 100:
        return list(default)
    return weights


def default_planner_capital(currency: str) -> int:
    return 100000 if currency == "TWD" else 10000


def parse_planner_capital_input(raw_value, default_value: int) -> int:
    try:
        if raw_value is None:
            return int(default_value)
        text_value = str(raw_value).strip()
        if not text_value:
            return int(default_value)
        cleaned = re.sub(r"[^0-9]", "", text_value)
        if not cleaned:
            return int(default_value)
        return max(0, int(cleaned))
    except Exception:
        return int(default_value)






def format_planner_capital_value(value: int | float | str | None, default_value: int = 0) -> str:
    amount = parse_planner_capital_input(value, default_value)
    return f"{amount:,}"


def format_planner_display_amount(value: int | float | str | None, symbol: str = "", negative: bool = False) -> str:
    amount = coerce_float(value)
    if pd.isna(amount):
        return "N/A"
    rounded = int(round(abs(float(amount))))
    prefix = "-" if negative else ""
    return f"{prefix}{symbol}{rounded:,}"


def set_planner_capital_state(state_key: str, value: int | float | str | None, default_value: int = 0) -> None:
    st.session_state[f"{state_key}__pending"] = format_planner_capital_value(value, default_value)


def apply_planner_capital_state(state_key: str, default_value: int = 0) -> None:
    pending_key = f"{state_key}__pending"
    if pending_key in st.session_state:
        st.session_state[state_key] = st.session_state.pop(pending_key)
    elif state_key in st.session_state:
        st.session_state[state_key] = format_planner_capital_value(st.session_state.get(state_key), default_value)


def normalize_planner_capital_state(state_key: str, default_value: int = 0) -> None:
    raw_value = st.session_state.get(state_key)
    st.session_state[state_key] = format_planner_capital_value(raw_value, default_value)


def planner_quick_amount_options(currency: str) -> list[tuple[str, int]]:
    if currency == "TWD":
        return [("50K", 50_000), ("100K", 100_000), ("300K", 300_000), ("1M", 1_000_000)]
    return [("1K", 1_000), ("5K", 5_000), ("10K", 10_000), ("25K", 25_000)]


def planner_ratio_mode_label(value: str) -> str:
    labels = {
        "linked": "單一聯動" if get_language() == "zh_TW" else "Linked control",
        "detailed": "細部調整" if get_language() == "zh_TW" else "Detailed sliders",
    }
    return labels.get(value, value)


def planner_ratio_bias_label(value: int) -> str:
    lang_zh = get_language() == "zh_TW"
    if value <= 20:
        return "前段集中" if lang_zh else "Front-loaded"
    if value <= 40:
        return "略偏前段" if lang_zh else "Slightly front-loaded"
    if value < 60:
        return "平衡" if lang_zh else "Balanced"
    if value < 80:
        return "略偏後段" if lang_zh else "Slightly back-loaded"
    return "後段集中" if lang_zh else "Back-loaded"


def build_linked_ratio_weights(default: tuple[int, int, int], bias: int) -> list[int]:
    default_weights = list(default)
    base_first, base_second, _ = default_weights
    front_loaded = normalize_planner_ratio_weights(min(75, base_first + 25), max(10, base_second - 10), default)
    back_loaded = normalize_planner_ratio_weights(max(10, base_first - 15), max(10, base_second - 15), default)

    bias = max(0, min(100, int(bias)))
    if bias <= 50:
        mix = bias / 50.0
        stage_one = round(front_loaded[0] * (1 - mix) + base_first * mix)
        stage_two = round(front_loaded[1] * (1 - mix) + base_second * mix)
    else:
        mix = (bias - 50) / 50.0
        stage_one = round(base_first * (1 - mix) + back_loaded[0] * mix)
        stage_two = round(base_second * (1 - mix) + back_loaded[1] * mix)

    return normalize_planner_ratio_weights(stage_one, stage_two, default)



def render_planner_ratio_slider(
    title: str,
    copy: str,
    key_prefix: str,
    default: tuple[int, int, int],
    fill_class: str = "",
) -> list[int]:
    default_weights = list(default)
    stage_one_key = f"{key_prefix}_stage1"
    stage_two_key = f"{key_prefix}_stage2"
    mode_key = f"{key_prefix}_mode"
    bias_key = f"{key_prefix}_bias"

    if stage_one_key not in st.session_state:
        st.session_state[stage_one_key] = int(default_weights[0])
    if stage_two_key not in st.session_state:
        st.session_state[stage_two_key] = int(default_weights[1])
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "linked"
    if bias_key not in st.session_state:
        st.session_state[bias_key] = 50

    lang_zh = get_language() == "zh_TW"
    mode = st.radio(
        f"{title} · {'控制模式' if lang_zh else 'Control mode'}",
        options=["linked", "detailed"],
        format_func=planner_ratio_mode_label,
        horizontal=True,
        key=mode_key,
        label_visibility="collapsed",
    )

    if mode == "linked":
        bias = st.slider(
            f"{title} · {'配置偏向' if lang_zh else 'Bias'}",
            min_value=0,
            max_value=100,
            value=int(st.session_state[bias_key]),
            key=bias_key,
            help="越偏左代表越集中前段，越偏右代表越集中後段。" if lang_zh else "Left loads earlier stages more aggressively. Right shifts more weight toward later stages.",
        )
        weights = build_linked_ratio_weights(default, bias)
        st.session_state[stage_one_key] = int(weights[0])
        st.session_state[stage_two_key] = int(weights[1])
        render_html_block(
            f"""
            <div class="planner-slider-locked-note planner-slider-locked-note-soft">
                <span>{escape('單一聯動控制' if lang_zh else 'Single linked control')}</span>
                <strong>{escape(planner_ratio_bias_label(bias))}</strong>
                <span>{escape('系統會自動保持三段合計 100%，並避免邊界錯誤。' if lang_zh else 'The ladder stays at 100% automatically and avoids edge-case slider locks.')}</span>
            </div>
            """
        )
    else:
        stage_one = st.slider(
            f"{title} · {'第 1 段' if lang_zh else 'Stage 1'}",
            min_value=5,
            max_value=90,
            value=int(st.session_state[stage_one_key]),
            key=stage_one_key,
        )
        stage_two_max = max(5, 95 - int(stage_one))
        if int(st.session_state[stage_two_key]) > stage_two_max:
            st.session_state[stage_two_key] = min(int(default_weights[1]), stage_two_max)
        stage_two_label = f"{title} · {'第 2 段' if lang_zh else 'Stage 2'}"
        if stage_two_max <= 5:
            stage_two = 5
            st.session_state[stage_two_key] = 5
            render_html_block(
                f"""
                <div class="planner-slider-locked-note">
                    <span>{escape(stage_two_label)}</span>
                    <strong>5%</strong>
                    <span>{escape("已固定，因為第 3 段至少保留 5%" if lang_zh else "Locked because Stage 3 must keep at least 5%.")}</span>
                </div>
                """
            )
        else:
            stage_two = st.slider(
                stage_two_label,
                min_value=5,
                max_value=stage_two_max,
                value=min(int(st.session_state[stage_two_key]), stage_two_max),
                key=stage_two_key,
            )
        weights = normalize_planner_ratio_weights(stage_one, stage_two, default)

    stage_labels = ['第 1 段', '第 2 段', '第 3 段'] if lang_zh else ['Stage 1', 'Stage 2', 'Stage 3']
    bar_class = f"scenario-ratio-fill {fill_class}".strip()
    bars = "".join([
        f"""
        <div class="scenario-ratio-bar">
            <div class="scenario-ratio-bar-label">{escape(stage_labels[idx])}</div>
            <div class="scenario-ratio-track"><div class="{bar_class}" style="width:{int(weight)}%;"></div></div>
            <div class="scenario-ratio-bar-value">{int(weight)}%</div>
        </div>
        """
        for idx, weight in enumerate(weights)
    ])
    distribution_segments = "".join([
        f'<div class="scenario-ratio-segment scenario-ratio-segment-{idx + 1}" style="width:{int(weight)}%;">{escape(stage_labels[idx])} {int(weight)}%</div>'
        for idx, weight in enumerate(weights)
    ])
    legend = "".join([
        f"""
        <div class="scenario-ratio-legend-item">
            <span class="scenario-ratio-legend-dot scenario-ratio-legend-dot-{idx + 1}"></span>
            <span>{escape(stage_labels[idx])} · {int(weight)}%</span>
        </div>
        """
        for idx, weight in enumerate(weights)
    ])
    render_html_block(
        f"""
        <div class="scenario-ratio-shell">
            <div class="scenario-ratio-title">{escape(title)}</div>
            <div class="scenario-ratio-copy">{escape(copy)}</div>
            <div class="scenario-ratio-value">{escape(planner_ratio_text(weights))}</div>
            <div class="scenario-ratio-distribution">{distribution_segments}</div>
            <div class="scenario-ratio-legend">{legend}</div>
            <div class="scenario-ratio-bars">{bars}</div>
        </div>
        """
    )
    return weights


def compute_planner_action_recommendation(summary: dict) -> dict:
    lang_zh = get_language() == "zh_TW"
    risk_reward_ratio = float(summary.get("risk_reward_ratio", 0.0) or 0.0)
    assumed_win_rate = float(summary.get("assumed_win_rate", 0.0) or 0.0)
    expected_value = float(summary.get("expected_value", 0.0) or 0.0)
    suggested_position_pct = float(summary.get("suggested_position_pct", 0.0) or 0.0)

    if expected_value >= 0 and risk_reward_ratio >= 1.8 and assumed_win_rate >= 0.58 and suggested_position_pct >= 65:
        return {
            "class": "planner-decision-action planner-decision-action-good",
            "title": "建議加碼" if lang_zh else "Suggested action: Add",
            "copy": (
                "風報比、期望值與建議倉位都站在偏強的一側，可以沿著分批進場規則做順勢加碼，但仍要把總風險控在可承受區間。"
                if lang_zh else
                "Risk/reward, expectancy, and suggested sizing all lean constructive. You can add through the staged ladder, while still keeping total risk inside your budget."
            ),
            "pills": [
                "順勢執行" if lang_zh else "Trend-follow",
                "分批加碼" if lang_zh else "Add in tranches",
                "保留最後一段火力" if lang_zh else "Keep final tranche",
            ],
        }

    if expected_value < 0 or risk_reward_ratio < 0.95 or suggested_position_pct <= 35:
        return {
            "class": "planner-decision-action planner-decision-action-bad",
            "title": "建議減碼 / 收斂風險" if lang_zh else "Suggested action: Reduce risk",
            "copy": (
                "目前風報比或期望值不夠有利，較好的做法是縮小倉位、把停損收緊，或先降低曝險等待更乾淨的訊號。"
                if lang_zh else
                "The setup is not paying enough for the risk right now. A better move is to reduce size, tighten stops, or cut exposure until the signal improves."
            ),
            "pills": [
                "降低倉位" if lang_zh else "Cut size",
                "提高現金比重" if lang_zh else "Raise cash",
                "等待重置" if lang_zh else "Wait for reset",
            ],
        }

    return {
        "class": "planner-decision-action planner-decision-action-warn",
        "title": "建議等待 / 分批布局" if lang_zh else "Suggested action: Wait / Build gradually",
        "copy": (
            "這是一個可以觀察並逐步佈局的狀態。先用前兩段小倉測試，等價格與新聞催化更一致後，再決定是否完成最後一段。"
            if lang_zh else
            "This is a selective setup. Start with smaller early tranches and only complete the final leg if price action and catalysts align more cleanly."
        ),
        "pills": [
            "先小倉試單" if lang_zh else "Probe small",
            "等催化確認" if lang_zh else "Wait for catalyst",
            "保留調整空間" if lang_zh else "Keep flexibility",
        ],
    }

def render_planner_decision_board(summary: dict, symbol: str, entry_weights: list[int], take_profit_weights: list[int], win_rate_mode: str):
    if not summary:
        return

    lang_zh = get_language() == "zh_TW"
    risk_reward_ratio = float(summary.get("risk_reward_ratio", 0.0) or 0.0)
    assumed_win_rate = float(summary.get("assumed_win_rate", 0.0) or 0.0)
    expected_value = float(summary.get("expected_value", 0.0) or 0.0)
    suggested_position_pct = float(summary.get("suggested_position_pct", 0.0) or 0.0)
    recommended_capital = float(summary.get("recommended_capital", 0.0) or 0.0)
    acceptable_loss_amount = float(summary.get("acceptable_loss_amount", 0.0) or 0.0)

    if expected_value >= 0 and risk_reward_ratio >= 1.8:
        stance_text = "可積極執行" if lang_zh else "Constructive setup"
        stance_class = "planner-decision-chip planner-decision-chip-good"
    elif expected_value >= 0 and risk_reward_ratio >= 1.1:
        stance_text = "可選擇性執行" if lang_zh else "Selective setup"
        stance_class = "planner-decision-chip planner-decision-chip-warn"
    else:
        stance_text = "先收斂風險" if lang_zh else "Tighten risk first"
        stance_class = "planner-decision-chip planner-decision-chip-bad"

    expected_chip_class = "planner-decision-chip planner-decision-chip-good" if expected_value >= 0 else "planner-decision-chip planner-decision-chip-bad"
    expected_chip_text = (
        f"期望值 {symbol}{expected_value:,.0f}"
        if lang_zh
        else f"Expected value {symbol}{expected_value:,.0f}"
    )

    action = compute_planner_action_recommendation(summary)
    action_pills = "".join(
        f'<div class="planner-decision-action-pill">{escape(str(pill))}</div>'
        for pill in action.get("pills", [])
    )

    board_html = f'''
    <div class="planner-decision-shell">
        <div class="planner-decision-head">
            <div>
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("進階決策面板" if lang_zh else "Advanced decision board")}</div>
                <div class="guide-copy">{escape("把風報比、勝率假設、期望值與建議倉位集中成一個更接近實戰的執行面板。" if lang_zh else "A compact execution board that pulls risk/reward, hit-rate, expectancy, and suggested sizing into one practical decision layer.")}</div>
            </div>
            <div class="planner-decision-chip-row">
                <div class="{stance_class}">{escape(stance_text)}</div>
                <div class="{expected_chip_class}">{escape(expected_chip_text)}</div>
            </div>
        </div>
        <div class="planner-decision-grid">
            <div class="planner-decision-card">
                <div class="planner-decision-label">{escape("風報比" if lang_zh else "Risk / reward")}</div>
                <div class="planner-decision-kpi planner-decision-kpi-up">{risk_reward_ratio:.2f}R</div>
                <div class="planner-decision-copy">{escape("以基準情境獲利 ÷ 止損風險估算。" if lang_zh else "Estimated as base-case upside divided by modeled stop-loss risk.")}</div>
            </div>
            <div class="planner-decision-card">
                <div class="planner-decision-label">{escape("勝率假設" if lang_zh else "Hit-rate assumption")}</div>
                <div class="planner-decision-kpi">{assumed_win_rate * 100:.0f}%</div>
                <div class="planner-decision-copy">{escape(planner_win_rate_label(win_rate_mode))}</div>
            </div>
            <div class="planner-decision-card">
                <div class="planner-decision-label">{escape("建議倉位" if lang_zh else "Suggested sizing")}</div>
                <div class="planner-decision-kpi planner-decision-kpi-gold">{suggested_position_pct:.0f}%</div>
                <div class="planner-decision-copy">{escape((f"建議資金上限 {symbol}{recommended_capital:,.0f}") if lang_zh else (f"Suggested cap {symbol}{recommended_capital:,.0f}"))}</div>
            </div>
            <div class="planner-decision-card">
                <div class="planner-decision-label">{escape("分批規則" if lang_zh else "Ladder mix")}</div>
                <div class="planner-decision-kpi">{escape(planner_ratio_text(entry_weights))}</div>
                <div class="planner-decision-copy">{escape((f"進場 {planner_ratio_text(entry_weights)} · 停利 {planner_ratio_text(take_profit_weights)} · 風險預算 {symbol}{acceptable_loss_amount:,.0f}") if lang_zh else (f"Entry {planner_ratio_text(entry_weights)} · Exit {planner_ratio_text(take_profit_weights)} · Risk budget {symbol}{acceptable_loss_amount:,.0f}"))}</div>
            </div>
        </div>
        <div class="{action.get('class', 'planner-decision-action')}">
            <div class="planner-decision-action-label">{escape("明確行動建議" if lang_zh else "Action recommendation")}</div>
            <div class="planner-decision-action-title">{escape(str(action.get('title', '')))}</div>
            <div class="planner-decision-action-copy">{escape(str(action.get('copy', '')))}</div>
            <div class="planner-decision-action-row">{action_pills}</div>
        </div>
    </div>
    '''
    render_html_block(board_html)

def planner_win_rate_label(mode: str) -> str:
    if get_language() == "zh_TW":
        return {
            "conservative": "保守勝率",
            "balanced": "平衡勝率",
            "aggressive": "積極勝率",
        }.get(mode, mode)
    return {
        "conservative": "Conservative hit rate",
        "balanced": "Balanced hit rate",
        "aggressive": "Aggressive hit rate",
    }.get(mode, mode)


def compute_planner_win_rate(scenario_df: pd.DataFrame, mode: str = "balanced") -> float:
    base_map = {"conservative": 0.45, "balanced": 0.55, "aggressive": 0.65}
    win_rate = float(base_map.get(mode, 0.55))
    if scenario_df is not None and not scenario_df.empty and "quality_score" in scenario_df.columns:
        quality_avg = float(pd.to_numeric(scenario_df["quality_score"], errors="coerce").fillna(0).mean())
        win_rate += max(-0.10, min(0.10, quality_avg * 0.03))
    return float(max(0.25, min(0.80, win_rate)))


def render_portfolio_execution_panel(
    scenario_df: pd.DataFrame,
    summary: dict,
    symbol: str,
    entry_weights: list[int],
    take_profit_weights: list[int],
    win_rate_mode: str,
):
    if scenario_df is None or scenario_df.empty:
        return

    lang_zh = get_language() == "zh_TW"
    risk_reward_ratio = float(summary.get("risk_reward_ratio", 0.0) or 0.0)
    assumed_win_rate = float(summary.get("assumed_win_rate", 0.0) or 0.0)
    expected_value = float(summary.get("expected_value", 0.0) or 0.0)
    suggested_position_pct = float(summary.get("suggested_position_pct", 0.0) or 0.0)

    shell_html = f"""
    <div class="scenario-single-shell">
        <div class="section-header" style="margin:0; color:#eef4ff;">{escape("多檔執行框架" if lang_zh else "Portfolio execution framework")}</div>
        <div class="scenario-single-grid">
            <div class="scenario-single-card">
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("分批規則" if lang_zh else "Ladder ratios")}</div>
                <div class="scenario-single-value">{escape("進場 " + planner_ratio_text(entry_weights) if lang_zh else "Entry " + planner_ratio_text(entry_weights))}</div>
                <div class="scenario-single-copy">{escape("停利 " + planner_ratio_text(take_profit_weights) if lang_zh else "Take profit " + planner_ratio_text(take_profit_weights))}</div>
            </div>
            <div class="scenario-single-card">
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("風報比" if lang_zh else "Risk / reward")}</div>
                <div class="scenario-single-value">{risk_reward_ratio:.2f}R</div>
                <div class="scenario-single-copy">{escape("以基準情境獲利 ÷ 止損風險估算。" if lang_zh else "Estimated as base-case upside divided by modeled stop-loss risk.")}</div>
            </div>
            <div class="scenario-single-card">
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("勝率假設" if lang_zh else "Hit-rate assumption")}</div>
                <div class="scenario-single-value">{assumed_win_rate * 100:.0f}%</div>
                <div class="scenario-single-copy">{escape(planner_win_rate_label(win_rate_mode))}</div>
            </div>
            <div class="scenario-single-card">
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("建議倉位" if lang_zh else "Suggested sizing")}</div>
                <div class="scenario-single-value">{suggested_position_pct:.0f}%</div>
                <div class="scenario-single-copy">{escape((f"對應資金上限 {symbol}{float(summary.get('recommended_capital', 0.0)):,.0f}") if lang_zh else (f"Cap near {symbol}{float(summary.get('recommended_capital', 0.0)):,.0f}"))}</div>
            </div>
        </div>
    </div>
    """
    render_html_block(shell_html)

    expected_class = "scenario-summary-badge" if expected_value >= 0 else "scenario-summary-badge scenario-summary-badge-danger"
    ev_html = f"""
    <div class="compare-shell">
        <div class="compare-topline">
            <div>
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape("進場 / 停利 / 風險摘要" if lang_zh else "Entry / exit / risk summary")}</div>
                <div class="compare-copy">{escape("每檔股票都保留分批進場、分批停利與風險預算，讓多檔配置也能直接執行。" if lang_zh else "Every selected stock keeps a staged entry, staged take-profit, and risk budget so the multi-name planner remains executable.")}</div>
            </div>
            <div class="{expected_class}">{escape((f"期望值 {symbol}{expected_value:,.0f}") if lang_zh else (f"Expected value {symbol}{expected_value:,.0f}"))}</div>
        </div>
    </div>
    """
    render_html_block(ev_html)

    card_chunks = []
    for _, row in scenario_df.iterrows():
        card_chunks.append(
            textwrap.dedent(
                f"""
                <div class="scenario-single-card">
                    <div class="section-header" style="margin:0; color:#eef4ff;">{escape(str(row.get('ticker_label', '')))}</div>
                    <div class="scenario-single-value">{escape(str(row.get('signal', '')))}</div>
                    <div class="scenario-single-copy">{escape((f"配置 {float(row.get('allocation_pct', 0.0)):.1f}% · 風險預算 {symbol}{float(row.get('max_loss_budget', 0.0)):,.0f}") if lang_zh else (f"Weight {float(row.get('allocation_pct', 0.0)):.1f}% · Risk budget {symbol}{float(row.get('max_loss_budget', 0.0)):,.0f}"))}</div>
                    <div class="scenario-ladder">
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag">{escape("分批進場" if lang_zh else "Entry ladder")}</span></div>
                            <div><div class="scenario-ladder-main">{escape(str(row.get('entry_plan', 'N/A')))}</div></div>
                        </div>
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag scenario-ladder-tag-up">{escape("分批停利" if lang_zh else "Take-profit")}</span></div>
                            <div><div class="scenario-ladder-main">{escape(str(row.get('take_profit_plan', 'N/A')))}</div></div>
                        </div>
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag scenario-ladder-tag-down">{escape("止損帶" if lang_zh else "Stop band")}</span></div>
                            <div><div class="scenario-ladder-main">{escape(str(row.get('stop_range', 'N/A')))}</div></div>
                        </div>
                    </div>
                </div>
                """
            ).strip()
        )
    render_html_block(f'<div class="scenario-single-shell"><div class="scenario-single-grid">{"".join(card_chunks)}</div></div>')
def build_entry_ladder(plan: dict, entry_weights: list[int] | None = None) -> list[dict]:
    current_price = coerce_float(plan.get("current_price"))
    target_ctx = plan.get("target_context", {}) or {}
    support = coerce_float(target_ctx.get("support_level"))
    if pd.isna(support):
        support = np.nan
    balanced_stop_pct = abs(coerce_float(plan.get("stop_balanced")))
    if pd.isna(current_price) or current_price <= 0:
        return []

    if pd.isna(support) or support <= 0 or support >= current_price:
        support = current_price * (1 - min(max(balanced_stop_pct * 0.55, 2.0), 8.0) / 100.0)
    deeper = support * (1 - min(max(balanced_stop_pct * 0.35, 1.5), 4.5) / 100.0)

    signal = str(plan.get("signal", "HOLD") or "HOLD").upper()
    default_weights = [45, 35, 20] if signal == "BUY" else [25, 35, 40] if signal == "SELL" else [35, 35, 30]
    weights = entry_weights or default_weights
    if signal == "BUY":
        parts = [(weights[0], current_price, "先建立核心部位" if get_language() == "zh_TW" else "Start with a core position"),
                 (weights[1], support, "若回踩支撐再加碼" if get_language() == "zh_TW" else "Add on a support retest"),
                 (weights[2], deeper, "僅在更深回檔才補滿" if get_language() == "zh_TW" else "Complete size only on a deeper pullback")]
    elif signal == "SELL":
        parts = [(weights[0], current_price, "僅少量試單" if get_language() == "zh_TW" else "Only probe with small size"),
                 (weights[1], support, "必須確認支撐有效" if get_language() == "zh_TW" else "Require support confirmation"),
                 (weights[2], deeper, "更好價格才考慮加碼" if get_language() == "zh_TW" else "Only add at meaningfully better prices")]
    else:
        parts = [(weights[0], current_price, "先保留彈性" if get_language() == "zh_TW" else "Keep flexibility at the start"),
                 (weights[1], support, "回測支撐再補第二段" if get_language() == "zh_TW" else "Use a support retest for the second tranche"),
                 (weights[2], deeper, "最後一段留給更佳風報比" if get_language() == "zh_TW" else "Reserve the last tranche for a better risk/reward")]

    ladder = []
    stage_labels = ["第 1 段", "第 2 段", "第 3 段"] if get_language() == "zh_TW" else ["Stage 1", "Stage 2", "Stage 3"]
    for idx, (weight, level, note) in enumerate(parts):
        if pd.isna(level) or level <= 0:
            level = current_price
        ladder.append(
            {
                "label": stage_labels[idx],
                "weight_pct": int(weight),
                "price": float(level),
                "note": note,
            }
        )
    return ladder


def build_take_profit_ladder(plan: dict, take_profit_weights: list[int] | None = None) -> list[dict]:
    current_price = coerce_float(plan.get("current_price"))
    if pd.isna(current_price) or current_price <= 0:
        return []
    weights = take_profit_weights or [30, 40, 30]
    targets = [
        ("TP1", weights[0], coerce_float(plan.get("conservative_up")), "先回收風險資本" if get_language() == "zh_TW" else "Take back initial risk"),
        ("TP2", weights[1], coerce_float(plan.get("base_up")), "保留主趨勢核心倉位" if get_language() == "zh_TW" else "Keep the core position for trend continuation"),
        ("TP3", weights[2], coerce_float(plan.get("stretch_up")), "延伸目標才處理最後部位" if get_language() == "zh_TW" else "Only release the final tranche at the stretch target"),
    ]
    ladder = []
    for label, weight_pct, up_pct, note in targets:
        if pd.isna(up_pct):
            continue
        ladder.append(
            {
                "label": label,
                "weight_pct": int(weight_pct),
                "target_pct": float(up_pct),
                "price": float(current_price * (1 + up_pct / 100.0)),
                "note": note,
            }
        )
    return ladder




def planner_entry_fill_probabilities(timeframe: str, stage_count: int = 3) -> list[float]:
    timeframe_key = normalize_planner_timeframe(timeframe)
    default_profile = list(PLANNER_ENTRY_FILL_PROBABILITIES.get(timeframe_key, (1.0, 0.72, 0.48)))
    if stage_count <= 0:
        return []
    profile = default_profile[:stage_count]
    while len(profile) < stage_count:
        profile.append(profile[-1] if profile else 1.0)
    return [float(np.clip(value, 0.05, 1.0)) for value in profile]


def compute_entry_execution_profile(
    plan: dict,
    allocation: float,
    timeframe: str = "6m",
    stop_profile: str = "balanced",
    entry_weights: list[int] | None = None,
) -> dict:
    current_price = coerce_float(plan.get("current_price"))
    entry_ladder = build_entry_ladder(plan, entry_weights=entry_weights)
    if pd.isna(current_price) or current_price <= 0 or allocation <= 0 or not entry_ladder:
        return {
            "ladder": entry_ladder,
            "fill_probabilities": [],
            "stages": [],
            "deployed_capital": 0.0,
            "deployed_ratio": 0.0,
            "units": 0.0,
            "average_entry_price": current_price,
            "stop_price": np.nan,
            "stop_loss_amount": 0.0,
        }

    fill_probabilities = planner_entry_fill_probabilities(timeframe, len(entry_ladder))
    stop_key = {"tight": "stop_tight", "balanced": "stop_balanced", "wide": "stop_wide"}.get(stop_profile, "stop_balanced")
    stop_pct = abs(coerce_float(plan.get(stop_key)))
    stop_price = current_price * (1.0 - (0.0 if pd.isna(stop_pct) else float(stop_pct) / 100.0))

    stages = []
    deployed_capital = 0.0
    total_units = 0.0
    stop_loss_amount = 0.0

    for stage, fill_prob in zip(entry_ladder, fill_probabilities):
        stage_weight = max(coerce_float(stage.get("weight_pct")), 0.0) / 100.0
        stage_price = coerce_float(stage.get("price"))
        if pd.isna(stage_price) or stage_price <= 0:
            stage_price = current_price

        committed_capital = float(allocation) * stage_weight
        expected_deployed = committed_capital * float(fill_prob)
        stage_units = expected_deployed / stage_price if stage_price > 0 else 0.0
        stage_stop_loss = max(stage_price - stop_price, 0.0) * stage_units if pd.notna(stop_price) else 0.0

        deployed_capital += expected_deployed
        total_units += stage_units
        stop_loss_amount += stage_stop_loss
        stages.append(
            {
                "label": stage.get("label"),
                "weight_pct": float(stage.get("weight_pct", 0.0) or 0.0),
                "fill_probability": float(fill_prob),
                "committed_capital": float(committed_capital),
                "deployed_capital": float(expected_deployed),
                "price": float(stage_price),
                "units": float(stage_units),
                "stop_loss_amount": float(stage_stop_loss),
            }
        )

    average_entry_price = (deployed_capital / total_units) if total_units > 0 else current_price
    deployed_ratio = (deployed_capital / float(allocation)) if float(allocation) > 0 else 0.0

    return {
        "ladder": entry_ladder,
        "fill_probabilities": fill_probabilities,
        "stages": stages,
        "deployed_capital": float(deployed_capital),
        "deployed_ratio": float(deployed_ratio),
        "units": float(total_units),
        "average_entry_price": float(average_entry_price) if pd.notna(average_entry_price) else current_price,
        "stop_price": float(stop_price) if pd.notna(stop_price) else np.nan,
        "stop_loss_amount": float(stop_loss_amount),
    }


def compute_take_profit_profile(plan: dict, take_profit_weights: list[int] | None = None) -> dict:
    weights = take_profit_weights or [30, 40, 30]
    conservative_up = coerce_float(plan.get("conservative_up"))
    base_up = coerce_float(plan.get("base_up"))
    stretch_up = coerce_float(plan.get("stretch_up"))

    targets = [
        0.0 if pd.isna(conservative_up) else float(conservative_up),
        0.0 if pd.isna(base_up) else float(base_up),
        0.0 if pd.isna(stretch_up) else float(stretch_up),
    ]
    normalized_weights = [max(float(weight), 0.0) for weight in weights[:3]]
    while len(normalized_weights) < 3:
        normalized_weights.append(0.0)
    total_weight = sum(normalized_weights) or 100.0
    normalized_weights = [weight / total_weight for weight in normalized_weights]

    weighted_up = sum(weight * target for weight, target in zip(normalized_weights, targets))
    conservative_weighted_up = sum(weight * target for weight, target in zip(normalized_weights, [targets[0], targets[0], targets[1]]))
    stretch_weighted_up = sum(weight * target for weight, target in zip(normalized_weights, [targets[1], targets[2], targets[2]]))

    return {
        "weighted_up": float(weighted_up),
        "conservative_weighted_up": float(conservative_weighted_up),
        "stretch_weighted_up": float(stretch_weighted_up),
    }


def format_entry_ladder_inline(ladder: list[dict], symbol: str) -> str:
    if not ladder:
        return "N/A"
    if get_language() == "zh_TW":
        return " / ".join(f"{row['label']} {row['weight_pct']}%@{format_planner_display_amount(row['price'], symbol)}" for row in ladder)
    return " / ".join(f"{row['label']} {row['weight_pct']}%@{format_planner_display_amount(row['price'], symbol)}" for row in ladder)


def format_take_profit_inline(ladder: list[dict], symbol: str) -> str:
    if not ladder:
        return "N/A"
    return " / ".join(f"{row['label']} {row['weight_pct']}%@+{row['target_pct']:.1f}%" for row in ladder)


def render_planner_ladder_card(title: str, kicker: str, rows: list[dict], symbol: str, is_take_profit: bool = False):
    if not rows:
        return
    row_html_parts = []
    for row in rows:
        main = (
            f"{row['weight_pct']}% · {format_planner_display_amount(row['price'], symbol)} · +{row['target_pct']:.1f}%"
            if is_take_profit
            else f"{row['weight_pct']}% · {format_planner_display_amount(row['price'], symbol)}"
        )
        row_html_parts.append(
            textwrap.dedent(
                f"""
                <div class="scenario-ladder-row">
                    <div><span class="scenario-ladder-tag {'scenario-ladder-tag-up' if is_take_profit else ''}">{escape(str(row['label']))}</span></div>
                    <div>
                        <div class="scenario-ladder-main">{escape(main)}</div>
                        <div class="scenario-ladder-sub">{escape(str(row.get('note', '')))}</div>
                    </div>
                </div>
                """
            ).strip()
        )
    html = f"""
    <div class="scenario-single-card">
        <div class="section-header" style="margin:0; color:#eef4ff;">{escape(kicker)}</div>
        <div class="scenario-single-value">{escape(title)}</div>
        <div class="scenario-ladder">
            {''.join(row_html_parts)}
        </div>
    </div>
    """
    render_html_block(html)


def render_single_stock_operating_panel(bundle: dict, plan: dict, symbol: str, stop_profile: str, timeframe: str, acceptable_loss_pct: float, summary: dict, entry_weights: list[int] | None = None, take_profit_weights: list[int] | None = None):
    lang_zh = get_language() == "zh_TW"
    entry_ladder = build_entry_ladder(plan, entry_weights=entry_weights)
    take_profit_ladder = build_take_profit_ladder(plan, take_profit_weights=take_profit_weights)
    stop_key = {"tight": "stop_tight", "balanced": "stop_balanced", "wide": "stop_wide"}.get(stop_profile, "stop_balanced")
    stop_pct = abs(coerce_float(plan.get(stop_key)))
    current_price = coerce_float(plan.get("current_price"))
    capital = coerce_float(summary.get("capital"))
    acceptable_loss_amount = coerce_float(summary.get("acceptable_loss_amount"))
    stop_loss_total = coerce_float(summary.get("stop_loss_total"))
    if pd.isna(current_price):
        current_price = 0.0
    if pd.isna(capital):
        capital = 0.0
    if pd.isna(acceptable_loss_amount):
        acceptable_loss_amount = 0.0
    if pd.isna(stop_loss_total):
        stop_loss_total = 0.0

    target_title = "分批停利規劃" if lang_zh else "Staged take-profit plan"
    entry_title = "分批進場規劃" if lang_zh else "Staged entry plan"
    kicker = "單檔操作節奏" if lang_zh else "Single-name execution"
    risk_text = (
        f"最大可承受虧損 {format_planner_display_amount(acceptable_loss_amount, symbol)}（{acceptable_loss_pct:.1f}%）。目前止損情境約 {format_planner_display_amount(stop_loss_total, symbol)}，{'落在容忍範圍內' if stop_loss_total <= acceptable_loss_amount else '高於目前容忍範圍，建議縮小部位或等更佳進場價'}。"
        if lang_zh
        else f"Max acceptable loss is {format_planner_display_amount(acceptable_loss_amount, symbol)} ({acceptable_loss_pct:.1f}%). Current modeled stop-loss is about {format_planner_display_amount(stop_loss_total, symbol)}, which {'sits within tolerance' if stop_loss_total <= acceptable_loss_amount else 'runs above tolerance, so consider a smaller size or a better entry price'}."
    )
    shell_html = f"""
    <div class="scenario-single-shell">
        <div class="section-header" style="margin:0; color:#eef4ff;">{escape(kicker)}</div>
        <div class="scenario-single-grid">
            <div class="scenario-single-card">
                <div class="section-header" style="margin:0; color:#eef4ff;">{escape('個股操作摘要' if lang_zh else 'Single-stock brief')}</div>
                <div class="scenario-single-value">{escape(display_ticker_label(bundle['ticker']))}</div>
                <div class="scenario-single-copy">{escape(planner_single_stock_caption(bundle, planner_market_currency(bundle['ticker'])))}</div>
                <div class="scenario-ladder">
                    <div class="scenario-ladder-row">
                        <div><span class="scenario-ladder-tag">{escape('期限' if lang_zh else 'Horizon')}</span></div>
                        <div>
                            <div class="scenario-ladder-main">{escape(planner_timeframe_label(timeframe))}</div>
                            <div class="scenario-ladder-sub">{escape(plan.get('reference_note', ''))}</div>
                        </div>
                    </div>
                    <div class="scenario-ladder-row">
                        <div><span class="scenario-ladder-tag scenario-ladder-tag-down">{escape('風險' if lang_zh else 'Risk')}</span></div>
                        <div>
                            <div class="scenario-ladder-main">{escape(risk_text)}</div>
                            <div class="scenario-ladder-sub">{escape(('目前止損參考：' + planner_stop_profile_label(stop_profile)) if lang_zh else ('Current stop profile: ' + planner_stop_profile_label(stop_profile)))}</div>
                        </div>
                    </div>
                </div>
            </div>
            <div>
                <div class="scenario-single-card">
                    <div class="section-header" style="margin:0; color:#eef4ff;">{escape('操作價位' if lang_zh else 'Working levels')}</div>
                    <div class="scenario-ladder">
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag">{escape('現價' if lang_zh else 'Price')}</span></div>
                            <div><div class="scenario-ladder-main">{escape(format_planner_display_amount(current_price, symbol))}</div></div>
                        </div>
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag scenario-ladder-tag-up">{escape('TP2' if lang_zh else 'TP2')}</span></div>
                            <div><div class="scenario-ladder-main">{escape(format_planner_display_amount(current_price * (1 + coerce_float(plan.get("base_up")) / 100.0), symbol))}</div><div class="scenario-ladder-sub">{escape(('基準情境目標' if lang_zh else 'Base-case target'))}</div></div>
                        </div>
                        <div class="scenario-ladder-row">
                            <div><span class="scenario-ladder-tag scenario-ladder-tag-down">{escape('SL' if lang_zh else 'SL')}</span></div>
                            <div><div class="scenario-ladder-main">{escape(f'-{abs(stop_pct):.1f}%')}</div><div class="scenario-ladder-sub">{escape(('目前採用的止損參考' if lang_zh else 'Current stop profile in use'))}</div></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    render_html_block(shell_html)
    render_planner_ladder_card(entry_title, "分批進場" if lang_zh else "Staged entry", entry_ladder, symbol, is_take_profit=False)
    render_planner_ladder_card(target_title, "分批停利" if lang_zh else "Staged exit", take_profit_ladder, symbol, is_take_profit=True)

def estimate_position_scenario(bundle: dict, timeframe: str = "6m") -> dict:
    ticker = bundle["ticker"]
    price_series = bundle.get("price_series")
    analysis = bundle.get("analysis", {})
    trading_lab = analysis.get("trading_lab", {}) or {}
    target_ctx = build_target_watch_context(ticker, price_series, bundle.get("news_items", []), timeframe=timeframe)

    current_price = coerce_float(analysis.get("last_price"))
    if pd.isna(current_price) and price_series is not None and not price_series.empty:
        current_price = coerce_float(price_series.iloc[-1])

    series = to_numeric_series(price_series).dropna() if price_series is not None else pd.Series(dtype="float64")
    monthly_vol = np.nan
    if len(series) >= 20:
        pct = series.pct_change().dropna()
        if not pct.empty:
            monthly_vol = float(pct.tail(20).std() * np.sqrt(20) * 100)

    signal = str(analysis.get("signal", "HOLD") or "HOLD").upper()
    timeframe = normalize_planner_timeframe(timeframe)
    upside_time_multiplier = PLANNER_UPSIDE_MULTIPLIERS[timeframe]
    stop_time_multiplier = PLANNER_STOP_MULTIPLIERS[timeframe]
    months = PLANNER_TIMEFRAME_MONTHS[timeframe]

    base_defaults = {
        "BUY": (6.0, 12.0, 20.0, 5.5),
        "HOLD": (4.0, 8.5, 14.0, 6.5),
        "SELL": (2.0, 5.0, 9.0, 5.0),
    }
    cons_default, base_default, stretch_default, stop_default = base_defaults.get(signal, base_defaults["HOLD"])
    cons_default *= upside_time_multiplier
    base_default *= upside_time_multiplier
    stretch_default *= upside_time_multiplier
    stop_default *= stop_time_multiplier

    if pd.notna(monthly_vol):
        horizon_vol = float(monthly_vol * np.sqrt(months / 6.0))
        cons_default = float(np.clip(horizon_vol * 0.65, 2.5, 16.0))
        base_default = float(np.clip(horizon_vol * 1.0, cons_default + 1.0, PLANNER_BASE_CAPS[timeframe]))
        stretch_default = float(np.clip(horizon_vol * 1.45, base_default + 1.0, PLANNER_STRETCH_CAPS[timeframe]))
        stop_default = float(np.clip(horizon_vol * 0.55, 3.0, PLANNER_STOP_BALANCED_CAPS[timeframe]))

    def _pct_to_level(level) -> float:
        level = coerce_float(level)
        if pd.isna(current_price) or pd.isna(level) or current_price == 0:
            return np.nan
        return float(((level / current_price) - 1) * 100)

    positive_candidates = [
        _pct_to_level(trading_lab.get("resistance")),
        _pct_to_level(trading_lab.get("bb_upper")),
        coerce_float(target_ctx.get("upside_to_mean")),
        _pct_to_level(target_ctx.get("high_target")),
    ]
    positive_candidates = [float(x) for x in positive_candidates if pd.notna(x) and x > 0]

    conservative_up = cons_default
    base_up = base_default
    stretch_up = stretch_default

    if positive_candidates:
        positive_candidates_sorted = [float(x) * upside_time_multiplier for x in sorted(positive_candidates)]
        conservative_up = float(np.clip(0.55 * cons_default + 0.45 * positive_candidates_sorted[0], 2.0, PLANNER_CONSERVATIVE_CAPS[timeframe]))
        base_up = float(np.clip(np.median(positive_candidates_sorted + [base_default]), conservative_up + 0.5, PLANNER_BASE_CAPS[timeframe] + 10.0))
        stretch_up = float(np.clip(max(max(positive_candidates_sorted), stretch_default), base_up + 0.5, PLANNER_STRETCH_CAPS[timeframe] + 2.0))
    else:
        base_up = max(base_up, conservative_up + 0.5)
        stretch_up = max(stretch_up, base_up + 0.5)

    negative_candidates = []
    for level in (trading_lab.get("support"), trading_lab.get("bb_lower"), target_ctx.get("low_target")):
        pct = _pct_to_level(level)
        if pd.notna(pct) and pct < 0:
            negative_candidates.append(abs(float(pct)))

    scaled_negative_candidates = [float(x) * stop_time_multiplier for x in negative_candidates]
    stop_tight = float(np.clip(min(scaled_negative_candidates) if scaled_negative_candidates else stop_default * 0.85, 2.5, PLANNER_STOP_TIGHT_CAPS[timeframe]))
    stop_balanced = float(np.clip(np.median(scaled_negative_candidates + [stop_default]) if scaled_negative_candidates else stop_default, stop_tight + 0.5, PLANNER_STOP_BALANCED_CAPS[timeframe]))
    stop_wide = float(np.clip(max(scaled_negative_candidates) if scaled_negative_candidates else stop_default * 1.35, stop_balanced + 0.5, PLANNER_STOP_WIDE_CAPS[timeframe]))

    quality = 0
    quality += 1 if signal == "BUY" else -1 if signal == "SELL" else 0
    quality += 1 if str(analysis.get("confidence", "")).lower() == "high" else 0
    quality += 1 if analysis.get("news_pulse", {}).get("score", 0) >= 1.4 else -1 if analysis.get("news_pulse", {}).get("score", 0) <= -1.4 else 0
    quality += 1 if trading_lab.get("setup") == "Momentum-led" else -1 if trading_lab.get("setup") == "Risk-off" else 0

    reference_note = (
        "Analyst target + technical resistance blend"
        if positive_candidates
        else "Volatility-derived reference band"
    )
    if get_language() == "zh_TW":
        reference_note = (
            "分析師目標價 + 技術壓力區綜合"
            if positive_candidates
            else "依近期波動推估的參考區間"
        )

    timeframe_note = planner_timeframe_label(timeframe)
    if get_language() == "zh_TW":
        reference_note = f"{reference_note} · {timeframe_note} 期限"
    else:
        reference_note = f"{reference_note} · {timeframe_note} horizon"

    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "current_price": current_price,
        "conservative_up": conservative_up,
        "base_up": base_up,
        "stretch_up": stretch_up,
        "stop_tight": stop_tight,
        "stop_balanced": stop_balanced,
        "stop_wide": stop_wide,
        "reference_note": reference_note,
        "quality_score": quality,
        "signal": signal,
        "target_context": target_ctx,
    }


def build_position_scenario_rows(
    bundles: list[dict],
    total_capital: float,
    allocation_method: str = "equal",
    stop_profile: str = "balanced",
    timeframe: str = "6m",
    acceptable_loss_pct: float = 2.0,
    entry_weights: list[int] | None = None,
    take_profit_weights: list[int] | None = None,
    win_rate_mode: str = "balanced",
) -> tuple[pd.DataFrame, dict]:
    valid_bundles = [bundle for bundle in bundles if pd.notna(coerce_float(bundle.get("analysis", {}).get("last_price")))]
    if not valid_bundles or total_capital <= 0:
        return pd.DataFrame(), {}

    timeframe = normalize_planner_timeframe(timeframe)
    scenario_map = {bundle["ticker"]: estimate_position_scenario(bundle, timeframe=timeframe) for bundle in valid_bundles}
    if allocation_method == "score_weighted":
        weights = []
        for bundle in valid_bundles:
            score = bundle.get("analysis", {}).get("pro_score", bundle.get("analysis", {}).get("score", 0))
            weights.append(max(float(score) + 6.0, 1.0))
    else:
        weights = [1.0] * len(valid_bundles)

    weight_sum = sum(weights) or float(len(valid_bundles))
    rows: list[dict] = []
    base_profit_total = 0.0
    conservative_profit_total = 0.0
    stretch_profit_total = 0.0
    stop_loss_total = 0.0
    deployed_capital_total = 0.0

    for bundle, weight in zip(valid_bundles, weights):
        ticker = bundle["ticker"]
        plan = scenario_map[ticker]
        current_price = coerce_float(plan["current_price"])
        if pd.isna(current_price) or current_price <= 0:
            continue

        allocation = float(total_capital) * float(weight / weight_sum)
        entry_execution = compute_entry_execution_profile(
            plan,
            allocation=allocation,
            timeframe=timeframe,
            stop_profile=stop_profile,
            entry_weights=entry_weights,
        )
        take_profit_profile = compute_take_profit_profile(plan, take_profit_weights=take_profit_weights)
        weighted_exit_price = current_price * (1.0 + float(take_profit_profile["weighted_up"]) / 100.0)
        conservative_exit_price = current_price * (1.0 + float(take_profit_profile["conservative_weighted_up"]) / 100.0)
        stretch_exit_price = current_price * (1.0 + float(take_profit_profile["stretch_weighted_up"]) / 100.0)

        avg_entry_price = coerce_float(entry_execution.get("average_entry_price"))
        total_units = float(entry_execution.get("units", 0.0) or 0.0)
        deployed_capital = float(entry_execution.get("deployed_capital", 0.0) or 0.0)
        deployed_ratio = float(entry_execution.get("deployed_ratio", 0.0) or 0.0)

        conservative_profit = max(conservative_exit_price - avg_entry_price, 0.0) * total_units if total_units > 0 else 0.0
        base_profit = max(weighted_exit_price - avg_entry_price, 0.0) * total_units if total_units > 0 else 0.0
        stretch_profit = max(stretch_exit_price - avg_entry_price, 0.0) * total_units if total_units > 0 else 0.0
        stop_loss = float(entry_execution.get("stop_loss_amount", 0.0) or 0.0)

        conservative_profit_total += conservative_profit
        base_profit_total += base_profit
        stretch_profit_total += stretch_profit
        stop_loss_total += stop_loss
        deployed_capital_total += deployed_capital

        entry_ladder = entry_execution.get("ladder", []) or build_entry_ladder(plan, entry_weights=entry_weights)
        take_profit_ladder = build_take_profit_ladder(plan, take_profit_weights=take_profit_weights)
        acceptable_loss_amount_row = allocation * float(acceptable_loss_pct) / 100.0
        rows.append(
            {
                "ticker": ticker,
                "ticker_label": display_ticker_label(ticker),
                "signal": tr_signal(plan["signal"]),
                "allocation_pct": float(weight / weight_sum * 100.0),
                "allocation_amount": allocation,
                "deployed_amount": deployed_capital,
                "deployment_pct": deployed_ratio * 100.0,
                "price": current_price,
                "avg_entry_price": avg_entry_price,
                "units": total_units,
                "upside_range": f"+{plan['conservative_up']:.1f}% / +{plan['base_up']:.1f}% / +{plan['stretch_up']:.1f}%",
                "stop_range": f"-{plan['stop_tight']:.1f}% / -{plan['stop_balanced']:.1f}% / -{plan['stop_wide']:.1f}%",
                "entry_plan": format_entry_ladder_inline(entry_ladder, planner_currency_symbol(planner_market_currency(ticker))),
                "take_profit_plan": format_take_profit_inline(take_profit_ladder, planner_currency_symbol(planner_market_currency(ticker))),
                "max_loss_budget": acceptable_loss_amount_row,
                "base_profit": base_profit,
                "stop_loss": stop_loss,
                "reference_note": plan["reference_note"],
                "quality_score": plan["quality_score"],
            }
        )

    table = pd.DataFrame(rows)
    acceptable_loss_amount = float(total_capital) * float(acceptable_loss_pct) / 100.0
    recommended_capital = float(total_capital)
    if stop_loss_total > 0 and acceptable_loss_amount > 0:
        recommended_capital = min(float(total_capital), float(total_capital) * acceptable_loss_amount / stop_loss_total)
    assumed_win_rate = compute_planner_win_rate(pd.DataFrame(rows), mode=win_rate_mode) if rows else 0.55
    risk_reward_ratio = base_profit_total / stop_loss_total if stop_loss_total > 0 else 0.0
    expected_value = assumed_win_rate * base_profit_total - (1.0 - assumed_win_rate) * stop_loss_total
    suggested_position_pct = (recommended_capital / float(total_capital) * 100.0) if float(total_capital) > 0 else 0.0
    summary = {
        "capital": float(total_capital),
        "deployed_capital_total": float(deployed_capital_total),
        "deployment_pct_total": (float(deployed_capital_total) / float(total_capital) * 100.0) if float(total_capital) > 0 else 0.0,
        "base_profit_total": base_profit_total,
        "conservative_profit_total": conservative_profit_total,
        "stretch_profit_total": stretch_profit_total,
        "stop_loss_total": stop_loss_total,
        "acceptable_loss_pct": float(acceptable_loss_pct),
        "acceptable_loss_amount": acceptable_loss_amount,
        "recommended_capital": recommended_capital,
        "row_count": len(rows),
        "allocation_method": allocation_method,
        "stop_profile": stop_profile,
        "timeframe": timeframe,
        "assumed_win_rate": assumed_win_rate,
        "risk_reward_ratio": risk_reward_ratio,
        "expected_value": expected_value,
        "suggested_position_pct": suggested_position_pct,
        "entry_weights": entry_weights or [],
        "take_profit_weights": take_profit_weights or [],
        "win_rate_mode": win_rate_mode,
    }
    return table, summary



def scenario_signal_pill_class(signal_value: str) -> str:
    signal_upper = str(signal_value or "").upper()
    if signal_upper == "BUY" or signal_value in ("買進",):
        return "scenario-pill scenario-pill-up"
    if signal_upper == "SELL" or signal_value in ("賣出",):
        return "scenario-pill scenario-pill-down"
    return "scenario-pill scenario-pill-neutral"



def render_scenario_planner_table(display_df: pd.DataFrame):
    if display_df is None or display_df.empty:
        return

    headers = "".join(f"<th>{escape(str(column))}</th>" for column in display_df.columns)
    rows_html = []
    signal_names = {"訊號", "Signal"}

    for _, row in display_df.iterrows():
        cell_html = []
        for column, value in row.items():
            value_str = str(value)
            if column == display_df.columns[0]:
                cell_html.append(
                    f'<td><div class="scenario-table-primary">{escape(value_str)}</div></td>'
                )
            elif column in signal_names:
                cell_html.append(
                    f'<td><span class="{scenario_signal_pill_class(value_str)}">{escape(value_str)}</span></td>'
                )
            elif "推估依據" in str(column) or "Reference" in str(column):
                cell_html.append(
                    f'<td class="scenario-text-wrap"><div class="scenario-table-secondary">{escape(value_str)}</div></td>'
                )
            elif "分批" in str(column) or "Entry" in str(column) or "Take-profit" in str(column):
                cell_html.append(
                    f'<td class="scenario-text-wrap"><div class="scenario-num">{escape(value_str)}</div></td>'
                )
            else:
                cell_html.append(
                    f'<td><div class="scenario-num">{escape(value_str)}</div></td>'
                )

        rows_html.append("<tr>" + "".join(cell_html) + "</tr>")

    html = f'''
    <div class="scenario-table-shell">
        <div class="scenario-table-scroll">
            <table class="scenario-table">
                <thead>
                    <tr>{headers}</tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>
    </div>
    '''
    render_html_block(html)



def render_position_scenario_planner(bundles: list[dict]):
    if not bundles:
        return

    lang_zh = get_language() == "zh_TW"
    single_mode = len(bundles) == 1

    header_title = (
        "輸入金額後，自動推估漲幅區間與止損參考"
        if not single_mode and lang_zh
        else "投入金額後，為這一檔股票建立分批進場、停利與風險框架"
        if single_mode and lang_zh
        else "Model upside bands and stop-loss references from your selected list"
        if not single_mode
        else "Build a staged entry, take-profit, and risk framework for this stock"
    )
    header_copy = (
        "這不是報酬保證，而是把目前的技術結構、分析師目標價、阻力/支撐區與訊號強度，整理成可操作的金額情境。若同時選到美股與台股，系統會分開用各自市場幣別試算。"
        if not single_mode and lang_zh
        else "這不是報酬保證，而是把目前的技術結構、分析師目標價、阻力/支撐區與訊號強度，整理成單檔可操作的進場、停利與風險框架。"
        if single_mode and lang_zh
        else "This is not a return guarantee. It turns current structure, analyst targets, support/resistance, and signal quality into a practical scenario model. If you selected both U.S. and Taiwan names, the planner splits them by local currency."
        if not single_mode
        else "This is not a return guarantee. It turns current structure, analyst targets, support/resistance, and signal quality into a single-name operating framework."
    )
    header_html = f"""
    <div class="guide-shell">
        <div class="section-header" style="margin:0; color:#f5ead8;">{"投資情境試算" if lang_zh else "Investment Scenario Planner"}</div>
        <div class="guide-title">{header_title}</div>
        <div class="guide-copy">{header_copy}</div>
    </div>
    """
    render_html_block(header_html)

    grouped: dict[str, list[dict]] = {"USD": [], "TWD": []}
    for bundle in bundles:
        grouped[planner_market_currency(bundle["ticker"])].append(bundle)

    active_groups = [(currency, rows) for currency, rows in grouped.items() if rows]
    for currency, group_bundles in active_groups:
        key_prefix = f"scenario_planner_{currency.lower()}"
        symbol = planner_currency_symbol(currency)
        group_single = len(group_bundles) == 1

        title = planner_market_title(currency)
        caption = planner_market_caption(currency)
        if group_single:
            title = planner_single_stock_title(group_bundles[0], currency)
            caption = planner_single_stock_caption(group_bundles[0], currency)

        render_html_block(
            f"""
            <div class="compare-shell">
                <div class="compare-topline">
                    <div>
                        <div class="section-header" style="margin:0; color:#eef4ff;">{"情境試算" if lang_zh else "Scenario model"}</div>
                        <div class="compare-title">{escape(title)}</div>
                        <div class="compare-copy">{escape(caption)}</div>
                    </div>
                </div>
            </div>
            """
        )

        control_cols = st.columns([1.1, 0.92, 0.92, 0.82, 0.78, 0.92, 0.92, 0.82])
        with control_cols[0]:
            capital_key = f"{key_prefix}_capital_text"
            capital_default = default_planner_capital(currency)
            apply_planner_capital_state(capital_key, capital_default)
            if capital_key not in st.session_state:
                legacy_capital = st.session_state.get(f"{key_prefix}_capital")
                st.session_state[capital_key] = format_planner_capital_value(legacy_capital, capital_default)
            capital_raw = st.text_input(
                "投入金額" if lang_zh else "Investment amount",
                key=capital_key,
                placeholder="例如 100,000" if lang_zh else "e.g. 100,000",
                help="系統會依你選的配置方式，把金額分配到目前已選股票。" if lang_zh else "The planner allocates this capital across the currently selected names.",
                on_change=normalize_planner_capital_state,
                args=(capital_key, capital_default),
            )
            capital_value = parse_planner_capital_input(capital_raw, capital_default)
            st.session_state[f"{key_prefix}_capital_value"] = capital_value
            capital = float(capital_value)

            quick_amount_cols = st.columns(4)
            for quick_col, (quick_label, quick_value) in zip(quick_amount_cols, planner_quick_amount_options(currency)):
                with quick_col:
                    if st.button(quick_label, key=f"{key_prefix}_quick_{quick_value}", use_container_width=True):
                        set_planner_capital_state(capital_key, quick_value, capital_default)
                        st.rerun()
        with control_cols[1]:
            allocation_method = st.selectbox(
                "配置方式" if lang_zh else "Allocation method",
                options=["equal", "score_weighted"],
                format_func=planner_allocation_label,
                key=f"{key_prefix}_allocation",
            )
        with control_cols[2]:
            stop_profile = st.selectbox(
                "止損參考" if lang_zh else "Stop reference",
                options=["tight", "balanced", "wide"],
                format_func=planner_stop_profile_label,
                index=1,
                key=f"{key_prefix}_stop",
            )
        with control_cols[3]:
            timeframe = st.selectbox(
                "投資期限" if lang_zh else "Time frame",
                options=PLANNER_TIMEFRAME_OPTIONS,
                format_func=planner_timeframe_label,
                index=PLANNER_TIMEFRAME_OPTIONS.index("6m"),
                key=f"{key_prefix}_timeframe",
            )
            st.session_state["dashboard_target_watch_timeframe"] = normalize_planner_timeframe(timeframe)
        with control_cols[4]:
            acceptable_loss_pct = st.number_input(
                "最大可承受虧損 %" if lang_zh else "Max loss %",
                min_value=0.5,
                max_value=20.0,
                value=2.0,
                step=0.5,
                format="%.1f",
                key=f"{key_prefix}_max_loss_pct",
                help="若整體止損風險高於這個比例，系統會提示你縮小部位。" if lang_zh else "If total modeled stop-loss risk exceeds this share of capital, the planner will flag it.",
            )
        with control_cols[5]:
            win_rate_mode = st.selectbox(
                "勝率假設" if lang_zh else "Hit-rate mode",
                options=["conservative", "balanced", "aggressive"],
                format_func=planner_win_rate_label,
                index=1,
                key=f"{key_prefix}_win_rate_mode",
            )
        with control_cols[6]:
            render_html_block(
                f'<div class="scenario-ratio-shell"><div class="scenario-ratio-title">{escape("滑桿調整" if lang_zh else "Slider mode")}</div><div class="scenario-ratio-copy">{escape("分批進場 / 分批停利改用滑桿調整，避免手打比例。" if lang_zh else "Entry and take-profit ladders now use sliders for faster tuning.")}</div></div>'
            )
        with control_cols[7]:
            render_html_block(
                f'<div class="scenario-ratio-shell"><div class="scenario-ratio-title">{escape("比率會自動正規化" if lang_zh else "Ratios auto-normalize")}</div><div class="scenario-ratio-copy">{escape("第 3 段會依前兩段自動補滿至 100%。" if lang_zh else "Stage 3 is automatically filled so the ladder always totals 100%.")}</div></div>'
            )

        slider_cols = st.columns(2)
        with slider_cols[0]:
            entry_weights = render_planner_ratio_slider(
                "分批進場比例" if lang_zh else "Entry ladder ratio",
                "拖曳前兩段，第三段會自動補滿為 100%。" if lang_zh else "Adjust the first two stages. The last stage fills automatically to 100%.",
                f"{key_prefix}_entry_ratio",
                (40, 35, 25),
                fill_class="",
            )
        with slider_cols[1]:
            take_profit_weights = render_planner_ratio_slider(
                "分批停利比例" if lang_zh else "Take-profit ratio",
                "拖曳前兩段，第三段會自動補滿為 100%。" if lang_zh else "Adjust the first two stages. The last stage fills automatically to 100%.",
                f"{key_prefix}_tp_ratio",
                (30, 40, 30),
                fill_class="scenario-ratio-fill-up",
            )

        scenario_df, summary = build_position_scenario_rows(
            group_bundles,
            total_capital=float(capital or 0.0),
            allocation_method=allocation_method,
            stop_profile=stop_profile,
            timeframe=timeframe,
            acceptable_loss_pct=float(acceptable_loss_pct or 0.0),
            entry_weights=entry_weights,
            take_profit_weights=take_profit_weights,
            win_rate_mode=win_rate_mode,
        )

        if scenario_df.empty:
            st.info("請先輸入有效金額，且所選股票必須有可用價格。" if lang_zh else "Enter a valid capital amount and make sure the selected tickers have usable prices.")
            continue

        timeframe_badge = (
            f"↑ {planner_timeframe_label(summary['timeframe'])} · {summary['row_count']} 檔"
            if lang_zh
            else f"↑ {planner_timeframe_label(summary['timeframe'])} · {summary['row_count']} names"
        )
        stop_badge = f"↑ {planner_stop_profile_label(summary['stop_profile'])}"
        acceptable_symbol = format_planner_display_amount(summary["acceptable_loss_amount"], symbol)
        risk_ok = summary["stop_loss_total"] <= summary["acceptable_loss_amount"]
        risk_badge_text = (
            f"風險預算 {acceptable_symbol}"
            if lang_zh
            else f"Risk budget {acceptable_symbol}"
        )
        risk_badge_class = "scenario-summary-badge" if risk_ok else "scenario-summary-badge scenario-summary-badge-danger"
        scale_badge_text = (
            f"建議資金上限 {symbol}{summary['recommended_capital']:,.0f}"
            if lang_zh
            else f"Suggested cap {symbol}{summary['recommended_capital']:,.0f}"
        )

        deployed_badge_text = (
            f"預估部署 {symbol}{summary['deployed_capital_total']:,.0f} · {summary['deployment_pct_total']:.0f}%"
            if lang_zh
            else f"Expected deployed {symbol}{summary['deployed_capital_total']:,.0f} · {summary['deployment_pct_total']:.0f}%"
        )

        summary_html = f"""
        <div class="scenario-summary-grid">
            <div class="scenario-summary-card">
                <div class="scenario-summary-label">{"投入本金" if lang_zh else "Capital"}</div>
                <div class="scenario-summary-value scenario-summary-value-gold">{escape(format_planner_display_amount(summary["capital"], symbol))}</div>
                <div class="scenario-summary-badge">{escape(deployed_badge_text)}</div>
            </div>
            <div class="scenario-summary-card">
                <div class="scenario-summary-label">{"基準情境獲利" if lang_zh else "Base-case upside"}</div>
                <div class="scenario-summary-value">{escape(format_planner_display_amount(summary["base_profit_total"], symbol))}</div>
                <div class="scenario-summary-badge">{escape(timeframe_badge)}</div>
            </div>
            <div class="scenario-summary-card">
                <div class="scenario-summary-label">{"保守情境獲利" if lang_zh else "Conservative upside"}</div>
                <div class="scenario-summary-value">{escape(format_planner_display_amount(summary["conservative_profit_total"], symbol))}</div>
                <div class="scenario-summary-badge scenario-summary-badge-warn">{escape(scale_badge_text)}</div>
            </div>
            <div class="scenario-summary-card">
                <div class="scenario-summary-label">{"止損風險" if lang_zh else "Stop-loss risk"}</div>
                <div class="scenario-summary-value">{escape(format_planner_display_amount(summary["stop_loss_total"], symbol, negative=True))}</div>
                <div class="{risk_badge_class}">{escape(risk_badge_text)}</div>
            </div>
        </div>
        """
        render_html_block(summary_html)
        render_planner_decision_board(
            summary,
            symbol=symbol,
            entry_weights=entry_weights,
            take_profit_weights=take_profit_weights,
            win_rate_mode=win_rate_mode,
        )

        display_df = scenario_df.copy()
        display_df["allocation_pct"] = display_df["allocation_pct"].map(lambda x: f"{x:.1f}%")
        display_df["allocation_amount"] = display_df["allocation_amount"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["deployed_amount"] = display_df["deployed_amount"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["deployment_pct"] = display_df["deployment_pct"].map(lambda x: f"{x:.1f}%")
        display_df["price"] = display_df["price"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["avg_entry_price"] = display_df["avg_entry_price"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["units"] = display_df["units"].map(lambda x: f"{int(round(x)):,}")
        display_df["max_loss_budget"] = display_df["max_loss_budget"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["base_profit"] = display_df["base_profit"].map(lambda x: format_planner_display_amount(x, symbol))
        display_df["stop_loss"] = display_df["stop_loss"].map(lambda x: format_planner_display_amount(x, symbol, negative=True))

        if lang_zh:
            display_df = display_df.rename(
                columns={
                    "ticker_label": "股票",
                    "signal": "訊號",
                    "allocation_pct": "配置比重",
                    "allocation_amount": "配置金額",
                    "deployed_amount": "預估部署",
                    "deployment_pct": "部署率",
                    "price": "現價",
                    "avg_entry_price": "預估均價",
                    "units": "估計股數",
                    "upside_range": "漲幅區間",
                    "stop_range": "止損區間",
                    "entry_plan": "分批進場",
                    "take_profit_plan": "分批停利",
                    "max_loss_budget": "單檔風險預算",
                    "base_profit": "基準情境獲利",
                    "stop_loss": "止損情境損失",
                    "reference_note": "推估依據",
                }
            )[["股票", "訊號", "配置比重", "配置金額", "預估部署", "部署率", "現價", "預估均價", "估計股數", "漲幅區間", "止損區間", "分批進場", "分批停利", "單檔風險預算", "基準情境獲利", "止損情境損失", "推估依據"]]
        else:
            display_df = display_df.rename(
                columns={
                    "ticker_label": "Ticker",
                    "signal": "Signal",
                    "allocation_pct": "Weight",
                    "allocation_amount": "Capital",
                    "deployed_amount": "Expected deployed",
                    "deployment_pct": "Deploy %",
                    "price": "Price",
                    "avg_entry_price": "Avg entry",
                    "units": "Est. units",
                    "upside_range": "Upside band",
                    "stop_range": "Stop band",
                    "entry_plan": "Entry ladder",
                    "take_profit_plan": "Take-profit ladder",
                    "max_loss_budget": "Risk budget",
                    "base_profit": "Base-case P/L",
                    "stop_loss": "Stop-loss P/L",
                    "reference_note": "Reference",
                }
            )[["Ticker", "Signal", "Weight", "Capital", "Expected deployed", "Deploy %", "Price", "Avg entry", "Est. units", "Upside band", "Stop band", "Entry ladder", "Take-profit ladder", "Risk budget", "Base-case P/L", "Stop-loss P/L", "Reference"]]

        render_scenario_planner_table(display_df)

        if group_single:
            single_bundle = group_bundles[0]
            single_plan = estimate_position_scenario(single_bundle, timeframe=timeframe)
            render_single_stock_operating_panel(
                single_bundle,
                single_plan,
                symbol=symbol,
                stop_profile=stop_profile,
                timeframe=timeframe,
                acceptable_loss_pct=float(summary["acceptable_loss_pct"]),
                summary=summary,
                entry_weights=entry_weights,
                take_profit_weights=take_profit_weights,
            )
        else:
            render_portfolio_execution_panel(
                scenario_df,
                summary,
                symbol=symbol,
                entry_weights=entry_weights,
                take_profit_weights=take_profit_weights,
                win_rate_mode=win_rate_mode,
            )

        note = (
            f"漲幅區間為 保守 / 基準 / 延伸 三種情境，並已按 {planner_timeframe_label(summary['timeframe'])} 的投資期限調整。止損區間為 緊 / 平衡 / 寬 三種參考。現在多檔與單檔都保留分批進場 / 分批停利、勝率假設、風報比與建議倉位，並改成用滑桿微調分批比例。"
            if lang_zh
            else f"Upside bands are shown as conservative / base / stretch and are adjusted for a {planner_timeframe_label(summary['timeframe'])} investment horizon. Stop bands are shown as tight / balanced / wide. Both single-name and multi-name modes now keep staged entry / take-profit ladders, a hit-rate assumption, risk/reward, and suggested sizing, now tuned with slider-based ladder controls."
        )
        st.caption(note)


def render_comparison_section(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, tickers: list[str], lens_meta: dict | None = None):
    if not tickers:
        return

    bundles = [collect_ticker_context(daily_data, intraday_data, ticker, news_limit=8, lens_meta=lens_meta) for ticker in tickers]
    bundles = [bundle for bundle in bundles if bundle is not None]
    if not bundles:
        return

    if len(bundles) < 2:
        return

    comparison_base_label = (
        "展開／收合 Comparison Arena"
        if get_language() == "zh_TW"
        else "Expand / collapse Comparison Arena"
    )
    comparison_helper_base = (
        "檢視多檔股票的贏家卡、機會雷達與比較總覽。"
        if get_language() == "zh_TW"
        else "Review the winner card, opportunity radar, and cross-ticker comparison overview."
    )

    with st.expander(
        planner_expander_label(comparison_base_label, "comparison", len(bundles)),
        expanded=planner_auto_expand("comparison", len(bundles)),
    ):
        render_expander_meta("comparison", len(bundles), comparison_helper_base)
        render_winner_card(bundles, lens_meta=lens_meta)
        render_opportunity_radar(bundles, lens_meta=lens_meta)

        strongest = max(bundles, key=lambda bundle: compute_lens_winner_fields(bundle, lens_meta)["lens_score"])
        best_return = max(
            bundles,
            key=lambda bundle: bundle["analysis"]["one_year_return"] if pd.notna(bundle["analysis"]["one_year_return"]) else -10**9,
        )
        most_bullish_news = max(bundles, key=lambda bundle: bundle["analysis"]["news_pulse"]["score"])

        st.markdown(
            f"""
            <div class="compare-shell">
                <div class="compare-topline">
                    <div>
                        <div class="section-header" style="margin:0; color:#eef4ff;">{t("comparison_arena")}</div>
                        <div class="compare-title">{t("comparison_title")}</div>
                        <div class="compare-copy">{t("comparison_copy")}</div>
                    </div>
                </div>
                <div class="compare-hero-grid">
                    <div class="compare-hero-tile">
                        <div class="compare-hero-label">{t("strongest_pro_setup")}</div>
                        <div class="compare-hero-value">{escape(display_ticker_label(strongest['ticker']))}</div>
                        <div class="compare-hero-sub">{t("lens_score")} {compute_lens_winner_fields(strongest, lens_meta)['lens_score']:+d} · {escape(tr_signal(strongest['analysis']['signal']))} · {escape(tr_confidence(strongest['analysis']['confidence']))}</div>
                    </div>
                    <div class="compare-hero-tile">
                        <div class="compare-hero-label">{t("best_1y_price_strength")}</div>
                        <div class="compare-hero-value">{escape(display_ticker_label(best_return['ticker']))}</div>
                        <div class="compare-hero-sub">{format_percent(best_return['analysis']['one_year_return'])}</div>
                    </div>
                    <div class="compare-hero-tile">
                        <div class="compare-hero-label">{t("best_current_news_tailwind")}</div>
                        <div class="compare-hero-value">{escape(display_ticker_label(most_bullish_news['ticker']))}</div>
                        <div class="compare-hero-sub">{escape(tr_news_label(most_bullish_news['analysis']['news_pulse']['label']))}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_comparison_overview_cards(bundles, lens_meta=lens_meta)

        row_html_parts: list[str] = []

        for bundle in bundles:
            analysis = bundle["analysis"]
            intraday = bundle["intraday"]
            signal = analysis["signal"]
            signal_class_name = signal_css_class(signal)
            row_html_parts.append(textwrap.dedent(f"""<div class="compare-table-row">
        <div class="compare-table-cell">
            <div class="compare-table-ticker">{escape(display_ticker_label(bundle['ticker']))}</div>
            <div class="compare-table-sub">{escape(tr_term(analysis["trend"]))}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("last_price")}</div>
            <div class="compare-table-value">{format_price(analysis['last_price'])}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("trend_1y")}</div>
            <div class="compare-table-value">{format_percent(analysis['one_year_return'])}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("signal")}</div>
            <div><span class="compare-table-chip {signal_class_name}">{escape(tr_signal(signal))}</span></div>
            <div class="compare-table-note">{escape(tr_confidence(analysis["confidence"]))}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("lens_score")}</div>
            <div class="compare-table-value">{compute_lens_winner_fields(bundle, lens_meta)['lens_score']:+d}</div>
            <div class="compare-table-note">RSI {"N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}"}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("intraday")}</div>
            <div class="compare-table-value">{format_percent(intraday['change_pct']) if intraday.get('available') else 'N/A'}</div>
            <div class="compare-table-note">{escape(analysis['rsi_status'])}</div>
        </div>
        <div class="compare-table-cell">
            <div class="compare-table-sub">{t("news_backing")}</div>
            <div class="compare-table-value">{escape(tr_news_label(analysis['news_pulse']['label']))}</div>
            <div class="compare-table-note">{analysis['news_pulse']['score']:+.1f}</div>
        </div>
        </div>""").strip())

        table_html = f"""
        <div class="compare-table-shell">
            <div class="compare-table-head">
                <div>{t("ticker")}</div>
                <div>{t("last_price")}</div>
                <div>{t("trend_1y")}</div>
                <div>{t("signal")}</div>
                <div>{t("lens_score")}</div>
                <div>{t("intraday")}</div>
                <div>{t("news_backing")}</div>
            </div>
            <div class="compare-table-body">
                {''.join(row_html_parts)}
            </div>
        </div>
        """
        render_html_block(table_html)

def render_target_watch_section(ticker: str, context: dict):
    if not context:
        return

    headline_blocks: list[str] = []
    for item in context.get("target_headlines", [])[:3]:
        title = escape(str(item.get("title", "") or ""))
        provider = escape(str(item.get("provider", "") or ""))
        url = str(item.get("url", "") or "").strip()
        link_html = (
            f'<a class="brief-link" href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
            if url
            else title
        )
        headline_blocks.append(
            "".join(
                [
                    '<div class="target-watch-headline">',
                    f'<div class="target-watch-headline-title">{link_html}</div>',
                    f'<div class="target-watch-headline-meta">{provider}</div>',
                    '</div>',
                ]
            )
        )

    headlines_html = (
        "".join(headline_blocks)
        if headline_blocks
        else f'<div class="target-watch-empty">{escape(t("no_structured_target"))}</div>'
    )

    warning_html = ""
    if context.get("warning"):
        warning_html = f'<div class="target-watch-warning">{escape(context["warning"])}</div>'

    shell_html = "".join(
        [
            '<div class="target-watch-shell">',
            '<div class="target-watch-head">',
            '<div>',
            f'<div class="section-header" style="margin:0; color:#f5ead8;">{t("target_watch")}</div>',
            f'<div class="target-watch-title">{t("target_watch")}</div>',
            f'<div class="target-watch-copy">{t("target_watch_copy")}</div>',
            '</div>',
            f'<div class="target-watch-pill">{escape(context.get("source_note", t("target_reference_source")))} · {escape(context.get("timeframe_label", planner_timeframe_label("6m")))}</div>',
            '</div>',
            '<div class="target-watch-grid">',
            '<div class="target-watch-card">',
            f'<div class="target-watch-label">{t("consensus_target")}</div>',
            f'<div class="target-watch-value">{format_local_price(context.get("mean_target"), ticker)}</div>',
            f'<div class="target-watch-sub">{t("current_price")}: {format_local_price(context.get("current_price"), ticker)}</div>',
            '</div>',
            '<div class="target-watch-card">',
            f'<div class="target-watch-label">{t("target_gap")}</div>',
            f'<div class="target-watch-value">{format_percent(context.get("upside_to_mean", pd.NA))}</div>',
            f'<div class="target-watch-sub">{t("upside_to_mean")} · {t("downside_to_low")}: {format_percent(context.get("downside_to_low", pd.NA))}</div>',
            '</div>',
            '<div class="target-watch-card">',
            f'<div class="target-watch-label">{t("high_low_band")}</div>',
            f'<div class="target-watch-value">{escape(context.get("band_text", "N/A"))}</div>',
            f'<div class="target-watch-sub">{t("analyst_count")}: {escape(context.get("analyst_count_text", "N/A"))}</div>',
            '</div>',
            '<div class="target-watch-card">',
            f'<div class="target-watch-label">{t("analyst_view")}</div>',
            f'<div class="target-watch-value">{escape(str(context.get("bias", "N/A")))}</div>',
            f'<div class="target-watch-sub">{t("latest_revision")}: {escape(context.get("latest_revision") or "N/A")}</div>',
            '</div>',
            '</div>',
            warning_html,
            '<div class="target-watch-board">',
            f'<div class="target-watch-board-label">{t("target_headlines")}</div>',
            '<div class="target-watch-headline-grid">',
            headlines_html,
            '</div>',
            '</div>',
            f'<div class="target-watch-note">{escape(context.get("horizon_note", ""))} {t("target_reference_note")}</div>',
            '</div>',
        ]
    )

    render_html_block(shell_html)




def render_global_scenario_planning_stack(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, tickers: list[str], lens_meta: dict | None = None):
    if not tickers:
        return

    bundles = [collect_ticker_context(daily_data, intraday_data, ticker, news_limit=8, lens_meta=lens_meta) for ticker in tickers]
    bundles = [bundle for bundle in bundles if bundle is not None]
    if not bundles:
        return

    planner_base_label = (
        "展開／收合情境規劃組" if get_language() == "zh_TW" else "Expand / collapse scenario planning stack"
    )
    planner_helper_base = (
        "這一組包含 Scenario Model、Entry ladder ratio、Advanced decision board、Portfolio Execution framework，以及 Entry / Exit / Risk Summary。"
        if get_language() == "zh_TW"
        else "This stack includes Scenario Model, Entry ladder ratio, Advanced decision board, Portfolio Execution framework, and Entry / Exit / Risk Summary."
    )

    with st.expander(
        planner_expander_label(planner_base_label, "scenario", len(bundles)),
        expanded=planner_auto_expand("scenario", len(bundles)),
    ):
        render_expander_meta("scenario", len(bundles), planner_helper_base)
        render_position_scenario_planner(bundles)
    render_html_block('<div class="planner-stack-spacer"></div>')




def render_target_tracking_focus_header(ticker: str, index: int):
    name = escape(display_ticker_label(ticker))
    symbol = escape(str(ticker).upper())
    focus_label = "目標追蹤焦點" if get_language() == "zh_TW" else "Target tracking focus"
    html = f'''
    <div class="target-tracking-focus">
        <div class="target-tracking-focus-left">
            <div class="target-tracking-focus-index">#{index:02d}</div>
            <div class="target-tracking-focus-copy">
                <div class="target-tracking-focus-kicker">{escape(focus_label)}</div>
                <div class="target-tracking-focus-name">{name}</div>
            </div>
        </div>
        <div class="target-tracking-focus-symbol">{symbol}</div>
    </div>
    '''
    render_html_block(html)


def render_precomparison_target_and_brief_groups(
    daily_data: pd.DataFrame,
    intraday_data: pd.DataFrame | None,
    tickers: list[str],
    lens_meta: dict | None = None,
):
    if not tickers:
        return

    bundles = [collect_ticker_context(daily_data, intraday_data, ticker, news_limit=10, lens_meta=lens_meta) for ticker in tickers]
    bundles = [bundle for bundle in bundles if bundle is not None]
    if not bundles:
        return

    target_base_label = "展開／收合 Target Tracking" if get_language() == "zh_TW" else "Expand / collapse Target Tracking"
    target_helper_base = (
        "先看各檔股票的目標價區間、落差與目標價相關新聞。"
        if get_language() == "zh_TW"
        else "Review target bands, current gaps, and target-related headlines before comparison."
    )
    with st.expander(
        planner_expander_label(target_base_label, "target", len(bundles)),
        expanded=planner_auto_expand("target", len(bundles)),
    ):
        render_expander_meta("target", len(bundles), target_helper_base)
        for idx, bundle in enumerate(bundles, start=1):
            ticker = bundle["ticker"]
            context = build_target_watch_context(
                ticker,
                bundle["price_series"],
                bundle["news_items"],
                timeframe=active_target_watch_timeframe(ticker),
            )
            render_target_tracking_focus_header(ticker, idx)
            render_target_watch_section(ticker, context)
            if idx != len(bundles):
                render_html_block('<div class="group-stack-divider"></div>')

    brief_base_label = "展開／收合 Decision Brief" if get_language() == "zh_TW" else "Expand / collapse Decision Brief"
    brief_helper_base = (
        "先掌握每檔股票的目前立場、主導催化與下一步執行摘要。"
        if get_language() == "zh_TW"
        else "Review the current stance, dominant catalyst, and next-step execution brief for each ticker."
    )
    with st.expander(
        planner_expander_label(brief_base_label, "brief", len(bundles)),
        expanded=planner_auto_expand("brief", len(bundles)),
    ):
        render_expander_meta("brief", len(bundles), brief_helper_base)
        for idx, bundle in enumerate(bundles, start=1):
            render_decision_brief(bundle["ticker"], bundle["analysis"], bundle["intraday"], bundle["news_items"])
            if idx != len(bundles):
                render_html_block('<div class="group-stack-divider"></div>')


def render_ticker_page(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str, lens_meta: dict | None = None, selected_count: int = 1):
    bundle = collect_ticker_context(daily_data, intraday_data, ticker, news_limit=10, lens_meta=lens_meta)
    if bundle is None:
        st.warning("找不到可用的價格序列。" if get_lang() == "繁體中文" else f"No usable price series found for {display_ticker_label(ticker)}.")
        return

    if bundle["news_error"]:
        st.warning(bundle["news_error"])

    analysis = bundle["analysis"]
    intraday = bundle["intraday"]
    news_items = bundle["news_items"]
    daily_ohlc = bundle.get("daily_ohlc", pd.DataFrame())
    intraday_ohlc = bundle.get("intraday_ohlc", pd.DataFrame())

    render_news_first_section(ticker, analysis, intraday, news_items)

    if is_taiwan_ticker(ticker):
        benchmark = build_taiwan_benchmark_context(ticker, bundle["price_series"], lens_meta=lens_meta)
        render_taiwan_benchmark_layer(ticker, benchmark)

    alert_base_label = (
        f"展開／收合 {display_ticker_label(ticker)} 警示層"
        if get_language() == "zh_TW"
        else f"Expand / collapse {display_ticker_label(ticker)} alert layer"
    )
    alert_helper_base = (
        "檢視不同鏡頭下的多空狀態與目前焦點。"
        if get_language() == "zh_TW"
        else "Review bullish, neutral, and bearish lens states plus the current focus."
    )
    with st.expander(
        planner_expander_label(alert_base_label, "alert", selected_count),
        expanded=planner_auto_expand("alert", selected_count),
    ):
        render_expander_meta("alert", selected_count, alert_helper_base)
        render_alert_layer(analysis, intraday)

    render_reference_guide(analysis, ticker, news_items)
    render_news_stream(ticker, news_items)
    render_trend_section(
        analysis,
        intraday,
        lens_meta=lens_meta,
        daily_ohlc=daily_ohlc,
        intraday_ohlc=intraday_ohlc,
        selected_count=selected_count,
    )


# ---------------------------
# Main app
# ---------------------------


def render_stock_explorer_nav(tickers: list[str]):
    chip_html = "".join(f'<span class="explorer-nav-chip">{escape(display_ticker_label(ticker))}</span>' for ticker in tickers[:10])
    if len(tickers) > 10:
        chip_html += f'<span class="explorer-nav-chip">+{len(tickers) - 10} more</span>'

    st.markdown(
        f"""
        <div class="explorer-nav-shell">
            <div class="explorer-nav-head">
                <div>
                    <div class="explorer-nav-kicker">{t("explorer_navigation")}</div>
                    <div class="explorer-nav-title">{t("choose_ticker_workspace")}</div>
                    <div class="explorer-nav-copy">{t("explorer_nav_copy")}</div>
                    <div class="explorer-nav-row">
                        {chip_html}
                    </div>
                </div>
                <div class="explorer-nav-panel">
                    <div class="explorer-nav-panel-label">{t("what_happens_next")}</div>
                    <div class="explorer-nav-panel-value">{t("open_ticker_workspace")}</div>
                    <div class="explorer-nav-panel-copy">{t("open_ticker_workspace_copy")}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def inject_localization_overrides():
    st.markdown(
        """
        <style>
        .news-helper-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 11px;
            border-radius: 999px;
            border: 1px solid rgba(244, 197, 106, 0.24);
            background: rgba(244, 197, 106, 0.10);
            color: #f4d8a3;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
        }
        
        .global-indicator-shell {
            position: sticky;
            top: 0.7rem;
            z-index: 30;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.11) 0%, rgba(244, 197, 106, 0) 34%),
                linear-gradient(180deg, rgba(31, 24, 18, 0.94) 0%, rgba(17, 14, 11, 0.98) 100%);
            border: 1px solid rgba(244, 197, 106, 0.14);
            border-radius: 24px;
            padding: 16px 18px 14px 18px;
            box-shadow: 0 18px 36px rgba(0,0,0,.28);
            margin: 12px 0 14px 0;
            color: #f8f1e5;
            backdrop-filter: blur(14px);
        }
        .global-indicator-shell::after {
            content: "";
            position: absolute;
            right: -84px;
            top: -72px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(244, 197, 106, 0.10) 0%, rgba(244, 197, 106, 0) 72%);
            pointer-events: none;
        }
        .global-indicator-header {
            display: grid;
            grid-template-columns: 1.25fr auto;
            gap: 12px;
            align-items: end;
        }
        .global-indicator-side {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            justify-content: end;
            gap: 8px;
        }
        .global-indicator-title {
            font-size: 23px;
            font-weight: 900;
            line-height: 1.02;
            color: #fff8ee;
            margin-top: 6px;
        }
        .global-indicator-copy {
            font-size: 13px;
            line-height: 1.55;
            color: rgba(248, 241, 229, 0.76);
            margin-top: 6px;
            max-width: 760px;
        }
        .global-indicator-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        .global-indicator-pill-row-tight {
            margin-top: 0;
        }
        .global-indicator-pill {
            display: inline-flex;
            align-items: center;
            padding: 7px 11px;
            border-radius: 999px;
            font-size: 10.5px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            border: 1px solid rgba(244, 197, 106, 0.18);
            color: #f8e7c2;
            background: rgba(255,255,255,.04);
            white-space: nowrap;
        }
        .global-indicator-card-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin-top: 12px;
        }
        .global-indicator-card {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 18px;
            padding: 12px 12px 11px 12px;
            min-width: 0;
        }
        .global-indicator-card-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .global-indicator-label {
            font-size: 10.5px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(248, 241, 229, 0.62);
        }
        .global-indicator-state-chip {
            display: inline-flex;
            align-items: center;
            padding: 5px 8px;
            border-radius: 999px;
            font-size: 10px;
            font-weight: 800;
            color: rgba(248, 241, 229, 0.82);
            border: 1px solid rgba(244, 197, 106, 0.16);
            background: rgba(255,255,255,.04);
            text-align: right;
        }
        .global-indicator-value {
            font-size: 22px;
            font-weight: 900;
            color: #fff8ee;
            margin-top: 8px;
            line-height: 1.02;
        }
        .global-indicator-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .global-indicator-mini-label {
            font-size: 10px;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: rgba(248, 241, 229, 0.56);
        }
        .global-indicator-mini-value {
            font-size: 15px;
            font-weight: 900;
            color: #fff8ee;
            margin-top: 4px;
        }
        .target-watch-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.10) 0%, rgba(244, 197, 106, 0) 34%),
                linear-gradient(180deg, rgba(31, 24, 18, 0.96) 0%, rgba(17, 14, 11, 0.98) 100%);
            border: 1px solid rgba(244, 197, 106, 0.14);
            border-radius: 24px;
            padding: 18px 18px 16px 18px;
            box-shadow: 0 20px 44px rgba(0,0,0,.26);
            margin: 14px 0 16px 0;
            color: #f8f1e5;
        }
        .target-watch-shell::after {
            content: "";
            position: absolute;
            right: -84px;
            top: -72px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(244, 197, 106, 0.10) 0%, rgba(244, 197, 106, 0) 72%);
            pointer-events: none;
        }
        .target-watch-head {
            display: grid;
            grid-template-columns: 1.2fr auto;
            gap: 12px;
            align-items: start;
        }
        .target-watch-title {
            font-size: 24px;
            font-weight: 900;
            line-height: 1.04;
            color: #fff8ee;
            margin-top: 8px;
        }
        .target-watch-copy {
            font-size: 13px;
            line-height: 1.6;
            color: rgba(248, 241, 229, 0.78);
            margin-top: 6px;
            max-width: 860px;
        }
        .target-watch-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 10.5px;
            font-weight: 900;
            letter-spacing: .05em;
            text-transform: uppercase;
            border: 1px solid rgba(244, 197, 106, 0.18);
            color: #f8e7c2;
            background: rgba(255,255,255,.04);
            text-align: right;
        }
        .target-watch-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin-top: 14px;
        }
        .target-watch-card {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 18px;
            padding: 13px 13px 12px 13px;
            min-width: 0;
        }
        .target-watch-label, .target-watch-board-label {
            font-size: 10.5px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(248, 241, 229, 0.60);
        }
        .target-watch-value {
            font-size: 22px;
            font-weight: 900;
            color: #fff8ee;
            line-height: 1.08;
            margin-top: 8px;
            word-break: break-word;
        }
        .target-watch-sub, .target-watch-note, .target-watch-warning, .target-watch-headline-meta, .target-watch-empty {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(248, 241, 229, 0.76);
            margin-top: 6px;
        }
        .target-watch-warning {
            margin-top: 12px;
            padding: 10px 12px;
            border-radius: 14px;
            border: 1px solid rgba(244, 197, 106, 0.12);
            background: rgba(255,255,255,.04);
        }
        .target-watch-board {
            margin-top: 14px;
            display: grid;
            gap: 10px;
        }
        .target-watch-headline-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 10px;
        }
        .target-watch-headline {
            padding: 11px 12px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,.08);
            background: linear-gradient(135deg, rgba(255,255,255,.05) 0%, rgba(255,255,255,.03) 100%);
            min-width: 0;
        }
        .target-watch-headline-title, .target-watch-headline-title a {
            color: #fff8ee;
            font-size: 14px;
            line-height: 1.36;
            font-weight: 800;
            text-decoration: none;
            word-break: break-word;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .target-watch-headline-meta {
            margin-top: 5px;
        }
        .target-watch-headline-title a:hover {
            text-decoration: underline;
        }
        .target-watch-note {
            margin-top: 12px;
        }

.benchmark-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(244, 197, 106, 0.10) 0%, rgba(244, 197, 106, 0) 34%),
                linear-gradient(180deg, rgba(31, 24, 18, 0.96) 0%, rgba(17, 14, 11, 0.98) 100%);
            border: 1px solid rgba(244, 197, 106, 0.14);
            border-radius: 26px;
            padding: 20px 20px 18px 20px;
            box-shadow: 0 22px 48px rgba(0,0,0,.26);
            margin: 14px 0 16px 0;
            color: #f8f1e5;
        }
        .benchmark-shell::after {
            content: "";
            position: absolute;
            right: -84px;
            top: -72px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(244, 197, 106, 0.12) 0%, rgba(244, 197, 106, 0) 72%);
            pointer-events: none;
        }
        .benchmark-title {
            font-size: 26px;
            font-weight: 900;
            line-height: 1.05;
            color: #fff8ee;
            margin-top: 8px;
        }
        .benchmark-copy {
            font-size: 14px;
            line-height: 1.65;
            color: rgba(248, 241, 229, 0.78);
            margin-top: 8px;
            max-width: 920px;
        }
        .benchmark-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
            margin-top: 14px;
        }
        .benchmark-box, .benchmark-row {
            background: linear-gradient(135deg, rgba(255,255,255,.06) 0%, rgba(255,255,255,.03) 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 20px;
            padding: 14px 14px 12px 14px;
        }
        .benchmark-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .10em;
            text-transform: uppercase;
            color: rgba(248, 241, 229, 0.60);
        }
        .benchmark-value {
            font-size: 22px;
            font-weight: 900;
            color: #fff8ee;
            line-height: 1.08;
            margin-top: 8px;
        }
        .benchmark-sub, .benchmark-row-note {
            font-size: 12.5px;
            line-height: 1.58;
            color: rgba(248, 241, 229, 0.74);
            margin-top: 6px;
        }
        .benchmark-table {
            display: grid;
            gap: 10px;
            margin-top: 14px;
        }
        .benchmark-row {
            display: grid;
            grid-template-columns: 160px 1fr 1.4fr;
            gap: 12px;
            align-items: center;
        }
        .benchmark-row-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: .08em;
            color: rgba(248, 241, 229, 0.60);
            font-weight: 800;
        }
        .benchmark-row-value {
            font-size: 17px;
            font-weight: 900;
            color: #fff8ee;
        }
        @media (max-width: 980px) {
            .global-indicator-header,
            .target-watch-head {
                grid-template-columns: 1fr;
            }
            .global-indicator-side {
                align-items: flex-start;
            }
            .global-indicator-card-grid,
            .target-watch-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        @media (max-width: 768px) {
            .global-indicator-shell {
                position: relative;
                top: auto;
            }
            .global-indicator-card-grid,
            .target-watch-grid {
                grid-template-columns: 1fr;
            }
            .benchmark-row {
                grid-template-columns: 1fr;
            }
            .benchmark-title,
            .global-indicator-title,
            .target-watch-title {
                font-size: 22px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )




def inject_device_layout_overrides(device_mode: str) -> None:
    device_mode = normalize_device_mode(device_mode)

    if device_mode == "Desktop":
        css = """
        <style>
        .block-container {
            max-width: 1540px;
        }
        .global-indicator-shell {
            top: 0.7rem;
        }
        </style>
        """
    elif device_mode == "iPad":
        css = """
        <style>
        .block-container {
            max-width: 980px !important;
            padding-left: 0.9rem !important;
            padding-right: 0.9rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.85rem !important;
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: calc(50% - 0.45rem) !important;
            flex: 1 1 calc(50% - 0.45rem) !important;
        }
        .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid, .lead-story-board {
            grid-template-columns: 1fr !important;
        }
        .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid,
        .compare-card-grid, .crypto-grid, .winner-rail-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
        .scenario-table-shell {
            overflow-x: auto;
        }
        .global-indicator-shell {
            top: 0.55rem !important;
        }
        </style>
        """
    elif device_mode == "Smartphone Fold Portrait":
        css = """
        <style>
        .block-container {
            max-width: 720px !important;
            padding-top: 0.65rem !important;
            padding-left: 0.7rem !important;
            padding-right: 0.7rem !important;
            padding-bottom: 1.2rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.75rem !important;
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: calc(50% - 0.4rem) !important;
            flex: 1 1 calc(50% - 0.4rem) !important;
        }
        .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid, .lead-story-board, .highlight-row {
            grid-template-columns: 1fr !important;
        }
        .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid,
        .compare-card-grid, .crypto-grid, .winner-rail-grid, .compare-mosaic-grid, .target-watch-headline-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
        .compare-table-head {
            display: none !important;
        }
        .compare-table-row {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 10px !important;
            padding: 14px !important;
        }
        .compare-table-cell {
            display: grid !important;
            grid-template-columns: 1fr !important;
            gap: 4px !important;
            border-bottom: 1px solid rgba(255,255,255,.07);
            padding-bottom: 6px !important;
        }
        .chip, .hero-chip, .small-pill, .impact-tag, .pro-tag, .lens-alert-chip, .explorer-nav-chip {
            justify-content: center;
        }
        .scenario-table-shell, .target-watch-headline-shell {
            overflow-x: auto;
        }
        .global-indicator-shell {
            top: 0.4rem !important;
        }
        </style>
        """
    elif device_mode == "Smartphone Fold Landscape":
        css = """
        <style>
        .block-container {
            max-width: 980px !important;
            padding-top: 0.55rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
            padding-bottom: 1.1rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.8rem !important;
            flex-wrap: wrap !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: calc(50% - 0.45rem) !important;
            flex: 1 1 calc(50% - 0.45rem) !important;
        }
        .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid {
            grid-template-columns: 1fr !important;
        }
        .lead-story-board {
            grid-template-columns: 1fr 1fr !important;
        }
        .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid,
        .compare-card-grid, .crypto-grid, .winner-rail-grid, .compare-mosaic-grid, .target-watch-grid, .target-watch-headline-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
        }
        .compare-table-head {
            display: none !important;
        }
        .compare-table-row {
            grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
            gap: 10px !important;
            padding: 14px !important;
        }
        .compare-table-cell {
            display: grid !important;
            grid-template-columns: 1fr !important;
            gap: 4px !important;
            border-bottom: 1px solid rgba(255,255,255,.07);
            padding-bottom: 6px !important;
        }
        .scenario-table-shell, .target-watch-headline-shell {
            overflow-x: auto;
        }
        .global-indicator-shell {
            top: 0.45rem !important;
        }
        </style>
        """
    else:
        css = """
        <style>
        .block-container {
            max-width: 460px !important;
            padding-top: 0.55rem !important;
            padding-left: 0.55rem !important;
            padding-right: 0.55rem !important;
            padding-bottom: 1.1rem !important;
        }
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
            gap: 0.7rem !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            width: 100% !important;
            min-width: 100% !important;
            flex: 1 1 100% !important;
        }
        .hero-title, .guide-title, .winner-title, .compare-title, .catalyst-title, .alert-title, .lab-title, .trend-title, .explorer-nav-title, .reference-title, .global-indicator-title {
            font-size: 22px !important;
        }
        .top-intro, .hero-copy, .guide-copy, .reference-copy, .lens-copy, .compare-copy, .winner-copy,
        .catalyst-copy, .alert-copy, .lab-copy, .trend-sub, .chart-copy, .explorer-nav-copy, .global-indicator-copy {
            font-size: 13px !important;
        }
        .winner-hero, .story-row-grid, .explorer-nav-head, .compare-topline, .news-first-grid, .lead-story-board, .highlight-row {
            grid-template-columns: 1fr !important;
        }
        .guide-grid, .reference-grid, .compare-hero-grid, .catalyst-grid, .winner-grid, .lab-grid, .alert-grid, .lens-grid,
        .compare-card-grid, .crypto-grid, .winner-rail-grid, .compare-mosaic-grid, .target-watch-headline-grid {
            grid-template-columns: 1fr !important;
        }
        .compare-table-head {
            display: none !important;
        }
        .compare-table-row {
            grid-template-columns: 1fr !important;
            gap: 10px !important;
            padding: 14px !important;
        }
        .compare-table-cell {
            display: grid !important;
            grid-template-columns: 1fr !important;
            gap: 4px !important;
            border-bottom: 1px solid rgba(255,255,255,.07);
            padding-bottom: 6px !important;
        }
        .chip, .hero-chip, .small-pill, .impact-tag, .pro-tag, .lens-alert-chip, .explorer-nav-chip {
            width: 100%;
            justify-content: center;
        }
        .scenario-table-shell, .target-watch-headline-shell {
            overflow-x: auto;
        }
        .global-indicator-shell {
            position: relative !important;
            top: 0 !important;
        }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)

def generate_dashboard():
    load_dashboard_preferences()
    inject_css()
    inject_premium_overrides()
    inject_localization_overrides()

    with st.sidebar:
        current_lang = st.session_state.get("dashboard_language", "English")
        selected_lang = st.selectbox(
            t("language"),
            options=list(LANGUAGE_OPTIONS.keys()),
            index=list(LANGUAGE_OPTIONS.keys()).index(current_lang),
        )
        st.session_state["dashboard_language"] = selected_lang

        current_device_control = st.session_state.get("dashboard_device_control_mode", "Auto detect")
        if current_device_control not in DEVICE_CONTROL_OPTIONS:
            current_device_control = "Auto detect"
        selected_device_control = st.selectbox(
            t("device_mode_control"),
            options=list(DEVICE_CONTROL_OPTIONS.keys()),
            index=list(DEVICE_CONTROL_OPTIONS.keys()).index(current_device_control),
            format_func=device_control_mode_label,
        )
        st.session_state["dashboard_device_control_mode"] = selected_device_control

        detected_device_mode = detect_device_mode_from_user_agent()
        st.session_state["dashboard_detected_device_mode"] = detected_device_mode

        current_device_mode = normalize_device_mode(st.session_state.get("dashboard_device_mode", "Desktop"))
        if selected_device_control == "Manual override":
            selected_device_mode = st.selectbox(
                t("device_mode"),
                options=list(DEVICE_MODE_OPTIONS.keys()),
                index=list(DEVICE_MODE_OPTIONS.keys()).index(current_device_mode)
                if current_device_mode in DEVICE_MODE_OPTIONS
                else 0,
                format_func=device_mode_label,
            )
            st.session_state["dashboard_device_mode"] = selected_device_mode
        else:
            selected_device_mode = detected_device_mode
            st.session_state["dashboard_device_mode"] = selected_device_mode
            st.caption(f"{t('device_mode_detected')}: {device_mode_label(detected_device_mode)}")

        st.caption(t("device_mode_control_note"))
        st.caption(t("device_mode_note"))
        inject_device_layout_overrides(get_effective_device_mode())

        current_news_mode = st.session_state.get("dashboard_news_mode", "Original source")
        selected_news_mode = st.selectbox(
            t("news_display_mode"),
            options=list(NEWS_DISPLAY_OPTIONS.keys()),
            index=list(NEWS_DISPLAY_OPTIONS.keys()).index(current_news_mode),
            format_func=lambda key: {
                "Original source": t("news_mode_original"),
                "Bilingual assist": t("news_mode_bilingual"),
                "Chinese-first assist": t("news_mode_chinese_first"),
            }.get(key, key),
        )
        st.session_state["dashboard_news_mode"] = selected_news_mode
        st.caption(t("headline_note"))
        st.caption(t("news_display_note"))
        st.caption(t("saved_preferences_note"))

        st.markdown(
            f"""
            <div class="side-hero">
                <div class="side-eyebrow">{t('control_center')}</div>
                <div class="side-title">{t('vision_deck')}</div>
                <div class="side-copy">{t('vision_deck_copy')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_html_block(f'<div class="side-group-label">{t("watchlist_universe")}</div>')
        current_market_scope = st.session_state.get("dashboard_market_scope", "Mixed (U.S. + Taiwan)")
        selected_market_scope = st.selectbox(
            t("market_scope"),
            options=list(MARKET_SCOPE_OPTIONS.keys()),
            index=list(MARKET_SCOPE_OPTIONS.keys()).index(current_market_scope) if current_market_scope in MARKET_SCOPE_OPTIONS else 0,
            format_func=market_scope_label,
        )
        st.session_state["dashboard_market_scope"] = selected_market_scope
        st.caption(t("market_scope_note"))


        scope_group_options = market_scope_group_options(selected_market_scope)
        is_zh = selected_lang == "繁體中文"
        selector_title = "專業選股器" if is_zh else "Professional Selector"
        selector_copy = (
            "用搜尋、產業、可見清單三段式管理，先加入，再整理已選股票。"
            if is_zh
            else "Use a cleaner add-manage flow: search, sector actions, then maintain the selected watchlist."
        )
        sector_action_label = "依產業加入" if is_zh else "Add by sector"
        selected_groups_label = "目前產業" if is_zh else "Active groups"
        add_group_label = "加入此產業" if is_zh else "Add group"
        apply_group_label = "套用此產業全部加入" if is_zh else "Add entire group"
        select_all_groups_label = "全部產業" if is_zh else "Select all groups"
        clear_groups_label = "清空產業" if is_zh else "Clear groups"
        custom_add_label = "加入自訂代號" if is_zh else "Add custom symbols"
        available_tickers_label = "可加入股票" if is_zh else "Available symbols"
        add_visible_label = "加入勾選股票" if is_zh else "Add highlighted"
        select_all_visible_label = "全選目前可見" if is_zh else "Add all visible"
        selected_watchlist_label = "已選股票管理" if is_zh else "Selected watchlist"
        remove_selected_label = "移除勾選" if is_zh else "Remove highlighted"
        clear_selected_label = "清空已選" if is_zh else "Clear selected"
        selected_count_label = "已選 {count} 檔" if is_zh else "{count} selected"
        search_add_label = "加入搜尋結果" if is_zh else "Add search results"

        previous_scope = st.session_state.get("dashboard_market_scope_previous")
        stored_groups = [
            group for group in st.session_state.get("dashboard_selected_groups", [])
            if group in scope_group_options
        ]
        if previous_scope != selected_market_scope and not stored_groups:
            stored_groups = [
                group for group in MARKET_SCOPE_DEFAULT_GROUPS[selected_market_scope]
                if group in scope_group_options
            ]
        elif not stored_groups:
            stored_groups = [
                group for group in MARKET_SCOPE_DEFAULT_GROUPS[selected_market_scope]
                if group in scope_group_options
            ]
        selected_groups = dedupe_keep_order(stored_groups)
        st.session_state["dashboard_selected_groups"] = selected_groups

        stored_ticker_picks = filter_tickers_for_market_scope(
            st.session_state.get("dashboard_selected_tickers", []),
            selected_market_scope,
        )
        default_ticker_pool = [
            ticker for ticker in default_tickers_for_market_scope(selected_market_scope)
            if ticker
        ]
        tickers_initialized = bool(st.session_state.get("dashboard_selected_tickers_initialized", False))
        has_explicit_ticker_state = "dashboard_selected_tickers" in st.session_state

        if not tickers_initialized and not has_explicit_ticker_state:
            stored_ticker_picks = default_ticker_pool
        elif previous_scope != selected_market_scope and not stored_ticker_picks and not tickers_initialized:
            stored_ticker_picks = default_ticker_pool

        selected_ticker_picks = dedupe_keep_order(stored_ticker_picks)
        st.session_state["dashboard_selected_tickers"] = selected_ticker_picks
        st.session_state["dashboard_market_scope_previous"] = selected_market_scope

        render_html_block(
            f"""
            <div class="side-group-label">{selector_title}</div>
            <div class="side-copy" style="margin-top:6px; margin-bottom:10px;">{selector_copy}</div>
            """
        )

        group_action_widget_key = "dashboard_group_action_picker"
        if group_action_widget_key not in st.session_state or st.session_state[group_action_widget_key] not in scope_group_options:
            st.session_state[group_action_widget_key] = scope_group_options[0] if scope_group_options else ""
        group_focus = st.selectbox(
            sector_action_label,
            options=scope_group_options,
            format_func=tr_group,
            key=group_action_widget_key,
        )
        group_action_cols = st.columns(2)
        if group_action_cols[0].button(add_group_label, use_container_width=True):
            st.session_state["dashboard_selected_groups"] = dedupe_keep_order(selected_groups + [group_focus])
            st.rerun()
        if group_action_cols[1].button(apply_group_label, use_container_width=True):
            st.session_state["dashboard_selected_groups"] = dedupe_keep_order(selected_groups + [group_focus])
            st.session_state["dashboard_selected_tickers"] = merge_ticker_selection(
                selected_ticker_picks,
                WATCHLIST_PRESETS.get(group_focus, []),
                selected_market_scope,
            )
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()

        group_scope_cols = st.columns(2)
        if group_scope_cols[0].button(select_all_groups_label, use_container_width=True):
            st.session_state["dashboard_selected_groups"] = scope_group_options.copy()
            st.rerun()
        if group_scope_cols[1].button(clear_groups_label, use_container_width=True):
            st.session_state["dashboard_selected_groups"] = []
            st.rerun()

        selected_groups = [
            group for group in st.session_state.get("dashboard_selected_groups", [])
            if group in scope_group_options
        ]
        st.session_state["dashboard_selected_groups"] = selected_groups
        if selected_groups:
            st.caption(
                f"{selected_groups_label}: " + " · ".join(tr_group(group) for group in selected_groups)
            )
        else:
            st.caption(
                f"{selected_groups_label}: " + ("未限制，顯示目前市場所有預設群組" if is_zh else "Not limited. Showing all preset groups in this market scope.")
            )

        custom_symbol_widget_key = "dashboard_custom_symbols_widget"
        if custom_symbol_widget_key not in st.session_state:
            st.session_state[custom_symbol_widget_key] = st.session_state.get("dashboard_custom_symbols", "")
        custom_ticker_text = st.text_input(
            t("custom_symbols"),
            placeholder=t("custom_symbols_placeholder"),
            key=custom_symbol_widget_key,
        )
        st.session_state["dashboard_custom_symbols"] = custom_ticker_text

        custom_tickers = [
            normalize_dashboard_ticker(ticker)
            for ticker in custom_ticker_text.replace("\n", ",").split(",")
            if ticker.strip()
        ]
        custom_tickers = filter_tickers_for_market_scope(custom_tickers, selected_market_scope)
        if st.button(custom_add_label, use_container_width=True) and custom_tickers:
            st.session_state["dashboard_selected_tickers"] = merge_ticker_selection(
                selected_ticker_picks,
                custom_tickers,
                selected_market_scope,
            )
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()

        symbol_search_widget_key = "dashboard_symbol_search_widget"
        if symbol_search_widget_key not in st.session_state:
            st.session_state[symbol_search_widget_key] = st.session_state.get("dashboard_symbol_search", "")
        symbol_search_query = st.text_input(
            t("symbol_search"),
            placeholder=t("symbol_search_placeholder"),
            key=symbol_search_widget_key,
        )
        st.session_state["dashboard_symbol_search"] = symbol_search_query

        symbol_search_matches: list[str] = []
        search_results: list[str] = []
        search_matches_widget_key = "dashboard_symbol_search_matches_widget"
        if symbol_search_query.strip():
            search_results = sort_ticker_options(
                build_symbol_search_results(symbol_search_query, selected_market_scope, max_results=12)
            )
            st.caption(t("search_results_help"))
            if search_results:
                if search_matches_widget_key not in st.session_state:
                    st.session_state[search_matches_widget_key] = []
                valid_search_matches = [
                    normalize_dashboard_ticker(value)
                    for value in st.session_state.get(search_matches_widget_key, [])
                    if normalize_dashboard_ticker(value) in set(search_results)
                ]
                st.session_state[search_matches_widget_key] = valid_search_matches
                symbol_search_matches = st.multiselect(
                    t("search_results"),
                    options=search_results,
                    format_func=display_ticker_label,
                    help=t("search_results_help"),
                    key=search_matches_widget_key,
                )
                symbol_search_matches = [
                    normalize_dashboard_ticker(value)
                    for value in symbol_search_matches
                    if normalize_dashboard_ticker(value) in set(search_results)
                ]
                st.session_state["dashboard_symbol_search_matches"] = symbol_search_matches
                if st.button(search_add_label, use_container_width=True):
                    st.session_state["dashboard_selected_tickers"] = merge_ticker_selection(
                        selected_ticker_picks,
                        symbol_search_matches,
                        selected_market_scope,
                    )
                    st.session_state["dashboard_selected_tickers_initialized"] = True
                    st.rerun()
            else:
                st.session_state["dashboard_symbol_search_matches"] = []
                st.caption(t("search_results_empty"))
        else:
            st.session_state["dashboard_symbol_search_matches"] = []

        available_universe = set()
        source_groups = selected_groups or scope_group_options
        for group in source_groups:
            available_universe.update(WATCHLIST_PRESETS.get(group, []))
        available_universe.update(
            ticker for ticker in DEFAULT_TICKERS
            if selected_market_scope != "Taiwan only" or is_taiwan_ticker(ticker)
        )
        for ticker in custom_tickers + st.session_state.get("dashboard_symbol_search_matches", []) + selected_ticker_picks:
            if not ticker:
                continue
            if selected_market_scope == "Taiwan only" and not is_taiwan_ticker(ticker):
                continue
            if selected_market_scope == "U.S. only" and is_taiwan_ticker(ticker):
                continue
            available_universe.add(ticker)
        available_universe = sort_ticker_options(available_universe)
        selected_ticker_set = {normalize_dashboard_ticker(value) for value in selected_ticker_picks}
        available_universe = [
            ticker for ticker in available_universe
            if normalize_dashboard_ticker(ticker) not in selected_ticker_set
        ]

        candidate_widget_key = "dashboard_candidate_tickers_widget"
        if candidate_widget_key not in st.session_state:
            st.session_state[candidate_widget_key] = []
        st.session_state[candidate_widget_key] = [
            normalize_dashboard_ticker(value)
            for value in st.session_state.get(candidate_widget_key, [])
            if normalize_dashboard_ticker(value) in set(available_universe)
        ]
        candidate_tickers = st.multiselect(
            available_tickers_label,
            options=available_universe,
            placeholder=t("pick_watchlist_symbols"),
            format_func=display_ticker_label,
            key=candidate_widget_key,
        )

        candidate_action_cols = st.columns(2)
        if candidate_action_cols[0].button(add_visible_label, use_container_width=True):
            st.session_state["dashboard_selected_tickers"] = merge_ticker_selection(
                selected_ticker_picks,
                candidate_tickers,
                selected_market_scope,
            )
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()
        if candidate_action_cols[1].button(select_all_visible_label, use_container_width=True):
            st.session_state["dashboard_selected_tickers"] = merge_ticker_selection(
                selected_ticker_picks,
                available_universe,
                selected_market_scope,
            )
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()

        selected_ticker_picks = filter_tickers_for_market_scope(
            st.session_state.get("dashboard_selected_tickers", []),
            selected_market_scope,
        )
        st.session_state["dashboard_selected_tickers"] = selected_ticker_picks

        render_html_block(
            f'<div class="side-group-label">{selected_watchlist_label}</div>'
        )
        st.caption(selected_count_label.format(count=len(selected_ticker_picks)))

        remove_widget_key = "dashboard_selected_remove_widget"
        if remove_widget_key not in st.session_state:
            st.session_state[remove_widget_key] = []
        st.session_state[remove_widget_key] = [
            normalize_dashboard_ticker(value)
            for value in st.session_state.get(remove_widget_key, [])
            if normalize_dashboard_ticker(value) in set(selected_ticker_picks)
        ]
        remove_candidates = st.multiselect(
            selected_watchlist_label,
            options=selected_ticker_picks,
            format_func=display_ticker_label,
            placeholder=t("pick_watchlist_symbols"),
            key=remove_widget_key,
        )

        selected_action_cols = st.columns(2)
        if selected_action_cols[0].button(remove_selected_label, use_container_width=True):
            removal_set = {normalize_dashboard_ticker(value) for value in remove_candidates}
            st.session_state["dashboard_selected_tickers"] = [
                ticker for ticker in selected_ticker_picks
                if normalize_dashboard_ticker(ticker) not in removal_set
            ]
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()
        if selected_action_cols[1].button(clear_selected_label, use_container_width=True):
            st.session_state["dashboard_selected_tickers"] = []
            st.session_state["dashboard_selected_tickers_initialized"] = True
            st.rerun()

        selected_ticker_picks = filter_tickers_for_market_scope(
            st.session_state.get("dashboard_selected_tickers", []),
            selected_market_scope,
        )
        st.session_state["dashboard_selected_tickers"] = selected_ticker_picks
        st.session_state["dashboard_selected_tickers_initialized"] = True

        if selected_ticker_picks:
            preview_items = "".join(
                f'<span class="chip chip-info" style="margin-right:6px; margin-bottom:6px;">{escape(display_ticker_label(ticker))}</span>'
                for ticker in selected_ticker_picks[:10]
            )
            if len(selected_ticker_picks) > 10:
                preview_items += (
                    f'<span class="chip" style="margin-right:6px; margin-bottom:6px;">+{len(selected_ticker_picks) - 10}</span>'
                )
            render_html_block(f'<div class="chip-row" style="margin-top:8px;">{preview_items}</div>')
        else:
            st.caption("目前尚未加入股票，請先從上方加入。" if is_zh else "No symbols added yet. Add symbols from the sections above.")

        tickers = dedupe_keep_order(selected_ticker_picks)
        st.session_state["dashboard_final_tickers"] = tickers
        st.caption(t("watchlist_caption"))
        render_html_block(f'<div class="side-group-label">{t("trend_lens")}</div>')

        stored_lens_name = st.session_state.get("dashboard_lens_name", DEFAULT_TREND_LENS)
        if stored_lens_name not in TREND_LENSES:
            stored_lens_name = DEFAULT_TREND_LENS
        lens_name = st.select_slider(
            t("trend_lens"),
            options=list(TREND_LENSES.keys()),
            value=stored_lens_name,
            format_func=tr_lens_name,
            help="Swap between purpose-built chart lenses instead of raw lookback periods." if get_lang() == "English" else "在不同的用途鏡頭間切換，而不是只看原始期間。",
        )
        st.session_state["dashboard_lens_name"] = lens_name

        manual_override = st.toggle(t("manual_period_override"), value=st.session_state.get("dashboard_manual_override", False))
        st.session_state["dashboard_manual_override"] = manual_override
        if manual_override:
            manual_period = st.selectbox(
                t("custom_lookback"),
                SUPPORTED_PERIODS,
                index=SUPPORTED_PERIODS.index(st.session_state.get("dashboard_manual_period", DEFAULT_PERIOD)),
            )
            manual_interval = st.selectbox(
                t("custom_interval"),
                SUPPORTED_INTERVALS,
                index=SUPPORTED_INTERVALS.index(st.session_state.get("dashboard_manual_interval", DEFAULT_INTERVAL)),
            )
        else:
            manual_period = st.session_state.get("dashboard_manual_period", DEFAULT_PERIOD)
            manual_interval = st.session_state.get("dashboard_manual_interval", DEFAULT_INTERVAL)
        st.session_state["dashboard_manual_period"] = manual_period
        st.session_state["dashboard_manual_interval"] = manual_interval

        lens_meta = resolve_trend_lens(lens_name, manual_override, manual_period, manual_interval)
        period = lens_meta["period"]
        interval = lens_meta["interval"]
        lens_display = tr_lens_meta(lens_meta)

        st.markdown(
            f"""
            <div class="side-lens-shell">
                <div class="side-lens-title">{escape(lens_display['title'])}</div>
                <div class="side-lens-copy">{escape(lens_display['hook'])}</div>
                <div class="side-lens-chip-row">
                    <span class="side-lens-chip">{escape(period)}</span>
                    <span class="side-lens-chip">{escape(interval)}</span>
                    <span class="side-lens-chip">{t('reference_lens')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        save_dashboard_preferences(
            {
                "lang": selected_lang,
                "devicectl": selected_device_control,
                "device": selected_device_mode,
                "news": selected_news_mode,
                "scope": selected_market_scope,
                "groups": _csv_encode(selected_groups),
                "picks": _csv_encode(
                    selected_ticker_picks,
                    empty_sentinel=EMPTY_SELECTION_SENTINEL
                    if st.session_state.get("dashboard_selected_tickers_initialized", False)
                    else None,
                ),
                "custom": custom_ticker_text.strip(),
                "search": symbol_search_query.strip(),
                "lens": lens_name,
                "manual": "1" if manual_override else "0",
                "period": manual_period,
                "interval": manual_interval,
            }
        )

        render_html_block(f'<div class="side-group-label">{t("live_refresh")}</div>')
        if st.button(t("refresh_live_data"), use_container_width=True):
            st.cache_data.clear()
        st.caption(t("refresh_caption"))

    render_html_block(f'<div class="top-kicker">{t("app_name")}</div>')
    st.title(t("app_name"))
    render_html_block(
        f'<div class="top-intro">{t("top_intro")}</div>'
    )

    if not tickers:
        st.warning(t("please_select_ticker"))
        return

    with st.spinner(t("loading_data")):
        daily_data = fetch_daily_data(tickers, period, interval)
        intraday_data = fetch_intraday_data(tickers)
        global_reference_data = fetch_global_reference_data(period, interval)

    if daily_data is None or daily_data.empty:
        st.error(t("no_market_data"))
        return

    global_indicator = build_global_market_indicator(global_reference_data, lens_meta=lens_meta)
    render_global_market_indicator(global_indicator)
    render_section_guide()
    render_active_trend_lens(lens_meta)

    render_stock_explorer_nav(tickers)
    render_global_scenario_planning_stack(daily_data, intraday_data, tickers, lens_meta=lens_meta)
    render_precomparison_target_and_brief_groups(daily_data, intraday_data, tickers, lens_meta=lens_meta)
    render_comparison_section(daily_data, intraday_data, tickers, lens_meta=lens_meta)

    tabs = st.tabs([display_ticker_label(ticker) for ticker in tickers])
    for tab, ticker in zip(tabs, tickers):
        with tab:
            render_ticker_page(daily_data, intraday_data, ticker, lens_meta=lens_meta, selected_count=len(tickers))

    render_html_block(
        f'<div class="footer-note">{t("footer_note")}</div>'
    )


if __name__ == "__main__":
    generate_dashboard()
