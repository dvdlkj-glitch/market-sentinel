#!/usr/bin/env python
# -------------------------------------------------------------------------
# Stock Dashboard Monitor for NVDA and TSM (Streamlit Web App - Enhanced V4)
# Author: AI Assistant (Market Sentinel Persona)
# Date: 2026-04-06
# -------------------------------------------------------------------------
# INSTRUCTIONS:
# 1. INSTALL DEPENDENCIES:
#    pip install yfinance pandas streamlit
# 2. SAVE THIS SCRIPT AS 'stock_dashboard_web_enhanced_v4_live.py' in your working directory.
# 3. RUN THE APP:
#    streamlit run stock_dashboard_web_enhanced_v4_live.py
#
# NOTES:
# - Uses 1-year daily data for Market Sentinel trend analysis.
# - Pulls separate intraday data (5-minute) for fresher session tracking.
# - Handles both flat and MultiIndex Yahoo Finance output.

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

# --- Default Configuration ---
DEFAULT_TICKERS = ["NVDA", "TSM"]
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
SUPPORTED_PERIODS = ["3mo", "6mo", "1y", "2y"]
SUPPORTED_INTERVALS = ["1d", "1wk"]
PRICE_FIELDS_PRIORITY = ["Adj Close", "Close"]
INTRADAY_PERIOD = "5d"
INTRADAY_INTERVAL = "5m"

US_TZ = ZoneInfo("America/New_York")
TW_TZ = ZoneInfo("Asia/Taipei")

POSITIVE_NEWS_KEYWORDS = {
    "beat", "beats", "upgrade", "upgrades", "surge", "surges", "gain", "gains",
    "growth", "record", "strong", "raises", "raise", "buyback", "partnership",
    "expansion", "expands", "wins", "outperform", "bullish", "rebound", "jump"
}
NEGATIVE_NEWS_KEYWORDS = {
    "miss", "misses", "downgrade", "downgrades", "fall", "falls", "drop", "drops",
    "slump", "slumps", "cuts", "cut", "weak", "warning", "lawsuit", "probe",
    "investigation", "delay", "delays", "decline", "declines", "bearish", "selloff"
}


st.set_page_config(
    page_title="Market Sentinel Dashboard",
    page_icon="📈",
    layout="wide",
)


@st.cache_data(ttl=300)
def fetch_stock_data(tickers: list[str], period: str, interval: str):
    try:
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
    except Exception as e:
        st.error(f"🛑 Could not download daily market data. Error: {e}")
        return None


@st.cache_data(ttl=120)
def fetch_intraday_data(tickers: list[str]):
    try:
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
    except Exception as e:
        st.warning(f"Intraday data unavailable right now. Error: {e}")
        return None


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
        series = get_series(data, field, ticker)
        if series is not None and not series.empty:
            return series, field
    return None, None



def ensure_datetime_index(series: pd.Series) -> pd.Series:
    if series is None or series.empty:
        return series
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s



