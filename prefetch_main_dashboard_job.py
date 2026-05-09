#!/usr/bin/env python
"""
Main Dashboard Daily Prefetch Job
==================================
Runs daily via GitHub Actions (.github/workflows/prefetch-daily.yml).
Fetches snapshot data for both Taiwan-only and U.S.-only market scopes,
serializes to JSON, and writes to Supabase main_dashboard_snapshot table.

Reuses the dashboard's own functions by importing the module directly.
This is intentional -- we want byte-for-byte the same data the live
dashboard produces.

Environment variables required:
    SUPABASE_URL                — https://xxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   — sb_secret_... (or legacy eyJhbGc...)

Optional:
    DASHBOARD_MODULE_PATH       — defaults to ./stock_dashboard_web_enhanced_v5_live_news.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE_NAME = "main_dashboard_snapshot"

# v6 dashboard file is the canonical source the prefetch script imports.
# When running from the repo root, the dashboard is at:
DEFAULT_DASHBOARD_PATH = "stock_dashboard_web_enhanced_v5_live_news.py"
DASHBOARD_PATH = os.environ.get("DASHBOARD_MODULE_PATH", DEFAULT_DASHBOARD_PATH)


def log(msg: str) -> None:
    """Timestamped stdout. GitHub Actions captures this as the job log."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Dashboard module loader
# ---------------------------------------------------------------------------
def load_dashboard_module():
    """Import the dashboard .py file as a module so we can call its
    fetchers / builders directly. Returns the loaded module object."""
    path = Path(DASHBOARD_PATH).resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"Dashboard module not found at {path}. "
            f"Set DASHBOARD_MODULE_PATH env var if your file is elsewhere."
        )
    log(f"Importing dashboard module from {path}")
    # Stub out streamlit/yfinance side-effects that would fail in a CLI run.
    _patch_streamlit_for_cli()
    spec = importlib.util.spec_from_file_location("dashboard_mod", path)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot create spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dashboard_mod"] = mod
    spec.loader.exec_module(mod)
    log("Dashboard module imported successfully")
    return mod


def _patch_streamlit_for_cli() -> None:
    """Streamlit's @cache_data and st.session_state need stubs for CLI usage.
    We replace them with passthroughs so the dashboard module can be imported
    without a Streamlit runtime."""
    try:
        import streamlit as st  # noqa: F401
        # When run by GitHub Actions with no Streamlit runtime, streamlit
        # actually still imports OK, but cache_data tries to spin up the
        # runtime. We intercept it with a no-op decorator.
        def _noop_cache(*args, **kwargs):
            def decorator(fn):
                return fn
            if args and callable(args[0]):
                return args[0]
            return decorator
        st.cache_data = _noop_cache  # type: ignore
        st.cache_resource = _noop_cache  # type: ignore
        # Provide a minimal session_state shim
        if not hasattr(st, "session_state") or st.session_state is None:
            class _SS(dict):
                def __getattr__(self, k): return self.get(k)
                def __setattr__(self, k, v): self[k] = v
            st.session_state = _SS()  # type: ignore
        # st.error / st.info / st.warning printed to stdout instead
        st.error = lambda *a, **k: log(f"st.error: {a}")  # type: ignore
        st.info = lambda *a, **k: log(f"st.info: {a}")  # type: ignore
        st.warning = lambda *a, **k: log(f"st.warning: {a}")  # type: ignore
        st.spinner = lambda *a, **k: _NullCtx()  # type: ignore
    except ImportError:
        pass


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


