"""
ai_recommender.py — Senior-PM AI recommender for the Market Sentinel stack.

Runs on a schedule (see ai_recommender.yml). Reads dashboard-style signals
from yfinance, current Alpaca paper positions, prior open recommendations
and the latest scorecard from Supabase, then asks Claude to play a senior
Wall Street PM and emit STRUCTURED JSON recommendations. Writes them to
Supabase (ai_recommendations) and pushes a summary to Telegram.

Decision support only — does NOT execute trades. Paper bot integration is
left intentionally loose; consume ai_recommendations from paper_trading_bot
if/when you decide to couple them.

Env / secrets expected (GitHub Actions + Streamlit Cloud, per memo §secrets):
    ANTHROPIC_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY     (write access)
    ALPACA_API_KEY_ID
    ALPACA_API_SECRET_KEY
    ALPACA_PAPER=true
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from typing import Any

import requests
import yfinance as yf

# Anthropic / Supabase / Alpaca imports are inside try/except so a partial
# environment still runs in --dry-run mode for local validation.
try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover
    Anthropic = None

try:
    from supabase import create_client, Client as SupabaseClient
except Exception:  # pragma: no cover
    create_client = None
    SupabaseClient = None

try:
    from alpaca.trading.client import TradingClient
except Exception:  # pragma: no cover
    TradingClient = None


# =============================================================================
# CONFIG  —  edit watchlists here
# =============================================================================

US_WATCHLIST: list[str] = [
    # Mag7
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    # David's memory picks
    "MU",
    # SpaceX proxies (per memo, position size halved at consumption side)
    "XOVR", "ARKX",
    # Benchmarks
    "SPY", "QQQ",
]

# EDIT ME — replace with your real TW shortlist. yfinance suffix .TW or .TWO.
TW_WATCHLIST: list[str] = [
    "2330.TW",  # TSMC
    "2317.TW",  # Hon Hai / Foxconn
    "2454.TW",  # MediaTek
    "2308.TW",  # Delta Electronics
    "2382.TW",  # Quanta
    "3008.TW",  # Largan (Apple supplier)
    "2891.TW",  # CTBC Financial (defensive)
    "0050.TW",  # Yuanta Taiwan 50 ETF (benchmark)
]

MODEL = os.environ.get("AI_RECOMMENDER_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 8000
PRIOR_REC_LOOKBACK_DAYS = 30


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class TickerSignal:
    ticker: str
    market: str
    company_name: str | None = None
    price: float | None = None
    pct_1d: float | None = None
    pct_5d: float | None = None
    pct_20d: float | None = None
    ma_20: float | None = None
    ma_60: float | None = None
    ma_200: float | None = None
    above_ma20: bool | None = None
    above_ma60: bool | None = None
    above_ma200: bool | None = None
    rsi_14: float | None = None
    vol_avg_20: float | None = None
    vol_today_vs_avg: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    drawdown_from_high_pct: float | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    sector: str | None = None
    error: str | None = None


@dataclass
class RiskGauge:
    score: int | None = None
    label: str | None = None
    vix: float | None = None
    vix_5d_change_pct: float | None = None
    tnx_10y: float | None = None
    yield_curve_bps: float | None = None
    spy_vs_ma200_pct: float | None = None
    twii_vs_ma60_pct: float | None = None
    hyg_vs_lqd_5d: float | None = None
    gld_5d_pct: float | None = None
    spx_drawdown_pct: float | None = None
    judgment: str | None = None


# =============================================================================
# SIGNAL COLLECTION
# =============================================================================


def _safe_hist(ticker: str, period: str = "1y", interval: str = "1d"):
    """Return a yfinance history DataFrame or None on failure."""
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        print(f"[warn] yfinance history failed for {ticker}: {exc}", file=sys.stderr)
        return None


def _rsi(closes, period: int = 14) -> float | None:
    try:
        deltas = closes.diff()
        gain = deltas.clip(lower=0).rolling(period).mean()
        loss = (-deltas.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        v = float(rsi.iloc[-1])
        if v != v:  # NaN
            return None
        return round(v, 2)
    except Exception:
        return None


def fetch_ticker_signal(ticker: str, market: str) -> TickerSignal:
    sig = TickerSignal(ticker=ticker, market=market)
    df = _safe_hist(ticker, period="1y")
    if df is None or len(df) < 30:
        sig.error = "no history"
        return sig

    closes = df["Close"]
    last = float(closes.iloc[-1])
    sig.price = round(last, 4)

    def pct(n):
        if len(closes) <= n:
            return None
        prior = float(closes.iloc[-(n + 1)])
        if prior == 0:
            return None
        return round((last / prior - 1) * 100, 2)

    sig.pct_1d = pct(1)
    sig.pct_5d = pct(5)
    sig.pct_20d = pct(20)

    if len(closes) >= 20:
        sig.ma_20 = round(float(closes.rolling(20).mean().iloc[-1]), 4)
        sig.above_ma20 = last > sig.ma_20
    if len(closes) >= 60:
        sig.ma_60 = round(float(closes.rolling(60).mean().iloc[-1]), 4)
        sig.above_ma60 = last > sig.ma_60
    if len(closes) >= 200:
        sig.ma_200 = round(float(closes.rolling(200).mean().iloc[-1]), 4)
        sig.above_ma200 = last > sig.ma_200

    sig.rsi_14 = _rsi(closes, 14)

    vols = df["Volume"]
    if len(vols) >= 20:
        avg20 = float(vols.rolling(20).mean().iloc[-1])
        sig.vol_avg_20 = round(avg20, 0)
        if avg20 > 0:
            sig.vol_today_vs_avg = round(float(vols.iloc[-1]) / avg20, 2)

    high52 = float(df["High"].max())
    low52 = float(df["Low"].min())
    sig.week52_high = round(high52, 4)
    sig.week52_low = round(low52, 4)
    if high52 > 0:
        sig.drawdown_from_high_pct = round((last / high52 - 1) * 100, 2)

    # Fundamentals — best-effort, yfinance .info is flaky
    try:
        info = yf.Ticker(ticker).info or {}
        sig.company_name = info.get("longName") or info.get("shortName")
        sig.market_cap = info.get("marketCap")
        sig.pe_ratio = info.get("trailingPE")
        sig.forward_pe = info.get("forwardPE")
        sig.sector = info.get("sector")
    except Exception as exc:
        print(f"[warn] info failed for {ticker}: {exc}", file=sys.stderr)

    return sig


def fetch_risk_gauge() -> RiskGauge:
    """Re-implementation of the dashboard's 9-indicator risk gauge."""
    g = RiskGauge()

    def last_close(t):
        d = _safe_hist(t, period="6mo")
        if d is None or d.empty:
            return None
        return float(d["Close"].iloc[-1])

    def pct_change(t, n):
        d = _safe_hist(t, period="6mo")
        if d is None or len(d) <= n:
            return None
        try:
            return round((float(d["Close"].iloc[-1]) / float(d["Close"].iloc[-(n + 1)]) - 1) * 100, 2)
        except Exception:
            return None

    vix = last_close("^VIX")
    if vix:
        g.vix = round(vix, 2)
    g.vix_5d_change_pct = pct_change("^VIX", 5)

    tnx = last_close("^TNX")
    irx = last_close("^IRX")
    if tnx:
        g.tnx_10y = round(tnx, 2)
    if tnx is not None and irx is not None:
        g.yield_curve_bps = round((tnx - irx) * 100, 1)

    # SPY vs 200DMA
    spy = _safe_hist("SPY", period="1y")
    if spy is not None and len(spy) >= 200:
        last = float(spy["Close"].iloc[-1])
        ma200 = float(spy["Close"].rolling(200).mean().iloc[-1])
        if ma200:
            g.spy_vs_ma200_pct = round((last / ma200 - 1) * 100, 2)
        # drawdown from 250-day high
        recent = spy["Close"].tail(250)
        peak = float(recent.max())
        if peak:
            g.spx_drawdown_pct = round((last / peak - 1) * 100, 2)

    twii = _safe_hist("^TWII", period="6mo")
    if twii is not None and len(twii) >= 60:
        last = float(twii["Close"].iloc[-1])
        ma60 = float(twii["Close"].rolling(60).mean().iloc[-1])
        if ma60:
            g.twii_vs_ma60_pct = round((last / ma60 - 1) * 100, 2)

    # HY vs IG (HYG vs LQD), 5-day relative
    hyg5 = pct_change("HYG", 5)
    lqd5 = pct_change("LQD", 5)
    if hyg5 is not None and lqd5 is not None:
        g.hyg_vs_lqd_5d = round(hyg5 - lqd5, 2)

    g.gld_5d_pct = pct_change("GLD", 5)

    # Score it — same shape as dashboard, simplified to 0-100
    score = 0
    sub = []
    if g.vix is not None:
        if g.vix >= 30: sub.append(95)
        elif g.vix >= 20: sub.append(70)
        elif g.vix >= 14: sub.append(40)
        else: sub.append(15)
    if g.vix_5d_change_pct is not None:
        sub.append(min(100, max(0, 50 + g.vix_5d_change_pct * 2)))
    if g.yield_curve_bps is not None:
        sub.append(80 if g.yield_curve_bps < 0 else 30)
    if g.spy_vs_ma200_pct is not None:
        sub.append(min(100, max(0, 50 - g.spy_vs_ma200_pct * 3)))
    if g.twii_vs_ma60_pct is not None:
        sub.append(min(100, max(0, 50 - g.twii_vs_ma60_pct * 3)))
    if g.tnx_10y is not None:
        sub.append(70 if g.tnx_10y >= 5 else 40 if g.tnx_10y >= 4 else 25)
    if g.hyg_vs_lqd_5d is not None:
        sub.append(min(100, max(0, 50 - g.hyg_vs_lqd_5d * 10)))
    if g.gld_5d_pct is not None:
        sub.append(min(100, max(0, 30 + g.gld_5d_pct * 5)))
    if g.spx_drawdown_pct is not None:
        if g.spx_drawdown_pct <= -20: sub.append(95)
        elif g.spx_drawdown_pct <= -10: sub.append(75)
        elif g.spx_drawdown_pct <= -5: sub.append(55)
        else: sub.append(25)

    if sub:
        score = int(round(sum(sub) / len(sub)))
        g.score = score
        if score >= 65:
            g.label = "HIGH RISK / 高風險"
            g.judgment = "Defensive posture. Tighten stops. Avoid new high-beta longs."
        elif score >= 45:
            g.label = "ELEVATED / 警戒"
            g.judgment = "Mixed regime. Selective adds. Maintain hedges."
        else:
            g.label = "CALM / 平穩"
            g.judgment = "Constructive. Trend-following allowed. Watch for complacency."

    return g


