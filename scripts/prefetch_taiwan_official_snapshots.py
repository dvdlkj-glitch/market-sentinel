from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import logging
import os
import sys
from pathlib import Path


def load_dashboard_module(dashboard_file: Path):
    spec = importlib.util.spec_from_file_location("market_sentinel_dashboard", dashboard_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load dashboard module from {dashboard_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_cli_logging() -> None:
    os.environ.setdefault("STREAMLIT_SUPPRESS_CONFIG_WARNINGS", "true")
    for logger_name in (
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.caching",
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


NOISY_LOG_PATTERNS = (
    "No runtime found, using MemoryCacheStorageManager",
    "missing ScriptRunContext",
    "Session state does not function when running a script without `streamlit run`",
)


def run_quietly(func):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        result = func()
    return result, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def emit_filtered_output(*chunks: str) -> None:
    for chunk in chunks:
        for raw_line in str(chunk or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(pattern in line for pattern in NOISY_LOG_PATTERNS):
                continue
            print(line, file=sys.stderr)


def parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


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
    parser.add_argument(
        "--scope",
        choices=("all", "macro", "tickers"),
        default="all",
        help="Choose whether to prefetch all snapshots, only the market macro snapshot, or only ticker snapshots.",
    )
    parser.add_argument(
        "--shard-index",
        default="",
        help="Optional zero-based shard index for splitting ticker snapshots across workflow jobs.",
    )
    parser.add_argument(
        "--shard-count",
        default="",
        help="Optional shard count for splitting ticker snapshots across workflow jobs.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force rebuilding snapshots even if a fresh snapshot already exists today.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_cli_logging()
    dashboard_file = Path(args.dashboard_file).resolve()
    if not dashboard_file.exists():
        raise FileNotFoundError(f"Dashboard file not found: {dashboard_file}")

    module, import_stdout, import_stderr = run_quietly(lambda: load_dashboard_module(dashboard_file))
    emit_filtered_output(import_stdout, import_stderr)
    tickers = None
    if str(args.tickers or "").strip():
        tickers = module.parse_taiwan_official_snapshot_tickers(args.tickers)

    result, job_stdout, job_stderr = run_quietly(
        lambda: module.prefetch_taiwan_official_snapshots_job(
            tickers=tickers,
            force_refresh=bool(args.force_refresh),
            shard_index=parse_optional_int(args.shard_index),
            shard_count=parse_optional_int(args.shard_count),
            include_macro=args.scope in {"all", "macro"},
            include_tickers=args.scope in {"all", "tickers"},
        )
    )
    emit_filtered_output(job_stdout, job_stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if str(result.get("status", "") or "") in {"ok", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
