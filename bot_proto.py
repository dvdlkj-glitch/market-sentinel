"""Prototype the 🤖 AI 策略實戰 front-end block visual."""
from html import escape

_BOT_CSS = """
<style>
.bot-shell {
    background: radial-gradient(120% 80% at 100% 0%, rgba(56,48,90,.35), transparent 60%),
        linear-gradient(180deg, rgba(20,26,45,.94), rgba(12,16,28,.96));
    border: 1px solid rgba(110,96,160,.32); border-radius: 16px; padding: 18px 20px; margin: 0 0 14px 0;
    color: #e9ecf3; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
}
.bot-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:14px; }
.bot-title { font-size:18px; font-weight:800; color:#f6f8fc; display:flex; align-items:center; gap:8px; }
.bot-sub { font-size:12.5px; color:#8b95ad; margin-top:3px; }
.bot-perf { display:flex; gap:18px; flex-wrap:wrap; }
.bot-perf-item { text-align:right; }
.bot-perf-val { font-size:20px; font-weight:800; font-variant-numeric:tabular-nums; }
.bot-perf-lbl { font-size:11px; color:#8b95ad; }
.bot-up { color:#6fd99a; } .bot-down { color:#f08894; } .bot-flat { color:#e6c35f; }
.bot-section-title { font-size:13px; font-weight:700; color:#aeb6ca; margin:14px 0 8px; letter-spacing:.3px; }
.bot-pos-table { width:100%; border-collapse:collapse; font-size:13px; }
.bot-pos-table th { text-align:left; color:#8b95ad; font-weight:600; padding:6px 8px; border-bottom:1px solid rgba(96,110,145,.2); font-size:11.5px; }
.bot-pos-table td { padding:7px 8px; border-bottom:1px solid rgba(96,110,145,.1); font-variant-numeric:tabular-nums; }
.bot-tk { font-weight:700; color:#f6f8fc; }
.bot-decision { background:rgba(40,48,72,.4); border-radius:10px; padding:12px 14px; margin-bottom:8px; border-left:3px solid rgba(110,96,160,.6); }
.bot-decision-buy { border-left-color:#6fd99a; }
.bot-decision-sell { border-left-color:#f08894; }
.bot-decision-hold { border-left-color:#e6c35f; }
.bot-d-head { display:flex; align-items:center; gap:8px; margin-bottom:5px; }
.bot-d-action { font-size:13px; font-weight:800; padding:1px 9px; border-radius:5px; }
.bot-act-buy { background:rgba(76,208,168,.18); color:#8be8b1; }
.bot-act-sell { background:rgba(217,102,112,.18); color:#f4a3aa; }
.bot-act-hold { background:rgba(230,195,95,.16); color:#f4d68a; }
.bot-d-tk { font-size:15px; font-weight:800; color:#f6f8fc; }
.bot-d-conf { font-size:11px; color:#8b95ad; margin-left:auto; }
.bot-d-row { font-size:12.5px; color:#c4ccdc; line-height:1.7; }
.bot-d-row b { color:#dfe4ef; }
.bot-disclaimer { font-size:11px; color:#6b7488; margin-top:12px; font-style:italic; border-top:1px solid rgba(96,110,145,.15); padding-top:10px; }
</style>
"""