# =============================================================================
# ALPACA + SUPABASE
# =============================================================================


def fetch_alpaca_positions() -> list[dict[str, Any]]:
    if TradingClient is None:
        return []
    key = os.environ.get("ALPACA_API_KEY_ID")
    sec = os.environ.get("ALPACA_API_SECRET_KEY")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    if not (key and sec):
        return []
    try:
        tc = TradingClient(key, sec, paper=paper)
        positions = tc.get_all_positions()
        out = []
        for p in positions:
            out.append({
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "unrealized_pl_pct": round(float(p.unrealized_plpc) * 100, 2) if p.unrealized_plpc else None,
                "market_value": float(p.market_value) if p.market_value else None,
            })
        return out
    except Exception as exc:
        print(f"[warn] alpaca positions failed: {exc}", file=sys.stderr)
        return []


def supabase_client() -> SupabaseClient | None:
    if create_client is None:
        return None
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        return create_client(url, key)
    except Exception as exc:
        print(f"[warn] supabase client failed: {exc}", file=sys.stderr)
        return None


def fetch_prior_open_recs(sb: SupabaseClient | None, tickers: list[str]) -> list[dict[str, Any]]:
    if sb is None:
        return []
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=PRIOR_REC_LOOKBACK_DAYS)).isoformat()
        res = (
            sb.table("ai_recommendations")
            .select("ticker,action,conviction,thesis,status,created_at,entry_low,entry_high,stop_loss,take_profit_1")
            .in_("ticker", tickers)
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(80)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        print(f"[warn] prior recs fetch failed: {exc}", file=sys.stderr)
        return []


def fetch_latest_scorecard(sb: SupabaseClient | None) -> list[dict[str, Any]]:
    if sb is None:
        return []
    try:
        res = (
            sb.table("ai_recommender_scorecard")
            .select("*")
            .order("computed_at", desc=True)
            .limit(6)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        print(f"[warn] scorecard fetch failed: {exc}", file=sys.stderr)
        return []


# =============================================================================
# CLAUDE PROMPT
# =============================================================================


SYSTEM_PROMPT = """You are a senior portfolio manager with 25 years on a Wall Street trading desk, covering US large-cap tech and Taiwan semiconductors. You write the morning note for a $500M book. Your reader is a sharp, time-poor investor who wants conviction and clarity, not hedging.

YOUR DISCIPLINE:
1. Top-down first. Read the regime from the risk gauge (VIX, yield curve, credit spreads, SPY 200DMA, drawdown from highs). Name it: risk-on / mixed / risk-off. Tilt every call by the regime.
2. Then bottom-up. For each ticker: price vs 20/60/200DMA, volume confirmation, RSI extremes, position relative to 52-week range, sector context.
3. Risk before reward. Define the stop FIRST (where the thesis is wrong), then the targets. If reward-to-risk is below 2:1, the call must be HOLD or AVOID.
4. Size by conviction (1-5). 5 = table-pounding, full size. 1 = barely interesting. 3 is the default; reserve 4-5 for genuine asymmetry.
5. Own your prior calls. The user will give you your open recommendations. Reaffirm, adjust, or cut. If a thesis is broken (stop hit, catalyst missed), say SELL or INVALIDATED.
6. Skepticism. Momentum without breadth is suspicious. Value without a catalyst is dead money. Crowded longs in a high-VIX regime are dangerous.
7. Honesty about uncertainty. If the data is mixed, HOLD is the right answer. Do not manufacture conviction.

OUTPUT RULES:
- Respond with a SINGLE JSON object, no prose outside it.
- Top-level keys: "regime_read" (string, 1-3 sentences), "recommendations" (array).
- Each recommendation object must include EXACTLY these keys:
  ticker, market, action, conviction, time_horizon, entry_low, entry_high,
  stop_loss, take_profit_1, take_profit_2, risk_reward, thesis, key_risks, catalysts
- action: one of BUY, ADD, HOLD, TRIM, SELL, AVOID
- conviction: integer 1-5
- time_horizon: one of "swing" (days-weeks), "position" (weeks-months), "long" (months-years)
- Prices in the ticker's listing currency (USD for US, TWD for TW).
- For HOLD/AVOID, entry/stop/targets may be null but thesis and key_risks must be filled.
- risk_reward: numeric, computed as (take_profit_1 - midpoint(entry)) / (midpoint(entry) - stop_loss). null if HOLD/AVOID.
- thesis: 2-4 sentences. Specific. Reference the actual data you were given.
- key_risks: 1-2 sentences naming what would invalidate the thesis.
- catalysts: upcoming events (earnings date, product launch, macro print). "None known" is acceptable.

You do not provide investment advice to retail clients. This is an internal desk note for paper-account decision support."""


def build_user_payload(
    risk_gauge: RiskGauge,
    us_signals: list[TickerSignal],
    tw_signals: list[TickerSignal],
    positions: list[dict[str, Any]],
    prior_recs: list[dict[str, Any]],
    scorecard: list[dict[str, Any]],
) -> str:
    payload = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "risk_gauge": asdict(risk_gauge),
        "us_tickers": [asdict(s) for s in us_signals],
        "tw_tickers": [asdict(s) for s in tw_signals],
        "current_paper_positions": positions,
        "your_open_prior_recommendations": prior_recs,
        "your_recent_scorecard": scorecard,
    }
    return (
        "Here are today's inputs. Emit the JSON object per the rules in the system prompt.\n\n"
        "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"
    )


def call_claude(system_prompt: str, user_payload: str) -> dict[str, Any]:
    if Anthropic is None:
        raise RuntimeError("anthropic package not installed")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_payload}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return _extract_json(text)


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction — strips ```json fences if present."""
    s = text.strip()
    if s.startswith("```"):
        # take the first fenced block
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    # find first { and last }
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("no JSON object in model response")
    return json.loads(s[i:j + 1])


