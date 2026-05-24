#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_daily_report.py — 每日「推估明日開盤方向」Telegram 推送
================================================================================
台灣時間每天 14:30 (台股收盤後), 推估:
  - 台股「明日開盤」方向 (用加權指數 ^TWII 日線算動能)
  - 美股「今晚即將開盤」方向 (用 S&P500 ^GSPC + Nasdaq ^IXIC 日線, 前一交易日收盤)
推送一份中文 Summary Report 到 Telegram Chat ID。

獨立運作: 自己用 yfinance 日線算方向, 不依賴 dashboard prefetch / Supabase。
節奏與 paper_trading_bot 一致 (GitHub Actions 排程)。

環境變數 (GitHub Secrets):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
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

# --- 方向判斷門檻 (動能分數 0-100; 與 paper bot 同邏輯) ---
BULLISH_THRESHOLD = 60.0   # ≥ 偏多
BEARISH_THRESHOLD = 40.0   # ≤ 偏空 (中間為中性)

# 台北時區
TPE = timezone(timedelta(hours=8))


def _fetch_daily_closes(ticker: str, days: int = 70) -> list[float]:
    """用 yfinance 抓近 N 日收盤價 list (舊→新)。失敗回 []。"""
    try:
        import yfinance as yf
        df = yf.download(ticker, period=f"{days}d", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []
        closes = df["Close"].dropna().values.flatten().tolist()
        return [float(c) for c in closes]
    except Exception as e:
        print(f"  [warn] 抓 {ticker} 失敗: {type(e).__name__}: {e}")
        return []


def _momentum_score(closes: list[float]) -> dict:
    """從收盤價算簡易動能分數 (0-100) + 方向 + 一句理由。
    邏輯與 paper bot _compute_signals 的 momentum_score 一致:
      站上均線幅度 + 短期趨勢。"""
    if not closes or len(closes) < 25:
        return {}
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20.0
    ma_days = min(50, len(closes))
    ma50 = sum(closes[-ma_days:]) / ma_days
    above_ma20 = (last / ma20 - 1.0) * 100.0 if ma20 else 0.0
    trend_10d = (last / closes[-11] - 1.0) * 100.0 if len(closes) >= 11 else 0.0
    raw = 50.0 + above_ma20 * 3.0 + trend_10d * 1.5
    score = max(0.0, min(100.0, raw))

    if score >= BULLISH_THRESHOLD:
        direction, emoji = "偏多", "📈"
    elif score <= BEARISH_THRESHOLD:
        direction, emoji = "偏空", "📉"
    else:
        direction, emoji = "中性", "➡️"

    # 一句理由
    ma_state = "站上" if last > ma20 else "跌破"
    reason = f"{ma_state} 20 日均線, 近10日趨勢 {trend_10d:+.1f}%, 動能分數 {score:.0f}/100"
    return {
        "score": score, "direction": direction, "emoji": emoji,
        "reason": reason, "last": last, "ma20": ma20,
    }


def _build_bot_summary() -> list[str]:
    """讀 Alpaca 帳戶/持倉 + Supabase 今日決策, 組成中等詳細度的 bot 摘要 (list of lines)。
    任何失敗回 [] (該段就不出現, 不影響方向推估主報告)。"""
    lines: list[str] = []
    alpaca_key = os.environ.get("ALPACA_API_KEY_ID", "")
    alpaca_secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
    if not alpaca_key or not alpaca_secret:
        return []
    # --- Alpaca 帳戶 + 持倉 ---
    try:
        from alpaca.trading.client import TradingClient
        paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
        client = TradingClient(alpaca_key, alpaca_secret, paper=paper)
        acct = client.get_account()
        pv = float(getattr(acct, "portfolio_value", 0) or 0)
        init = 30000.0  # 初始資金 (與 bot/前台一致)
        ret_pct = (pv / init - 1.0) * 100.0 if init else 0.0
        try:
            pos_count = len(client.get_all_positions())
        except Exception:
            pos_count = 0
        ret_emoji = "📈" if ret_pct > 0 else ("📉" if ret_pct < 0 else "➡️")
        lines.append("🤖 *AI 策略實戰* (Paper, 30K)")
        lines.append(f"總資產: ${pv:,.0f} ({ret_pct:+.2f}% {ret_emoji}) | 持倉 {pos_count} 檔")
    except Exception as e:
        print(f"  [warn] Alpaca 讀取失敗: {type(e).__name__}: {e}")
        return []
    # --- Supabase 今日決策 (最新一個 decision_date) ---
    try:
        sb_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        sb_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
                  or os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""))
        if sb_url and sb_key:
            sel = urllib.parse.quote("decision_date,ticker,action,est_gain_pct,confidence,signals_json,is_spacex_proxy")
            path = (f"{sb_url}/rest/v1/paper_decisions"
                    f"?select={sel}&order=created_at.desc&limit=20")
            req = urllib.request.Request(path, headers={
                "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            if isinstance(rows, list) and rows:
                latest = rows[0].get("decision_date")
                today_rows = [r for r in rows if r.get("decision_date") == latest]
                buys = [r for r in today_rows if r.get("action") == "buy"]
                sells = [r for r in today_rows if r.get("action") == "sell"]
                lines.append("")
                lines.append("今日動作:")
                if not buys and not sells:
                    lines.append("• 觀望 (無符合條件標的)")
                for r in buys[:6]:
                    tk = r.get("ticker", "?")
                    eg = r.get("est_gain_pct")
                    sig = r.get("signals_json") or {}
                    mom = ""
                    if isinstance(sig, dict) and sig.get("momentum_score") is not None:
                        try:
                            mom = f"動能{float(sig['momentum_score']):.0f}, "
                        except Exception:
                            mom = ""
                    proxy = " ⚠️代理" if r.get("is_spacex_proxy") else ""
                    eg_txt = f"目標{float(eg):+.0f}%" if eg not in (None, "") else ""
                    lines.append(f"• 買入 {tk}{proxy} — {mom}{eg_txt}".rstrip(" —,"))
                for r in sells[:4]:
                    lines.append(f"• 賣出 {r.get('ticker','?')}")
    except Exception as e:
        print(f"  [warn] Supabase 決策讀取失敗: {type(e).__name__}: {e}")
        # 帳戶那段還是保留, 只是少了今日動作清單
    return lines


def _build_report() -> str:
    now = datetime.now(TPE)
    date_str = now.strftime("%Y/%m/%d %H:%M")

    lines = [f"📊 *每日開盤方向推估* — {date_str}", ""]

    # === 台股 (推明日開盤) ===
    lines.append("🇹🇼 *台股* (推估明日開盤)")
    tw = _momentum_score(_fetch_daily_closes("^TWII"))
    if tw:
        lines.append(f"方向: {tw['direction']} {tw['emoji']}")
        lines.append(f"依據: 加權指數 {tw['reason']}")
    else:
        lines.append("方向: 資料不足, 暫無法推估")
    lines.append("")

    # === 美股 (推今晚即將開盤) ===
    lines.append("🇺🇸 *美股* (推估今晚即將開盤)")
    sp = _momentum_score(_fetch_daily_closes("^GSPC"))
    nq = _momentum_score(_fetch_daily_closes("^IXIC"))
    if sp:
        lines.append(f"S&P500: {sp['direction']} {sp['emoji']} ({sp['reason']})")
    if nq:
        lines.append(f"Nasdaq: {nq['direction']} {nq['emoji']} ({nq['reason']})")
    if not sp and not nq:
        lines.append("方向: 資料不足, 暫無法推估")
    lines.append("")

    # === Paper Trading Bot 摘要 (美股, 接在方向推估後) ===
    _bot_lines = _build_bot_summary()
    if _bot_lines:
        lines.extend(_bot_lines)
        lines.append("")

    lines.append("※ 推估僅供參考, 非投資建議")
    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[error] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 未設定")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            print(f"  Telegram 推送: {'✓ 成功' if ok else '✗ 失敗 (HTTP ' + str(resp.status) + ')'}")
            return ok
    except Exception as e:
        print(f"  [error] Telegram 推送失敗: {type(e).__name__}: {e}")
        return False


def main():
    print(f"=== Telegram 每日開盤方向推估 — {datetime.now(TPE).strftime('%Y-%m-%d %H:%M')} ===")
    report = _build_report()
    print("--- 報告內容 ---")
    print(report)
    print("----------------")
    _send_telegram(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