def render_bot_block(account, positions, decisions, lang_zh=True):
    pv = account.get("portfolio_value", 0)
    init = account.get("initial", 30000)
    total_ret = (pv / init - 1) * 100 if init else 0
    ret_cls = "bot-up" if total_ret > 0 else ("bot-down" if total_ret < 0 else "bot-flat")

    P = ['<div class="bot-shell">']
    # Head
    P.append('<div class="bot-head"><div>')
    P.append(f'<div class="bot-title">🤖 {"AI 策略實戰 (模擬交易)" if lang_zh else "AI Strategy in Action"}</div>')
    P.append(f'<div class="bot-sub">{"動能趨勢穩健型 · 美股 · Alpaca Paper" if lang_zh else "Momentum-Trend Steady · US · Alpaca Paper"}</div>')
    P.append('</div>')
    P.append('<div class="bot-perf">')
    P.append(f'<div class="bot-perf-item"><div class="bot-perf-val {ret_cls}">{total_ret:+.2f}%</div><div class="bot-perf-lbl">{"總報酬率" if lang_zh else "Total Return"}</div></div>')
    P.append(f'<div class="bot-perf-item"><div class="bot-perf-val">${pv:,.0f}</div><div class="bot-perf-lbl">{"總資產" if lang_zh else "Equity"}</div></div>')
    P.append(f'<div class="bot-perf-item"><div class="bot-perf-val">{len(positions)}</div><div class="bot-perf-lbl">{"持倉檔數" if lang_zh else "Positions"}</div></div>')
    P.append('</div></div>')

    # Positions
    P.append(f'<div class="bot-section-title">📊 {"目前持倉" if lang_zh else "Positions"}</div>')
    if positions:
        P.append('<table class="bot-pos-table"><tr>')
        for h in (["標的","股數","成本","現價","未實現損益"] if lang_zh else ["Ticker","Qty","Cost","Price","Unrealized P/L"]):
            P.append(f'<th>{h}</th>')
        P.append('</tr>')
        for p in positions:
            pnl = p.get("unrealized_pnl",0)
            pnl_cls = "bot-up" if pnl>0 else ("bot-down" if pnl<0 else "bot-flat")
            P.append(
                f'<tr><td class="bot-tk">{escape(p["ticker"])}</td>'
                f'<td>{p.get("qty",0):g}</td>'
                f'<td>${p.get("avg_entry",0):.2f}</td>'
                f'<td>${p.get("current_price",0):.2f}</td>'
                f'<td class="{pnl_cls}">${pnl:+,.0f}</td></tr>'
            )
        P.append('</table>')
    else:
        P.append(f'<div class="bot-sub">{"目前無持倉 (觀望中)" if lang_zh else "No positions"}</div>')

    # Today's decisions + reports
    P.append(f'<div class="bot-section-title">📋 {"今日決策與依據" if lang_zh else "Today\'s Decisions"}</div>')
    for d in decisions:
        act = d.get("action","hold")
        act_cls = {"buy":"bot-decision-buy","sell":"bot-decision-sell"}.get(act,"bot-decision-hold")
        act_badge = {"buy":"bot-act-buy","sell":"bot-act-sell"}.get(act,"bot-act-hold")
        act_txt = {"buy":"買入","sell":"賣出","hold":"觀望"}.get(act,act) if lang_zh else act.upper()
        conf_txt = {"high":"高信心","mid":"中信心","low":"低信心"}.get(d.get("confidence","mid"),"") if lang_zh else d.get("confidence","")
        P.append(f'<div class="bot-decision {act_cls}">')
        P.append('<div class="bot-d-head">')
        P.append(f'<span class="bot-d-action {act_badge}">{act_txt}</span>')
        P.append(f'<span class="bot-d-tk">{escape(str(d.get("ticker","—")))}</span>')
        P.append(f'<span class="bot-d-conf">{conf_txt}</span></div>')
        if d.get("entry_basis"):
            P.append(f'<div class="bot-d-row"><b>{"進場依據" if lang_zh else "Basis"}:</b> {escape(d["entry_basis"])}</div>')
        if d.get("target_price"):
            P.append(f'<div class="bot-d-row"><b>{"目標價" if lang_zh else "Target"}:</b> ${d["target_price"]:.2f} ({"預估" if lang_zh else "est"} +{d.get("est_gain_pct",0):.1f}%)</div>')
        if d.get("exit_plan"):
            P.append(f'<div class="bot-d-row"><b>{"出場預測" if lang_zh else "Exit"}:</b> {escape(d["exit_plan"])}</div>')
        if d.get("claude_note"):
            P.append(f'<div class="bot-d-row"><b>🧠 Claude:</b> {escape(d["claude_note"])}</div>')
        P.append('</div>')

    P.append(f'<div class="bot-disclaimer">{"本區為依據 Dashboard 訊號的模擬交易展示 (Alpaca Paper, 非真實資金), 僅供研究參考, 非投資建議。歷史模擬績效不代表未來表現。" if lang_zh else "Simulated trading demo based on dashboard signals (Alpaca Paper, not real money). For research only, not investment advice."}</div>')
    P.append('</div>')
    return "".join(P)


if __name__ == "__main__":
    account = {"portfolio_value": 31250, "initial": 30000}
    positions = [
        {"ticker":"NVDA","qty":2,"avg_entry":875.0,"current_price":910.0,"unrealized_pnl":70},
        {"ticker":"MU","qty":8,"avg_entry":112.0,"current_price":108.0,"unrealized_pnl":-32},
        {"ticker":"XOVR","qty":15,"avg_entry":19.5,"current_price":20.8,"unrealized_pnl":19.5},
    ]
    decisions = [
        {"action":"buy","ticker":"NVDA","confidence":"high",
         "entry_basis":"站上 50 日均線 (910 > MA 862); 動能分數 78/100 ≥ 60 (偏多); 近5日漲幅 +4.2% < 12% (未追高)",
         "target_price":1020.0,"est_gain_pct":12.1,
         "exit_plan":"停利 +18% (約 1074) 或達目標價 1020; 停損 -8% (約 837); 或跌破 50 日均線 / 動能 ≤ 35 轉空出場。"},
        {"action":"buy","ticker":"XOVR","confidence":"mid",
         "entry_basis":"站上 50 日均線; 動能 66/100 偏多; 未追高。 ⚠️ SpaceX 代理標的(含溢價/SPV 結構風險, 非直接持有 SpaceX), 部位減半。",
         "target_price":23.5,"est_gain_pct":13.0,
         "exit_plan":"停利 +18% 或達目標 23.5; 停損 -8%; 轉空出場。"},
        {"action":"hold","ticker":"—","confidence":"mid",
         "entry_basis":"其餘選股池標的未同時滿足三條件; 維持觀望 (穩健型不強迫交易)。"},
    ]
    html = _BOT_CSS + render_bot_block(account, positions, decisions, True)
    page = f'<html><head><meta charset="utf-8"></head><body style="background:#080b14;padding:28px;max-width:980px;margin:auto;">{html}</body></html>'
    open("bot.html","w").write(page); print("written", len(page))