# =============================================================================
# WRITE + TELEGRAM
# =============================================================================


REQUIRED_KEYS = {
    "ticker", "market", "action", "conviction", "time_horizon",
    "entry_low", "entry_high", "stop_loss", "take_profit_1", "take_profit_2",
    "risk_reward", "thesis", "key_risks", "catalysts",
}
VALID_ACTIONS = {"BUY", "ADD", "HOLD", "TRIM", "SELL", "AVOID"}


def validate_rec(r: dict[str, Any]) -> tuple[bool, str]:
    missing = REQUIRED_KEYS - set(r.keys())
    if missing:
        return False, f"missing keys: {missing}"
    if r.get("action") not in VALID_ACTIONS:
        return False, f"bad action: {r.get('action')}"
    try:
        c = int(r.get("conviction") or 0)
        if not (1 <= c <= 5):
            return False, f"bad conviction: {c}"
    except Exception:
        return False, "conviction not int"
    return True, ""


def write_recs(
    sb: SupabaseClient | None,
    run_id: str,
    regime_read: str,
    recs: list[dict[str, Any]],
    signal_snapshot_by_ticker: dict[str, dict[str, Any]],
) -> int:
    if sb is None:
        print("[info] no supabase client — skipping write")
        return 0
    rows = []
    for r in recs:
        ok, err = validate_rec(r)
        if not ok:
            print(f"[warn] skipping invalid rec: {err} :: {r}", file=sys.stderr)
            continue
        ticker = r["ticker"]
        snap = signal_snapshot_by_ticker.get(ticker, {})
        snap = dict(snap)
        snap["regime_read"] = regime_read
        rows.append({
            "run_id": run_id,
            "market": r.get("market"),
            "ticker": ticker,
            "company_name": snap.get("company_name"),
            "action": r["action"],
            "conviction": int(r["conviction"]),
            "time_horizon": r.get("time_horizon"),
            "entry_low": r.get("entry_low"),
            "entry_high": r.get("entry_high"),
            "stop_loss": r.get("stop_loss"),
            "take_profit_1": r.get("take_profit_1"),
            "take_profit_2": r.get("take_profit_2"),
            "risk_reward": r.get("risk_reward"),
            "thesis": r.get("thesis"),
            "key_risks": r.get("key_risks"),
            "catalysts": r.get("catalysts"),
            "signal_snapshot": snap,
            "model": MODEL,
            "status": "open",
            "price_at_call": snap.get("price"),
        })
    if not rows:
        return 0
    try:
        sb.table("ai_recommendations").insert(rows).execute()
        return len(rows)
    except Exception as exc:
        print(f"[error] supabase insert failed: {exc}", file=sys.stderr)
        return 0


