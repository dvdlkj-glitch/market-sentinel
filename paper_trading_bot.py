#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_trading_bot.py — AI 策略實戰 Paper Trading Bot (階段 1, 美股)
================================================================================
用 Dashboard 的訊號做模擬交易, 透過 Alpaca paper trading 下單。
節奏 A: 美股收盤後決策 → 隔天開盤市價成交。一天一輪, 穩定投資型。

每筆買入決策都產出「決策報告」(進場依據/目標價/預估漲幅/出場預測/信心),
寫進 Supabase paper_decisions 表, 前台「🤖 AI 策略實戰」顯示。

階段 1: 純技術法 (不接 Claude)。策略參數見 CONFIG 區, 都是常數, 好調。
階段 2 會接 Claude API 補白話判讀。

執行環境: GitHub Actions 排程 (美股收盤後 ~05:30 Taipei)。
需要的環境變數 (放 GitHub Secrets):
  ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, ALPACA_PAPER(=true)
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

# ============================================================================
# CONFIG — 策略參數 (David 確認用提議值; 都是常數, 想調改這裡就好)
# ============================================================================

STRATEGY_NAME = "momentum_trend_steady"   # 動能趨勢穩健型

# --- 資金 ---
INITIAL_CAPITAL_USD = 30_000.0            # 初始虛擬資金 (David 指定 30K 起步)

# --- 進場條件 ---
MOMENTUM_BUY_THRESHOLD = 60.0             # 動能 score ≥ 60 才考慮買
MA_TREND_DAYS = 50                        # 站上 50 日均線 (波段多頭)
NO_CHASE_5D_GAIN_PCT = 12.0               # 近 5 日漲幅 ≥ 12% 視為追高, 不買

# --- 出場條件 ---
STOP_LOSS_PCT = -8.0                      # 停損 -8%
TAKE_PROFIT_PCT = 18.0                    # 停利 +18%
MOMENTUM_EXIT_THRESHOLD = 35.0            # 動能 score ≤ 35 視為轉空, 賣出

# --- 部位管理 (穩健分散) ---
MAX_POSITION_PCT = 20.0                   # 一般股單檔上限 = 組合 20%
MAX_POSITION_PCT_SPACEX_PROXY = 10.0      # SpaceX 代理標的上限砍半 = 10%
BUY_CASH_FRACTION = 0.20                  # 一次買入用可用現金的 1/5
MAX_HOLDINGS = 8                          # 最多同時持有 8 檔
MIN_CASH_RESERVE_PCT = 20.0               # 永遠保留 ≥ 20% 現金

# --- 目標價推估 (技術法) ---
ATR_TARGET_MULTIPLE = 2.0                 # 目標價 = 進場價 × (1 + 2×ATR%)
TARGET_LOOKBACK_DAYS = 60                 # 近 60 日高點

# ============================================================================
# 選股池 (主題式 — David 指定: 記憶體 / SpaceX 代理 / 太空 ETF / 大盤 ETF / Mag7)
# ============================================================================

UNIVERSE_MEMORY = ["MU"]                                  # 記憶體
UNIVERSE_SPACEX_PROXY = ["XOVR", "NASA", "RONB", "SATS", "DXYZ"]  # SpaceX 代理 (保守部位)
UNIVERSE_SPACE_ETF = ["UFO", "ARKX", "ROKT"]              # 太空 ETF
UNIVERSE_BROAD_ETF = ["SPY", "QQQ"]                       # 大盤 ETF
UNIVERSE_MAG7 = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]

UNIVERSE = (
    UNIVERSE_MEMORY + UNIVERSE_SPACEX_PROXY + UNIVERSE_SPACE_ETF
    + UNIVERSE_BROAD_ETF + UNIVERSE_MAG7
)
SPACEX_PROXY_SET = set(UNIVERSE_SPACEX_PROXY)

# ============================================================================
# 決策報告資料結構
# ============================================================================

