#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_us_premarket.py — 美股開盤前簡報 Telegram 推播
================================================================================
台灣時間每天 21:00 (美股開盤前約 1 小時) 推送一則盤前簡報, 內容:
  1. 大盤前夜收盤方向 (S&P500 / Nasdaq / 道瓊 / VIX)
  2. Paper Bot 選股池盤前動向 (記憶體/SpaceX代理/太空ETF/Mag7 重點標的)
  3. Paper Bot 持倉今日焦點 (接近停利/停損的提醒, 若有持倉)

設計原則: 穩定優先 — 主要用 yfinance 指數/個股 (不依賴 prefetch/Supabase),
便於測試推播本身穩定性。Alpaca 持倉為加分項, 讀取失敗不影響主簡報。

環境變數 (GitHub Secrets):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  (選用) ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY  — 有才顯示持倉焦點
================================================================================
"""

from __future__ import annotations
import os
import sys
import json
import traceback
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

TPE = timezone(timedelta(hours=8))

# Paper Bot 選股池 (與 paper_trading_bot.py 一致) — 盤前掃這些
WATCH_MEMORY = ["MU"]
WATCH_SPACEX = ["XOVR", "NASA", "RONB", "SATS", "DXYZ"]
WATCH_SPACE_ETF = ["UFO", "ARKX", "ROKT"]
WATCH_MAG7 = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
# 盤前簡報只挑代表性幾檔, 避免訊息太長
WATCH_HIGHLIGHT = ["NVDA", "MU", "AAPL", "MSFT", "TSLA", "XOVR", "ARKX"]

STOP_LOSS_PCT = -8.0
TAKE_PROFIT_PCT = 18.0


def _fetch_closes(ticker: str, days: int = 12) -> list[float]:
    try:
        import yfinance as yf
        df = yf.download(ticker, period=f"{days}d", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []
        return [float(c) for c in df["Close"].dropna().values.flatten().tolist()]
    except Exception as e:
        print(f"  [warn] {ticker}: {type(e).__name__}: {e}")
        return []


def _pct_chg(closes: list[float]) -> float | None:
    """最近一日漲跌幅 %。"""
    if len(closes) < 2:
        return None
    return (closes[-1] / closes[-2] - 1.0) * 100.0


def _arrow(pct: float | None) -> str:
    if pct is None:
        return "—"
    return "🟢" if pct > 0 else ("🔴" if pct < 0 else "⚪")


def _build_index_section() -> list[str]:
    lines = ["📈 *大盤前夜方向*"]
    idx = [("S&P500", "^GSPC"), ("Nasdaq", "^IXIC"), ("道瓊", "^DJI"), ("VIX", "^VIX")]
    for name, tk in idx:
        closes = _fetch_closes(tk)
        pct = _pct_chg(closes)
        if pct is None:
            lines.append(f"• {name}: 資料暫缺")
            continue
        last = closes[-1]
        if name == "VIX":
            mood = "高波動⚠️" if last >= 20 else ("溫和" if last >= 14 else "平靜")
            lines.append(f"• {name}: {last:.1f} ({mood})")
        else:
            lines.append(f"• {name}: {_arrow(pct)} {pct:+.2f}%")
    return lines


def _build_watchlist_section() -> list[str]:
    lines = ["", "🎯 *選股池盤前動向*"]
    rows = []
    for tk in WATCH_HIGHLIGHT:
        closes = _fetch_closes(tk)
        pct = _pct_chg(closes)
        if pct is not None:
            rows.append((tk, pct, closes[-1]))
    if not rows:
        lines.append("• 資料暫缺")
        return lines
    rows.sort(key=lambda x: x[1], reverse=True)
    for tk, pct, last in rows:
        tag = " ⚠️代理" if tk in WATCH_SPACEX else ""
        lines.append(f"• {_arrow(pct)} {tk}{tag}: {pct:+.2f}% (${last:.2f})")
    return lines


def _build_holdings_focus() -> list[str]:
    """Alpaca 持倉今日焦點 (接近停利/停損)。讀取失敗回 []。"""
    key = os.environ.get("ALPACA_API_KEY_ID", "")
    secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
    if not key or not secret:
        return []
    try:
        from alpaca.trading.client import TradingClient
        paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
        client = TradingClient(key, secret, paper=paper)
        positions = client.get_all_positions()
    except Exception as e:
        print(f"  [warn] Alpaca: {type(e).__name__}: {e}")
        return []
    if not positions:
        return []
    lines = ["", "💼 *持倉今日焦點*"]
    any_focus = False
    for p in positions:
        try:
            entry = float(p.avg_entry_price)
            cur = float(p.current_price or 0)
            pnl_pct = (cur / entry - 1.0) * 100.0 if entry else 0.0
            near = ""
            if pnl_pct <= STOP_LOSS_PCT + 2:
                near = "⚠️ 接近停損"
            elif pnl_pct >= TAKE_PROFIT_PCT - 3:
                near = "🎯 接近停利"
            if near:
                any_focus = True
                lines.append(f"• {p.symbol}: {pnl_pct:+.1f}% {near}")
        except Exception:
            continue
    if not any_focus:
        lines.append(f"• {len(positions)} 檔持倉, 均在正常區間")
    return lines


def _build_report() -> str:
    now = datetime.now(TPE)
    lines = [f"🌅 *美股盤前簡報* — {now.strftime('%m/%d %H:%M')} (台北)", ""]
    lines += _build_index_section()
    lines += _build_watchlist_section()
    lines += _build_holdings_focus()
    lines += ["", "※ 盤前資訊僅供參考, 非投資建議"]
    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[error] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 未設定")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            print(f"  Telegram 推送: {'✓ 成功' if ok else '✗ HTTP ' + str(resp.status)}")
            return ok
    except Exception as e:
        print(f"  [error] Telegram: {type(e).__name__}: {e}")
        return False


def main():
    print(f"=== 美股盤前簡報 — {datetime.now(TPE).strftime('%Y-%m-%d %H:%M')} ===")
    report = _build_report()
    print("--- 內容 ---\n" + report + "\n------------")
    _send_telegram(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