def send_telegram(regime_read: str, recs: list[dict[str, Any]], scorecard: list[dict[str, Any]]) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[info] no telegram credentials — skipping push")
        return

    # Group by conviction descending; only push conviction >= 3
    keep = [r for r in recs if int(r.get("conviction") or 0) >= 3]
    keep.sort(key=lambda r: (-int(r["conviction"]), r["ticker"]))

    lines = ["🧠 *AI 建議 / Senior PM Desk Note*", ""]
    lines.append(f"*Regime / 市場判讀:* {regime_read}")
    lines.append("")

    if scorecard:
        sc30 = next((s for s in scorecard if s.get("window_days") == 30 and s.get("market") == "ALL"), None)
        if sc30:
            hr = sc30.get("hit_rate_pct")
            exp = sc30.get("expectancy_pct")
            lines.append(
                f"📊 *30d track record:* hit-rate {hr}% · expectancy {exp}% "
                f"({sc30.get('closed_calls')} closed)"
            )
            lines.append("")

    if not keep:
        lines.append("_No conviction-3+ calls in this run._")
    else:
        for r in keep[:12]:
            emoji = {"BUY": "🟢", "ADD": "🟢", "HOLD": "⚪", "TRIM": "🟡", "SELL": "🔴", "AVOID": "⛔"}.get(r["action"], "•")
            tag = "⭐" * int(r["conviction"])
            lines.append(f"{emoji} *{r['ticker']}* — {r['action']} {tag}")
            entry = (
                f"{r.get('entry_low')}–{r.get('entry_high')}"
                if r.get("entry_low") is not None else "—"
            )
            stop = r.get("stop_loss") or "—"
            tp1 = r.get("take_profit_1") or "—"
            rr = r.get("risk_reward")
            rr_s = f" R:R {rr}" if rr is not None else ""
            lines.append(f"   entry `{entry}` · stop `{stop}` · tp1 `{tp1}`{rr_s}")
            thesis = (r.get("thesis") or "").strip()
            if len(thesis) > 280:
                thesis = thesis[:277] + "…"
            lines.append(f"   _{thesis}_")
            lines.append("")

    lines.append("_Decision support · 非投資建議 · paper account_")
    body = "\n".join(lines)

    try:
        # Telegram cap is 4096 chars; chunk if needed
        for chunk_start in range(0, len(body), 3800):
            chunk = body[chunk_start:chunk_start + 3800]
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": chunk, "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=15,
            )
    except Exception as exc:
        print(f"[warn] telegram send failed: {exc}", file=sys.stderr)