@dataclass
class DecisionReport:
    """一筆決策報告 — 對應 Supabase paper_decisions 表。"""
    decision_date: str
    ticker: str
    action: str                          # buy / sell / hold
    market: str = "US"
    strategy: str = STRATEGY_NAME
    entry_basis: str = ""                # 進場依據: 觸發了哪些 dashboard 訊號
    target_price: Optional[float] = None # 目標價
    est_gain_pct: Optional[float] = None # 預估漲幅 %
    exit_plan: str = ""                  # 出場預測
    confidence: str = "mid"              # low / mid / high
    decision_price: Optional[float] = None
    claude_note: str = ""                # 階段2
    is_spacex_proxy: bool = False
    alpaca_order_id: str = ""
    signals_json: dict = field(default_factory=dict)

    def to_supabase_row(self) -> dict:
        d = asdict(self)
        return d


# ============================================================================
# Alpaca 介接
# ============================================================================

def _get_alpaca_clients():
    """建立 Alpaca trading + data client (paper)。金鑰從環境變數讀。"""
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient

    key = os.environ.get("ALPACA_API_KEY_ID", "")
    secret = os.environ.get("ALPACA_API_SECRET_KEY", "")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() != "false"
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY 未設定 (GitHub Secrets)")
    trading = TradingClient(key, secret, paper=paper)
    data = StockHistoricalDataClient(key, secret)
    return trading, data


def _get_account_snapshot(trading) -> dict:
    """查帳戶: 現金、買賣力、總資產。"""
    acct = trading.get_account()
    return {
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "portfolio_value": float(acct.portfolio_value),
        "equity": float(acct.equity),
    }


def _get_positions(trading) -> dict:
    """查目前持倉, 回傳 {ticker: {qty, avg_entry, current_price, unrealized_pnl}}。"""
    out = {}
    try:
        for p in trading.get_all_positions():
            out[p.symbol] = {
                "qty": float(p.qty),
                "avg_entry": float(p.avg_entry_price),
                "current_price": float(p.current_price or 0),
                "unrealized_pnl": float(p.unrealized_pl or 0),
                "market_value": float(p.market_value or 0),
            }
    except Exception:
        pass
    return out


# ============================================================================
# 訊號取得 (階段1: 從歷史日線自己算技術訊號; 之後可接 dashboard 訊號 API)
# ============================================================================

def _fetch_daily_bars(data, tickers: list[str], days: int = 90) -> dict:
    """抓近 N 日日線, 回傳 {ticker: list[bar]}。Alpaca 免費 IEX 資料。"""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from datetime import timedelta

    start = datetime.now(timezone.utc) - timedelta(days=days + 20)
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=start,
    )
    bars = data.get_stock_bars(req)
    out: dict[str, list] = {}
    try:
        for sym in tickers:
            sym_bars = bars.data.get(sym, []) if hasattr(bars, "data") else []
            out[sym] = sym_bars
    except Exception:
        pass
    return out


def _compute_signals(bars: list) -> dict:
    """從日線算技術訊號: 收盤、50日均線、近5日漲幅、ATR%、60日高點、簡易動能分數。

    階段1 用「自算的技術動能分數」近似 dashboard 的明日動能 score。
    階段3 可改接 dashboard 真正的 build_tomorrow_momentum_pulse_us。
    """
    if not bars or len(bars) < MA_TREND_DAYS + 5:
        return {}
    closes = [float(b.close) for b in bars]
    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    last = closes[-1]

    ma = sum(closes[-MA_TREND_DAYS:]) / MA_TREND_DAYS
    gain_5d = (last / closes[-6] - 1.0) * 100.0 if len(closes) >= 6 else 0.0
    hi_60 = max(highs[-TARGET_LOOKBACK_DAYS:]) if len(highs) >= TARGET_LOOKBACK_DAYS else max(highs)

    # ATR% (近14日真實波幅均值 / 現價)
    trs = []
    for i in range(-14, 0):
        if abs(i) < len(closes):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
    atr_pct = (sum(trs) / len(trs) / last * 100.0) if trs and last else 2.0

    # 簡易動能分數 (0-100): 綜合「站上均線幅度 + 短期趨勢」, 近似 dashboard 動能
    above_ma_pct = (last / ma - 1.0) * 100.0 if ma else 0.0
    trend_10d = (last / closes[-11] - 1.0) * 100.0 if len(closes) >= 11 else 0.0
    raw = 50.0 + above_ma_pct * 3.0 + trend_10d * 1.5
    momentum_score = max(0.0, min(100.0, raw))

    return {
        "close": last,
        "ma50": ma,
        "above_ma": last > ma,
        "gain_5d_pct": gain_5d,
        "high_60d": hi_60,
        "atr_pct": atr_pct,
        "momentum_score": momentum_score,
    }


