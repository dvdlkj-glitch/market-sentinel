#!/usr/bin/env python
from __future__ import annotations

from html import escape
import textwrap
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
import yfinance as yf

# ---------------------------
# Configuration
# ---------------------------
DEFAULT_TICKERS = ["NVDA", "TSM"]
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
SUPPORTED_PERIODS = ["3mo", "6mo", "1y", "2y"]
SUPPORTED_INTERVALS = ["1d", "1wk"]

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
}
NEGATIVE_NEWS_KEYWORDS = {
    "miss", "misses", "downgrade", "downgrades", "fall", "falls", "drop", "drops",
    "slump", "slumps", "cuts", "cut", "weak", "warning", "lawsuit", "probe",
    "investigation", "delay", "delays", "decline", "declines", "bearish", "selloff",
    "recall", "ban", "tariff", "fine", "antitrust", "layoff", "margin pressure",
}

st.set_page_config(page_title="David Lau Stock Market Vision", page_icon="📈", layout="wide")




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
            gap: 10px;
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

        .stDataFrame, div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.90);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: var(--shadow-md);
            overflow: hidden;
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
    try:
        tk = yf.Ticker(ticker)
        try:
            raw_news = tk.news or []
        except Exception:
            raw_news = tk.get_news() or []
    except Exception as e:
        return [], f"News unavailable for {ticker}: {e}"

    items = []
    ticker_upper = ticker.upper()

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

        text_blob = f"{title} {summary}".upper()
        relevance = 0
        if ticker_upper in related:
            relevance += 4
        if ticker_upper in text_blob:
            relevance += 2
        if any(keyword in text_blob for keyword in ("EARNINGS", "GUIDANCE", "AI", "CHIPS", "DEMAND", "REVENUE", "EXPORT", "TARIFF")):
            relevance += 1

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
        })

    items.sort(key=lambda x: (x["relevance"], pd.Timestamp.min.tz_localize("UTC") if pd.isna(x["published"]) else x["published"]), reverse=True)
    filtered = [x for x in items if x["relevance"] > 0]
    return (filtered or items)[:max_items], None


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


def calculate_rsi(series: pd.Series, period: int = 14):
    if series is None or len(series) < period + 1:
        return pd.Series(dtype="float64")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).astype("float64")


