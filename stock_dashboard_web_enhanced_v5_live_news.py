#!/usr/bin/env python
from __future__ import annotations

from html import escape
from zoneinfo import ZoneInfo

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
            --bg: #08111f;
            --panel: #0f172a;
            --card: #ffffff;
            --card-soft: #f8fafc;
            --text: #0f172a;
            --text-soft: #475467;
            --muted: #667085;
            --line: #d7e0ea;
            --brand: #2563eb;
            --brand-soft: #e8f0ff;
            --success: #067647;
            --success-soft: #e7f8ef;
            --warning: #b54708;
            --warning-soft: #fff3dd;
            --danger: #b42318;
            --danger-soft: #ffe8e6;
        }
        .stApp {
            background: radial-gradient(circle at top left, #102043 0%, var(--bg) 42%, #060b14 100%);
        }
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }
        h1, h2, h3 {
            color: #f8fafc !important;
            letter-spacing: -0.02em;
        }
        p, label, .stCaption, .stMarkdown, .st-emotion-cache-10trblm, .st-emotion-cache-1c7y2kd {
            color: #d0d5dd;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d1628 0%, #0a1220 100%);
            border-right: 1px solid rgba(255,255,255,0.06);
        }
        section[data-testid="stSidebar"] * {
            color: #f8fafc;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid var(--line);
            padding: 16px 18px;
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(2, 8, 23, 0.18);
            min-height: 126px;
        }
        div[data-testid="stMetricLabel"] > div,
        div[data-testid="stMetricLabel"] label,
        [data-testid="stMetricLabel"] {
            color: var(--muted) !important;
            font-weight: 700 !important;
            letter-spacing: .01em;
        }
        div[data-testid="stMetricValue"] > div,
        [data-testid="stMetricValue"] {
            color: var(--text) !important;
            font-weight: 800 !important;
        }
        div[data-testid="stMetricDelta"] > div,
        [data-testid="stMetricDelta"] {
            color: #175cd3 !important;
            font-weight: 700 !important;
        }
        .stDataFrame, div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.96);
            border-radius: 18px;
            border: 1px solid var(--line);
            box-shadow: 0 12px 24px rgba(2, 8, 23, 0.12);
            overflow: hidden;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 999px;
            color: #e5e7eb;
            padding: 8px 16px;
        }
        .stTabs [aria-selected="true"] {
            background: #f8fafc !important;
            color: #0f172a !important;
        }
        .sentinel-shell {
            background: linear-gradient(135deg, #f8fbff 0%, #eef4ff 38%, #dbeafe 100%);
            border: 1px solid rgba(37, 99, 235, 0.18);
            border-radius: 26px;
            padding: 24px 26px;
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.18);
            margin-bottom: 20px;
            position: relative;
            overflow: hidden;
        }
        .sentinel-shell::after {
            content: "";
            position: absolute;
            inset: auto -60px -70px auto;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(37,99,235,.18) 0%, rgba(37,99,235,0) 70%);
            pointer-events: none;
        }
        .sentinel-kicker {
            font-size: 12px;
            font-weight: 800;
            letter-spacing: .1em;
            color: #475467;
            text-transform: uppercase;
        }
        .sentinel-title {
            font-size: 42px;
            font-weight: 900;
            color: #0f172a;
            margin-top: 4px;
            line-height: 1.05;
        }
        .sentinel-sub {
            font-size: 17px;
            color: #334155;
            margin-top: 10px;
            max-width: 840px;
            font-weight: 500;
        }
        .chip-row {display:flex; flex-wrap:wrap; gap:10px; margin-top: 14px;}
        .chip {
            display:inline-flex; align-items:center; gap:6px; padding:9px 14px; border-radius:999px;
            font-size:13px; font-weight:800; border: 1px solid transparent; background:#fff;
            box-shadow: 0 2px 8px rgba(15,23,42,.06);
        }
        .chip-buy {background: var(--success-soft); color: var(--success); border-color: #9fe0b9;}
        .chip-hold {background: var(--warning-soft); color: var(--warning); border-color: #f4cc7d;}
        .chip-sell {background: var(--danger-soft); color: var(--danger); border-color: #f3b0aa;}
        .chip-info {background: var(--brand-soft); color: #1d4ed8; border-color: #bfd2ff;}
        .news-card {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
            border:1px solid var(--line); border-radius:22px; padding:20px 20px 16px 20px;
            box-shadow: 0 12px 30px rgba(15,23,42,.10); margin-bottom:16px;
        }
        .news-card h4 {margin:0 0 8px 0; font-size: 22px; line-height:1.3; color:var(--text);}
        .news-meta {font-size:12px; color:var(--muted); margin-bottom:10px; font-weight:600;}
        .news-summary {font-size:15px; color:#344054; line-height:1.6; margin: 10px 0 14px 0;}
        .impact-bar-wrap {background:#e5eaf2; border-radius:999px; height:11px; overflow:hidden; margin-top:10px;}
        .impact-bar-pos {background:linear-gradient(90deg,#16a34a,#4ade80); height:11px;}
        .impact-bar-neg {background:linear-gradient(90deg,#ef4444,#f97316); height:11px;}
        .impact-bar-neu {background:linear-gradient(90deg,#94a3b8,#cbd5e1); height:11px;}
        .side-card {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border:1px solid var(--line); border-radius:22px; padding:18px 20px; margin-bottom:16px;
            box-shadow: 0 12px 26px rgba(15,23,42,.10);
        }
        .side-card h4 {margin:0 0 10px 0; font-size:17px; color:var(--text);}
        .mini {font-size:12.5px; color:var(--muted); line-height:1.55;}
        .mini strong {color: var(--text);}
        .pulse-grid {display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin-top:10px;}
        .pulse-box {padding:12px 12px; border-radius:16px; text-align:center; font-size:12px; font-weight:800;}
        .pulse-up {background:var(--success-soft); color:var(--success);}
        .pulse-neu {background:#eef2f6; color:#475467;}
        .pulse-down {background:var(--danger-soft); color:var(--danger);}
        .list-tight {margin:0; padding-left: 18px;}
        .list-tight li {margin-bottom: 8px; color:#334155;}
        .section-label {font-size: 11px; font-weight: 900; letter-spacing: .12em; color:#667085; text-transform: uppercase; margin-bottom:9px;}
        .disclaimer {font-size: 12px; color:#d0d5dd; margin-top: 12px;}
        a.inline-link {color:#175cd3; text-decoration:none; font-weight:800;}
        a.inline-link:hover {text-decoration:underline;}
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
def render_story_card(item: dict, ticker: str, idx: int):
    label = item["impact_label"]
    if "bullish" in label.lower():
        badge_kind = "buy"
    elif "bearish" in label.lower():
        badge_kind = "sell"
    else:
        badge_kind = "hold"

    related = ", ".join(item.get("related", [])[:6]) if item.get("related") else "Not provided"
    title = escape(item["title"])
    summary = escape(item["summary"] or item["impact_reason"])
    provider = escape(str(item["provider"]))
    us_time = format_us_timestamp(item["published"])
    tw_time = format_tw_timestamp(item["published"])
    relevance_text = {0: "Low", 1: "Low", 2: "Medium", 3: "Medium", 4: "High", 5: "High", 6: "High"}.get(item.get("relevance", 0), "High")

    link_html = ""
    if item.get("url"):
        safe_url = escape(str(item["url"]))
        link_html = f'<a class="inline-link" href="{safe_url}" target="_blank">Open article ↗</a>'

    st.markdown(
        f"""
        <div class="news-card">
            <div class="section-label">Story {idx:02d}</div>
            <h4>{title}</h4>
            <div class="chip-row">
                {badge_html(label, badge_kind)}
                {badge_html(f"Confidence: {item['confidence']}", 'info')}
                {badge_html(f"Relevance: {relevance_text}", 'info')}
            </div>
            <div class="news-meta">{provider} · US {us_time} · Taiwan {tw_time}</div>
            <div class="news-summary">{summary}</div>
            <div class="mini"><strong>Why this could matter to {escape(ticker)}:</strong> {escape(item['impact_reason'])}</div>
            {impact_bar(item)}
            <div class="mini" style="margin-top:8px;">Related tickers: {escape(related)}</div>
            <div style="margin-top:10px;">{link_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_right_rail(analysis: dict, intraday: dict, news_items: list[dict]):
    pulse = analysis["news_pulse"]
    signal = analysis["signal"]
    st.markdown(
        f"""
        <div class="side-card">
            <h4>Market Sentinel</h4>
            <div class="chip-row">
                {badge_html(signal, 'buy' if signal == 'BUY' else 'sell' if signal == 'SELL' else 'hold')}
                {badge_html(f"Confidence: {analysis['confidence']}", 'info')}
            </div>
            <p class="mini" style="margin-top:8px;">{escape(analysis['summary'])}</p>
            <div class="mini">Sentinel score: <strong>{analysis['score']}</strong></div>
            <div class="mini">1Y trend: <strong>{escape(analysis['trend'])}</strong></div>
            <div class="mini">RSI: <strong>{analysis['rsi_status']}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="side-card">
            <h4>News pulse</h4>
            <div class="mini">{escape(pulse['label'])}</div>
            <div class="pulse-grid">
                <div class="pulse-box pulse-up">Bullish<br>{pulse['up']}</div>
                <div class="pulse-box pulse-neu">Mixed<br>{pulse['neutral']}</div>
                <div class="pulse-box pulse-down">Bearish<br>{pulse['down']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    last_intraday = format_price(intraday["last_price"]) if intraday.get("available") else "N/A"
    intraday_change = format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A"
    intraday_time = format_tw_timestamp(intraday.get("timestamp")) if intraday.get("available") else "N/A"
    st.markdown(
        f"""
        <div class="side-card">
            <h4>Live snapshot</h4>
            <div class="mini">Intraday price: <strong>{last_intraday}</strong></div>
            <div class="mini">Intraday change: <strong>{intraday_change}</strong></div>
            <div class="mini">Taiwan time: <strong>{intraday_time}</strong></div>
            <div class="mini">Daily trend date: <strong>{format_us_timestamp(analysis['latest_daily_ts'])}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_reasons = "".join(f"<li>{escape(r)}</li>" for r in analysis["reasons"][:4])
    st.markdown(
        f"""
        <div class="side-card">
            <h4>Why the signal looks this way</h4>
            <ul class="list-tight">{top_reasons}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="side-card">
            <h4>How to read this page</h4>
            <div class="mini">News labels show the article’s possible directional effect on the stock, not certainty. The trading signal combines 1-year trend, moving averages, RSI, volume, and recent news pulse.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview_header(ticker: str, analysis: dict, intraday: dict, news_items: list[dict]):
    signal = analysis["signal"]
    signal_kind = "buy" if signal == "BUY" else "sell" if signal == "SELL" else "hold"
    pulse = analysis["news_pulse"]
    intraday_line = f"Intraday {format_price(intraday['last_price'])} ({format_percent(intraday['change_pct'])})" if intraday.get("available") else "Intraday snapshot unavailable"
    st.markdown(
        f"""
        <div class="sentinel-shell">
            <div class="sentinel-kicker">David Lau Stock Market Vision</div>
            <div class="sentinel-title">{escape(ticker)}</div>
            <div class="sentinel-sub">{escape(analysis['summary'])}</div>
            <div class="chip-row">
                {badge_html(signal, signal_kind)}
                {badge_html(f"Confidence: {analysis['confidence']}", 'info')}
                {badge_html(f"1Y Return: {format_percent(analysis['one_year_return'])}", 'info')}
                {badge_html(f"News pulse: {pulse['label']}", 'info')}
            </div>
            <div class="chip-row">
                {badge_html(intraday_line, 'info')}
                {badge_html(f"Latest daily trend bar: {format_us_timestamp(analysis['latest_daily_ts'])}", 'info')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_market_panel(analysis: dict, intraday: dict):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last daily close", format_price(analysis["last_price"]))
    c2.metric("SMA 50 vs 200", f"{format_price(analysis['sma50'])} / {format_price(analysis['sma200'])}")
    c3.metric("RSI 14", "N/A" if pd.isna(analysis["rsi14"]) else f"{analysis['rsi14']:.2f}")
    c4.metric("Intraday move", format_percent(intraday["change_pct"]) if intraday.get("available") else "N/A")

    indicators = analysis["indicators"][["Price", "SMA 20", "SMA 50", "SMA 200"]].tail(252).copy()
    st.markdown("**1-year trend and moving averages**")
    st.line_chart(indicators)

    if intraday.get("available") and not intraday["chart"].empty:
        st.markdown("**Live intraday trend (5m)**")
        st.line_chart(intraday["chart"])


def render_news_feed(ticker: str, news_items: list[dict]):
    st.markdown("### Related news feed")
    st.caption("Only stories associated with the selected stock are shown here. The impact badge is a reference signal, not a guarantee.")
    if not news_items:
        st.info(f"No recent stock-specific news was returned for {ticker}.")
        return
    for idx, item in enumerate(news_items, start=1):
        render_story_card(item, ticker, idx)


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


def render_ticker_page(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str):
    price_series, _ = get_price_series(daily_data, ticker)
    volume_series = get_series(daily_data, "Volume", ticker)
    news_items, news_error = fetch_ticker_news(ticker, max_items=10)
    intraday = get_intraday_snapshot(intraday_data, ticker)

    if news_error:
        st.warning(news_error)

    if price_series is None or price_series.empty:
        st.warning(f"No usable price series found for {ticker}.")
        return

    analysis = analyze_market_sentinel(price_series, volume_series, news_items, ticker)
    render_overview_header(ticker, analysis, intraday, news_items)

    main_col, right_col = st.columns([2.2, 1.0], gap="large")
    with main_col:
        render_market_panel(analysis, intraday)
        render_news_feed(ticker, news_items)
    with right_col:
        render_right_rail(analysis, intraday, news_items)


# ---------------------------
# Main app
# ---------------------------
def generate_dashboard():
    inject_css()
    st.title("📈 David Lau Stock Market Vision")
    st.caption("Ground News–inspired stock dashboard with high-contrast cards, fast visual scanning, and per-stock news impact references.")

    with st.sidebar:
        st.header("Settings")
        tickers = st.multiselect(
            "Tickers",
            options=["NVDA", "TSM", "AAPL", "MSFT", "AMD", "QQQ", "TSLA", "META", "AMZN"],
            default=DEFAULT_TICKERS,
        )
        period = st.selectbox("Trend lookback", SUPPORTED_PERIODS, index=SUPPORTED_PERIODS.index(DEFAULT_PERIOD))
        interval = st.selectbox("Trend interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index(DEFAULT_INTERVAL))
        if st.button("Refresh now", use_container_width=True):
            st.cache_data.clear()
        st.caption("Daily trend drives the Sentinel signal. Intraday is a live reference layer.")

    if not tickers:
        st.warning("Please select at least one ticker.")
        return

    with st.spinner("Loading market data and stock-specific news..."):
        daily_data = fetch_daily_data(tickers, period, interval)
        intraday_data = fetch_intraday_data(tickers)

    if daily_data is None or daily_data.empty:
        st.error("No market data was returned. Please try again.")
        return

    st.markdown("### Snapshot")
    snapshot_df = pd.DataFrame([build_snapshot_row(daily_data, intraday_data, t) for t in tickers])
    st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    tabs = st.tabs(tickers)
    for tab, ticker in zip(tabs, tickers):
        with tab:
            render_ticker_page(daily_data, intraday_data, ticker)

    st.markdown('<div class="disclaimer">This dashboard is for research and reference. News impact labels are heuristic and should not be used alone as a trading decision.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    generate_dashboard()
