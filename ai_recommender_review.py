"""
ai_recommender_review.py — outcome tracker + scorecard for ai_recommender.

Walks every status='open' row in ai_recommendations, pulls OHLC since
created_at via yfinance, and marks:
    - stopped       (any low  <= stop_loss)
    - hit_tp2       (any high >= take_profit_2)
    - hit_tp1       (any high >= take_profit_1)
    - expired       (>30 days, no trigger)
HOLD / AVOID rows expire at 30d with their realized move recorded as
"informational" — they don't count in the hit-rate but they're not lost.

Then recomputes the rolling scorecard (30d / 90d windows × US/TW/ALL)
and writes one row per (window, market) into ai_recommender_scorecard.

Runs once per day after US close. Cron: see ai_recommender_review.yml.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

import yfinance as yf

try:
    from supabase import create_client, Client as SupabaseClient
except Exception:  # pragma: no cover
    create_client = None
    SupabaseClient = None


EXPIRY_DAYS = 30
TRACKED_ACTIONS = {"BUY", "ADD", "SELL", "TRIM"}  # actionable with entry/stop/tp
INFORMATIONAL_ACTIONS = {"HOLD", "AVOID"}


# =============================================================================
# SUPABASE
# =============================================================================


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


def fetch_open_recs(sb: SupabaseClient) -> list[dict[str, Any]]:
    try:
        res = (
            sb.table("ai_recommendations")
            .select("*")
            .eq("status", "open")
            .order("created_at")
            .limit(500)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        print(f"[error] fetch_open_recs failed: {exc}", file=sys.stderr)
        return []


def update_rec(sb: SupabaseClient, rec_id: str, patch: dict[str, Any]) -> None:
    try:
        sb.table("ai_recommendations").update(patch).eq("id", rec_id).execute()
    except Exception as exc:
        print(f"[warn] update {rec_id} failed: {exc}", file=sys.stderr)


def fetch_recent_closed(sb: SupabaseClient, days: int, market: str | None) -> list[dict[str, Any]]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        q = (
            sb.table("ai_recommendations")
            .select("market,action,conviction,realized_pnl_pct,status,stop_loss,entry_low,entry_high,take_profit_1,closed_at,created_at")
            .gte("created_at", since)
            .neq("status", "open")
        )
        if market and market != "ALL":
            q = q.eq("market", market)
        res = q.limit(5000).execute()
        return res.data or []
    except Exception as exc:
        print(f"[warn] fetch_recent_closed failed: {exc}", file=sys.stderr)
        return []


def fetch_recent_open(sb: SupabaseClient, days: int, market: str | None) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        q = (
            sb.table("ai_recommendations")
            .select("id", count="exact")
            .eq("status", "open")
            .gte("created_at", since)
        )
        if market and market != "ALL":
            q = q.eq("market", market)
        res = q.execute()
        return res.count or 0
    except Exception:
        return 0


# =============================================================================
# YFINANCE OHLC SINCE CALL
# =============================================================================


def fetch_ohlc_since(ticker: str, since_iso: str):
    try:
        start = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    except Exception:
        return None
    try:
        df = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
        )
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        print(f"[warn] ohlc fetch failed for {ticker}: {exc}", file=sys.stderr)
        return None


# =============================================================================
# REVIEW LOGIC
# =============================================================================


def review_rec(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Return a patch dict if this rec should be updated, else None."""
    action = rec.get("action")
    ticker = rec.get("ticker")
    created_at = rec.get("created_at")
    if not (action and ticker and created_at):
        return None

    df = fetch_ohlc_since(ticker, created_at)
    if df is None or df.empty:
        return None

    high_since = float(df["High"].max())
    low_since = float(df["Low"].min())
    last = float(df["Close"].iloc[-1])
    price_at = float(rec.get("price_at_call") or rec.get("entry_high") or rec.get("entry_low") or last)

    days_open = (datetime.now(timezone.utc) - datetime.fromisoformat(created_at.replace("Z", "+00:00"))).days

    patch: dict[str, Any] = {
        "high_since_call": round(high_since, 4),
        "low_since_call": round(low_since, 4),
    }

    # HOLD / AVOID: informational, expire at EXPIRY_DAYS with realized move
    if action in INFORMATIONAL_ACTIONS:
        if days_open >= EXPIRY_DAYS:
            patch["status"] = "expired"
            patch["closed_at"] = datetime.now(timezone.utc).isoformat()
            if price_at:
                patch["realized_pnl_pct"] = round((last / price_at - 1) * 100, 2)
            patch["review_notes"] = f"informational {action}; auto-expired at {EXPIRY_DAYS}d"
        return patch

    # Tracked actions need stop_loss + take_profit_1 to be reviewable
    if action not in TRACKED_ACTIONS:
        return patch

    stop = rec.get("stop_loss")
    tp1 = rec.get("take_profit_1")
    tp2 = rec.get("take_profit_2")
    is_short = action in {"SELL", "TRIM"}  # tracked as bearish call

    triggered = None  # 'stopped' / 'hit_tp1' / 'hit_tp2'

    if not is_short:
        # long-biased: stop on lows, targets on highs
        if stop is not None and low_since <= float(stop):
            triggered = "stopped"
        elif tp2 is not None and high_since >= float(tp2):
            triggered = "hit_tp2"
        elif tp1 is not None and high_since >= float(tp1):
            triggered = "hit_tp1"
    else:
        # bearish call (sell/trim of a holding, or short): stop on highs, target on lows
        if stop is not None and high_since >= float(stop):
            triggered = "stopped"
        elif tp2 is not None and low_since <= float(tp2):
            triggered = "hit_tp2"
        elif tp1 is not None and low_since <= float(tp1):
            triggered = "hit_tp1"

    def realized(exit_px: float) -> float:
        if not price_at:
            return 0.0
        if is_short:
            return round((price_at / exit_px - 1) * 100, 2)
        return round((exit_px / price_at - 1) * 100, 2)

    if triggered == "stopped" and stop is not None:
        patch["status"] = "stopped"
        patch["realized_pnl_pct"] = realized(float(stop))
        patch["closed_at"] = datetime.now(timezone.utc).isoformat()
        patch["review_notes"] = f"stop hit at ~{stop}"
    elif triggered == "hit_tp2" and tp2 is not None:
        patch["status"] = "hit_tp2"
        patch["realized_pnl_pct"] = realized(float(tp2))
        patch["closed_at"] = datetime.now(timezone.utc).isoformat()
        patch["review_notes"] = f"tp2 hit at ~{tp2}"
    elif triggered == "hit_tp1" and tp1 is not None:
        patch["status"] = "hit_tp1"
        patch["realized_pnl_pct"] = realized(float(tp1))
        patch["closed_at"] = datetime.now(timezone.utc).isoformat()
        patch["review_notes"] = f"tp1 hit at ~{tp1}"
    elif days_open >= EXPIRY_DAYS:
        patch["status"] = "expired"
        patch["realized_pnl_pct"] = realized(last)
        patch["closed_at"] = datetime.now(timezone.utc).isoformat()
        patch["review_notes"] = f"expired at {EXPIRY_DAYS}d, mark-to-market"
    # else: still open, just update high/low

    return patch