# ============================================================================
# 策略決策邏輯
# ============================================================================

def _decide_buy(ticker: str, sig: dict, today: str) -> Optional[DecisionReport]:
    """套進場條件, 符合則產出買入決策報告 (含目標價/出場/信心)。"""
    if not sig:
        return None

    reasons = []
    passed = 0

    # 條件1: 趨勢向上 (站上 50 日均線)
    cond_trend = sig["above_ma"]
    if cond_trend:
        passed += 1
        reasons.append(f"站上 {MA_TREND_DAYS} 日均線 (收盤 {sig['close']:.2f} > MA {sig['ma50']:.2f})")

    # 條件2: 動能偏多
    cond_mom = sig["momentum_score"] >= MOMENTUM_BUY_THRESHOLD
    if cond_mom:
        passed += 1
        reasons.append(f"動能分數 {sig['momentum_score']:.0f}/100 ≥ {MOMENTUM_BUY_THRESHOLD:.0f} (偏多)")

    # 條件3: 不追高
    cond_nochase = sig["gain_5d_pct"] < NO_CHASE_5D_GAIN_PCT
    if cond_nochase:
        passed += 1
        reasons.append(f"近5日漲幅 {sig['gain_5d_pct']:+.1f}% < {NO_CHASE_5D_GAIN_PCT:.0f}% (未追高)")

    # 三個條件都要滿足才買 (穩健型)
    if not (cond_trend and cond_mom and cond_nochase):
        return None

    # --- 目標價推估 (技術法): 取「60日高點」與「進場價×(1+2ATR%)」較低者 (保守) ---
    entry = sig["close"]
    target_atr = entry * (1.0 + ATR_TARGET_MULTIPLE * sig["atr_pct"] / 100.0)
    target = min(sig["high_60d"], target_atr) if sig["high_60d"] > entry else target_atr
    est_gain = (target / entry - 1.0) * 100.0

    # --- 信心: 由通過條件數 + 動能強度 ---
    if sig["momentum_score"] >= 75 and passed == 3:
        conf = "high"
    elif passed == 3:
        conf = "mid"
    else:
        conf = "low"

    is_proxy = ticker in SPACEX_PROXY_SET
    proxy_note = " ⚠️ SpaceX 代理標的(含溢價/SPV 結構風險, 非直接持有 SpaceX), 部位減半。" if is_proxy else ""

    stop_price = entry * (1.0 + STOP_LOSS_PCT / 100.0)
    tp_price = entry * (1.0 + TAKE_PROFIT_PCT / 100.0)
    exit_plan = (
        f"停利 +{TAKE_PROFIT_PCT:.0f}% (約 {tp_price:.2f}) 或達目標價 {target:.2f}; "
        f"停損 {STOP_LOSS_PCT:.0f}% (約 {stop_price:.2f}); "
        f"或跌破 {MA_TREND_DAYS} 日均線 / 動能 ≤ {MOMENTUM_EXIT_THRESHOLD:.0f} 轉空出場。"
    )

    return DecisionReport(
        decision_date=today,
        ticker=ticker,
        action="buy",
        entry_basis="; ".join(reasons) + proxy_note,
        target_price=round(target, 2),
        est_gain_pct=round(est_gain, 1),
        exit_plan=exit_plan,
        confidence=conf,
        decision_price=round(entry, 2),
        is_spacex_proxy=is_proxy,
        signals_json={k: (round(v, 3) if isinstance(v, float) else v) for k, v in sig.items()},
    )