def localize_timestamp(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        return ts.tz_localize(US_TZ)
    return ts.tz_convert(US_TZ)



def format_us_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return "N/A"
    localized = localize_timestamp(ts)
    return localized.strftime("%Y-%m-%d %H:%M %Z")



def format_tw_timestamp(ts) -> str:
    if ts is None or pd.isna(ts):
        return "N/A"
    localized = localize_timestamp(ts).tz_convert(TW_TZ)
    return localized.strftime("%Y-%m-%d %H:%M %Z")


@st.cache_data(ttl=600)
def fetch_ticker_news(ticker: str, max_items: int = 8):
    """Fetch ticker-specific news from yfinance and score relevance conservatively."""
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

        provider = None
        provider_data = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        provider = provider_data.get("displayName") or item.get("publisher") or item.get("provider") or "Unknown source"

        url = None
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
            relevance += 3
        if ticker_upper in text_blob:
            relevance += 2

        impact, impact_score = infer_news_impact(title, summary)
        if relevance > 0 or not items:
            items.append({
                "title": title,
                "summary": summary,
                "provider": provider,
                "url": url,
                "published": published_ts,
                "related": related,
                "relevance": relevance,
                "impact": impact,
                "impact_score": impact_score,
            })

    items.sort(key=lambda x: (x["relevance"], pd.Timestamp.min.tz_localize("UTC") if pd.isna(x["published"]) else x["published"]), reverse=True)

    filtered = [x for x in items if x["relevance"] > 0]
    final_items = (filtered or items)[:max_items]
    return final_items, None


def infer_news_impact(title: str, summary: str = ""):
    text = f"{title} {summary}".lower()
    pos = sum(1 for kw in POSITIVE_NEWS_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_NEWS_KEYWORDS if kw in text)
    score = pos - neg
    if score >= 2:
        return "Possible Upward Bias", score
    if score <= -2:
        return "Possible Downward Bias", score
    if score != 0:
        return "Mixed / Mild Bias", score
    return "Neutral / Unclear", score


def render_news_section(ticker: str):
    st.markdown("**Related News Reference**")
    st.caption("This section is a reference only. The possible price effect is a simple headline heuristic, not a trading recommendation.")

    news_items, news_error = fetch_ticker_news(ticker)
    if news_error:
        st.info(news_error)
        return

    if not news_items:
        st.info(f"No recent ticker-related news was returned for {ticker}.")
        return

    up_count = sum(1 for item in news_items if item["impact"] == "Possible Upward Bias")
    down_count = sum(1 for item in news_items if item["impact"] == "Possible Downward Bias")
    neutral_count = len(news_items) - up_count - down_count

    col1, col2, col3 = st.columns(3)
    col1.metric("Possible Upward", str(up_count))
    col2.metric("Possible Downward", str(down_count))
    col3.metric("Neutral / Mixed", str(neutral_count))

    for idx, item in enumerate(news_items, start=1):
        published_us = format_us_timestamp(item["published"]) if not pd.isna(item["published"]) else "N/A"
        published_tw = format_tw_timestamp(item["published"]) if not pd.isna(item["published"]) else "N/A"

        with st.container():
            st.markdown(f"**{idx}. {escape(item['title'])}**")
            st.markdown(f"**Possible effect on {ticker}:** {item['impact']}")
            st.caption(f"Source: {item['provider']} | Published (US): {published_us} | Taiwan: {published_tw}")
            if item["summary"]:
                st.write(item["summary"])
            if item["related"]:
                st.caption(f"Yahoo related tickers: {', '.join(item['related'][:6])}")
            if item["url"]:
                st.markdown(f"[Open article]({item['url']})")



def calculate_rsi(series: pd.Series, period: int = 14):
    if series is None or len(series) < period + 1:
        return pd.Series(dtype="float64")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.astype("float64")



def build_indicator_frame(price_series: pd.Series):
    price_series = ensure_datetime_index(price_series)
    df = pd.DataFrame({"Price": price_series.copy()})
    df["SMA 20"] = price_series.rolling(20).mean()
    df["SMA 50"] = price_series.rolling(50).mean()
    df["SMA 200"] = price_series.rolling(200).mean()
    df["RSI 14"] = calculate_rsi(price_series)
    df["1Y Return %"] = ((price_series / price_series.iloc[0]) - 1) * 100
    return df



def format_percent(value):
    if pd.isna(value):
        return "N/A"
    return f"{value:+.2f}%"



def format_price(value):
    if pd.isna(value):
        return "N/A"
    return f"${value:,.2f}"



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



def analyze_market_sentinel(price_series: pd.Series, volume_series: pd.Series | None, ticker: str):
    indicators = build_indicator_frame(price_series)
    latest = indicators.iloc[-1]

    last_price = latest["Price"]
    sma20 = latest["SMA 20"]
    sma50 = latest["SMA 50"]
    sma200 = latest["SMA 200"]
    rsi14 = latest["RSI 14"]
    one_year_return = latest["1Y Return %"]

    score = 0
    reasons: list[str] = []

    if pd.notna(last_price) and pd.notna(sma200):
        if last_price > sma200:
            score += 2
            reasons.append("Price is above SMA 200, which supports a long-term uptrend.")
        else:
            score -= 2
            reasons.append("Price is below SMA 200, which points to a weaker long-term trend.")

    if pd.notna(sma50) and pd.notna(sma200):
        if sma50 > sma200:
            score += 2
            reasons.append("SMA 50 is above SMA 200, showing medium-term trend strength.")
        else:
            score -= 2
            reasons.append("SMA 50 is below SMA 200, showing medium-term trend weakness.")

    if pd.notna(sma20) and pd.notna(sma50):
        if sma20 > sma50:
            score += 1
            reasons.append("SMA 20 is above SMA 50, confirming short-term momentum.")
        else:
            score -= 1
            reasons.append("SMA 20 is below SMA 50, showing near-term momentum has softened.")

    if pd.notna(rsi14):
        if 50 <= rsi14 <= 68:
            score += 1
            reasons.append("RSI is in a healthy bullish zone without being heavily overbought.")
        elif rsi14 > 75:
            score -= 1
            reasons.append("RSI is very high, so upside may be stretched in the short term.")
        elif rsi14 < 35:
            score -= 1
            reasons.append("RSI is weak, which suggests sellers still have control.")

    if pd.notna(one_year_return):
        if one_year_return > 15:
            score += 1
            reasons.append("The stock is up meaningfully over the past year, supporting trend-following bias.")
        elif one_year_return < -10:
            score -= 1
            reasons.append("The stock is down over the past year, which weakens the broader trend picture.")

    volume_note = "Volume trend unavailable."
    volume_status = "N/A"
    last_volume = pd.NA
    avg_volume_50 = pd.NA
    if volume_series is not None and not volume_series.empty:
        volume_series = ensure_datetime_index(volume_series)
        last_volume = volume_series.iloc[-1]
        avg_volume_50 = volume_series.tail(50).mean()
        if pd.notna(last_volume) and pd.notna(avg_volume_50) and avg_volume_50 != 0:
            vol_ratio = last_volume / avg_volume_50
            if vol_ratio >= 1.2:
                volume_status = "Elevated"
                volume_note = "Latest volume is above the 50-day average, which strengthens the latest move."
                score += 1
            elif vol_ratio <= 0.8:
                volume_status = "Light"
                volume_note = "Latest volume is below the 50-day average, so conviction behind the move is lighter."
            else:
                volume_status = "Normal"
                volume_note = "Latest volume is close to the 50-day average."
        reasons.append(volume_note)

    if score >= 4:
        signal = "BUY"
        confidence = "High" if score >= 6 else "Moderate"
        summary = "Trend structure is favorable across long-, medium-, and short-term signals."
    elif score <= -3:
        signal = "SELL"
        confidence = "High" if score <= -5 else "Moderate"
        summary = "Trend structure is weak, and current momentum does not support accumulation."
    else:
        signal = "HOLD"
        confidence = "Moderate"
        summary = "Signals are mixed, so waiting for stronger confirmation is more prudent."

    latest_daily_ts = indicators.index[-1] if not indicators.empty else None

    return {
        "Ticker": ticker,
        "Signal": signal,
        "Confidence": confidence,
        "Sentinel Score": score,
        "Trend": trend_label(one_year_return),
        "1Y Return %": one_year_return,
        "RSI 14": rsi14,
        "RSI Signal": rsi_signal(rsi14),
        "Last Price": last_price,
        "SMA 20": sma20,
        "SMA 50": sma50,
        "SMA 200": sma200,
        "Last Volume": last_volume,
        "50D Avg Volume": avg_volume_50,
        "Volume Status": volume_status,
        "Summary": summary,
        "Reasons": reasons,
        "Indicators": indicators,
        "Latest Daily Timestamp": latest_daily_ts,
    }



def get_intraday_snapshot(intraday_data: pd.DataFrame | None, ticker: str):
    price_series, field_name = get_price_series(intraday_data, ticker)
    volume_series = get_series(intraday_data, "Volume", ticker)

    if price_series is None or price_series.empty:
        return {
            "Price Source": "N/A",
            "Last Price": pd.NA,
            "Prev Price": pd.NA,
            "Change %": pd.NA,
            "Last Volume": pd.NA,
            "Latest Timestamp": None,
            "Available": False,
        }

    price_series = ensure_datetime_index(price_series)
    latest_ts = price_series.index[-1]
    last_price = price_series.iloc[-1]
    prev_price = price_series.iloc[-2] if len(price_series) >= 2 else pd.NA
    change_pct = ((last_price / prev_price) - 1) * 100 if pd.notna(prev_price) and prev_price != 0 else pd.NA
    last_volume = volume_series.iloc[-1] if volume_series is not None and not volume_series.empty else pd.NA

    return {
        "Price Source": field_name,
        "Last Price": last_price,
        "Prev Price": prev_price,
        "Change %": change_pct,
        "Last Volume": last_volume,
        "Latest Timestamp": latest_ts,
        "Available": True,
    }



def build_snapshot_row(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str):
    price_series, field_name = get_price_series(daily_data, ticker)
    volume_series = get_series(daily_data, "Volume", ticker)
    intraday = get_intraday_snapshot(intraday_data, ticker)

    if price_series is None or price_series.empty:
        return {
            "Ticker": ticker,
            "Daily Source": "Missing",
            "Latest Daily Date": "N/A",
            "Last Daily Close": "N/A",
            "Live / Latest Intraday": "N/A",
            "Intraday Change": "N/A",
            "1Y Trend": "N/A",
            "Signal": "N/A",
            "Confidence": "N/A",
            "SMA 200": "N/A",
            "RSI 14": "N/A",
        }

    sentinel = analyze_market_sentinel(price_series, volume_series, ticker)
    latest_daily_ts = sentinel["Latest Daily Timestamp"]

    return {
        "Ticker": ticker,
        "Daily Source": field_name,
        "Latest Daily Date": pd.Timestamp(latest_daily_ts).strftime("%Y-%m-%d") if latest_daily_ts is not None else "N/A",
        "Last Daily Close": format_price(sentinel["Last Price"]),
        "Live / Latest Intraday": format_price(intraday["Last Price"]) if intraday["Available"] else "N/A",
        "Intraday Change": format_percent(intraday["Change %"]) if intraday["Available"] else "N/A",
        "1Y Trend": sentinel["Trend"],
        "Signal": sentinel["Signal"],
        "Confidence": sentinel["Confidence"],
        "SMA 200": format_price(sentinel["SMA 200"]),
        "RSI 14": f"{sentinel['RSI 14']:.2f}" if pd.notna(sentinel["RSI 14"]) else "N/A",
    }



def make_chart_frame(series: pd.Series, column_name: str):
    if series is None or series.empty:
        return pd.DataFrame(columns=[column_name])
    clean = ensure_datetime_index(pd.Series(series.copy()))
    clean.name = column_name
    return clean.to_frame()



def render_market_sentinel_card(sentinel: dict):
    signal = sentinel["Signal"]
    if signal == "BUY":
        st.success(f"🟢 Market Sentinel Signal: BUY | Confidence: {sentinel['Confidence']}")
    elif signal == "SELL":
        st.error(f"🔴 Market Sentinel Signal: SELL | Confidence: {sentinel['Confidence']}")
    else:
        st.warning(f"🟡 Market Sentinel Signal: HOLD | Confidence: {sentinel['Confidence']}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sentinel Score", str(sentinel["Sentinel Score"]))
    col2.metric("1Y Return", format_percent(sentinel["1Y Return %"]))
    col3.metric("Trend", sentinel["Trend"])
    col4.metric("Volume Status", sentinel["Volume Status"])

    st.markdown(f"**Summary:** {sentinel['Summary']}")
    st.markdown("**Why the model says this:**")
    for reason in sentinel["Reasons"][:6]:
        st.markdown(f"- {reason}")



def render_data_freshness_banner(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, tickers: list[str]):
    daily_dates = []
    intraday_dates = []

    for ticker in tickers:
        price_series, _ = get_price_series(daily_data, ticker)
        if price_series is not None and not price_series.empty:
            price_series = ensure_datetime_index(price_series)
            daily_dates.append(price_series.index[-1])

        intraday = get_intraday_snapshot(intraday_data, ticker)
        if intraday["Available"] and intraday["Latest Timestamp"] is not None:
            intraday_dates.append(intraday["Latest Timestamp"])

    col1, col2 = st.columns(2)
    if daily_dates:
        max_daily = max(pd.to_datetime(daily_dates))
        col1.info(
            f"Daily trend data is based on the latest completed U.S. trading day: "
            f"**{pd.Timestamp(max_daily).strftime('%Y-%m-%d')}**"
        )
    else:
        col1.warning("No daily trend timestamp available.")

    if intraday_dates:
        max_intraday = max(pd.to_datetime(intraday_dates))
        col2.success(
            f"Latest intraday update: **{format_us_timestamp(max_intraday)}** "
            f"| Taiwan time: **{format_tw_timestamp(max_intraday)}**"
        )
    else:
        col2.warning("Intraday quotes are unavailable right now.")



def render_ticker_section(daily_data: pd.DataFrame, intraday_data: pd.DataFrame | None, ticker: str):
    price_series, field_name = get_price_series(daily_data, ticker)
    volume_series = get_series(daily_data, "Volume", ticker)
    intraday = get_intraday_snapshot(intraday_data, ticker)

    st.subheader(f"{ticker} Overview")

    if price_series is None or price_series.empty:
        st.warning(f"No usable price data found for {ticker}.")
        return

    sentinel = analyze_market_sentinel(price_series, volume_series, ticker)
    indicators = sentinel["Indicators"]
    latest = indicators.iloc[-1]

    daily_change = pd.NA
    if len(price_series) >= 2:
        daily_change = ((price_series.iloc[-1] / price_series.iloc[-2]) - 1) * 100

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Last Daily Close", format_price(latest["Price"]), format_percent(daily_change))
    col_b.metric("SMA 50", format_price(latest["SMA 50"]))
    col_c.metric("SMA 200", format_price(latest["SMA 200"]))
    col_d.metric("RSI 14", f"{latest['RSI 14']:.2f}" if pd.notna(latest["RSI 14"]) else "N/A")

    st.caption(
        f"Daily price source: {field_name} | Latest completed daily bar: "
        f"{pd.Timestamp(sentinel['Latest Daily Timestamp']).strftime('%Y-%m-%d')}"
    )

    intraday_col1, intraday_col2, intraday_col3, intraday_col4 = st.columns(4)
    intraday_col1.metric(
        "Latest Intraday Price",
        format_price(intraday["Last Price"]) if intraday["Available"] else "N/A",
        format_percent(intraday["Change %"]) if intraday["Available"] else None,
    )
    intraday_col2.metric(
        "Intraday Volume",
        f"{int(intraday['Last Volume']):,}" if intraday["Available"] and pd.notna(intraday["Last Volume"]) else "N/A",
    )
    intraday_col3.metric(
        "Intraday Timestamp (US)",
        format_us_timestamp(intraday["Latest Timestamp"]) if intraday["Available"] else "N/A",
    )
    intraday_col4.metric(
        "Intraday Timestamp (TW)",
        format_tw_timestamp(intraday["Latest Timestamp"]) if intraday["Available"] else "N/A",
    )

    render_market_sentinel_card(sentinel)

    chart_df = indicators[["Price", "SMA 20", "SMA 50", "SMA 200"]].tail(252).copy()
    chart_df.columns = ["Price", "SMA 20", "SMA 50", "SMA 200"]
    st.markdown("**1-Year Daily Trend with Moving Averages**")
    st.line_chart(chart_df)

    rsi_df = indicators[["RSI 14"]].tail(252).copy()
    rsi_df.columns = ["RSI 14"]
    st.markdown("**RSI (14)**")
    st.line_chart(rsi_df)

    intraday_price_series, _ = get_price_series(intraday_data, ticker)
    if intraday_price_series is not None and not intraday_price_series.empty:
        st.markdown("**Intraday Price (5-minute)**")
        intraday_chart = make_chart_frame(intraday_price_series.tail(78), f"{ticker} Intraday")
        st.line_chart(intraday_chart)

    if volume_series is not None and not volume_series.empty:
        st.markdown("**Daily Trading Volume**")
        volume_df = make_chart_frame(volume_series.tail(252), f"{ticker} Daily Volume")
        st.bar_chart(volume_df)
    else:
        st.info(f"Daily volume data is not available for {ticker}.")

    st.markdown("---")
    render_news_section(ticker)

    recent_df = indicators[["Price", "SMA 20", "SMA 50", "SMA 200", "RSI 14", "1Y Return %"]].tail(10).copy()
    recent_df.index.name = "Date"
    recent_df = recent_df.reset_index()
    st.markdown("**Last 10 Daily Trading Rows**")
    st.dataframe(recent_df, use_container_width=True, hide_index=True)



def generate_dashboard():
    st.title("📈 Market Sentinel Dashboard")
    st.markdown(
        "This version separates **1-year daily trend analysis** from **fresh intraday tracking**. "
        "The Market Sentinel signal uses the daily 1-year structure, while the intraday panel shows the latest live session data returned by Yahoo Finance."
    )

    with st.sidebar:
        st.header("Settings")
        tickers = st.multiselect(
            "Tickers",
            options=["NVDA", "TSM", "AAPL", "MSFT", "AMD", "QQQ", "TSLA", "AVGO", "PLTR"],
            default=DEFAULT_TICKERS,
        )
        period = st.selectbox("Lookback Period (Trend Model)", SUPPORTED_PERIODS, index=SUPPORTED_PERIODS.index(DEFAULT_PERIOD))
        interval = st.selectbox("Trend Interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index(DEFAULT_INTERVAL))
        st.caption("Daily trend data is cached for 5 minutes. Intraday data is cached for 2 minutes.")
        if st.button("🔄 Refresh now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not tickers:
        st.warning("Please select at least one ticker in the sidebar.")
        return

    with st.spinner("Fetching daily trend data from Yahoo Finance..."):
        daily_data = fetch_stock_data(tickers, period, interval)

    with st.spinner("Fetching intraday live data from Yahoo Finance..."):
        intraday_data = fetch_intraday_data(tickers)

    if daily_data is None or daily_data.empty:
        st.error("No daily market data returned. Please try again later or adjust the selected tickers/period.")
        return

    render_data_freshness_banner(daily_data, intraday_data, tickers)

    st.header("📊 Snapshot")
    snapshot_rows = [build_snapshot_row(daily_data, intraday_data, ticker) for ticker in tickers]
    snapshot_df = pd.DataFrame(snapshot_rows)
    st.dataframe(snapshot_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.header("📉 Detailed Trend Panels")

    tabs = st.tabs(tickers)
    for tab, ticker in zip(tabs, tickers):
        with tab:
            render_ticker_section(daily_data, intraday_data, ticker)

    with st.expander("Show raw daily downloaded data"):
        st.dataframe(daily_data.tail(20), use_container_width=True)

    if intraday_data is not None and not intraday_data.empty:
        with st.expander("Show raw intraday downloaded data"):
            st.dataframe(intraday_data.tail(20), use_container_width=True)


if __name__ == "__main__":
    generate_dashboard()