# =============================================================================
# SCORECARD
# =============================================================================


def compute_scorecard(closed_recs: list[dict[str, Any]], open_count: int, window_days: int, market: str) -> dict[str, Any]:
    tracked = [r for r in closed_recs if r.get("action") in TRACKED_ACTIONS and r.get("realized_pnl_pct") is not None]
    wins = [r for r in tracked if (r.get("realized_pnl_pct") or 0) > 0]
    losses = [r for r in tracked if (r.get("realized_pnl_pct") or 0) < 0]

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    win_pcts = [float(r["realized_pnl_pct"]) for r in wins]
    loss_pcts = [float(r["realized_pnl_pct"]) for r in losses]
    all_pcts = [float(r["realized_pnl_pct"]) for r in tracked]

    # R-multiple = realized% / planned-risk%
    r_multiples = []
    for r in tracked:
        entry_mid = None
        if r.get("entry_low") is not None and r.get("entry_high") is not None:
            entry_mid = (float(r["entry_low"]) + float(r["entry_high"])) / 2
        elif r.get("entry_high") is not None:
            entry_mid = float(r["entry_high"])
        stop = r.get("stop_loss")
        if entry_mid and stop and entry_mid != float(stop):
            planned_risk_pct = abs((float(stop) / entry_mid - 1) * 100)
            if planned_risk_pct > 0:
                r_multiples.append(float(r["realized_pnl_pct"]) / planned_risk_pct)

    by_action: dict[str, dict[str, Any]] = {}
    for r in closed_recs:
        a = r.get("action", "?")
        slot = by_action.setdefault(a, {"n": 0, "avg_pnl_pct": None, "_sum": 0.0, "_with_pnl": 0})
        slot["n"] += 1
        if r.get("realized_pnl_pct") is not None:
            slot["_sum"] += float(r["realized_pnl_pct"])
            slot["_with_pnl"] += 1
    for a, slot in by_action.items():
        slot["avg_pnl_pct"] = round(slot["_sum"] / slot["_with_pnl"], 2) if slot["_with_pnl"] else None
        slot.pop("_sum", None)
        slot.pop("_with_pnl", None)

    return {
        "window_days": window_days,
        "market": market,
        "total_calls": len(closed_recs) + open_count,
        "open_calls": open_count,
        "closed_calls": len(closed_recs),
        "wins": len(wins),
        "losses": len(losses),
        "hit_rate_pct": round(len(wins) / len(tracked) * 100, 1) if tracked else None,
        "avg_win_pct": avg(win_pcts),
        "avg_loss_pct": avg(loss_pcts),
        "expectancy_pct": avg(all_pcts),
        "biggest_win": round(max(win_pcts), 2) if win_pcts else None,
        "biggest_loss": round(min(loss_pcts), 2) if loss_pcts else None,
        "avg_r_multiple": round(sum(r_multiples) / len(r_multiples), 2) if r_multiples else None,
        "by_action": by_action,
    }