def _decide_sell(ticker: str, sig: dict, pos: dict, today: str) -> Optional[DecisionReport]:
    """套出場條件, 符合則產出賣出決策報告。"""
    if not sig or not pos:
        return None
    entry = pos["avg_entry"]
    cur = sig["close"]
    pnl_pct = (cur / entry - 1.0) * 100.0 if entry else 0.0

    reason = None
    if pnl_pct <= STOP_LOSS_PCT:
        reason = f"觸發停損: 損益 {pnl_pct:+.1f}% ≤ {STOP_LOSS_PCT:.0f}%"
    elif pnl_pct >= TAKE_PROFIT_PCT:
        reason = f"觸發停利: 損益 {pnl_pct:+.1f}% ≥ +{TAKE_PROFIT_PCT:.0f}%"
    elif not sig["above_ma"]:
        reason = f"趨勢轉空: 跌破 {MA_TREND_DAYS} 日均線"
    elif sig["momentum_score"] <= MOMENTUM_EXIT_THRESHOLD:
        reason = f"動能轉弱: 分數 {sig['momentum_score']:.0f} ≤ {MOMENTUM_EXIT_THRESHOLD:.0f}"

    if not reason:
        return None

    return DecisionReport(
        decision_date=today,
        ticker=ticker,
        action="sell",
        entry_basis=reason,
        exit_plan="市價賣出平倉。",
        confidence="high",
        decision_price=round(cur, 2),
        is_spacex_proxy=(ticker in SPACEX_PROXY_SET),
        signals_json={"pnl_pct": round(pnl_pct, 2), **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in sig.items()}},
    )


# ============================================================================
# 下單 (Alpaca) + 記錄決策報告 (Supabase)
# ============================================================================

def _submit_order(trading, ticker: str, side: str, notional: float = None, qty: float = None) -> str:
    """送出市價單。買用 notional (金額, 支援碎股), 賣用 qty。回傳 order id。"""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    kwargs = dict(symbol=ticker, side=order_side, time_in_force=TimeInForce.DAY)
    if notional is not None:
        kwargs["notional"] = round(notional, 2)
    if qty is not None:
        kwargs["qty"] = qty
    req = MarketOrderRequest(**kwargs)
    order = trading.submit_order(req)
    return str(order.id)


def _write_decision_to_supabase(report: DecisionReport) -> bool:
    """把決策報告寫進 Supabase paper_decisions 表 (用 service role key)。"""
    import urllib.request
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("  [warn] Supabase 未設定, 跳過寫入決策報告")
        return False
    endpoint = f"{url}/rest/v1/paper_decisions"
    row = report.to_supabase_row()
    row["signals_json"] = row.get("signals_json") or {}
    data = json.dumps(row).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data, method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print(f"  [warn] 寫入決策報告失敗: {type(e).__name__}: {e}")
        return False


# ============================================================================
# 主流程
# ============================================================================

