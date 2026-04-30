from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_dashboard_module(dashboard_file: Path):
    spec = importlib.util.spec_from_file_location("market_sentinel_dashboard", dashboard_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load dashboard module from {dashboard_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prefetch Taiwan official dashboard snapshots into Supabase/local cache."
    )
    parser.add_argument(
        "--dashboard-file",
        default=str(Path(__file__).resolve().parents[1] / "stock_dashboard_web_enhanced_v5_live_news.py"),
        help="Path to the dashboard Python file.",
    )
    parser.add_argument(
        "--tickers",
        default="",
        help="Optional comma-separated Taiwan tickers. Falls back to TAIWAN_OFFICIAL_SNAPSHOT_TICKERS env.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dashboard_file = Path(args.dashboard_file).resolve()
    if not dashboard_file.exists():
        raise FileNotFoundError(f"Dashboard file not found: {dashboard_file}")

    module = load_dashboard_module(dashboard_file)
    tickers = None
    if str(args.tickers or "").strip():
        tickers = module.parse_taiwan_official_snapshot_tickers(args.tickers)

    result = module.prefetch_taiwan_official_snapshots_job(tickers=tickers, force_refresh=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if str(result.get("status", "") or "") in {"ok", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