# ---------------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------------
def build_snapshot_for_scope(mod, market_scope: str) -> dict:
    """Build a complete dashboard snapshot for one market scope.
    Returns a dict with the JSON payloads ready for Supabase insert.
    """
    log(f"Building snapshot for scope={market_scope}")
    payload: dict[str, Any] = {
        "snapshot_date": datetime.now(timezone.utc).date().isoformat(),
        "market_scope": market_scope,
        "global_indicator_payload": None,
        "cockpit_q1_payload": None,
        "cockpit_q2_payload": None,
        "cockpit_q3_payload": None,
        "cockpit_q4_payload": None,
        "fetch_metadata": {"errors": []},
    }
    started = datetime.now(timezone.utc)

    # ---- 1. Global market indicator ----
    try:
        log("  Fetching global market indicator...")
        # Use the dashboard's default trend lens for prefetch
        lens_meta = {"period": "1y", "interval": "1d"}
        ref_data = mod.fetch_global_reference_data(
            lens_meta["period"], lens_meta["interval"]
        )
        # Live quotes only for the scope-relevant tickers
        scope_indices = mod.get_indices_for_scope(market_scope)
        # v1.5.5: TX=F removed; IX0126.TW now uses standard yfinance path.
        live_tickers = tuple(
            item["ticker"] for item in scope_indices
            if not item["ticker"].startswith("__")
        )
        live_quotes = mod.fetch_live_reference_quotes(live_tickers)
        indicator = mod.build_global_market_indicator(
            ref_data,
            lens_meta=lens_meta,
            live_quotes=live_quotes,
            market_scope=market_scope,
        )
        payload["global_indicator_payload"] = _sanitize_for_json(indicator)
        log(f"  ✓ Global indicator built ({len(indicator.get('cards', []))} cards)")
    except Exception as exc:
        log(f"  ✗ Global indicator failed: {exc}")
        payload["fetch_metadata"]["errors"].append(
            f"global_indicator: {type(exc).__name__}: {exc}"
        )

    # ---- 2-5. Cockpit Q1-Q4 ----
    try:
        log("  Fetching cockpit data...")
        # Default tickers for the scope drive the cockpit builders.
        dashboard_tickers = mod.default_tickers_for_market_scope(market_scope)
        # v1.7.0: US-only mode skips Q1/Q2/Q4 entirely and only builds the
        # US Theme Radar. The dashboard's render_decision_cockpit reads
        # snapshot_q3.us_theme_radar when market_scope=='U.S. only'.
        if market_scope == "U.S. only":
            log("  US-only mode: building US Theme Radar (5 themes)")
            # Fetch daily/intraday for ALL US theme tickers (28 tickers).
            us_tickers = mod.all_us_theme_tickers()
            us_daily = mod.fetch_daily_data(us_tickers, "3mo", "1d")
            us_intraday = mod.fetch_intraday_data(us_tickers)
            us_radar = mod.build_us_theme_radar(
                us_daily, us_intraday, top_n_per_theme=3, lang_zh=True,
                auto_fetch=False,
            )
            payload["cockpit_q1_payload"] = None
            payload["cockpit_q2_payload"] = None
            payload["cockpit_q3_payload"] = _sanitize_for_json({
                "us_theme_radar": us_radar,
                "lang_zh": True,
            })
            payload["cockpit_q4_payload"] = None
            log(f"  ✓ US Theme Radar built ({len(us_radar)} themes)")
        else:
            # Taiwan-only path (existing logic)
            period = "1y"
            interval = "1d"
            daily = mod.fetch_daily_data(dashboard_tickers, period, interval)
            intraday = mod.fetch_intraday_data(dashboard_tickers)
            lens_meta = {"period": period, "interval": interval}
            supply_chain_groups = mod.MARKET_SCOPE_DEFAULT_GROUPS.get(market_scope, [])
            top_movers = mod.build_home_news_top_taiwan_movers(
                daily, intraday, dashboard_tickers, supply_chain_groups
            )
            chain_rankings = mod.build_home_news_supply_chain_rankings(
                supply_chain_groups, lens_meta=lens_meta
            )
            active_etfs = mod.build_home_news_active_etf_spotlight(
                daily, intraday, dashboard_tickers, lens_meta, "General Market"
            )
            lang_zh = True
            q1 = mod._cockpit_compute_q1_verdict(top_movers, chain_rankings, lang_zh)
            payload["cockpit_q1_payload"] = _sanitize_for_json(q1)
            payload["cockpit_q2_payload"] = _sanitize_for_json({
                "chains": chain_rankings[:3],
                "lang_zh": lang_zh,
            })
            payload["cockpit_q3_payload"] = _sanitize_for_json({
                "top_movers": top_movers[:5],
                "chain_rankings": chain_rankings[:3],
                "active_etfs": active_etfs[:3],
                "lang_zh": lang_zh,
            })
            q4 = mod._cockpit_compute_q4_signal(
                daily, intraday, chain_rankings, top_movers, lang_zh
            )
            payload["cockpit_q4_payload"] = _sanitize_for_json(q4)
        log(f"  ✓ Cockpit data built")
    except Exception as exc:
        log(f"  ✗ Cockpit failed: {exc}\n{traceback.format_exc()}")
        payload["fetch_metadata"]["errors"].append(
            f"cockpit: {type(exc).__name__}: {exc}"
        )

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    payload["fetch_metadata"]["duration_sec"] = round(elapsed, 1)
    log(f"  Snapshot built in {elapsed:.1f}s")
    return payload


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert obj into a Supabase-JSON-compatible structure.
    Drops pandas / numpy / datetime / non-serializable types."""
    import math
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        pd = None  # type: ignore
        np = None  # type: ignore

    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if np is not None and isinstance(obj, np.generic):
        try:
            return _sanitize_for_json(obj.item())
        except Exception:
            return None
    if pd is not None:
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            try:
                return _sanitize_for_json(obj.to_dict())
            except Exception:
                return None
    # Last resort: stringify
    try:
        return str(obj)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Supabase upsert
# ---------------------------------------------------------------------------
def upsert_snapshot(payload: dict) -> bool:
    """Upsert one snapshot row into main_dashboard_snapshot.
    The table has UNIQUE(snapshot_date, market_scope), so PostgREST upsert
    via on_conflict matches existing rows on those two columns.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("✗ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set; skipping upsert")
        return False
    url = (
        f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"
        f"?on_conflict=snapshot_date,market_scope"
    )
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
    try:
        with urlopen(req, timeout=30) as resp:
            log(f"  Supabase upsert HTTP {resp.status}")
            return 200 <= resp.status < 300
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        log(f"  ✗ Supabase HTTPError {exc.code}: {body_text[:300]}")
        return False
    except URLError as exc:
        log(f"  ✗ Supabase URLError: {exc.reason}")
        return False
    except Exception as exc:
        log(f"  ✗ Supabase upsert failed: {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    log("=" * 60)
    log("Main Dashboard Prefetch Job — start")
    log("=" * 60)

    if not SUPABASE_URL:
        log("✗ SUPABASE_URL env var missing")
        return 1
    if not SUPABASE_KEY:
        log("✗ SUPABASE_SERVICE_ROLE_KEY env var missing")
        return 1

    try:
        mod = load_dashboard_module()
    except Exception as exc:
        log(f"✗ Failed to load dashboard module: {exc}")
        log(traceback.format_exc())
        return 2

    scopes = ["Taiwan only", "U.S. only"]
    failures = 0
    for scope in scopes:
        try:
            snapshot = build_snapshot_for_scope(mod, scope)
            ok = upsert_snapshot(snapshot)
            if ok:
                log(f"✓ Wrote snapshot for {scope}")
            else:
                failures += 1
                log(f"✗ Upsert failed for {scope}")
        except Exception as exc:
            failures += 1
            log(f"✗ Scope {scope} crashed: {exc}")
            log(traceback.format_exc())

    log("=" * 60)
    if failures == 0:
        log("Main Dashboard Prefetch Job — DONE (all scopes succeeded)")
        return 0
    log(f"Main Dashboard Prefetch Job — DONE WITH {failures} FAILURES")
    return 3


if __name__ == "__main__":
    sys.exit(main())