# =============================================================================
# MAIN
# =============================================================================


def main(dry_run: bool = False) -> int:
    started = time.time()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    print(f"[info] run_id={run_id} model={MODEL} dry_run={dry_run}")

    print("[1/6] fetching risk gauge …")
    rg = fetch_risk_gauge()
    print(f"        score={rg.score} label={rg.label}")

    print("[2/6] fetching US signals …")
    us_signals = [fetch_ticker_signal(t, "US") for t in US_WATCHLIST]
    print("[3/6] fetching TW signals …")
    tw_signals = [fetch_ticker_signal(t, "TW") for t in TW_WATCHLIST]

    sb = supabase_client()
    positions = fetch_alpaca_positions()
    print(f"[4/6] alpaca positions: {len(positions)}")

    all_tickers = US_WATCHLIST + TW_WATCHLIST
    prior = fetch_prior_open_recs(sb, all_tickers)
    score = fetch_latest_scorecard(sb)
    print(f"        prior open recs: {len(prior)}  scorecard rows: {len(score)}")

    user_payload = build_user_payload(rg, us_signals, tw_signals, positions, prior, score)

    if dry_run:
        print("[dry-run] payload:\n", user_payload[:2000], "\n…")
        return 0

    print("[5/6] calling Claude …")
    result = call_claude(SYSTEM_PROMPT, user_payload)
    regime_read = result.get("regime_read", "")
    recs = result.get("recommendations", []) or []
    print(f"        got {len(recs)} recommendations")

    snapshot_map: dict[str, dict[str, Any]] = {}
    for s in us_signals + tw_signals:
        snapshot_map[s.ticker] = asdict(s)

    print("[6/6] writing + pushing …")
    written = write_recs(sb, run_id, regime_read, recs, snapshot_map)
    print(f"        wrote {written} rows to ai_recommendations")
    send_telegram(regime_read, recs, score)

    print(f"[done] elapsed={time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry))