def write_scorecard(sb: SupabaseClient, row: dict[str, Any]) -> None:
    try:
        sb.table("ai_recommender_scorecard").insert(row).execute()
    except Exception as exc:
        print(f"[warn] scorecard insert failed: {exc}", file=sys.stderr)


# =============================================================================
# MAIN
# =============================================================================


def main() -> int:
    sb = supabase_client()
    if sb is None:
        print("[error] no supabase client; aborting")
        return 1

    open_recs = fetch_open_recs(sb)
    print(f"[info] {len(open_recs)} open recs to review")

    updated = 0
    closed = 0
    for rec in open_recs:
        patch = review_rec(rec)
        if not patch:
            continue
        update_rec(sb, rec["id"], patch)
        updated += 1
        if patch.get("status") and patch["status"] != "open":
            closed += 1
            print(f"   {rec['ticker']:>10}  {patch['status']:>8}  pnl={patch.get('realized_pnl_pct')}%")

    print(f"[info] updated {updated}, newly closed {closed}")

    # Recompute scorecard for 30d / 90d × US/TW/ALL
    for window_days in (30, 90):
        for market in ("US", "TW", "ALL"):
            closed_recs = fetch_recent_closed(sb, window_days, market)
            open_count = fetch_recent_open(sb, window_days, market)
            sc = compute_scorecard(closed_recs, open_count, window_days, market)
            write_scorecard(sb, sc)
            print(
                f"        scorecard {window_days}d/{market}: "
                f"hit={sc['hit_rate_pct']}% exp={sc['expectancy_pct']}% "
                f"({sc['closed_calls']} closed, {sc['open_calls']} open)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
