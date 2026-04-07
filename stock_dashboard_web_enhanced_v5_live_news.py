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
            --page: #f3f1ea;
            --ink: #161b22;
            --ink-soft: #555c67;
            --ink-muted: #727986;
            --line: #cbc6ba;
            --paper: #fcfbf7;
            --card: #ffffff;
            --navy: #0b1323;
            --navy-2: #101a2d;
            --blue: #2952ff;
            --blue-soft: #dfe7ff;
            --red: #9d2b2f;
            --red-soft: #f7dfdf;
            --green: #0d9f6e;
            --green-soft: #dff8ee;
            --amber: #e6a700;
            --amber-soft: #fff4ce;
            --shadow: 0 18px 34px rgba(19, 28, 45, 0.08);
            --radius-xl: 26px;
            --radius-lg: 20px;
            --radius-md: 16px;
        }
        html, body, [class*="css"], .stApp, .stMarkdown, .stButton button, .stSelectbox label,
        .stMultiSelect label, .stCaption, .stDataFrame, input, textarea, select {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
        }
        .stApp {
            background: var(--page);
            color: var(--ink);
        }
        .block-container {
            max-width: 1480px;
            padding-top: 1.2rem;
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
                radial-gradient(circle at top left, rgba(77, 109, 255, 0.20) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #11192c 0%, #0a1020 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }
        section[data-testid="stSidebar"] * {
            color: #eef2ff !important;
        }
        .side-hero {
            background: linear-gradient(135deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.04) 100%);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 22px;
            padding: 18px 16px;
            margin-bottom: 16px;
            box-shadow: 0 14px 26px rgba(0,0,0,.18);
            backdrop-filter: blur(12px);
        }
        .side-eyebrow {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: .16em;
            color: rgba(238,242,255,.62) !important;
            font-weight: 900;
        }
        .side-title {
            font-size: 22px;
            font-weight: 900;
            letter-spacing: -0.03em;
            color: #ffffff !important;
            margin-top: 6px;
        }
        .side-copy {
            font-size: 13px;
            line-height: 1.55;
            color: rgba(238,242,255,.76) !important;
            margin-top: 8px;
        }
        .side-group-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: rgba(238,242,255,.58) !important;
            margin: 16px 0 8px 0;
        }
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: rgba(255,255,255,.06) !important;
            border: 1px solid rgba(255,255,255,.12) !important;
            border-radius: 18px !important;
            min-height: 56px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.02), 0 8px 18px rgba(0,0,0,.14);
        }
        section[data-testid="stSidebar"] [data-baseweb="select"] input,
        section[data-testid="stSidebar"] [data-baseweb="select"] span,
        section[data-testid="stSidebar"] [data-baseweb="select"] div {
            color: #f8fbff !important;
        }
        section[data-testid="stSidebar"] [data-baseweb="tag"] {
            background: linear-gradient(135deg, rgba(59,130,246,.24) 0%, rgba(99,102,241,.22) 100%) !important;
            border: 1px solid rgba(125,160,255,.34) !important;
            border-radius: 999px !important;
            color: #f8fbff !important;
            font-weight: 800 !important;
        }
        section[data-testid="stSidebar"] [data-baseweb="tag"] span,
        section[data-testid="stSidebar"] [data-baseweb="tag"] svg {
            color: #f8fbff !important;
            fill: #f8fbff !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 50px;
            border-radius: 16px;
            background: linear-gradient(135deg, #3b82f6 0%, #4f46e5 100%);
            color: #ffffff !important;
            border: none;
            font-weight: 900;
            letter-spacing: .02em;
            box-shadow: 0 12px 28px rgba(59,130,246,.28);
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: linear-gradient(135deg, #4c8eff 0%, #635bff 100%);
        }
        section[data-testid="stSidebar"] .stButton > button:disabled {
            opacity: .45;
        }
        section[data-testid="stSidebar"] label {
            font-size: 12px !important;
            font-weight: 800 !important;
            letter-spacing: .04em;
            color: rgba(238,242,255,.74) !important;
            text-transform: uppercase;
        }
        
        .explorer-nav-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.20) 0%, rgba(77,109,255,0) 36%),
                linear-gradient(180deg, #10192c 0%, #091120 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 26px;
            padding: 18px 18px 14px 18px;
            box-shadow: 0 18px 36px rgba(19, 28, 45, 0.14);
            margin: 16px 0 14px 0;
            color: #eef4ff;
        }
        .explorer-nav-shell::after {
            content: "";
            position: absolute;
            right: -70px;
            top: -60px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(255,91,91,.14) 0%, rgba(255,91,91,0) 70%);
            pointer-events: none;
        }
        .explorer-nav-head {
            display:grid;
            grid-template-columns: 1.25fr .9fr;
            gap: 16px;
            align-items: start;
        }
        .explorer-nav-kicker {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: rgba(238,244,255,.60);
        }
        .explorer-nav-title {
            font-size: 26px;
            font-weight: 900;
            color:#ffffff;
            line-height:1.04;
            margin-top: 6px;
        }
        .explorer-nav-copy {
            font-size: 13px;
            line-height: 1.62;
            color: rgba(238,244,255,.78);
            margin-top: 8px;
            max-width: 880px;
        }
        .explorer-nav-panel {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 18px;
            padding: 14px 14px 12px 14px;
            backdrop-filter: blur(12px);
        }
        .explorer-nav-panel-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: .10em;
            color: rgba(238,244,255,.62);
            font-weight: 900;
        }
        .explorer-nav-panel-value {
            font-size: 18px;
            font-weight: 900;
            color: #ffffff;
            margin-top: 8px;
            line-height: 1.12;
        }
        .explorer-nav-panel-copy {
            font-size: 12.5px;
            line-height: 1.56;
            color: rgba(238,244,255,.74);
            margin-top: 8px;
        }
        .explorer-nav-row {
            display:flex;
            flex-wrap:wrap;
            gap:8px;
            margin-top: 14px;
        }
        .explorer-nav-chip {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            padding: 8px 12px;
            border-radius:999px;
            background: rgba(255,255,255,.08);
            border:1px solid rgba(255,255,255,.10);
            color:#eef4ff;
            font-size:11px;
            font-weight:900;
            letter-spacing:.05em;
            text-transform:uppercase;
        }
        .stTabs [data-baseweb="tab-list"]::before {
            content: "Select a ticker to open its full research page";
            display: block;
            width: 100%;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: #667085;
            margin-bottom: 2px;
            padding: 0 4px 4px 4px;
        }
.stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            background: linear-gradient(180deg, rgba(255,255,255,.86) 0%, rgba(255,255,255,.72) 100%);
            border: 1px solid #d9d2c4;
            border-radius: 24px;
            padding: 10px;
            box-shadow: 0 10px 22px rgba(19, 28, 45, 0.08);
            margin-bottom: 12px;
        }
        .stTabs [data-baseweb="tab"] {
            position: relative;
            background: linear-gradient(180deg, #f7f3ea 0%, #ffffff 100%);
            border: 1px solid #d7d1c4;
            border-radius: 999px;
            color: #2b3140;
            font-weight: 800;
            padding: 12px 18px;
            min-height: 50px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.6), 0 8px 18px rgba(19, 28, 45, 0.06);
        }
        .stTabs [data-baseweb="tab"]:hover {
            transform: translateY(-1px);
            border-color: #b9c7ff;
            box-shadow: 0 10px 18px rgba(41,82,255,.12);
        }
        .stTabs [aria-selected="true"] {
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.18) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #10192c 0%, #091120 100%) !important;
            color: #fff !important;
            border-color: rgba(114,140,255,.45) !important;
            box-shadow: 0 12px 20px rgba(19, 28, 45, 0.18), inset 0 -2px 0 rgba(255,91,91,.9) !important;
        }
        .stTabs [aria-selected="true"] * {
            color: #fff !important;
        }
        .stDataFrame, div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.88);
            border: 1px solid #ddd6c8;
            border-radius: 18px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }
        .top-kicker {
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .18em;
            color: #70778a;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .top-intro {
            font-size: 15px;
            line-height: 1.6;
            color: #525967;
            max-width: 880px;
            margin-top: 8px;
        }
        .section-header {
            font-size: 18px;
            font-weight: 900;
            letter-spacing: -0.03em;
            color: #1d2430;
            margin: 6px 0 12px 0;
        }
        .news-brief-card {
            background: var(--card);
            border: 1px solid #d8d2c6;
            border-radius: 18px;
            padding: 18px 18px 16px 18px;
            box-shadow: var(--shadow);
            min-height: 640px;
        }
        .brief-item {
            padding: 14px 0;
            border-bottom: 1px solid #ece5d7;
        }
        .brief-item:last-child { border-bottom: none; }
        .brief-meta {
            font-size: 12px;
            font-weight: 700;
            color: #6c7380;
            margin-bottom: 8px;
        }
        .brief-headline {
            font-size: 18px;
            line-height: 1.28;
            font-weight: 900;
            color: #161b22;
            margin-bottom: 10px;
        }
        .brief-summary {
            font-size: 14px;
            line-height: 1.55;
            color: #4c5563;
        }
        .brief-link {
            display: inline-block;
            margin-top: 10px;
            font-weight: 800;
            font-size: 13px;
            color: #2643db;
            text-decoration: none;
        }
        .brief-link:hover { text-decoration: underline; }

        .lead-story {
            position: relative;
            min-height: 640px;
            border-radius: 0;
            overflow: hidden;
            background:
                linear-gradient(180deg, rgba(5, 8, 17, 0.05) 0%, rgba(5, 8, 17, 0.78) 58%, rgba(5, 8, 17, 0.95) 100%),
                radial-gradient(circle at 78% 26%, rgba(44, 86, 255, 0.35) 0%, rgba(44, 86, 255, 0) 24%),
                linear-gradient(140deg, #090c11 0%, #131927 45%, #1b2233 100%);
            box-shadow: var(--shadow);
            border-left: 1px solid #d1cabd;
            border-right: 1px solid #d1cabd;
            padding: 18px 22px 22px 22px;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
        }
        .lead-kicker {
            position: absolute;
            top: 18px;
            left: 22px;
            font-size: 13px;
            font-weight: 800;
            color: rgba(255,255,255,.82);
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .lead-eyebrow {
            font-size: 13px;
            color: rgba(255,255,255,.74);
            font-weight: 700;
            margin-bottom: 12px;
        }
        .lead-title {
            font-size: 34px;
            line-height: 1.04;
            font-weight: 900;
            color: #fff;
            max-width: 720px;
            margin: 0 0 16px 0;
            text-wrap: balance;
        }
        .lead-summary {
            max-width: 760px;
            font-size: 16px;
            line-height: 1.55;
            color: rgba(255,255,255,.86);
            margin-bottom: 16px;
        }
        .impact-meter {
            border-radius: 999px;
            overflow: hidden;
            background: rgba(255,255,255,.2);
            height: 24px;
            border: 1px solid rgba(255,255,255,.18);
            display: grid;
            grid-template-columns: 1fr 1fr;
            margin-top: 14px;
        }
        .impact-pos, .impact-neg {
            display:flex; align-items:center; justify-content:center;
            font-size: 12px; font-weight: 900; color: #fff;
        }
        .impact-pos { background: linear-gradient(90deg, #1aa36f 0%, #2bd78d 100%); }
        .impact-neg { background: linear-gradient(90deg, #982730 0%, #d5434d 100%); }
        .lead-meta-row {
            display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px;
        }
        .small-pill {
            display: inline-flex;
            align-items: center;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,.12);
            border: 1px solid rgba(255,255,255,.18);
            color: #fff;
            font-size: 12px;
            font-weight: 800;
            backdrop-filter: blur(8px);
        }

        .crypto-card {
            background: radial-gradient(circle at top left, rgba(47, 85, 255, .28) 0%, rgba(47, 85, 255, 0) 38%), linear-gradient(180deg, #11192c 0%, #09111f 100%);
            border: 1px solid rgba(77, 109, 255, 0.22);
            border-radius: 24px;
            padding: 20px 20px 18px 20px;
            min-height: 640px;
            color: #eef4ff;
            box-shadow: 0 18px 36px rgba(19, 28, 45, 0.18);
            position: relative;
            overflow: hidden;
        }
        .crypto-card::after {
            content: "";
            position: absolute;
            width: 240px;
            height: 240px;
            right: -50px;
            top: -70px;
            background: radial-gradient(circle, rgba(77, 109, 255, .22) 0%, rgba(77, 109, 255, 0) 66%);
            pointer-events: none;
        }
        .crypto-kicker {
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .16em;
            text-transform: uppercase;
            color: rgba(238,244,255,.6);
        }
        .crypto-signal {
            margin-top: 12px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 10px 18px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .crypto-buy { background: rgba(16,185,129,.16); color: #6ff0bc; border: 1px solid rgba(111, 240, 188, .32); }
        .crypto-hold { background: rgba(245, 158, 11, .14); color: #ffd166; border: 1px solid rgba(255, 209, 102, .28); }
        .crypto-sell { background: rgba(239,68,68,.16); color: #ff8b8b; border: 1px solid rgba(255, 139, 139, .28); }
        .crypto-main-number {
            font-size: 54px;
            line-height: 1;
            font-weight: 900;
            color: #fff;
            margin-top: 12px;
        }
        .crypto-sub {
            font-size: 14px;
            line-height: 1.6;
            color: rgba(238,244,255,.74);
            margin-top: 10px;
        }
        .crypto-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 18px;
        }
        .crypto-mini {
            background: rgba(255,255,255,.05);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 18px;
            padding: 14px 14px;
        }
        .crypto-mini-label {
            font-size: 11px;
            color: rgba(238,244,255,.58);
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
        }
        .crypto-mini-value {
            font-size: 20px;
            color: #fff;
            font-weight: 900;
            margin-top: 4px;
        }
        .crypto-mini-sub {
            font-size: 12px;
            color: rgba(238,244,255,.74);
            margin-top: 4px;
            line-height: 1.5;
        }
        .crypto-reasons {
            margin-top: 16px;
            padding-left: 18px;
        }
        .crypto-reasons li {
            color: rgba(238,244,255,.78);
            margin-bottom: 8px;
            line-height: 1.55;
        }

        .story-stream-shell {
            margin-top: 22px;
            background: transparent;
        }
        .story-row {
            background: var(--card);
            border: 1px solid #d8d2c6;
            border-radius: 18px;
            box-shadow: var(--shadow);
            padding: 18px 18px 16px 18px;
            margin-bottom: 14px;
        }
        .story-row-head {
            display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:flex-start;
        }
        .story-row-title {
            font-size: 22px;
            line-height: 1.25;
            font-weight: 900;
            color: #171b22;
            margin: 6px 0 8px 0;
            max-width: 920px;
        }
        .story-row-meta {
            font-size: 12px;
            color: #6e7685;
            font-weight: 700;
        }
        .impact-tag {
            display:inline-flex; align-items:center; padding:8px 12px; border-radius:999px;
            font-size:12px; font-weight:900; border:1px solid transparent;
        }
        .impact-up { background: #dff8ee; color: #087f5b; border-color: #ace6cf; }
        .impact-flat { background: #fff4ce; color: #9b6b00; border-color: #f4dd8a; }
        .impact-down { background: #f8dfe0; color: #9d2b2f; border-color: #e9afb3; }
        .story-row-summary {
            font-size: 15px;
            color: #4c5562;
            line-height: 1.65;
            margin-top: 8px;
        }
        .story-row-grid {
            display:grid; grid-template-columns: 1fr 180px; gap:16px; align-items:end; margin-top:14px;
        }
        .prob-box {
            background: #f5f3ec;
            border: 1px solid #ded7c8;
            border-radius: 18px;
            padding: 14px 14px;
            text-align: center;
        }
        .prob-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .1em;
            color: #6e7684;
            text-transform: uppercase;
        }
        .prob-value {
            font-size: 34px;
            font-weight: 900;
            color: #161b22;
            line-height: 1;
            margin-top: 6px;
        }
        .prob-sub {
            font-size: 12px;
            color: #586171;
            margin-top: 6px;
            line-height: 1.45;
        }
        .row-meter {
            width: 100%;
            height: 12px;
            background: #e7e0d1;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 12px;
        }
        .row-meter-fill-up { height: 12px; background: linear-gradient(90deg, #0d9f6e, #44d89f); }
        .row-meter-fill-flat { height: 12px; background: linear-gradient(90deg, #d7c48c, #f6dd8b); }
        .row-meter-fill-down { height: 12px; background: linear-gradient(90deg, #9d2b2f, #d44c54); }
        .inline-link { color:#2643db; text-decoration:none; font-weight:800; }
        .inline-link:hover { text-decoration: underline; }

        
        .compare-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.24) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #10192c 0%, #091120 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 28px;
            padding: 20px 20px 22px 20px;
            box-shadow: 0 18px 36px rgba(19, 28, 45, 0.18);
            margin: 14px 0 22px 0;
            color: #eef4ff;
        }
        .compare-shell::after {
            content: "";
            position: absolute;
            width: 280px;
            height: 280px;
            right: -80px;
            top: -90px;
            background: radial-gradient(circle, rgba(77,109,255,.18) 0%, rgba(77,109,255,0) 68%);
            pointer-events: none;
        }
        .compare-topline {
            display:flex; justify-content:space-between; gap:14px; flex-wrap:wrap; align-items:end;
            margin-bottom: 14px;
            position: relative;
            z-index: 1;
        }
        .compare-title {
            font-size: 30px;
            line-height: 1.02;
            font-weight: 900;
            letter-spacing: -.04em;
            color: #ffffff;
        }
        .compare-copy {
            font-size: 14px;
            line-height: 1.62;
            color: rgba(238,244,255,.76);
            margin-top: 8px;
            max-width: 860px;
        }
        .compare-hero-grid {
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-top: 16px;
            position: relative;
            z-index: 1;
        }
        .compare-hero-tile {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 20px;
            padding: 16px 16px;
            backdrop-filter: blur(12px);
        }
        .compare-hero-label {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .12em;
            text-transform: uppercase;
            color: rgba(238,244,255,.60);
        }
        .compare-hero-value {
            margin-top: 8px;
            font-size: 22px;
            line-height: 1.05;
            font-weight: 900;
            color: #ffffff;
        }
        .compare-hero-sub {
            margin-top: 6px;
            font-size: 13px;
            line-height: 1.55;
            color: rgba(238,244,255,.74);
        }
        .compare-card {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.22) 0%, rgba(77,109,255,0) 40%),
                linear-gradient(180deg, #11192c 0%, #09111f 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 24px;
            padding: 18px 18px 16px 18px;
            box-shadow: 0 18px 34px rgba(19, 28, 45, 0.18);
            min-height: 218px;
            color: #eef4ff;
            margin-bottom: 10px;
        }
        .compare-card::after {
            content: "";
            position: absolute;
            inset: auto -30px -40px auto;
            width: 180px;
            height: 180px;
            background: radial-gradient(circle, rgba(77,109,255,.18) 0%, rgba(77,109,255,0) 70%);
            pointer-events: none;
        }
        .compare-card-kicker {
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .14em;
            text-transform: uppercase;
            color: rgba(238,244,255,.58);
        }
        .compare-card-title {
            font-size: 30px;
            line-height: 1;
            font-weight: 900;
            color: #fff;
            margin-top: 10px;
        }
        .compare-card-price {
            font-size: 34px;
            line-height: 1;
            font-weight: 900;
            color: #fff;
            margin-top: 12px;
        }
        .compare-card-grid {
            display:grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 14px;
        }
        .compare-stat {
            background: rgba(255,255,255,.05);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            padding: 12px 12px;
        }
        .compare-stat-label {
            font-size: 10.5px;
            font-weight: 900;
            letter-spacing: .1em;
            text-transform: uppercase;
            color: rgba(238,244,255,.56);
        }
        .compare-stat-value {
            margin-top: 4px;
            font-size: 17px;
            font-weight: 900;
            color: #ffffff;
        }
        .compare-chart-shell {
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.16) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #ffffff 0%, #fbfaf6 100%);
            border: 1px solid #d8d2c6;
            border-radius: 24px;
            padding: 18px 18px 12px 18px;
            box-shadow: var(--shadow);
            margin-top: 16px;
        }
        .compare-chart-title {
            font-size: 22px;
            line-height: 1.06;
            font-weight: 900;
            color: #161b22;
        }
        .compare-chart-copy {
            font-size: 13px;
            line-height: 1.55;
            color: #5c6472;
            margin-top: 6px;
            margin-bottom: 8px;
            max-width: 860px;
        }
        .compare-table-shell {
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.22) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #10192c 0%, #091120 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 26px;
            padding: 18px 18px 8px 18px;
            box-shadow: 0 18px 36px rgba(19, 28, 45, 0.18);
            margin-top: 16px;
        }
        .compare-table-shell::after {
            content: "";
            position: absolute;
            width: 240px;
            height: 240px;
            right: -70px;
            bottom: -90px;
            background: radial-gradient(circle, rgba(77,109,255,.16) 0%, rgba(77,109,255,0) 68%);
            pointer-events: none;
        }
        .compare-table-title {
            font-size: 22px;
            line-height: 1.06;
            font-weight: 900;
            color: #ffffff;
        }
        .compare-table-copy {
            font-size: 13px;
            line-height: 1.55;
            color: rgba(238,244,255,.70);
            margin-top: 6px;
            margin-bottom: 14px;
            max-width: 900px;
        }
        .compare-table-head {
            display:grid;
            grid-template-columns: 1.2fr 1fr 1fr 1.15fr 1fr 1fr 1.35fr;
            gap: 10px;
            padding: 0 12px 10px 12px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: .1em;
            text-transform: uppercase;
            color: rgba(238,244,255,.52);
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
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 18px;
            padding: 14px 12px;
            margin-bottom: 10px;
            backdrop-filter: blur(12px);
            position: relative;
            z-index: 1;
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
            line-height: 1;
        }
        .compare-table-sub {
            font-size: 12px;
            color: rgba(238,244,255,.64);
            line-height: 1.4;
        }
        .compare-table-value {
            font-size: 16px;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.2;
        }
        .compare-table-chip {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            width: fit-content;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .06em;
            text-transform: uppercase;
        }
        .compare-table-note {
            font-size: 12px;
            color: rgba(238,244,255,.70);
            line-height: 1.4;
        }
        .trend-shell {
            background: linear-gradient(180deg, #ffffff 0%, #fbfaf6 100%);
            border: 1px solid #d8d2c6;
            border-radius: 22px;
            padding: 18px 18px 20px 18px;
            box-shadow: var(--shadow);
            margin-top: 18px;
        }
        .trend-header {
            display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:end; margin-bottom: 14px;
        }
        .trend-title {
            font-size: 28px;
            line-height: 1.08;
            font-weight: 900;
            color: #161b22;
        }
        .trend-sub {
            font-size: 14px;
            color: #5c6472;
            line-height: 1.55;
            margin-top: 6px;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff 0%, #fbfaf6 100%);
            border: 1px solid #ddd6c8;
            padding: 15px 16px;
            border-radius: 18px;
            box-shadow: var(--shadow);
            min-height: 118px;
        }
        div[data-testid="stMetricLabel"] > div,
        div[data-testid="stMetricLabel"] label,
        [data-testid="stMetricLabel"] {
            color: #6e7684 !important;
            font-weight: 800 !important;
            letter-spacing: .02em;
        }
        div[data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] {
            color: #161b22 !important;
            font-weight: 900 !important;
        }
        div[data-testid="stMetricDelta"] > div,
        [data-testid="stMetricDelta"] {
            color: #2643db !important;
            font-weight: 800 !important;
        }
        .footer-note {
            font-size: 12px;
            color: #697180;
            line-height: 1.6;
            margin-top: 14px;
        }
        @media (max-width: 1200px) {
            .news-brief-card, .lead-story, .crypto-card { min-height: unset; }
            .story-row-grid { grid-template-columns: 1fr; }
        }

        @media (max-width: 980px) {
            .block-container {
                padding-left: 0.7rem;
                padding-right: 0.7rem;
            }
            .sentinel-shell,
            .story-card,
            .news-card,
            .side-card,
            .trend-shell,
            .compare-shell,
            .compare-table-shell,
            .compare-chart-shell,
            .chart-shell {
                border-radius: 20px !important;
            }
            .sentinel-title {
                font-size: 30px !important;
            }
            .sentinel-sub,
            .top-intro,
            .compare-copy,
            .compare-table-copy,
            .chart-copy,
            .trend-sub {
                font-size: 14px !important;
                line-height: 1.55 !important;
            }
            .chip-row {
                gap: 8px !important;
            }
            .chip {
                padding: 8px 12px !important;
                font-size: 12px !important;
            }
            .compare-topline {
                grid-template-columns: 1fr !important;
                gap: 12px !important;
            }
            .compare-hero-grid,
            .news-first-grid,
            .story-grid {
                grid-template-columns: 1fr !important;
                gap: 12px !important;
            }
            div[data-testid="stHorizontalBlock"] {
                gap: 0.75rem !important;
            }
        }
        @media (max-width: 768px) {
            .explorer-nav-head {grid-template-columns: 1fr;}
            .explorer-nav-title {font-size: 22px;}

            .lens-grid {grid-template-columns: 1fr;}
            .block-container {
                max-width: 100% !important;
                padding-top: 0.6rem !important;
                padding-left: 0.55rem !important;
                padding-right: 0.55rem !important;
                padding-bottom: 1.2rem !important;
            }
            .top-kicker {
                font-size: 10px !important;
                letter-spacing: .14em !important;
            }
            h1 {
                font-size: 1.85rem !important;
                line-height: 1.05 !important;
            }
            .top-intro {
                font-size: 14px !important;
                line-height: 1.55 !important;
            }
            .sentinel-shell {
                padding: 16px 15px !important;
            }
            .sentinel-title {
                font-size: 28px !important;
            }
            .compare-shell,
            .compare-chart-shell,
            .compare-table-shell,
            .story-stream-shell,
            .trend-shell,
            .chart-shell,
            .side-card,
            .news-card,
            .story-card {
                padding-left: 14px !important;
                padding-right: 14px !important;
            }
            .compare-title,
            .compare-table-title,
            .chart-title,
            .trend-title {
                font-size: 20px !important;
            }
            .section-header,
            .section-label,
            .compare-table-head {
                letter-spacing: .09em !important;
            }
            .compare-table-head {
                display: none !important;
            }
            .compare-table-body {
                gap: 12px !important;
            }
            .compare-table-row {
                grid-template-columns: 1fr !important;
                gap: 10px !important;
                padding: 14px !important;
                border-radius: 18px !important;
            }
            .compare-table-cell {
                display: grid !important;
                grid-template-columns: minmax(92px, 110px) 1fr !important;
                gap: 10px !important;
                align-items: start !important;
                padding-bottom: 6px !important;
                border-bottom: 1px solid rgba(255,255,255,.07);
            }
            .compare-table-cell:last-child {
                border-bottom: none !important;
                padding-bottom: 0 !important;
            }
            .compare-table-ticker {
                font-size: 22px !important;
            }
            .compare-table-sub {
                font-size: 11px !important;
                text-transform: uppercase;
                letter-spacing: .08em;
            }
            .compare-table-value {
                font-size: 17px !important;
            }
            .compare-table-note {
                font-size: 12px !important;
            }
            .compare-table-chip {
                padding: 7px 11px !important;
                font-size: 11px !important;
            }
            .mini-candle-grid {
                grid-template-columns: 1fr !important;
            }
            div[data-testid="stMetric"] {
                min-height: 104px !important;
                padding: 14px 14px !important;
                border-radius: 16px !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 6px !important;
                overflow-x: auto !important;
                scrollbar-width: none;
                padding-bottom: 2px;
            }
            .stTabs [data-baseweb="tab"] {
                white-space: nowrap !important;
                min-width: max-content !important;
                padding: 10px 14px !important;
                font-size: 13px !important;
                min-height: 46px !important;
            }
            section[data-testid="stSidebar"] .stButton > button {
                min-height: 48px !important;
                font-size: 14px !important;
            }
        }
        @media (max-width: 520px) {
            .sentinel-title {
                font-size: 24px !important;
            }
            .sentinel-sub,
            .compare-copy,
            .compare-table-copy,
            .chart-copy,
            .trend-sub,
            .news-summary,
            .story-summary {
                font-size: 13px !important;
            }
            .chip-row {
                gap: 6px !important;
            }
            .chip {
                width: 100%;
                justify-content: center;
            }
            .compare-table-shell,
            .compare-chart-shell,
            .trend-shell,
            .chart-shell {
                padding-top: 14px !important;
                padding-bottom: 12px !important;
            }
            .compare-table-row {
                padding: 12px !important;
            }
            .compare-table-cell {
                grid-template-columns: 1fr !important;
                gap: 4px !important;
            }
            .compare-table-sub {
                font-size: 10px !important;
            }
            .compare-table-value {
                font-size: 18px !important;
            }
            .compare-table-note {
                font-size: 11.5px !important;
                line-height: 1.45 !important;
            }
            .news-meta,
            .story-meta {
                font-size: 11px !important;
            }
        }


        .catalyst-shell, .lab-shell, .winner-shell {
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.18) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #10192c 0%, #091120 100%);
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 24px;
            padding: 18px 18px 16px 18px;
            box-shadow: 0 18px 36px rgba(19, 28, 45, 0.12);
            margin: 14px 0 16px 0;
            color: #eef4ff;
        }
        .catalyst-title, .lab-title, .winner-title {font-size: 22px; font-weight: 900; color:#fff; line-height:1.08;}
        .catalyst-copy, .lab-copy, .winner-copy {font-size: 13px; line-height:1.55; color: rgba(238,244,255,.72); margin-top:6px;}
        .catalyst-grid, .winner-grid {
            display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top:14px;
        }
        .catalyst-box, .winner-box {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 18px; padding: 14px 14px 12px 14px; backdrop-filter: blur(12px);
        }
        .catalyst-label, .winner-label {font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: rgba(238,244,255,.62); font-weight:900;}
        .catalyst-value, .winner-value {font-size: 22px; font-weight: 900; color:#fff; margin-top: 6px; line-height:1.05;}
        .catalyst-sub, .winner-sub {font-size: 12.5px; line-height:1.5; color: rgba(238,244,255,.72); margin-top:6px;}
        .catalyst-row {
            display:grid; grid-template-columns: 1.15fr 3fr .9fr; gap: 10px; align-items:center;
            padding: 9px 0; border-bottom:1px solid rgba(255,255,255,.07);
        }
        .catalyst-row:last-child {border-bottom:none;}
        .catalyst-meter {height: 10px; background: rgba(255,255,255,.10); border-radius:999px; overflow:hidden;}
        .catalyst-meter-fill {height:10px; background: linear-gradient(90deg, #60a5fa, #a78bfa);}
        .lab-grid {display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top:14px;}
        .lab-box {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 18px; padding: 14px 14px 12px 14px;
        }
        .lab-label {font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: rgba(238,244,255,.62); font-weight:900;}
        .lab-value {font-size: 18px; font-weight: 900; color:#fff; margin-top: 6px; line-height:1.08;}
        .lab-sub {font-size: 12.5px; color: rgba(238,244,255,.72); margin-top:6px; line-height:1.5;}
        .tag-row {display:flex; flex-wrap:wrap; gap:8px; margin-top:12px;}
        .pro-tag {
            display:inline-flex; align-items:center; justify-content:center; padding: 7px 11px; border-radius:999px;
            font-size:11px; font-weight:900; letter-spacing:.05em; text-transform:uppercase;
            border:1px solid rgba(255,255,255,.10);
        }
        .pro-tag-up {background: rgba(25,195,125,.16); color:#8bf0c8;}
        .pro-tag-down {background: rgba(255,91,91,.14); color:#ffb4b4;}
        .pro-tag-neutral {background: rgba(255,255,255,.08); color:#eef4ff;}
        @media (max-width: 768px) {
            .catalyst-row {grid-template-columns: 1fr; gap: 6px;}
            .catalyst-grid, .winner-grid, .lab-grid {grid-template-columns: 1fr;}
            .catalyst-title, .lab-title, .winner-title {font-size: 20px;}
        }

        .editorial-hero {
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.18) 0%, rgba(77,109,255,0) 36%),
                linear-gradient(135deg, #ffffff 0%, #fcfbf7 42%, #f1ede4 100%);
            border: 1px solid #d9d2c3;
            border-radius: 28px;
            padding: 24px 24px 20px 24px;
            box-shadow: 0 22px 38px rgba(19,28,45,.08);
            margin: 14px 0 18px 0;
            position: relative;
            overflow: hidden;
        }
        .editorial-hero::after {
            content: "";
            position: absolute;
            right: -70px;
            top: -80px;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(77,109,255,.16) 0%, rgba(77,109,255,0) 70%);
            pointer-events: none;
        }
        .hero-kicker {font-size:11px; font-weight:900; letter-spacing:.16em; text-transform:uppercase; color:#6f7684;}
        .hero-title {font-size:40px; font-weight:900; letter-spacing:-.04em; color:#141a22; line-height:1.0; margin-top:6px; max-width:860px;}
        .hero-copy {font-size:15px; line-height:1.7; color:#525967; margin-top:10px; max-width:940px;}
        .hero-chip-row {display:flex; flex-wrap:wrap; gap:10px; margin-top:14px;}
        .hero-chip {
            display:inline-flex; align-items:center; gap:8px; padding:10px 14px; border-radius:999px;
            background:#fff; border:1px solid #ddd6c8; box-shadow:0 8px 20px rgba(19,28,45,.06);
            font-size:12px; font-weight:800; color:#222a35;
        }
        .guide-shell, .reference-shell {
            background: linear-gradient(135deg, #ffffff 0%, #fcfbf7 100%);
            border: 1px solid #d8d2c6;
            border-radius: 24px;
            padding: 18px 18px 16px 18px;
            box-shadow: var(--shadow);
            margin: 12px 0 16px 0;
        }
        .guide-title, .reference-title {font-size:22px; font-weight:900; color:#171d25; line-height:1.08;}
        .guide-copy, .reference-copy {font-size:13px; line-height:1.6; color:#59606d; margin-top:6px;}
        .guide-grid, .reference-grid {display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top:14px;}
        .guide-card, .reference-card {
            background: linear-gradient(135deg, #f8f5ee 0%, #ffffff 100%);
            border: 1px solid #e3dccd; border-radius:18px; padding:14px 14px 12px 14px;
        }
        .guide-label, .reference-label {font-size:11px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; color:#727986;}
        .guide-head, .reference-head {font-size:18px; font-weight:900; color:#161b22; margin-top:8px; line-height:1.15;}
        .guide-sub, .reference-sub {font-size:12.5px; line-height:1.55; color:#5c6472; margin-top:6px;}

        .lens-shell {
            background: linear-gradient(135deg, #fff 0%, #fbf7ee 100%);
            border: 1px solid #ddd6c8;
            border-radius: 24px;
            padding: 16px 16px 14px 16px;
            box-shadow: var(--shadow);
            margin: 0 0 16px 0;
        }
        .lens-title {font-size: 24px; font-weight: 900; color:#161b22; line-height:1.05;}
        .lens-copy {font-size: 13px; line-height:1.6; color:#5c6472; margin-top:6px;}
        .lens-grid {display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top:14px;}
        .lens-card {
            background: linear-gradient(135deg, #f8f5ee 0%, #ffffff 100%);
            border: 1px solid #e3dccd;
            border-radius: 18px;
            padding: 14px 14px 12px 14px;
        }
        .lens-label {font-size:11px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; color:#727986;}
        .lens-head {font-size:18px; font-weight:900; color:#161b22; margin-top:8px; line-height:1.12;}
        .lens-sub {font-size:12.5px; line-height:1.58; color:#5c6472; margin-top:6px;}
        .side-lens-shell {
            background: linear-gradient(135deg, rgba(255,255,255,.10) 0%, rgba(255,255,255,.04) 100%);
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 18px;
            padding: 14px 14px 12px 14px;
            margin-top: 10px;
            backdrop-filter: blur(12px);
        }
        .side-lens-title {font-size:18px; font-weight:900; color:#ffffff !important; line-height:1.08;}
        .side-lens-copy {font-size:12.5px; line-height:1.55; color:rgba(238,242,255,.76) !important; margin-top:6px;}
        .side-lens-chip-row {display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;}
        .side-lens-chip {
            display:inline-flex; align-items:center; justify-content:center;
            padding:7px 10px; border-radius:999px;
            background: rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.10);
            color:#eef2ff; font-size:11px; font-weight:900; letter-spacing:.05em; text-transform:uppercase;
        }
        
            background:
                radial-gradient(circle at top left, rgba(77,109,255,.22) 0%, rgba(77,109,255,0) 34%),
                linear-gradient(180deg, #10192c 0%, #091120 100%);
            border:1px solid rgba(255,255,255,.08);
            border-radius:28px; padding:20px 20px 18px 20px; box-shadow:0 22px 40px rgba(19,28,45,.16); margin: 0 0 16px 0;
        }
        .winner-hero {
            display:grid; grid-template-columns: 1.4fr .9fr; gap:14px; margin-top:14px;
        }
        .winner-hero-main, .winner-hero-side {
            background: linear-gradient(135deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
            border:1px solid rgba(255,255,255,.10); border-radius:22px; padding:16px 16px 14px 16px;
        }
        .winner-badge {
            display:inline-flex; align-items:center; justify-content:center; padding:8px 12px; border-radius:999px;
            background: rgba(25,195,125,.16); color:#9cf0cc; font-size:11px; font-weight:900; letter-spacing:.08em; text-transform:uppercase;
        }
        .winner-main-title {font-size:32px; font-weight:900; color:#fff; line-height:1.0; margin-top:10px;}
        .winner-main-copy {font-size:14px; line-height:1.65; color:rgba(238,244,255,.78); margin-top:10px;}
        .winner-reason-list {margin:12px 0 0 0; padding-left:18px; color:rgba(238,244,255,.84);} 
        .winner-reason-list li {margin-bottom:8px;}
        .winner-rail-grid {display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; margin-top:12px;}
        .winner-mini {
            background: rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08); border-radius:16px; padding:12px 12px 10px 12px;
        }
        .winner-mini-label {font-size:11px; text-transform:uppercase; letter-spacing:.1em; color:rgba(238,244,255,.58); font-weight:900;}
        .winner-mini-value {font-size:20px; font-weight:900; color:#fff; margin-top:6px;}
        .winner-mini-sub {font-size:12px; line-height:1.5; color:rgba(238,244,255,.72); margin-top:6px;}
        .highlight-shell {
            background: linear-gradient(135deg, #fff 0%, #fbf7ee 100%); border:1px solid #ddd6c8; border-radius:22px; padding:16px 16px 14px 16px; box-shadow: var(--shadow); margin-bottom: 14px;
        }
        .highlight-row {display:grid; grid-template-columns: 1.1fr 2.2fr .9fr; gap: 12px; align-items:center; padding:10px 0; border-bottom:1px solid #ece5d7;}
        .highlight-row:last-child {border-bottom:none;}
        .highlight-tag {display:inline-flex; align-items:center; width:fit-content; padding:7px 10px; border-radius:999px; font-size:11px; font-weight:900; text-transform:uppercase; letter-spacing:.06em;}
        .highlight-up {background:#def6ec; color:#0c8d61;}
        .highlight-down {background:#f9dfdf; color:#9d2b2f;}
        .highlight-mixed {background:#ece8de; color:#5c6472;}
        .soft-note {font-size:12.5px; line-height:1.6; color:#5d6471;}
        @media (max-width: 900px) {
            .hero-title {font-size:32px;}
            .winner-hero {grid-template-columns: 1fr;}
            .winner-rail-grid {grid-template-columns: 1fr 1fr;}
        }
        @media (max-width: 768px) {
            .editorial-hero, .guide-shell, .reference-shell, .winner-shell {padding:16px 16px 14px 16px; border-radius:22px;}
            .hero-title {font-size:28px;}
            .guide-grid, .reference-grid, .winner-rail-grid {grid-template-columns: 1fr;}
            .highlight-row {grid-template-columns: 1fr; gap:6px;}
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
            <div class="hero-kicker">Experience Layer</div>
            <div class="hero-title">Stay longer, explore deeper, and know what each section is trying to tell you.</div>
            <div class="hero-copy">This upgraded layout keeps your existing theme, but makes the dashboard feel more editorial and sticky. News explains why a stock may move, the winner card tells you which setup looks strongest right now, and each section now acts like a guided reference panel instead of just raw output.</div>
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
            <div class="guide-title">How to read the dashboard like a pro</div>
            <div class="guide-copy">Use this page as a guided sequence. Start with context, then conviction, then confirmation. That flow helps you avoid reacting to one headline or one chart in isolation.</div>
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
                <div class="reference-head" style="font-size:16px; margin-top:0;">{title}</div>
                <div class="soft-note">{provider} · Why it matters to {escape(ticker)}: {reason}</div>
            </div>
            <div class="soft-note" style="text-align:right;"><strong>{probability}%</strong><br>estimated effect</div>
        </div>
        """)
    st.markdown(
        f"""
        <div class="highlight-shell">
            <div class="section-header" style="margin:0;">News highlights worth exploring</div>
            <div class="soft-note">These are the most immediately relevant stories for the selected stock. Treat them as directional clues, then confirm them in the Catalyst Engine and Trading Lab.</div>
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
    else:
        lead = None
        direction_text = "Direction currently mixed"
        probability = 50
        title = escape(f"{ticker} is trading on technical and news cross-currents")
        summary = escape(analysis["summary"])
        meta = "No stock-specific story returned"
        link_html = ""
        pos = neg = 50

    st.markdown(
        f"""
        <div class="lead-story">
            <div class="lead-kicker">Top News Story</div>
            <div class="lead-eyebrow">{escape(meta)}</div>
            <div class="lead-title">{title}</div>
            <div class="lead-summary">{summary}</div>
            <div class="lead-meta-row">
                <span class="small-pill">{escape(direction_text)}</span>
                <span class="small-pill">Estimated effect on {escape(ticker)}: {probability}%</span>
                <span class="small-pill">{escape(analysis['news_pulse']['label'])}</span>
                {link_html}
            </div>
            <div class="impact-meter">
                <div class="impact-pos">Up {pos}%</div>
                <div class="impact-neg">Down {neg}%</div>
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
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_news_stream(ticker: str, news_items: list[dict]):
    st.markdown('<div class="section-header">Top News Stories</div>', unsafe_allow_html=True)
    st.caption("Selected-stock stories first. Use the highlight box to spot what matters most, then open the full story rows for detail and context.")
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
    st.markdown('<div class="story-stream-shell"></div>', unsafe_allow_html=True)
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
                    <div class="explorer-nav-title">Open any selected stock below for its full research page</div>
                    <div class="explorer-nav-copy">This is the handoff point from <strong>comparison mode</strong> into <strong>deep-dive mode</strong>. Click a ticker tab below to open its own page with related news, Catalyst Engine, lens-aware alerts, Trading Lab, and candlestick confirmation.</div>
                    <div class="explorer-nav-row">
                        {chip_html}
                    </div>
                </div>
                <div class="explorer-nav-panel">
                    <div class="explorer-nav-panel-label">What happens next</div>
                    <div class="explorer-nav-panel-value">Tap a ticker tab ↓</div>
                    <div class="explorer-nav-panel-copy">You’ll move into that stock’s dedicated workspace, where the news, catalysts, alerts, and chart structure are all focused on just that one name.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def generate_dashboard():
    inject_css()
    st.markdown('<div class="top-kicker">David Lau Stock Market Vision</div>', unsafe_allow_html=True)
    st.title("David Lau Stock Market Vision")
    st.markdown(
        '<div class="top-intro">Pro v12: Catalyst Engine + Trading Lab + Smart Compare. The trend lookback is now upgraded into purpose-built lenses, the Winner Card changes with the active lens, the Alert Layer shows how each lens reads the same stock differently, and the stock explorer navigation makes it much clearer where to open each name’s full page.</div>',
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