def run_bot():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"=== Paper Trading Bot ({STRATEGY_NAME}) — {today} ===")
    print(f"選股池 ({len(UNIVERSE)} 檔): {', '.join(UNIVERSE)}")

    trading, data = _get_alpaca_clients()

    # v1.1: 休市偵測 — 用 Alpaca get_clock() 查市場是否開盤 (含假期/週末)。
    # 美股假期 (如 Memorial Day) 或週末 bot 不該動作, 避免無意義掛單與決策報告。
    # 節奏 A 是「收盤後決策、隔天開盤成交」, 所以邏輯: 若「下一個開盤日」不是
    # 緊接著的交易日 (即今天非交易日), 或當下市場已收盤且非交易日, 則跳過。
    # 最穩健: 直接看 get_clock 的 is_open + 今天是否在交易日曆。
    try:
        clock = trading.get_clock()
        # clock.is_open: 當下是否盤中; next_open/next_close 是下一個開關盤時間。
        # bot 在收盤後跑, is_open 通常 False (正常)。要分辨「收盤後」vs「整天休市」:
        # 用 trading calendar 查今天是否為交易日。
        is_trading_day = True
        try:
            from alpaca.trading.requests import GetCalendarRequest
            from datetime import date as _date
            today_d = datetime.now(timezone.utc).date()
            cal = trading.get_calendar(filters=GetCalendarRequest(start=today_d, end=today_d))
            # cal 為空 list = 今天不是交易日 (週末/假期)
            is_trading_day = bool(cal)
        except Exception as _ce:
            print(f"  [warn] 交易日曆查詢失敗, 改用 clock 判斷: {type(_ce).__name__}: {_ce}")
            # fallback: 若 clock 顯示 next_open 距今超過 ~20 小時, 多半是長假/週末
            is_trading_day = True  # 查不到就保守當交易日 (Alpaca 仍會擋休市成交)

        if not is_trading_day:
            print("今天美股休市 (假期/週末) — bot 不動作, 跳過本次決策。")
            return
    except Exception as _e:
        print(f"  [warn] 休市偵測失敗 ({type(_e).__name__}: {_e}), 繼續執行 (Alpaca 仍會擋休市成交)")

    acct = _get_account_snapshot(trading)
    positions = _get_positions(trading)
    print(f"帳戶: 總資產 ${acct['portfolio_value']:,.0f} / 現金 ${acct['cash']:,.0f} / 持倉 {len(positions)} 檔")

    bars_map = _fetch_daily_bars(data, UNIVERSE, days=90)

    decisions: list[DecisionReport] = []

    # --- 1) 先檢查現有持倉的「出場」 ---
    for tk, pos in positions.items():
        sig = _compute_signals(bars_map.get(tk, []))
        sell = _decide_sell(tk, sig, pos, today)
        if sell:
            decisions.append(sell)

    # --- 2) 再檢查選股池的「進場」(排除已持有、已達上限) ---
    held = set(positions.keys())
    room = MAX_HOLDINGS - len(held)
    cash_reserve_floor = acct["portfolio_value"] * MIN_CASH_RESERVE_PCT / 100.0
    available_cash = max(0.0, acct["cash"] - cash_reserve_floor)

    if room > 0 and available_cash > 100:
        buy_candidates = []
        for tk in UNIVERSE:
            if tk in held:
                continue
            sig = _compute_signals(bars_map.get(tk, []))
            buy = _decide_buy(tk, sig, today)
            if buy:
                buy_candidates.append((buy, sig["momentum_score"]))
        # 動能強的優先
        buy_candidates.sort(key=lambda x: x[1], reverse=True)
        for buy, _score in buy_candidates[:room]:
            decisions.append(buy)

    # --- 3) 執行決策: 下單 + 記錄報告 ---
    if not decisions:
        print("今日無符合條件的買賣 (穩健型不強迫交易)。")
        # 仍記一筆 hold 報告供前台顯示「今天觀望」
        hold = DecisionReport(decision_date=today, ticker="—", action="hold",
                              entry_basis="今日選股池無標的同時滿足趨勢/動能/不追高三條件; 維持觀望。",
                              confidence="mid")
        _write_decision_to_supabase(hold)
        return

    for d in decisions:
        try:
            if d.action == "buy":
                pct_cap = MAX_POSITION_PCT_SPACEX_PROXY if d.is_spacex_proxy else MAX_POSITION_PCT
                notional = min(available_cash * BUY_CASH_FRACTION,
                               acct["portfolio_value"] * pct_cap / 100.0)
                notional = max(0.0, round(notional, 2))
                if notional < 1:
                    print(f"  [skip] {d.ticker}: 可用資金不足")
                    continue
                oid = _submit_order(trading, d.ticker, "buy", notional=notional)
                d.alpaca_order_id = oid
                available_cash -= notional
                print(f"  [BUY] {d.ticker} ${notional:,.0f} | {d.confidence} | 目標 {d.target_price} (+{d.est_gain_pct}%) | order={oid}")
            elif d.action == "sell":
                pos = positions.get(d.ticker)
                if pos:
                    oid = _submit_order(trading, d.ticker, "sell", qty=pos["qty"])
                    d.alpaca_order_id = oid
                    print(f"  [SELL] {d.ticker} x{pos['qty']} | {d.entry_basis} | order={oid}")
            _write_decision_to_supabase(d)
        except Exception as e:
            print(f"  [error] {d.ticker} {d.action} 失敗: {type(e).__name__}: {e}")

    print(f"完成: 共 {len(decisions)} 筆決策。")


if __name__ == "__main__":
    try:
        run_bot()
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