def build_indicator_frame(price_series: pd.Series):
    price_series = ensure_datetime_index(price_series)
    df = pd.DataFrame({"Price": price_series.copy()})
    df["SMA 20"] = price_series.rolling(20).mean()
    df["SMA 50"] = price_series.rolling(50).mean()
    df["SMA 200"] = price_series.rolling(200).mean()
    df["RSI 14"] = calculate_rsi(price_series)
    df["1Y Return %"] = ((price_series / price_series.iloc[0]) - 1) * 100
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
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def build_trading_lab(price_series: pd.Series, volume_series: pd.Series | None) -> dict:
    series = ensure_datetime_index(price_series).dropna()
    if series.empty:
        return {}
    macd_line, signal_line, hist = calculate_macd(series)
    sma20 = series.rolling(20).mean()
    std20 = series.rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20

    last_price = series.iloc[-1]
    recent_high = series.tail(20).max()
    recent_low = series.tail(20).min()
    support = series.tail(20).nsmallest(min(3, len(series.tail(20)))).mean()
    resistance = series.tail(20).nlargest(min(3, len(series.tail(20)))).mean()

    tags = []
    if pd.notna(upper.iloc[-1]) and last_price > upper.iloc[-1]:
        tags.append("Breakout stretch")
    elif pd.notna(lower.iloc[-1]) and last_price < lower.iloc[-1]:
        tags.append("Breakdown risk")
    elif pd.notna(sma20.iloc[-1]) and last_price < sma20.iloc[-1] and last_price > support:
        tags.append("Pullback zone")
    else:
        tags.append("Trend continuation")

    if hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
        tags.append("MACD improving")
    elif hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
        tags.append("MACD weakening")

    volume_ratio = pd.NA
    if volume_series is not None and not volume_series.empty:
        vol = ensure_datetime_index(volume_series).dropna()
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

    return {
        "macd": macd_line.iloc[-1],
        "macd_signal": signal_line.iloc[-1],
        "macd_hist": hist.iloc[-1],
        "bb_upper": upper.iloc[-1],
        "bb_mid": sma20.iloc[-1],
        "bb_lower": lower.iloc[-1],
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
    st.markdown(
        f"""
        <div class="lens-shell">
            <div class="section-header" style="margin:0;">Trend Lens</div>
            <div class="lens-title">{escape(lens_meta.get('title', 'Trend Lens'))}</div>
            <div class="lens-copy">{escape(lens_meta.get('hook', ''))}</div>
            <div class="lens-grid">
                <div class="lens-card">
                    <div class="lens-label">Best use</div>
                    <div class="lens-head">{escape(lens_meta.get('title', 'Trend Lens'))}</div>
                    <div class="lens-sub">{escape(lens_meta.get('hook', ''))}</div>
                </div>
                <div class="lens-card">
                    <div class="lens-label">How to read it</div>
                    <div class="lens-head">What this lens is good at</div>
                    <div class="lens-sub">{escape(lens_meta.get('how_to_read', ''))}</div>
                </div>
                <div class="lens-card">
                    <div class="lens-label">Watch for</div>
                    <div class="lens-head">Most useful reference points</div>
                    <div class="lens-sub">{escape(lens_meta.get('watch_for', ''))}</div>
                </div>
            </div>
            <div class="lens-copy" style="margin-top:12px;">The Winner Card and comparison scores now adapt to this active lens, so the strongest stock can change depending on whether you care about fresh reaction, swing structure, position strength, or cycle leadership.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_explore_hero():
    st.markdown(
        """
        <div class="editorial-hero">
            <div class="hero-kicker">Command Layer</div>
            <div class="hero-title">Institutional-style market research, redesigned with a calmer premium theme.</div>
            <div class="hero-copy">The new direction is cleaner, darker, and more focused. It reduces visual noise, strengthens hierarchy, and makes the journey from watchlist scan to deep ticker research feel more intentional.</div>
            <div class="hero-chip-row">
                <span class="hero-chip">News-first reading flow</span>
                <span class="hero-chip">Winner card with context</span>
                <span class="hero-chip">Catalyst Engine reference guide</span>
                <span class="hero-chip">Trading Lab interpretation</span>
                <span class="hero-chip">Same theme, richer journey</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_guide():
    st.markdown(
        """
        <div class="guide-shell">
            <div class="guide-title">A more focused flow for deeper exploration</div>
            <div class="guide-copy">Each section now behaves like part of a deliberate workflow: scan, compare, understand the driver, then validate the setup.</div>
            <div class="guide-grid">
                <div class="guide-card">
                    <div class="guide-label">Step 1</div>
                    <div class="guide-head">Comparison Arena</div>
                    <div class="guide-sub">Scan the watchlist fast. This is the shortlist stage where you decide which names deserve attention first.</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">Step 2</div>
                    <div class="guide-head">Winner Card</div>
                    <div class="guide-sub">See which selected stock currently has the strongest setup and why the edge exists versus the next name.</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">Step 3</div>
                    <div class="guide-head">Catalyst + News + Alerts</div>
                    <div class="guide-sub">Find out what is actually driving the narrative, then check how each lens sees the setup: earnings, AI demand, regulation, macro, analysts, or supply chain can shift different lenses in different ways.</div>
                </div>
                <div class="guide-card">
                    <div class="guide-label">Step 4</div>
                    <div class="guide-head">Trading Lab + Candles</div>
                    <div class="guide-sub">Only after the narrative makes sense should you confirm the structure with the active trend lens, MACD, Bollinger context, support, resistance, and candles.</div>
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
            <div class="reference-title">Reference guide for {escape(ticker)}</div>
            <div class="reference-copy">This panel explains what matters most in the current setup, so readers understand why each section exists instead of just seeing another chart or score.</div>
            <div class="reference-grid">
                <div class="reference-card">
                    <div class="reference-label">What to watch in news</div>
                    <div class="reference-head">{escape(catalyst.get('dominant', 'Macro'))}</div>
                    <div class="reference-sub">This is the most active catalyst bucket right now. If new headlines keep leaning the same way, they can strengthen or weaken the current signal faster than technicals alone.</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">What gives conviction</div>
                    <div class="reference-head">{escape(analysis.get('confidence', 'Moderate'))} confidence</div>
                    <div class="reference-sub">Confidence comes from trend structure, news pulse, and trade setup aligning. When those disagree, the dashboard tends to fall back to HOLD.</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">Trading lens</div>
                    <div class="reference-head">{escape(lab.get('setup', 'Balanced'))}</div>
                    <div class="reference-sub">Use this as the action style: momentum-led means continuation is cleaner, pullback watch means patience matters, and risk-off means price can stay fragile.</div>
                </div>
                <div class="reference-card">
                    <div class="reference-label">Lead story context</div>
                    <div class="reference-head">{escape((lead.get('title') or 'No strong lead story')[:56])}</div>
                    <div class="reference-sub">The lead story is the fastest narrative snapshot. Check whether its direction agrees with the Catalyst Engine before trusting it too much.</div>
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
                <div class="soft-note">{provider} · Why it matters to {escape(ticker)}: {reason}</div>
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
    return mapping.get(lens_title, {}).get(state, f"{lens_title} {state}")


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

    reasons_html = "".join(f"<li>{escape(item)}</li>" for item in active_state.get("reasons", [])) or "<li>No extra alert context is active.</li>"

    st.markdown(
        f"""
        <div class="alert-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">Alert Layer</div>
            <div class="alert-title">{escape(alert_map.get('headline', 'Lens states are mixed.'))}</div>
            <div class="alert-copy">Each lens now has its own alert state, so the same stock can be Fast Read bullish while still being Cycle View mixed or laggard.</div>
            <div class="alert-grid">
                <div class="alert-box">
                    <div class="alert-label">Fast Read</div>
                    <div class="alert-value">{escape(states.get('Fast Read', {}).get('label', 'N/A'))}</div>
                    <div class="alert-sub">Score {states.get('Fast Read', {}).get('score', 0):+d}</div>
                </div>
                <div class="alert-box">
                    <div class="alert-label">Swing Map</div>
                    <div class="alert-value">{escape(states.get('Swing Map', {}).get('label', 'N/A'))}</div>
                    <div class="alert-sub">Score {states.get('Swing Map', {}).get('score', 0):+d}</div>
                </div>
                <div class="alert-box">
                    <div class="alert-label">Position View</div>
                    <div class="alert-value">{escape(states.get('Position View', {}).get('label', 'N/A'))}</div>
                    <div class="alert-sub">Score {states.get('Position View', {}).get('score', 0):+d}</div>
                </div>
                <div class="alert-box">
                    <div class="alert-label">Cycle View</div>
                    <div class="alert-value">{escape(states.get('Cycle View', {}).get('label', 'N/A'))}</div>
                    <div class="alert-sub">Score {states.get('Cycle View', {}).get('score', 0):+d}</div>
                </div>
            </div>
            <div class="lens-alert-row">{''.join(chip_html)}</div>
            <div class="lens-alert-note"><strong>Active lens focus:</strong> {escape(active_title)} · {escape(active_state.get('label', 'N/A'))}</div>
            <ul class="crypto-reasons">{reasons_html}</ul>
            <div class="lens-alert-note">Bullish {counts.get('bullish', 0)} · Neutral {counts.get('neutral', 0)} · Bearish {counts.get('bearish', 0)}</div>
        </div>
        """,
        unsafe_allow_html=True,
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
    guide = "Start here when you want one answer first. The winner card now adapts to the active Trend Lens, so leadership can change based on the question you are asking."
    why = leader_fields["lens_reasons"][:3] or leader_analysis["reasons"][:3]

    st.markdown(
        f"""
        <div class="winner-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">Smart Compare</div>
            <div class="winner-copy">{escape(guide)}</div>
            <div class="winner-hero">
                <div class="winner-hero-main">
                    <span class="winner-badge">Winner Card</span>
                    <div class="winner-main-title">{escape(leader['ticker'])} is leading under {escape(leader_fields['lens_title'])}</div>
                    <div class="winner-main-copy">Compared with {escape(runner['ticker'])}, this setup currently has the cleaner edge for the active lens. Change the lens and the winner can change too.</div>
                    <ul class="winner-reason-list">{''.join(f'<li>{escape(item)}</li>' for item in why)}</ul>
                </div>
                <div class="winner-hero-side">
                    <div class="winner-rail-grid">
                        <div class="winner-mini">
                            <div class="winner-mini-label">Current leader</div>
                            <div class="winner-mini-value">{escape(leader['ticker'])}</div>
                            <div class="winner-mini-sub">Lens score {leader_fields['lens_score']:+d} · {escape(leader_analysis['signal'])}</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">Nearest rival</div>
                            <div class="winner-mini-value">{escape(runner['ticker'])}</div>
                            <div class="winner-mini-sub">Lens score {runner_fields['lens_score']:+d} · {escape(runner['analysis']['signal'])}</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">Lens adjustment</div>
                            <div class="winner-mini-value">{leader_fields['lens_adjustment']:+d}</div>
                            <div class="winner-mini-sub">Base score {leader_fields['base_score']:+d} adjusted by the active lens.</div>
                        </div>
                        <div class="winner-mini">
                            <div class="winner-mini-label">Catalyst edge</div>
                            <div class="winner-mini-value">{escape(catalyst)}</div>
                            <div class="winner-mini-sub">Runner-up focus: {escape(runner_catalyst)} · Current edge {diff:+d}</div>
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
    latest = indicators.iloc[-1]
    last_price = latest["Price"]
    sma20 = latest["SMA 20"]
    sma50 = latest["SMA 50"]
    sma200 = latest["SMA 200"]
    rsi14 = latest["RSI 14"]
    one_year_return = latest["1Y Return %"]

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
        volume_series = ensure_datetime_index(volume_series)
        avg_volume_50 = volume_series.tail(50).mean()
        vol_ratio = (volume_series.iloc[-1] / avg_volume_50) if pd.notna(avg_volume_50) and avg_volume_50 != 0 else pd.NA
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
        return "High"
    if relevance >= 2:
        return "Medium"
    return "Low"


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
        return "Likely to support upside", "impact-up", "row-meter-fill-up"
    if "bearish" in label_l:
        return "Likely to pressure downside", "impact-down", "row-meter-fill-down"
    return "Likely to keep direction mixed", "impact-flat", "row-meter-fill-flat"


def signal_css_class(signal: str) -> str:
    return {"BUY": "crypto-buy", "HOLD": "crypto-hold", "SELL": "crypto-sell"}.get(signal, "crypto-hold")


def compact_story_line(item: dict, ticker: str) -> str:
    direction_text, tag_class, _ = article_direction_meta(item)
    prob = article_probability(item)
    title = escape(item.get("title", "Untitled"))
    summary = escape((item.get("summary") or item.get("impact_reason") or "")[:180])
    provider = escape(str(item.get("provider", "Unknown source")))
    us_time = format_us_timestamp(item.get("published"))
    link_html = ""
    if item.get("url"):
        link_html = f'<a class="brief-link" href="{escape(str(item["url"]))}" target="_blank">Open article ↗</a>'
    return f"""
        <div class="brief-item">
            <div class="brief-meta">{provider} · {us_time}</div>
            <div class="brief-headline">{title}</div>
            <div class="brief-summary">{summary}</div>
            <div style="margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
                <span class="impact-tag {tag_class}">{escape(direction_text)}</span>
                <span class="impact-tag impact-flat">Impact chance {prob}%</span>
            </div>
            {link_html}
        </div>
    """


def render_daily_briefing(ticker: str, news_items: list[dict]):
    top_items = news_items[:3]
    if not top_items:
        st.info(f"No recent stock-specific news was returned for {ticker}.")
        return
    body = "".join(compact_story_line(item, ticker) for item in top_items)
    st.markdown(
        f"""
        <div class="news-brief-card">
            <div class="section-header">Daily Briefing</div>
            {body}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_story(ticker: str, analysis: dict, news_items: list[dict]):
    if news_items:
        lead = news_items[0]
        direction_text, _, _ = article_direction_meta(lead)
        probability = article_probability(lead)
        title = escape(lead.get("title", f"{ticker} market setup"))
        summary = escape((lead.get("summary") or lead.get("impact_reason") or analysis["summary"])[:420])
        provider = escape(str(lead.get("provider", "Unknown source")))
        meta = f"{provider} · Taiwan {format_tw_timestamp(lead.get('published'))}"
        link_html = ""
        if lead.get("url"):
            link_html = f'<a class="small-pill" href="{escape(str(lead["url"]))}" target="_blank">Open article ↗</a>'
        pos = probability if "bullish" in lead.get("impact_label", "").lower() else max(100 - probability, 18)
        neg = probability if "bearish" in lead.get("impact_label", "").lower() else max(100 - probability, 18)
        why_copy = escape(lead.get("impact_reason", analysis["summary"]))
    else:
        lead = None
        direction_text = "Direction currently mixed"
        probability = 50
        title = escape(f"{ticker} is trading on technical and news cross-currents")
        summary = escape(analysis["summary"])
        meta = "No stock-specific story returned"
        link_html = ""
        pos = neg = 50
        why_copy = escape(analysis["summary"])

    st.markdown(
        f"""
        <div class="lead-story">
            <div class="section-header" style="margin:0; color:#eef4ff;">Top Story</div>
            <div class="lead-kicker">{escape(meta)}</div>
            <div class="lead-title">{title}</div>
            <div class="lead-summary">{summary}</div>
            <div class="lead-meta-row">
                <span class="small-pill">{escape(direction_text)}</span>
                <span class="small-pill">Estimated effect on {escape(ticker)}: {probability}%</span>
                <span class="small-pill">{escape(analysis['news_pulse']['label'])}</span>
                {link_html}
            </div>
            <div class="lead-story-board">
                <div class="lead-story-panel">
                    <div class="lead-panel-label">Why this matters now</div>
                    <div class="lead-panel-value">{escape(ticker)} setup context</div>
                    <div class="lead-panel-copy">{why_copy}</div>
                </div>
                <div class="lead-story-panel">
                    <div class="lead-panel-label">Directional pressure</div>
                    <div class="lead-panel-value">Up {pos}% / Down {neg}%</div>
                    <div class="lead-panel-copy">This is a reference estimate of how strongly the story could influence the selected stock in the near term.</div>
                    <div class="impact-meter" style="margin-top:12px;">
                        <div class="impact-pos" style="width:{pos}%;"></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_signal_panel(ticker: str, analysis: dict, intraday: dict, news_items: list[dict]):
    pulse = analysis["news_pulse"]
    signal = analysis["signal"]
    signal_class = signal_css_class(signal)
    intraday_price = format_price(intraday["last_price"]) if intraday.get("available") else "N/A"
    intraday_change = format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A"
    latest_trend_date = format_us_timestamp(analysis["latest_daily_ts"])
    top_reasons = "".join(f"<li>{escape(r)}</li>" for r in analysis["reasons"][:3])
    alert_html = "".join(f"<li>{escape(a)}</li>" for a in analysis.get("alerts", [])[:2]) or "<li>No urgent alert is active.</li>"
    st.markdown(
        f"""
        <div class="crypto-card">
            <div class="crypto-kicker">Pro Signal Deck</div>
            <div class="crypto-signal {signal_class}">{escape(signal)}</div>
            <div class="crypto-main-number">{analysis.get('pro_score', analysis['score']):+d}</div>
            <div class="crypto-sub">{escape(analysis['summary'])}</div>
            <div class="crypto-grid">
                <div class="crypto-mini">
                    <div class="crypto-mini-label">Confidence</div>
                    <div class="crypto-mini-value">{escape(analysis['confidence'])}</div>
                    <div class="crypto-mini-sub">1Y trend: {escape(analysis['trend'])}</div>
                </div>
                <div class="crypto-mini">
                    <div class="crypto-mini-label">News Pulse</div>
                    <div class="crypto-mini-value">{pulse['up']}/{pulse['down']}</div>
                    <div class="crypto-mini-sub">{escape(pulse['label'])}</div>
                </div>
                <div class="crypto-mini">
                    <div class="crypto-mini-label">Intraday</div>
                    <div class="crypto-mini-value">{intraday_change}</div>
                    <div class="crypto-mini-sub">{intraday_price}</div>
                </div>
                <div class="crypto-mini">
                    <div class="crypto-mini-label">Trading Lab</div>
                    <div class="crypto-mini-value">{escape(analysis.get('trading_lab', {}).get('setup', 'Balanced'))}</div>
                    <div class="crypto-mini-sub">{latest_trend_date}</div>
                </div>
            </div>
            <ul class="crypto-reasons">{top_reasons}</ul>
            <ul class="crypto-reasons">{alert_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
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


def render_story_row(item: dict, ticker: str, idx: int):
    direction_text, tag_class, meter_class = article_direction_meta(item)
    probability = article_probability(item)
    title = escape(item.get("title", "Untitled"))
    summary = escape(item.get("summary") or item.get("impact_reason") or "")
    provider = escape(str(item.get("provider", "Unknown source")))
    related = ", ".join(item.get("related", [])[:5]) if item.get("related") else "Not provided"
    meta = f"{provider} · US {format_us_timestamp(item.get('published'))} · Taiwan {format_tw_timestamp(item.get('published'))}"
    relevance = relevance_label(int(item.get("relevance", 0)))
    link_html = ""
    if item.get("url"):
        link_html = f'<a class="inline-link" href="{escape(str(item["url"]))}" target="_blank">Open article ↗</a>'
    st.markdown(
        f"""
        <div class="story-row">
            <div class="story-row-head">
                <div>
                    <div class="story-row-meta">Story {idx:02d} · {escape(meta)}</div>
                    <div class="story-row-title">{title}</div>
                    <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">
                        <span class="impact-tag {tag_class}">{escape(direction_text)}</span>
                        <span class="impact-tag impact-flat">Confidence {escape(item.get('confidence', 'N/A'))}</span>
                        <span class="impact-tag impact-flat">Relevance {escape(relevance)}</span>
                    </div>
                </div>
            </div>
            <div class="story-row-grid">
                <div>
                    <div class="story-row-summary">{summary}</div>
                    <div class="story-row-summary"><strong>Why this could matter to {escape(ticker)}:</strong> {escape(item.get('impact_reason', ''))}</div>
                    <div class="story-row-summary"><strong>Related tickers:</strong> {escape(related)}</div>
                    <div class="row-meter"><div class="{meter_class}" style="width:{probability}%;"></div></div>
                    <div style="margin-top:10px;">{link_html}</div>
                </div>
                <div class="prob-box">
                    <div class="prob-label">Estimated effect</div>
                    <div class="prob-value">{probability}%</div>
                    <div class="prob-sub">Chance this story materially nudges {escape(ticker)} in the shown direction over the near term.</div>
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
        """
        <div class="news-board-shell">
            <div class="section-header" style="margin:0; color:#eef4ff;">Top News Stories</div>
            <div class="news-board-copy">Selected-stock stories first. Use the highlights board to spot what matters most, then move into the full story rows for detail, relevance, and directional context.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not news_items:
        st.info(f"No recent stock-specific news was returned for {ticker}.")
        return
    render_news_highlights(ticker, news_items)
    for idx, item in enumerate(news_items, start=1):
        render_story_row(item, ticker, idx)

def render_trend_section(analysis: dict, intraday: dict, lens_meta: dict | None = None, daily_ohlc: pd.DataFrame | None = None, intraday_ohlc: pd.DataFrame | None = None):
    st.markdown(
        f"""
        <div class="trend-shell">
            <div class="trend-header">
                <div>
                    <div class="section-header" style="margin:0;">Trend Lab</div>
                    <div class="trend-title">Candlestick confirmation</div>
                    <div class="trend-sub">This section stays at the bottom so readers first absorb the news and estimated stock impact, then confirm the setup with the active trend lens and live tape.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last daily close", format_price(analysis["last_price"]))
    c2.metric("SMA 50 vs 200", f"{format_price(analysis['sma50'])} / {format_price(analysis['sma200'])}")
    c3.metric("RSI 14", "N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}")
    c4.metric("Intraday move", format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A")

    render_trading_lab_panel(analysis)

    render_candlestick_chart(
        daily_ohlc.tail(252) if daily_ohlc is not None else pd.DataFrame(),
        "Candlestick structure under the active trend lens",
        f"{lens_meta.get('title', 'Trend Lens')}: {lens_meta.get('how_to_read', 'Use this view to confirm structure.')}" if lens_meta else "Daily candlesticks with SMA 20 and SMA 50 overlays for structure confirmation.",
        height=440,
        show_ma=True,
    )

    if intraday.get("available") and intraday_ohlc is not None and not intraday_ohlc.empty:
        render_candlestick_chart(
            intraday_ohlc.tail(78),
            "Live intraday candlestick tape (5m)",
            "Latest intraday price action in the same dark premium theme.",
            height=300,
            show_ma=False,
        )

    st.markdown(
        f'<div class="footer-note">Research view only. The signal combines moving averages, RSI, volume confirmation, 1-year trend, and current stock-specific news pulse.</div>',
        unsafe_allow_html=True,
    )


def build_snapshot_row(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str):
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



def render_comparison_section(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, tickers: list[str], lens_meta: dict | None = None):
    if len(tickers) < 2:
        return

    bundles = [collect_ticker_context(daily_data, intraday_data, ticker, news_limit=8, lens_meta=lens_meta) for ticker in tickers]
    bundles = [bundle for bundle in bundles if bundle is not None]
    if len(bundles) < 2:
        return

    render_winner_card(bundles, lens_meta=lens_meta)

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
                    <div class="section-header" style="margin:0; color:#eef4ff;">Comparison Arena</div>
                    <div class="compare-title">Modern side-by-side setup for price strength and signal quality</div>
                    <div class="compare-copy">This section now follows the same premium dark control-panel style as your sidebar. It lets you scan which stock has stronger trend structure, cleaner recommendation quality, and better news support before you open each individual page.</div>
                </div>
            </div>
            <div class="compare-hero-grid">
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">Strongest Pro setup</div>
                    <div class="compare-hero-value">{escape(strongest['ticker'])}</div>
                    <div class="compare-hero-sub">Lens score {compute_lens_winner_fields(strongest, lens_meta)['lens_score']:+d} · {escape(strongest['analysis']['signal'])} · {escape(strongest['analysis']['confidence'])} confidence</div>
                </div>
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">Best 1Y price strength</div>
                    <div class="compare-hero-value">{escape(best_return['ticker'])}</div>
                    <div class="compare-hero-sub">{format_percent(best_return['analysis']['one_year_return'])} over the selected trend window</div>
                </div>
                <div class="compare-hero-tile">
                    <div class="compare-hero-label">Best current news tailwind</div>
                    <div class="compare-hero-value">{escape(most_bullish_news['ticker'])}</div>
                    <div class="compare-hero-sub">{escape(most_bullish_news['analysis']['news_pulse']['label'])}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
                    <div class="compare-card-kicker">Side-by-side profile</div>
                    <div style="margin-top:10px;"><span class="crypto-signal {signal_class_name}">{escape(signal)}</span></div>
                    <div class="compare-card-title">{escape(bundle['ticker'])}</div>
                    <div class="compare-card-price">{format_price(analysis['last_price'])}</div>
                    <div class="compare-card-grid">
                        <div class="compare-stat">
                            <div class="compare-stat-label">1Y Return</div>
                            <div class="compare-stat-value">{format_percent(analysis['one_year_return'])}</div>
                        </div>
                        <div class="compare-stat">
                            <div class="compare-stat-label">Confidence</div>
                            <div class="compare-stat-value">{escape(analysis['confidence'])}</div>
                        </div>
                        <div class="compare-stat">
                            <div class="compare-stat-label">Lens Score</div>
                            <div class="compare-stat-value">{compute_lens_winner_fields(bundle, lens_meta)['lens_score']:+d}</div>
                        </div>
                        <div class="compare-stat">
                            <div class="compare-stat-label">RSI 14</div>
                            <div class="compare-stat-value">{"N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}"}</div>
                        </div>
                    </div>
                    <div class="compare-card-meta">
                        Intraday <strong>{format_percent(intraday['change_pct']) if intraday.get('available') else 'N/A'}</strong> · News pulse <strong>{escape(pulse)}</strong>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    row_html_parts = []
    candle_card_parts = []

    for bundle in bundles:
        analysis = bundle["analysis"]
        intraday = bundle["intraday"]
        daily_ohlc = bundle.get("daily_ohlc", pd.DataFrame())

        signal = analysis["signal"]
        signal_class_name = signal_css_class(signal)
        row_html_parts.append(textwrap.dedent(f"""<div class="compare-table-row">
    <div class="compare-table-cell">
        <div class="compare-table-ticker">{escape(bundle['ticker'])}</div>
        <div class="compare-table-sub">{escape(analysis['trend'])}</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">Last price</div>
        <div class="compare-table-value">{format_price(analysis['last_price'])}</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">1Y return</div>
        <div class="compare-table-value">{format_percent(analysis['one_year_return'])}</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">Signal</div>
        <div><span class="compare-table-chip {signal_class_name}">{escape(signal)}</span></div>
        <div class="compare-table-note">{escape(analysis['confidence'])} confidence</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">Lens score</div>
        <div class="compare-table-value">{compute_lens_winner_fields(bundle, lens_meta)['lens_score']:+d}</div>
        <div class="compare-table-note">RSI {"N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}"}</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">Intraday</div>
        <div class="compare-table-value">{format_percent(intraday['change_pct']) if intraday.get('available') else 'N/A'}</div>
        <div class="compare-table-note">{escape(analysis['rsi_status'])}</div>
    </div>
    <div class="compare-table-cell">
        <div class="compare-table-sub">News pulse</div>
        <div class="compare-table-value">{escape(analysis['news_pulse']['label'])}</div>
        <div class="compare-table-note">{escape(analysis['summary'])}</div>
    </div>
</div>
"""))

    st.markdown(
        """
        <div class="compare-chart-shell">
            <div class="compare-chart-title">Candlestick comparison</div>
            <div class="compare-chart-copy">The line race is replaced with candle structure so each selected stock keeps the same premium chart language as the rest of the dashboard.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="mini-candle-grid">', unsafe_allow_html=True)
    for bundle in bundles:
        st.markdown(
            f"""
            <div class="mini-candle-card">
                <div class="mini-candle-name">{escape(bundle['ticker'])}</div>
                <div class="mini-candle-sub">{escape(bundle['analysis']['signal'])} · {escape(bundle['analysis']['trend'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_candlestick_chart(
            bundle.get("daily_ohlc", pd.DataFrame()).tail(60),
            f"{bundle['ticker']} recent structure",
            "Recent daily candles in the shared dashboard theme.",
            height=220,
            show_ma=False,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    board_html = (
        '<div class="compare-table-shell">'
        '<div class="compare-table-title">Recommendation board</div>'
        '<div class="compare-table-copy">This replaces the old plain table with a dark premium board that matches your sidebar style. Use it to compare trend, price, recommendation, momentum, and news context in one scan.</div>'
        '<div class="compare-table-head">'
        '<div>Ticker</div>'
        '<div>Price</div>'
        '<div>1Y Return</div>'
        '<div>Signal</div>'
        '<div>Momentum</div>'
        '<div>Intraday</div>'
        '<div>News Context</div>'
        '</div>'
        '<div class="compare-table-body">'
        + "".join(row_html_parts) +
        '</div>'
        '</div>'
    )
    st.markdown(board_html, unsafe_allow_html=True)

def render_ticker_page(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str, lens_meta: dict | None = None):
    bundle = collect_ticker_context(daily_data, intraday_data, ticker, news_limit=10, lens_meta=lens_meta)
    if bundle is None:
        st.warning(f"No usable price series found for {ticker}.")
        return

    if bundle["news_error"]:
        st.warning(bundle["news_error"])

    analysis = bundle["analysis"]
    intraday = bundle["intraday"]
    news_items = bundle["news_items"]
    daily_ohlc = bundle.get("daily_ohlc", pd.DataFrame())
    intraday_ohlc = bundle.get("intraday_ohlc", pd.DataFrame())
    render_news_first_section(ticker, analysis, intraday, news_items)
    render_reference_guide(analysis, ticker, news_items)
    render_news_stream(ticker, news_items)
    render_trend_section(analysis, intraday, lens_meta=lens_meta, daily_ohlc=daily_ohlc, intraday_ohlc=intraday_ohlc)


# ---------------------------
# Main app
# ---------------------------


def render_stock_explorer_nav(tickers: list[str]):
    chip_html = "".join(f'<span class="explorer-nav-chip">{escape(ticker)}</span>' for ticker in tickers[:10])
    if len(tickers) > 10:
        chip_html += f'<span class="explorer-nav-chip">+{len(tickers) - 10} more</span>'

    st.markdown(
        f"""
        <div class="explorer-nav-shell">
            <div class="explorer-nav-head">
                <div>
                    <div class="explorer-nav-kicker">Explorer Navigation</div>
                    <div class="explorer-nav-title">Choose a ticker below to enter its full market workspace</div>
                    <div class="explorer-nav-copy">This is the transition from <strong>screening</strong> into <strong>deep research</strong>. Select any ticker tab below and the dashboard shifts into that stock’s own workspace with related news, catalyst mapping, lens-aware alerts, Trading Lab, and candlestick confirmation.</div>
                    <div class="explorer-nav-row">
                        {chip_html}
                    </div>
                </div>
                <div class="explorer-nav-panel">
                    <div class="explorer-nav-panel-label">What happens next</div>
                    <div class="explorer-nav-panel-value">Open a ticker workspace ↓</div>
                    <div class="explorer-nav-panel-copy">You’ll move into that stock’s dedicated workspace, where the news, catalysts, alerts, and chart structure are all focused on just that one name.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def generate_dashboard():
    inject_css()
    inject_premium_overrides()
    st.markdown('<div class="top-kicker">David Lau Stock Market Vision</div>', unsafe_allow_html=True)
    st.title("David Lau Stock Market Vision")
    st.markdown(
        '<div class="top-intro">A calmer, more premium market workspace focused on clarity, hierarchy, and deeper exploration across comparison, catalysts, news, and chart structure.</div>',
        unsafe_allow_html=True,
    )
    render_explore_hero()
    render_section_guide()

    with st.sidebar:
        st.markdown(
            """
            <div class="side-hero">
                <div class="side-eyebrow">Control Center</div>
                <div class="side-title">Vision Deck</div>
                <div class="side-copy">Build a much broader U.S. market watchlist, compare selected stocks side by side, and refresh the live tape in one modern control panel.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-group-label">Watchlist universe</div>', unsafe_allow_html=True)
        selected_groups = st.multiselect(
            "Preset groups",
            options=list(WATCHLIST_PRESETS.keys()),
            default=["Tech & AI", "Semiconductors", "Financials", "Healthcare", "Consumer", "Industrials", "Energy", "Market ETFs"],
            placeholder="Expand by sector...",
            label_visibility="collapsed",
        )

        available_universe = set(DEFAULT_WATCHLIST_UNIVERSE)
        for group in selected_groups:
            available_universe.update(WATCHLIST_PRESETS.get(group, []))
        available_universe = sorted(available_universe)

        tickers = st.multiselect(
            "Tickers",
            options=available_universe,
            default=[ticker for ticker in DEFAULT_TICKERS if ticker in available_universe],
            placeholder="Pick any watchlist symbols...",
        )

        custom_ticker_text = st.text_input(
            "Custom symbols",
            value="",
            placeholder="Add any U.S. ticker, e.g. HOOD, NET, CRWD, SHOP",
        )
        custom_tickers = [
            ticker.strip().upper()
            for ticker in custom_ticker_text.replace("\n", ",").split(",")
            if ticker.strip()
        ]

        final_tickers = []
        for ticker in tickers + custom_tickers:
            if ticker not in final_tickers:
                final_tickers.append(ticker)
        tickers = final_tickers

        st.caption("You can now build a much broader U.S. stock watchlist by sector, and also type any extra symbol manually.")
        st.markdown('<div class="side-group-label">Trend lens</div>', unsafe_allow_html=True)
        lens_name = st.select_slider(
            "Trend lens",
            options=list(TREND_LENSES.keys()),
            value=DEFAULT_TREND_LENS,
            help="Swap between purpose-built chart lenses instead of raw lookback periods.",
        )
        manual_override = st.toggle("Manual period override", value=False)
        if manual_override:
            manual_period = st.selectbox("Custom lookback", SUPPORTED_PERIODS, index=SUPPORTED_PERIODS.index(DEFAULT_PERIOD))
            manual_interval = st.selectbox("Custom interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index(DEFAULT_INTERVAL))
        else:
            manual_period = DEFAULT_PERIOD
            manual_interval = DEFAULT_INTERVAL

        lens_meta = resolve_trend_lens(lens_name, manual_override, manual_period, manual_interval)
        period = lens_meta["period"]
        interval = lens_meta["interval"]

        st.markdown(
            f"""
            <div class="side-lens-shell">
                <div class="side-lens-title">{escape(lens_meta['title'])}</div>
                <div class="side-lens-copy">{escape(lens_meta['hook'])}</div>
                <div class="side-lens-chip-row">
                    <span class="side-lens-chip">{escape(period)}</span>
                    <span class="side-lens-chip">{escape(interval)}</span>
                    <span class="side-lens-chip">Reference lens</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="side-group-label">Live refresh</div>', unsafe_allow_html=True)
        if st.button("Refresh live data", use_container_width=True):
            st.cache_data.clear()
        st.caption("News-first layout. Daily trend drives the Sentinel signal. When 2 or more stocks are selected, a comparison arena appears automatically.")

    if not tickers:
        st.warning("Please select at least one ticker.")
        return

    with st.spinner("Loading market data and stock-specific news..."):
        daily_data = fetch_daily_data(tickers, period, interval)
        intraday_data = fetch_intraday_data(tickers)

    if daily_data is None or daily_data.empty:
        st.error("No market data was returned. Please try again.")
        return

    render_active_trend_lens(lens_meta)
    render_comparison_section(daily_data, intraday_data, tickers, lens_meta=lens_meta)

    render_stock_explorer_nav(tickers)
    tabs = st.tabs(tickers)
    for tab, ticker in zip(tabs, tickers):
        with tab:
            render_ticker_page(daily_data, intraday_data, ticker, lens_meta=lens_meta)

    st.markdown(
        '<div class="footer-note">This dashboard is for research and reference. The news effect percentages and directional labels are heuristic estimates, not guarantees or investment advice.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    generate_dashboard()
