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
SUPPORTED_PERIODS = ["6mo", "1y", "2y"]
SUPPORTED_INTERVALS = ["1d", "1wk"]
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
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            margin-bottom: 12px;
        }
        .stTabs [data-baseweb="tab"] {
            background: #ece8de;
            border: 1px solid #d7d1c4;
            border-radius: 999px;
            color: #2b3140;
            font-weight: 700;
            padding: 10px 18px;
        }
        .stTabs [aria-selected="true"] {
            background: #161b22 !important;
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
    st.markdown(
        f"""
        <div class="crypto-card">
            <div class="crypto-kicker">Crypto-style signal deck</div>
            <div class="crypto-signal {signal_class}">{escape(signal)}</div>
            <div class="crypto-main-number">{analysis['score']:+d}</div>
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
                    <div class="crypto-mini-label">Latest Trend Bar</div>
                    <div class="crypto-mini-value">{format_percent(analysis['one_year_return'])}</div>
                    <div class="crypto-mini-sub">{latest_trend_date}</div>
                </div>
            </div>
            <ul class="crypto-reasons">{top_reasons}</ul>
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
    st.caption("Selected-stock stories first. The estimated effect is a reference score from headline tone, ticker relevance, and recency, not certainty.")
    if not news_items:
        st.info(f"No recent stock-specific news was returned for {ticker}.")
        return
    for idx, item in enumerate(news_items, start=1):
        render_story_row(item, ticker, idx)


def render_trend_section(analysis: dict, intraday: dict, daily_ohlc: pd.DataFrame | None = None, intraday_ohlc: pd.DataFrame | None = None):
    st.markdown(
        f"""
        <div class="trend-shell">
            <div class="trend-header">
                <div>
                    <div class="section-header" style="margin:0;">Trend Lab</div>
                    <div class="trend-title">Candlestick confirmation</div>
                    <div class="trend-sub">This section stays at the bottom so readers first absorb the news and estimated stock impact, then confirm the setup with candlestick structure and live tape.</div>
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

    render_candlestick_chart(
        daily_ohlc.tail(252) if daily_ohlc is not None else pd.DataFrame(),
        "1-year candlestick structure",
        "Daily candlesticks with SMA 20 and SMA 50 overlays for structure confirmation.",
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


def collect_ticker_context(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str, news_limit: int = 10):
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



def render_comparison_section(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, tickers: list[str]):
    if len(tickers) < 2:
        return

    bundles = [collect_ticker_context(daily_data, intraday_data, ticker, news_limit=8) for ticker in tickers]
    bundles = [bundle for bundle in bundles if bundle is not None]
    if len(bundles) < 2:
        return

    strongest = max(bundles, key=lambda bundle: bundle["analysis"]["score"])
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
                    <div class="compare-hero-label">Strongest Sentinel setup</div>
                    <div class="compare-hero-value">{escape(strongest['ticker'])}</div>
                    <div class="compare-hero-sub">Score {strongest['analysis']['score']:+d} · {escape(strongest['analysis']['signal'])} · {escape(strongest['analysis']['confidence'])} confidence</div>
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
                            <div class="compare-stat-label">Sentinel Score</div>
                            <div class="compare-stat-value">{analysis['score']:+d}</div>
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
        <div class="compare-table-sub">Momentum</div>
        <div class="compare-table-value">{analysis['score']:+d}</div>
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

    compare_cols = st.columns(min(3, len(bundles)))
    for idx, bundle in enumerate(bundles):
        with compare_cols[idx % len(compare_cols)]:
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

def render_ticker_page(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str):
    bundle = collect_ticker_context(daily_data, intraday_data, ticker, news_limit=10)
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
    st.markdown('<div class="story-stream-shell"></div>', unsafe_allow_html=True)
    render_news_stream(ticker, news_items)
    render_trend_section(analysis, intraday, daily_ohlc=daily_ohlc, intraday_ohlc=intraday_ohlc)


# ---------------------------
# Main app
# ---------------------------
def generate_dashboard():
    inject_css()
    st.markdown('<div class="top-kicker">David Lau Stock Market Vision</div>', unsafe_allow_html=True)
    st.title("David Lau Stock Market Vision")
    st.markdown(
        '<div class="top-intro">Ground News–inspired reading flow: readers see stock-specific news and estimated directional impact first, then confirm the setup with a modern crypto-style buy/hold/sell signal deck, and only then move into the 1-year trend section.</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown(
            """
            <div class="side-hero">
                <div class="side-eyebrow">Control Center</div>
                <div class="side-title">Vision Deck</div>
                <div class="side-copy">Build the watchlist, compare the selected stocks side by side, and refresh the live tape in one modern control panel.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="side-group-label">Watchlist</div>', unsafe_allow_html=True)
        tickers = st.multiselect(
            "Tickers",
            options=["NVDA", "TSM", "AAPL", "MSFT", "AMD", "QQQ", "TSLA", "META", "AMZN"],
            default=DEFAULT_TICKERS,
            placeholder="Add tickers to compare...",
        )
        st.markdown('<div class="side-group-label">Trend setup</div>', unsafe_allow_html=True)
        period = st.selectbox("Trend lookback", SUPPORTED_PERIODS, index=SUPPORTED_PERIODS.index(DEFAULT_PERIOD))
        interval = st.selectbox("Trend interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index(DEFAULT_INTERVAL))
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

    render_comparison_section(daily_data, intraday_data, tickers)

    st.markdown("---")
    tabs = st.tabs(tickers)
    for tab, ticker in zip(tabs, tickers):
        with tab:
            render_ticker_page(daily_data, intraday_data, ticker)

    st.markdown(
        '<div class="footer-note">This dashboard is for research and reference. The news effect percentages and directional labels are heuristic estimates, not guarantees or investment advice.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    generate_dashboard()
