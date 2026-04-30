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
        description="Prefetch supply-chain dashboard snapshots into Supabase/local cache."
    )
    parser.add_argument(
        "--dashboard-file",
        default=str(Path(__file__).resolve().parents[1] / "stock_dashboard_web_enhanced_v5_live_news.py"),
        help="Path to the dashboard Python file.",
    )
    parser.add_argument(
        "--keys",
        default="",
        help="Optional comma-separated supply-chain config keys. Falls back to SUPPLY_CHAIN_SNAPSHOT_KEYS env.",
    )
    parser.add_argument("--period", default="", help="Optional market period override, for example 1y.")
    parser.add_argument("--interval", default="", help="Optional market interval override, for example 1d.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dashboard_file = Path(args.dashboard_file).resolve()
    if not dashboard_file.exists():
        raise FileNotFoundError(f"Dashboard file not found: {dashboard_file}")

    module = load_dashboard_module(dashboard_file)
    config_keys = None
    if str(args.keys or "").strip():
        config_keys = module.parse_supply_chain_snapshot_keys(args.keys)

    result = module.prefetch_supply_chain_focus_snapshots_job(
        config_keys=config_keys,
        period=str(args.period or "").strip() or None,
        interval=str(args.interval or "").strip() or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if str(result.get("status", "") or "") in {"ok", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
